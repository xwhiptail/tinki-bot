"""Model compatibility tests that also run on the pre-historian live release."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.openai_helpers import (
    _normalize_chat_completion_kwargs,
    create_async_chat_completion,
    create_chat_completion,
    gpt_wrap_fact,
)


@pytest.mark.parametrize("model,effort", [
    ("gpt-6-luna", "none"),
    ("gpt-6.1-sol", "low"),
])
async def test_sync_model_calls_preserve_content_and_normalize_parameters(model, effort):
    completion = SimpleNamespace(choices=[])
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    messages = [{"role": "user", "content": "hello"}]
    result = await create_chat_completion(
        client, model=model, messages=messages, max_tokens=40, temperature=1.1,
    )
    assert result is completion
    sent = client.chat.completions.create.call_args.kwargs
    assert sent["messages"] == messages
    assert sent["model"] == model
    assert sent["reasoning_effort"] == effort
    assert sent["max_completion_tokens"] == 40
    assert "max_tokens" not in sent
    assert ("temperature" in sent) == (effort == "none")


async def test_async_model_call_preserves_json_output_contract():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value="response")
    result = await create_async_chat_completion(
        client, model="gpt-6-luna", messages=[],
        response_format={"type": "json_object"}, max_completion_tokens=1600,
    )
    assert result == "response"
    sent = client.chat.completions.create.await_args.kwargs
    assert sent["reasoning_effort"] == "none"
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["max_completion_tokens"] == 1600


def test_explicit_reasoning_removes_incompatible_sampling_without_mutating_input():
    original = dict(model="gpt-6-luna", reasoning_effort="high", temperature=1.1,
                    top_p=0.9, top_logprobs=2, logprobs=True, max_tokens=80)
    sent = _normalize_chat_completion_kwargs(original)
    assert sent == dict(model="gpt-6-luna", reasoning_effort="high", max_completion_tokens=80)
    assert original["temperature"] == 1.1
    assert original["max_tokens"] == 80


def test_older_model_override_keeps_its_existing_request_parameters():
    original = dict(model="gpt-5.4-mini", temperature=1.1, max_tokens=40)
    assert _normalize_chat_completion_kwargs(original) == dict(
        model="gpt-5.4-mini", temperature=1.1, max_completion_tokens=40,
    )


def test_legacy_model_override_keeps_legacy_token_limit():
    original = dict(model="gpt-4.1-mini", max_tokens=40)
    assert _normalize_chat_completion_kwargs(original) == original


@pytest.mark.parametrize("tail,expected", [
    ("tiny math, big menace", "4 — tiny math, big menace"),
    ("4 — tiny math, big menace", "4 — tiny math, big menace"),
    ("4", "4"),
    (None, "4"),
])
async def test_fact_flavor_does_not_repeat_or_replace_verified_answer(tail, expected):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=tail))],
    )
    with patch("utils.openai_helpers.get_openai_client", return_value=client):
        assert await gpt_wrap_fact("4", "2+2", "") == expected
