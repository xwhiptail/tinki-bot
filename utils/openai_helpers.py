import asyncio
import os
import aiohttp
from openai import OpenAI

from config import GREMLIN_SYSTEM_STYLE, OPENAI_FAST_MODEL, OPENAI_MODEL
from utils.current_awareness import build_current_time_context


def get_openai_client() -> OpenAI:
    return OpenAI()


def _model_prefers_max_completion_tokens(model: str) -> bool:
    model_name = str(model or "").lower()
    return model_name.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _normalize_chat_completion_kwargs(kwargs):
    normalized = dict(kwargs)
    model = str(normalized.get("model") or "").lower()
    if model.startswith("gpt-6"):
        # Keep quick chat non-reasoning; Sol 6.1 and Astra require at least low.
        default_effort = "low" if model.startswith(("gpt-6.1-sol", "gpt-6-astra")) else "none"
        effort = normalized.setdefault("reasoning_effort", default_effort)
        if effort != "none":
            for parameter in ("temperature", "top_p", "top_logprobs", "logprobs"):
                normalized.pop(parameter, None)
    if (
        "max_tokens" in normalized
        and "max_completion_tokens" not in normalized
        and _model_prefers_max_completion_tokens(normalized.get("model"))
    ):
        normalized["max_completion_tokens"] = normalized.pop("max_tokens")
    return normalized


async def create_async_chat_completion(client, **kwargs):
    return await client.chat.completions.create(**_normalize_chat_completion_kwargs(kwargs))


async def run_blocking(func, *args, **kwargs):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args, **kwargs)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def create_chat_completion(client: OpenAI, **kwargs):
    return await run_blocking(
        client.chat.completions.create,
        **_normalize_chat_completion_kwargs(kwargs),
    )


async def fetch_openai_balance() -> str:
    billing_url = "https://platform.openai.com/settings/organization/billing/overview"
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return f"❌ OPENAI_API_KEY not set — {billing_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return f"✅ API key live — {billing_url}"
                return f"❌ API key error (HTTP {resp.status}) — {billing_url}"
    except Exception as e:
        return f"❌ API key error ({e}) — {billing_url}"


async def gpt_wrap_fact(fact: str, user_text: str, system_prompt, model: str = OPENAI_FAST_MODEL) -> str:
    """Keep the verified fact intact and add only a short personality flourish."""
    client = get_openai_client()
    system = (
        GREMLIN_SYSTEM_STYLE + "\n\n"
        + build_current_time_context() + "\n\n"
        f"The verified deterministic fact is: {fact}\n"
        "The application will prepend that fact and a dash to your output. "
        "Return only a very short flavor flourish, never repeat the fact or add a leading dash. "
        "Do not contradict it, recalculate it, list alternate answers, or add new factual claims; "
        "only add a very short flavor flourish after the dash, or return nothing.\n\n"
        f"Your name is @Tinki-bot. "
        f"Use this persona description as extra flavor: {system_prompt}"
    )
    try:
        completion = await create_chat_completion(
            client,
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            max_tokens=40,
        )
        tail = (completion.choices[0].message.content or "").strip() if completion.choices else ""
        if tail == fact:
            return fact
        # Some models echo the full answer despite being asked for flavor only.
        for separator in (" — ", " - ", " – ", "—"):
            if tail.startswith(fact + separator):
                tail = tail[len(fact + separator):].strip()
                break
        tail = tail.lstrip('— ').strip()
        return f"{fact} — {tail}" if tail else fact
    except Exception:
        return fact
