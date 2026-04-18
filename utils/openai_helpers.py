import asyncio
import os
import aiohttp
from openai import OpenAI

from config import GREMLIN_SYSTEM_STYLE, OPENAI_FAST_MODEL, OPENAI_MODEL


def get_openai_client() -> OpenAI:
    return OpenAI()


async def run_blocking(func, *args, **kwargs):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args, **kwargs)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def create_chat_completion(client: OpenAI, **kwargs):
    return await run_blocking(client.chat.completions.create, **kwargs)


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
    """Deliver a pre-computed factual answer wrapped in Tinki's personality via assistant prefill."""
    client = get_openai_client()
    system = (
        GREMLIN_SYSTEM_STYLE + " "
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
                {"role": "assistant", "content": f"{fact} —"},
            ],
        )
        tail = completion.choices[0].message.content if completion.choices else ""
        return f"{fact} — {tail.lstrip('— ').strip()}" if tail else fact
    except Exception:
        return fact
