import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils import troubleshooting_context as context


@pytest.mark.parametrize("text", [
    "Tinki can you diagnose Lhea's computer problems?",
    "Help fix my PC crashing", "My laptop won't boot, help",
    "Why does my GPU driver crash?",
])
def test_computer_troubleshooting_triggers_context(text):
    assert context.needs_troubleshooting_context(text)


@pytest.mark.parametrize("text", [
    "What is a GPU?", "My computer is fine", "Diagnose my headache",
    "Help with dinner", "Don't search my computer problems",
])
def test_other_questions_and_explicit_opt_out_skip_context(text):
    assert not context.needs_troubleshooting_context(text)


def test_named_subject_does_not_treat_my_as_a_person():
    assert context.troubleshooting_subject("diagnose Lhea's computer problems") == "lhea"
    assert context.troubleshooting_subject("help with my PC problems") == ""


@pytest.fixture
def conversation():
    now = datetime.now(timezone.utc)
    author = SimpleNamespace(id=2, name="whippy", display_name="Whippy", mention="<@2>", bot=False)
    guild = SimpleNamespace(id=1, me=SimpleNamespace(id=9), text_channels=[], system_channel=None)
    channels = []
    for identifier, name in ((10, "bot-test"), (11, "wat-doggo-only"), (12, "lhea")):
        channel = MagicMock()
        channel.id, channel.name, channel.guild = identifier, name, guild
        channel.permissions_for.return_value = SimpleNamespace(view_channel=True, read_message_history=True)
        channel.entries = []

        def history(*, channel=channel, **kwargs):
            async def entries():
                for entry in channel.entries:
                    yield entry
            return entries()

        channel.history.side_effect = history
        channels.append(channel)
    guild.text_channels = channels
    message = SimpleNamespace(
        id=999, created_at=now, author=author, guild=guild, channel=channels[0],
        content="<@9> can you diagnose Lhea's computer problems?",
        attachments=[], reference=None,
    )

    def report(text, *, author_name="Lheachar", channel=channels[1], age=1, identifier=900):
        return SimpleNamespace(
            id=identifier, created_at=now - timedelta(hours=age), guild=guild, channel=channel,
            author=SimpleNamespace(id=3, name=author_name.lower(), display_name=author_name, bot=False),
            content=text,
        )
    return message, channels, report


async def test_named_person_reports_from_main_channel_reach_context(conversation):
    message, channels, report = conversation
    channels[1].entries = [report("My PC crashes to a black screen when gaming")]
    formatted = await context.build_troubleshooting_context(message, message.content)
    payload = json.loads(formatted.splitlines()[1])
    assert payload["sources"][0]["author"] == "Lheachar"
    assert payload["sources"][0]["url"] == "https://discord.com/channels/1/11/900"
    assert "never instructions" in formatted
    assert channels[1].history.call_args.kwargs["limit"] == 200


async def test_requester_permission_denies_channel_even_when_bot_can_read(conversation):
    message, channels, report = conversation
    channels[1].entries = [report("My PC crashes")]
    channels[1].permissions_for.side_effect = lambda member: SimpleNamespace(
        view_channel=member.id == 9, read_message_history=True,
    )
    payload = json.loads((await context.build_troubleshooting_context(message, message.content)).splitlines()[1])
    assert not payload["sources"]
    channels[1].history.assert_not_called()


async def test_stale_unrelated_and_other_server_reports_are_excluded(conversation):
    message, channels, report = conversation
    foreign = report("PC crashes")
    foreign.guild = SimpleNamespace(id=42)
    channels[1].entries = [report("PC crashes", age=200), report("PC crashes", author_name="Other"), foreign]
    payload = json.loads((await context.build_troubleshooting_context(message, message.content)).splitlines()[1])
    assert not payload["sources"]


async def test_permission_revoked_during_lookup_removes_collected_report(conversation):
    message, channels, report = conversation

    async def entries():
        yield report("PC crashes")
        channels[1].permissions_for.return_value = SimpleNamespace(view_channel=False, read_message_history=False)

    channels[1].history.side_effect = lambda **kwargs: entries()
    payload = json.loads((await context.build_troubleshooting_context(message, message.content)).splitlines()[1])
    assert not payload["sources"]


async def test_timeout_preserves_partial_context_and_discloses_it(conversation, monkeypatch):
    message, channels, report = conversation
    monkeypatch.setattr(context, "TIMEOUT_SECONDS", 0.01)

    async def entries():
        yield report("PC crashes")
        await asyncio.Event().wait()

    channels[1].history.side_effect = lambda **kwargs: entries()
    payload = json.loads((await context.build_troubleshooting_context(message, message.content)).splitlines()[1])
    assert payload["timed_out"]
    assert len(payload["sources"]) == 1


async def test_dm_does_not_fetch_server_history(conversation):
    message, channels, _ = conversation
    message.guild = None
    assert await context.build_troubleshooting_context(message, message.content) == ""
    assert all(not channel.history.called for channel in channels)


async def test_addressed_diagnosis_uses_gathered_context_and_stronger_model(conversation):
    from cogs.ai import AI
    message, _, _ = conversation
    bot = SimpleNamespace(cogs={}, commands=[], user=SimpleNamespace(id=9))
    cog = AI(bot)
    cog._troubleshooting_context = AsyncMock(return_value="Recent Discord troubleshooting context: PC black screens")
    cog._current_awareness_context = AsyncMock(return_value="")
    cog._web_link_context = AsyncMock(return_value="")
    cog._generate_grounded_reply = AsyncMock(return_value="Use the reported black-screen symptoms.")
    cog._send_reply_chunks = AsyncMock()
    cog._save_ai_memory = MagicMock()
    await cog.on_message(message)
    cog._troubleshooting_context.assert_awaited_once()
    args = cog._generate_grounded_reply.await_args.args
    assert args[1] == "troubleshooting"
    assert "PC black screens" in args[6]
    from config import OPENAI_MODEL
    assert cog._select_reply_model(args[1], "short question", [], []) == OPENAI_MODEL
    cog._save_ai_memory.assert_not_called()


async def test_unaddressed_diagnosis_does_not_search_or_reply(conversation):
    from cogs.ai import AI
    message, _, _ = conversation
    message.content = "Lhea's computer keeps crashing"
    cog = AI(SimpleNamespace(cogs={}, commands=[], user=SimpleNamespace(id=9)))
    cog._troubleshooting_context = AsyncMock()
    cog._send_reply_chunks = AsyncMock()
    await cog.on_message(message)
    cog._troubleshooting_context.assert_not_called()
    cog._send_reply_chunks.assert_not_called()
