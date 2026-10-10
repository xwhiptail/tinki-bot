import asyncio
from copy import copy
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
    guild.get_channel = lambda identifier: next((channel for channel in channels if channel.id == identifier), None)
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


async def test_verified_fact_flavor_preserves_identity_at_reply_boundary(conversation):
    from cogs.ai import AI
    from unittest.mock import patch
    message, _, _ = conversation
    cog = AI(SimpleNamespace(cogs={}, commands=[], user=SimpleNamespace(id=9)))
    cog._send_reply_chunks = AsyncMock()
    cog._save_ai_memory = MagicMock()
    with patch("cogs.ai.gpt_wrap_fact", new=AsyncMock(return_value="4 — calculator goblin")):
        await cog._handle_mention(message, "2+2")
    assert cog._send_reply_chunks.await_args.args[2] == "4 — calculator gnome"


@pytest.fixture
def interactive_cog(conversation):
    from cogs.ai import AI
    message, channels, _ = conversation
    cog = AI(SimpleNamespace(cogs={}, commands=[], user=SimpleNamespace(id=9)))
    cog._troubleshooting_context = AsyncMock(return_value=(
        "Recent Discord troubleshooting context:\n" + json.dumps({"sources": [{
            "text": "PC crashes after boot", "url": "https://discord.com/channels/1/11/900",
        }]})
    ))
    cog._generate_grounded_reply = AsyncMock(return_value="When it crashes, is it a freeze, restart, blue screen, or black screen?")
    cog._save_ai_memory = MagicMock()
    cog._update_conversation_history = MagicMock()
    channels[0].send = AsyncMock(return_value=SimpleNamespace(id=2000))
    return cog


async def test_reply_without_ping_continues_with_symptoms_and_previous_answers(conversation, interactive_cog):
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    assert "Use **Reply** to answer" in channels[0].send.await_args.args[0]
    answer = copy(message)
    answer.content = "Black screen, but the fans keep spinning"
    answer.reference = SimpleNamespace(message_id=2000)
    channels[0].send.return_value = SimpleNamespace(id=2001)
    cog._generate_grounded_reply.return_value = "Does sound keep playing after the display goes black?"
    await cog.on_message(answer)
    args = cog._generate_grounded_reply.await_args.args
    assert args[0] == answer.content
    assert args[1] == "troubleshooting"
    assert "PC crashes after boot" in args[6]
    assert "freeze, restart" in args[6]
    assert "Lhea" in args[6]
    assert set(cog._troubleshooting_sessions) == {2001}
    cog._troubleshooting_context.assert_awaited_once()
    cog._save_ai_memory.assert_not_called()
    cog._update_conversation_history.assert_not_called()

    answer.reference.message_id = 2001
    answer.content = "Yes, sound keeps playing"
    await cog.on_message(answer)
    assert "Black screen, but the fans keep spinning" in cog._generate_grounded_reply.await_args.args[6]


@pytest.mark.parametrize("change", ["unaddressed", "other_user", "other_channel", "other_server", "expired", "command"])
async def test_active_session_does_not_wake_on_unrelated_messages(conversation, interactive_cog, change):
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    answer = copy(message)
    answer.content = "Black screen"
    answer.reference = SimpleNamespace(message_id=2000)
    if change == "unaddressed":
        answer.reference = None
    elif change == "other_user":
        answer.author = SimpleNamespace(id=123, bot=False)
    elif change == "other_channel":
        answer.channel = channels[1]
    elif change == "other_server":
        answer.guild = SimpleNamespace(id=123)
    elif change == "expired":
        cog._troubleshooting_sessions[2000].expires_at = 0
    elif change == "command":
        answer.content = "!commands"
    cog._generate_grounded_reply.reset_mock()
    channels[0].send.reset_mock()
    await cog.on_message(answer)
    cog._generate_grounded_reply.assert_not_awaited()
    channels[0].send.assert_not_awaited()


@pytest.mark.parametrize("answer", ["stop", "it's fixed", "hush"])
async def test_user_can_end_the_interactive_session(conversation, interactive_cog, answer):
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    followup = copy(message)
    followup.content = answer
    followup.reference = SimpleNamespace(message_id=2000)
    cog._generate_grounded_reply.reset_mock()
    await cog.on_message(followup)
    assert not cog._troubleshooting_sessions
    cog._generate_grounded_reply.assert_not_awaited()


@pytest.mark.parametrize("during_generation", [False, True])
async def test_followup_rechecks_source_permissions_and_discards_session(conversation, interactive_cog, during_generation):
    from cogs.ai import TROUBLESHOOTING_ACCESS_REPLY
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    answer = copy(message)
    answer.content = "Black screen"
    answer.reference = SimpleNamespace(message_id=2000)
    cog._generate_grounded_reply.reset_mock()

    def revoke():
        channels[1].permissions_for.return_value = SimpleNamespace(view_channel=False, read_message_history=False)

    if during_generation:
        async def generate(*args, **kwargs):
            revoke()
            return "Private report summary"
        cog._generate_grounded_reply.side_effect = generate
    else:
        revoke()
    await cog.on_message(answer)
    assert not cog._troubleshooting_sessions
    assert channels[0].send.await_args.args[0] == "<@2> " + TROUBLESHOOTING_ACCESS_REPLY
    if not during_generation:
        cog._generate_grounded_reply.assert_not_awaited()


async def test_duplicate_followup_is_ignored_while_answer_is_running(conversation, interactive_cog):
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    answer = copy(message)
    answer.content = "Black screen"
    answer.reference = SimpleNamespace(message_id=2000)
    started, finish = asyncio.Event(), asyncio.Event()

    async def generate(*args, **kwargs):
        started.set()
        await finish.wait()
        return "Does sound keep playing?"

    cog._generate_grounded_reply.reset_mock()
    cog._generate_grounded_reply.side_effect = generate
    task = asyncio.create_task(cog.on_message(answer))
    await started.wait()
    await cog.on_message(answer)
    finish.set()
    await task
    cog._generate_grounded_reply.assert_awaited_once()


async def test_stop_during_generation_cancels_pending_answer(conversation, interactive_cog):
    message, channels, _ = conversation
    cog = interactive_cog
    await cog.on_message(message)
    answer = copy(message)
    answer.content = "Black screen"
    answer.reference = SimpleNamespace(message_id=2000)
    started, finish = asyncio.Event(), asyncio.Event()

    async def generate(*args, **kwargs):
        started.set()
        await finish.wait()
        return "Does sound keep playing?"

    cog._generate_grounded_reply.side_effect = generate
    task = asyncio.create_task(cog.on_message(answer))
    await started.wait()
    answer.content = "stop"
    await cog.on_message(answer)
    channels[0].send.reset_mock()
    finish.set()
    await task
    assert not cog._troubleshooting_sessions
    channels[0].send.assert_not_awaited()


async def test_session_storage_and_turns_are_bounded(conversation, interactive_cog, monkeypatch):
    import cogs.ai as ai_module
    message, channels, _ = conversation
    cog = interactive_cog
    monkeypatch.setattr(ai_module, "SESSION_LIMIT", 2)
    for identifier in range(2000, 2003):
        channels[0].send.return_value = SimpleNamespace(id=identifier)
        await cog.on_message(message)
    assert set(cog._troubleshooting_sessions) == {2001, 2002}
    answer = copy(message)
    answer.content = "Still a black screen"
    answer.reference = SimpleNamespace(message_id=2002)
    for _ in range(12):
        await cog.on_message(answer)
    assert len(cog._troubleshooting_sessions[2002].turns) == context.TURN_LIMIT


async def test_generated_troubleshooting_reply_is_short_and_one_question(conversation):
    from cogs.ai import AI
    message, _, _ = conversation
    cog = AI(SimpleNamespace(cogs={}, commands=[], user=SimpleNamespace(id=9)))

    def completion(text):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))]), ""

    cog._create_openai_chat_completion = AsyncMock(side_effect=[
        completion("What is your CPU? What is your GPU? What is your PSU?"),
        completion("Does sound keep playing after the black screen?"),
    ])
    reply = await cog._generate_grounded_reply(
        "Black screen", "troubleshooting", "", {"facts": [], "topics": [], "preferences": []},
        [], [], "Recent reports: PC crashes",
    )
    assert reply == "Does sound keep playing after the black screen?"
    assert cog._create_openai_chat_completion.await_count == 2
    system = cog._create_openai_chat_completion.await_args.kwargs["messages"][0]["content"]
    assert "ONE focused question" in system
    assert "Do not dump a list" in system


def test_session_sources_are_only_real_source_urls_not_quoted_links():
    quoted = "header\n" + json.dumps({"sources": [{
        "text": "https://discord.com/channels/1/99/101",
        "url": "https://discord.com/channels/1/11/900",
    }]})
    assert context.source_channel_ids(quoted) == {11}
    assert context.source_channel_ids("") == set()
