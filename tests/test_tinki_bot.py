"""
Pytest suite for pure functions and isolated command helpers in tinki-bot.

Install test deps (once):
    pip install pytest pytest-asyncio

Run:
    pytest
"""
import io
import json
import sys
import os
import shutil
import subprocess
import importlib.util
from pathlib import Path
from contextlib import ExitStack
from types import SimpleNamespace

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

# ── ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.url_rewriter import rewrite_social_urls
from utils.ai_brain import (
    build_memory_context,
    build_system_prompt,
    classify_intent,
    extract_user_facts,
    parse_natural_command,
    retrieve_repo_context,
    update_memory_state,
    validate_grounded_reply,
)
from utils.calculator import maybe_calculate_reply
from utils.bot_insight import maybe_bot_insight_reply
from utils.letter_counter import maybe_count_letter_reply
import config
from utils.aws_costs import AWSCostSummary, _format_client_error, _month_bounds, _to_money, fetch_aws_cost_summary

try:
    from botocore.exceptions import ClientError
except Exception:  # pragma: no cover - optional dependency in test env
    ClientError = None

# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolate_bowling_scores_file(tmp_path, monkeypatch):
    scores_file = tmp_path / "scores.json"
    scores_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(config, "SCORES_FILE", str(scores_file), raising=False)

    if "cogs.bowling" in sys.modules:
        bowling_module = sys.modules["cogs.bowling"]
        monkeypatch.setattr(bowling_module, "SCORES_FILE", str(scores_file), raising=False)
        monkeypatch.setattr(bowling_module, "LEGACY_SCORES_FILES", [], raising=False)

    return scores_file


@pytest.fixture(autouse=True)
def isolate_reminders_database_file(tmp_path, monkeypatch):
    db_file = tmp_path / "reminders.db"

    monkeypatch.setattr(config, "DATABASE_FILE", str(db_file), raising=False)

    if "cogs.reminders" in sys.modules:
        reminders_module = sys.modules["cogs.reminders"]
        monkeypatch.setattr(reminders_module, "DATABASE_FILE", str(db_file), raising=False)

    return db_file

def make_ctx():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    return ctx


def make_message(content):
    message = MagicMock()
    message.content = content
    message.author = MagicMock()
    message.author.bot = False
    message.author.mention = "<@123>"
    message.channel = MagicMock()
    message.channel.send = AsyncMock()
    message.channel.fetch_message = AsyncMock()
    message.delete = AsyncMock()
    message.embeds = []
    message.mentions = []
    message.reference = None
    return message


def _async_iter(items):
    async def _generator():
        for item in items:
            yield item

    return _generator()


def make_reaction(message, emoji):
    reaction = MagicMock()
    reaction.message = message
    reaction.emoji = emoji
    return reaction


class FakeAiohttpResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def read(self):
        return self.payload


def _wire_cog(cog):
    """Attach the cog instance to all its Command objects so direct calls work."""
    for cmd in cog.get_commands():
        cmd.cog = cog
    return cog


def make_bowling_cog():
    from cogs.bowling import Bowling
    cog = Bowling(MagicMock())
    cog.scores.clear()
    return _wire_cog(cog)


def make_personas_cog():
    from cogs.personas import Personas
    cog = Personas(MagicMock())
    cog.personas.clear()
    cog.current_persona = None
    cog.conversations.clear()
    return _wire_cog(cog)


def make_uma_cog(pity_file=None):
    from cogs.uma import Uma
    cog = Uma(MagicMock())
    if pity_file is not None:
        cog.pity_file = pity_file
    return cog


def make_ai_cog():
    from cogs.ai import AI
    bot = MagicMock()
    bot.cogs = {}
    bot.commands = []
    bot.process_commands = AsyncMock()
    cog = AI(bot)
    return _wire_cog(cog)


def make_admin_cog():
    from cogs.admin import Admin
    return _wire_cog(Admin(MagicMock()))


def make_utility_cog():
    from cogs.utility import Utility
    return _wire_cog(Utility(MagicMock()))


def make_tracking_cog():
    from cogs.tracking import Tracking
    cog = Tracking(MagicMock())
    cog.sus_and_sticker_usage.clear()
    cog.explode.clear()
    cog.spinny.clear()
    return _wire_cog(cog)


def make_emotes_cog():
    from cogs.emotes import Emotes
    bot = MagicMock()
    bot.guilds = []
    bot.wait_for = AsyncMock()
    cog = Emotes(bot)
    return _wire_cog(cog)


def make_reminders_cog():
    from cogs.reminders import Reminders
    return _wire_cog(Reminders(MagicMock()))


def load_tinki_bot_module():
    module_name = "tinki_bot_entrypoint_test"
    module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tinki-bot.py"))
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    with patch("discord.ext.commands.Bot.run"):
        spec.loader.exec_module(module)
    return module


COMMAND_COG_FACTORIES = (
    make_admin_cog,
    make_bowling_cog,
    make_emotes_cog,
    make_reminders_cog,
    make_tracking_cog,
    make_uma_cog,
    make_utility_cog,
)


def make_smoke_ctx(author_name="tester"):
    ctx = make_ctx()
    ctx.author = MagicMock()
    ctx.author.id = 1
    ctx.author.name = author_name
    ctx.author.display_name = author_name
    ctx.author.mention = "<@1>"
    ctx.author.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 456
    ctx.channel.send = AsyncMock()
    ctx.channel.pins = AsyncMock(return_value=[])
    ctx.channel.purge = AsyncMock(return_value=[])
    ctx.guild = MagicMock()
    ctx.guild.id = 789
    ctx.guild.emojis = []
    ctx.guild.members = []
    ctx.message = MagicMock()
    ctx.message.id = 123
    ctx.message.reference = None
    ctx.message.delete = AsyncMock()
    return ctx


def _registered_command_names():
    return {
        cmd.name
        for factory in COMMAND_COG_FACTORIES
        for cmd in factory().get_commands()
    }


def _make_client_session_cm():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _build_command_smoke_cases(tmp_path, monkeypatch):
    async def smoke_admin(command_name):
        cog = make_admin_cog()
        ctx = make_smoke_ctx(author_name="whiptail")
        with ExitStack() as stack:
            if command_name == "restart":
                stack.enter_context(patch("cogs.admin.asyncio.sleep", new=AsyncMock()))
                stack.enter_context(patch("cogs.admin.subprocess.Popen"))
                await cog.restart_bot.callback(cog, ctx)
            elif command_name == "deploy":
                fake_session = _make_client_session_cm()
                stack.enter_context(patch("cogs.admin.aiohttp.ClientSession", return_value=fake_session))
                stack.enter_context(patch.object(cog, "_read_deployed_commit", return_value="abc1234"))
                stack.enter_context(patch.object(cog, "_fetch_json_with_retries", new=AsyncMock(return_value={
                    "sha": "abc1234",
                    "commit": {"message": "Already current"},
                })))
                await cog.deploy_latest.callback(cog, ctx)
            elif command_name == "awscost":
                stack.enter_context(patch("cogs.admin.fetch_aws_cost_summary", new=AsyncMock(return_value="AWS cost summary")))
                await cog.aws_cost.callback(cog, ctx)
            elif command_name == "runtests":
                stack.enter_context(patch.object(cog, "_run_command_selftests", new=AsyncMock(return_value=[("pb", True, None)])))
                await cog.runtests.callback(cog, ctx)
            elif command_name == "testurls":
                stack.enter_context(patch("cogs.admin.run_url_selftests", return_value=[("twitter", True, None)]))
                await cog.testurls.callback(cog, ctx)
        assert ctx.send.await_count >= 1

    async def smoke_bowling(command_name):
        from datetime import datetime

        cog = make_bowling_cog()
        ctx = make_smoke_ctx()
        if command_name in {"pb", "avg", "median", "all", "bowlinggraph", "bowlingdistgraph"}:
            cog.scores = [
                (100, datetime(2026, 1, 1, 0, 0, 0)),
                (150, datetime(2026, 1, 2, 0, 0, 0)),
            ]

        with ExitStack() as stack:
            if command_name == "pb":
                await cog.personal_best.callback(cog, ctx)
            elif command_name == "avg":
                await cog.average_score.callback(cog, ctx)
            elif command_name == "median":
                await cog.median_score.callback(cog, ctx)
            elif command_name == "all":
                await cog.all_scores.callback(cog, ctx)
            elif command_name == "delete":
                await cog.delete_score.callback(cog, ctx, timestamp_str="2026-01-03 00:00:00")
            elif command_name == "add":
                await cog.add_score.callback(cog, ctx, 123, timestamp_str="2026-01-03 00:00:00")
            elif command_name == "bowlinggraph":
                stack.enter_context(patch("cogs.bowling.plt.savefig"))
                stack.enter_context(patch("cogs.bowling.discord.File", return_value="graph-file"))
                await cog.graph_scores.callback(cog, ctx)
            elif command_name == "bowlingdistgraph":
                stack.enter_context(patch("cogs.bowling.plt.savefig"))
                stack.enter_context(patch("cogs.bowling.discord.File", return_value="dist-file"))
                await cog.distribution_graph.callback(cog, ctx)
        assert ctx.send.await_count >= 1

    async def smoke_emotes(command_name):
        cog = make_emotes_cog()
        ctx = make_smoke_ctx()
        with ExitStack() as stack:
            if command_name == "spinny":
                user = SimpleNamespace(id=99, mention="<@99>")
                await cog.spinny_activate.callback(cog, ctx, user)
            elif command_name == "stopspinny":
                cog.sticker_users["99"] = True
                await cog.spinny_deactivate.callback(cog, ctx, target="<@99>")
            elif command_name == "silentspinny":
                await cog.silent_spinny.callback(cog, ctx, "someone")
            elif command_name == "allemotes":
                ctx.guild = SimpleNamespace(emojis=[])
                await cog.all_emotes.callback(cog, ctx)
            elif command_name == "emote":
                session = MagicMock()
                session.close = AsyncMock()
                fake_view = MagicMock()
                fake_view.start = AsyncMock()
                emote = SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1")
                stack.enter_context(patch("cogs.emotes.aiohttp.ClientSession", return_value=session))
                stack.enter_context(patch.object(cog, "_search_7tv_page", new=AsyncMock(return_value=[emote])))
                stack.enter_context(patch("cogs.emotes.SevenTvEmoteBrowserView", return_value=fake_view))
                await cog.emote.callback(cog, ctx, "sus", "2x")
                fake_view.start.assert_awaited_once()
                return
        assert ctx.send.await_count >= 1

    async def smoke_reminders(command_name):
        import cogs.reminders as reminders_module
        from cogs.reminders import Reminders

        db_path = tmp_path / f"{command_name}_reminders.db"
        monkeypatch.setattr(reminders_module, "DATABASE_FILE", str(db_path), raising=False)
        cog = _wire_cog(Reminders(MagicMock()))
        ctx = make_smoke_ctx()
        if command_name == "remind":
            await cog.remind.callback(cog, ctx)
        elif command_name == "remindme":
            await cog.remindme.callback(cog, ctx, args=None)
        elif command_name == "deletereminder":
            await cog.deletereminder.callback(cog, ctx, 404)
        elif command_name == "currenttime":
            await cog.currenttime.callback(cog, ctx)
        assert ctx.send.await_count >= 1

    async def smoke_tracking(command_name):
        cog = make_tracking_cog()
        cog.bot.guilds = []
        ctx = make_smoke_ctx()
        with ExitStack() as stack:
            if command_name == "sussy":
                await cog.sussy_count.callback(cog, ctx)
            elif command_name == "sussygraph":
                stack.enter_context(patch.object(cog, "_build_cumulative_graph", return_value="sus-file"))
                stack.enter_context(patch("cogs.tracking.discord.File", return_value="sus-file"))
                await cog.sussy_graph.callback(cog, ctx)
            elif command_name == "explode":
                await cog.explode_count.callback(cog, ctx)
            elif command_name == "explodegraph":
                stack.enter_context(patch.object(cog, "_build_cumulative_graph", return_value="explode-file"))
                stack.enter_context(patch("cogs.tracking.discord.File", return_value="explode-file"))
                await cog.explode_graph.callback(cog, ctx)
            elif command_name == "grindcount":
                await cog.spinny_count.callback(cog, ctx)
            elif command_name == "grindgraph":
                stack.enter_context(patch.object(cog, "_build_cumulative_graph", return_value="grind-file"))
                stack.enter_context(patch("cogs.tracking.discord.File", return_value="grind-file"))
                await cog.spinny_graph.callback(cog, ctx)
        assert ctx.send.await_count >= 1

    async def smoke_uma(command_name):
        pity_path = tmp_path / f"{command_name}_pity.json"
        cog = make_uma_cog(pity_file=str(pity_path))
        ctx = make_smoke_ctx()
        with ExitStack() as stack:
            if command_name == "gacha":
                result_message = MagicMock()
                result_message.add_reaction = AsyncMock()
                result_message.remove_reaction = AsyncMock()
                send_mock = stack.enter_context(patch.object(cog, "_send_gacha_results", new=AsyncMock(return_value=result_message)))
                repull_mock = stack.enter_context(patch.object(cog, "_offer_repull", new=AsyncMock()))
                await cog.uma_gacha.callback(cog, ctx, 1)
                send_mock.assert_awaited_once()
                repull_mock.assert_awaited_once()
                return
            elif command_name == "pity":
                await cog.uma_pity.callback(cog, ctx)
            elif command_name == "uma":
                member = SimpleNamespace(display_name="Teio")
                await cog.uma_assign.callback(cog, ctx, member)
            elif command_name == "race":
                member = SimpleNamespace(display_name="Teio")
                await cog.uma_race.callback(cog, ctx, member)
            elif command_name == "umagif":
                stack.enter_context(patch.object(cog, "_gif", new=AsyncMock(return_value="https://gif.example/uma")))
                await cog.uma_gif_cmd.callback(cog, ctx)
        assert ctx.send.await_count >= 1

    async def smoke_utility(command_name):
        cog = make_utility_cog()
        ctx = make_smoke_ctx(author_name="whiptail")
        with ExitStack() as stack:
            if command_name == "purge":
                await cog.purge_bot_messages.callback(cog, ctx)
            elif command_name in {"gif", "roulette"}:
                response = MagicMock()
                response.json = AsyncMock(return_value={"data": {"images": {"original": {"url": "https://giphy.example/random"}}}})
                session = _make_client_session_cm()
                session.get = AsyncMock(return_value=response)
                stack.enter_context(patch("cogs.utility.aiohttp.ClientSession", return_value=session))
                callback = cog.send_gif if command_name == "gif" else cog.roulette
                await callback.callback(cog, ctx)
            elif command_name == "random":
                await cog.random_cmd.callback(cog, ctx)
            elif command_name == "cat":
                session = _make_client_session_cm()
                stack.enter_context(patch("cogs.utility.aiohttp.ClientSession", return_value=session))
                stack.enter_context(patch.object(cog, "_fetch_url", new=AsyncMock(return_value=[{"url": "https://cat.example/cat"}])))
                await cog.cat.callback(cog, ctx)
            elif command_name == "dog":
                session = _make_client_session_cm()
                stack.enter_context(patch("cogs.utility.aiohttp.ClientSession", return_value=session))
                stack.enter_context(patch.object(cog, "_fetch_url", new=AsyncMock(return_value={"status": "success", "message": "https://dog.example/dog"})))
                await cog.dog.callback(cog, ctx)
            elif command_name == "dogbark":
                await cog.dogbark.callback(cog, ctx)
            elif command_name == "ss":
                await cog.ss.callback(cog, ctx)
            elif command_name == "github":
                await cog.github_repo.callback(cog, ctx)
            elif command_name == "changelog":
                stack.enter_context(patch.object(cog, "_get_changelog_entries", new=AsyncMock(return_value=[("abc1234", "Fix deploy path")])))
                await cog.changelog.callback(cog, ctx, 1)
            elif command_name == "commands":
                await cog.show_commands.callback(cog, ctx)
            elif command_name == "startminecraft":
                await cog.startminecraft.callback(cog, ctx)
            elif command_name == "stopminecraft":
                await cog.stopminecraft.callback(cog, ctx)
            elif command_name == "minecraftstatus":
                await cog.minecraftstatus.callback(cog, ctx)
            elif command_name == "minecraftserver":
                await cog.fetch_server_ip.callback(cog, ctx)
            elif command_name == "startskyfactory":
                await cog.startskyfactory.callback(cog, ctx)
            elif command_name == "stopskyfactory":
                await cog.stopskyfactory.callback(cog, ctx)
            elif command_name == "skyfactorystatus":
                await cog.skyfactorystatus.callback(cog, ctx)
            elif command_name == "skyfactoryserver":
                await cog.fetch_skyfactory_ip.callback(cog, ctx)
            elif command_name == "uptime":
                await cog.uptime.callback(cog, ctx)
        if command_name == "commands":
            assert ctx.author.send.await_count == 3
            assert ctx.send.await_count == 1
        else:
            assert ctx.send.await_count >= 1

    return {
        "restart": lambda: smoke_admin("restart"),
        "deploy": lambda: smoke_admin("deploy"),
        "awscost": lambda: smoke_admin("awscost"),
        "runtests": lambda: smoke_admin("runtests"),
        "testurls": lambda: smoke_admin("testurls"),
        "pb": lambda: smoke_bowling("pb"),
        "avg": lambda: smoke_bowling("avg"),
        "median": lambda: smoke_bowling("median"),
        "all": lambda: smoke_bowling("all"),
        "delete": lambda: smoke_bowling("delete"),
        "add": lambda: smoke_bowling("add"),
        "bowlinggraph": lambda: smoke_bowling("bowlinggraph"),
        "bowlingdistgraph": lambda: smoke_bowling("bowlingdistgraph"),
        "spinny": lambda: smoke_emotes("spinny"),
        "stopspinny": lambda: smoke_emotes("stopspinny"),
        "silentspinny": lambda: smoke_emotes("silentspinny"),
        "allemotes": lambda: smoke_emotes("allemotes"),
        "emote": lambda: smoke_emotes("emote"),
        "remind": lambda: smoke_reminders("remind"),
        "remindme": lambda: smoke_reminders("remindme"),
        "deletereminder": lambda: smoke_reminders("deletereminder"),
        "currenttime": lambda: smoke_reminders("currenttime"),
        "sussy": lambda: smoke_tracking("sussy"),
        "sussygraph": lambda: smoke_tracking("sussygraph"),
        "explode": lambda: smoke_tracking("explode"),
        "explodegraph": lambda: smoke_tracking("explodegraph"),
        "grindcount": lambda: smoke_tracking("grindcount"),
        "grindgraph": lambda: smoke_tracking("grindgraph"),
        "gacha": lambda: smoke_uma("gacha"),
        "pity": lambda: smoke_uma("pity"),
        "uma": lambda: smoke_uma("uma"),
        "race": lambda: smoke_uma("race"),
        "umagif": lambda: smoke_uma("umagif"),
        "purge": lambda: smoke_utility("purge"),
        "gif": lambda: smoke_utility("gif"),
        "random": lambda: smoke_utility("random"),
        "roulette": lambda: smoke_utility("roulette"),
        "cat": lambda: smoke_utility("cat"),
        "dog": lambda: smoke_utility("dog"),
        "dogbark": lambda: smoke_utility("dogbark"),
        "ss": lambda: smoke_utility("ss"),
        "github": lambda: smoke_utility("github"),
        "changelog": lambda: smoke_utility("changelog"),
        "commands": lambda: smoke_utility("commands"),
        "startminecraft": lambda: smoke_utility("startminecraft"),
        "stopminecraft": lambda: smoke_utility("stopminecraft"),
        "minecraftstatus": lambda: smoke_utility("minecraftstatus"),
        "minecraftserver": lambda: smoke_utility("minecraftserver"),
        "startskyfactory": lambda: smoke_utility("startskyfactory"),
        "stopskyfactory": lambda: smoke_utility("stopskyfactory"),
        "skyfactorystatus": lambda: smoke_utility("skyfactorystatus"),
        "skyfactoryserver": lambda: smoke_utility("skyfactoryserver"),
        "uptime": lambda: smoke_utility("uptime"),
    }


class TestCommandSmokeMatrix:
    @pytest.mark.asyncio
    async def test_all_registered_commands_have_smoke_cases_and_invoke_cleanly(self, tmp_path, monkeypatch):
        smoke_cases = _build_command_smoke_cases(tmp_path, monkeypatch)
        registered = _registered_command_names()
        covered = set(smoke_cases)

        missing = sorted(registered - covered)
        unexpected = sorted(covered - registered)
        assert not missing and not unexpected, (
            "Command smoke matrix drifted.\n"
            f"Missing smoke cases: {missing}\n"
            f"Unexpected smoke cases: {unexpected}"
        )

        failures = []
        for command_name in sorted(registered):
            try:
                await smoke_cases[command_name]()
            except Exception as exc:
                failures.append(f"{command_name}: {type(exc).__name__}: {exc}")

        assert not failures, "Command smoke failures:\n" + "\n".join(failures)


# ── rewrite_social_urls ──────────────────────────────────────────────────────

class TestRewriteSocialUrls:
    def test_twitter_rewritten_to_vxtwitter(self):
        out = rewrite_social_urls("https://twitter.com/foo/status/123")
        assert "vxtwitter.com/foo/status/123" in out
        assert "//twitter.com" not in out

    def test_twitter_preserves_user_and_status(self):
        out = rewrite_social_urls("https://www.twitter.com/alice/status/999")
        assert "alice" in out
        assert "999" in out

    def test_x_com_rewritten_to_fixvx(self):
        out = rewrite_social_urls("https://x.com/user/status/1")
        assert "fixvx.com" in out
        assert "//x.com" not in out

    def test_instagram_rewritten_to_eeinstagram(self):
        out = rewrite_social_urls("https://www.instagram.com/p/abc123/")
        assert "eeinstagram.com" in out
        assert "//www.instagram.com" not in out

    def test_tiktok_rewritten_to_tnktok(self):
        out = rewrite_social_urls("https://www.tiktok.com/@user/video/1")
        assert "tnktok.com" in out
        assert "tiktok.com" not in out

    def test_reddit_rewritten_to_rxddit(self):
        out = rewrite_social_urls("https://www.reddit.com/r/python/comments/abc/")
        assert "rxddit.com" in out
        assert "reddit.com" not in out

    def test_github_url_unchanged(self):
        msg = "see https://github.com/some/repo for details"
        assert rewrite_social_urls(msg) == msg

    def test_plain_text_unchanged(self):
        msg = "no links here at all"
        assert rewrite_social_urls(msg) == msg

    def test_surrounding_text_preserved(self):
        out = rewrite_social_urls("hey https://twitter.com/x/status/1 lol")
        assert out.startswith("hey ")
        assert out.endswith(" lol")

    def test_multiple_social_urls_in_one_message(self):
        msg = "https://twitter.com/a/status/1 and https://instagram.com/p/2/"
        out = rewrite_social_urls(msg)
        assert "vxtwitter.com" in out
        assert "eeinstagram.com" in out
        assert "//twitter.com" not in out
        assert "//www.instagram.com" not in out


# ── maybe_calculate_reply ────────────────────────────────────────────────────

class TestMaybeCalculateReply:
    def test_bare_addition(self):
        r = maybe_calculate_reply("2 + 2")
        assert r is not None and "4" in r

    def test_what_is_prefix_stripped(self):
        r = maybe_calculate_reply("what is 10 + 5")
        assert r is not None and "15" in r

    def test_whats_prefix_stripped(self):
        r = maybe_calculate_reply("what's 3 + 3")
        assert r is not None and "6" in r

    def test_calculate_prefix_stripped(self):
        r = maybe_calculate_reply("calculate 3 * 7")
        assert r is not None and "21" in r

    def test_x_as_multiplication(self):
        r = maybe_calculate_reply("3x4")
        assert r is not None and "12" in r

    def test_subtraction(self):
        r = maybe_calculate_reply("100 - 37")
        assert r is not None and "63" in r

    def test_float_division(self):
        r = maybe_calculate_reply("10 / 4")
        assert r is not None and "2.5" in r

    def test_large_number_comma_formatted(self):
        r = maybe_calculate_reply("1000000 + 1")
        assert r is not None and "1,000,001" in r

    def test_trailing_question_mark_ok(self):
        r = maybe_calculate_reply("5 + 5?")
        assert r is not None and "10" in r

    def test_plain_text_returns_none(self):
        assert maybe_calculate_reply("hello world") is None

    def test_words_with_digits_returns_none(self):
        assert maybe_calculate_reply("give me 5 reasons") is None

    def test_division_by_zero_returns_none(self):
        assert maybe_calculate_reply("5 / 0") is None

    def test_result_is_just_the_number(self):
        assert maybe_calculate_reply("1 + 1") == "2"


# ── maybe_count_letter_reply ─────────────────────────────────────────────────

class TestMaybeCountLetterReply:
    def test_count_r_in_strawberry(self):
        r = maybe_count_letter_reply("how many r's in strawberry")
        assert r is not None and "3" in r

    def test_count_s_in_mississippi(self):
        r = maybe_count_letter_reply("how many s's in mississippi")
        assert r is not None and "4" in r

    def test_singular_time_when_count_is_one(self):
        r = maybe_count_letter_reply("how many b's in cob")
        assert r is not None
        assert " time" in r and "times" not in r

    def test_plural_times_when_count_gt_one(self):
        r = maybe_count_letter_reply("how many l's in hello")
        assert r is not None and "times" in r

    def test_zero_occurrences(self):
        r = maybe_count_letter_reply("how many z's in apple")
        assert r is not None and "0" in r

    def test_trailing_question_mark_stripped(self):
        r = maybe_count_letter_reply("how many e's in cheese?")
        assert r is not None and "3" in r

    def test_unrelated_message_returns_none(self):
        assert maybe_count_letter_reply("what time is it") is None

    def test_no_match_returns_none(self):
        assert maybe_count_letter_reply("tell me something") is None

    def test_result_is_factual_only(self):
        r = maybe_count_letter_reply("how many t's in butter")
        assert r is not None and "2" in r and "butter" in r

    def test_with_the_word_phrasing(self):
        r = maybe_count_letter_reply("how many letter e's in the word sleep")
        assert r is not None and "2" in r


class TestMaybeBotInsightReply:
    def test_model_question_returns_configured_model(self):
        r = maybe_bot_insight_reply("what gpt model do you use")
        assert r is not None and config.OPENAI_MODEL in r

    def test_architecture_question_describes_cogs(self):
        r = maybe_bot_insight_reply("how do you work")
        assert r is not None and "Discord bot" in r and "cogs" in r

    def test_commands_question_mentions_commands_and_repo(self):
        r = maybe_bot_insight_reply("what commands do you have")
        assert r is not None and "!commands" in r and "!github" in r

    def test_what_can_i_ask_you_lists_plain_language_uses(self):
        r = maybe_bot_insight_reply("what can I ask you")
        assert r is not None
        assert "plain English" in r
        assert "reminders" in r
        assert "Uma" in r
        assert "bowling" in r

    def test_hosting_question_mentions_ec2(self):
        r = maybe_bot_insight_reply("how are you hosted")
        assert r is not None and "EC2" in r and ".deploy-commit" in r

    def test_repo_question_returns_github_repo(self):
        r = maybe_bot_insight_reply("what is your github")
        assert r is not None and config.GITHUB_REPO_URL in r

    def test_unrelated_message_returns_none(self):
        assert maybe_bot_insight_reply("tell me a joke") is None


class TestAIBrain:
    def test_classify_intent_detects_command_help(self):
        assert classify_intent("what commands do you have") == "command_help"

    def test_classify_intent_detects_repo_question(self):
        assert classify_intent("how are you deployed on ec2") == "bot_repo"

    def test_classify_intent_keeps_remember_command_questions_grounded(self):
        assert classify_intent("do you remember what !gacha does?") == "command_help"

    def test_classify_intent_keeps_remember_repo_questions_grounded(self):
        assert classify_intent("remember when we deployed to ec2") == "bot_repo"

    def test_classify_intent_detects_general_question(self):
        assert classify_intent("why is gold ship so cursed?") == "question_answer"

    def test_classify_intent_marks_memory_lookup_questions(self):
        assert classify_intent("didn't i tell you my main is hunter?") == "memory_lookup"

    def test_extract_user_facts_finds_simple_profile_facts(self):
        facts = extract_user_facts("my name is Matt and I like WoW")
        assert "Matt" in facts[0]
        assert any("WoW" in fact for fact in facts)

    def test_extract_user_facts_captures_preference_style_statements(self):
        facts = extract_user_facts("my main is hunter and my favorite spec is marksman")
        assert any("main hunter" in fact.lower() for fact in facts)
        assert any("favorite spec marksman" in fact.lower() for fact in facts)

    def test_update_memory_state_stores_user_facts_and_topics(self):
        state = update_memory_state({"users": {}, "guilds": {}}, "123", "456", "my name is Matt and I like raiding")
        memory = build_memory_context(state, "123", "456", "what do I like")
        assert any("Matt" in fact for fact in memory["facts"])
        assert "raiding" in memory["topics"]

    def test_retrieve_repo_context_finds_matching_doc_chunks(self):
        docs = {"README.md": "Deploy with deploy-ec2.ps1\nUse !commands for help"}
        context = retrieve_repo_context("how do you deploy", docs)
        assert context
        assert "deploy-ec2.ps1" in context[0]

    def test_validate_grounded_reply_rejects_unknown_commands(self):
        valid, reason = validate_grounded_reply(
            "Use !fakecommand and !commands.",
            {"commands", "github"},
            "command_help",
            ["[README]\n!commands"],
        )
        assert valid is False
        assert "!fakecommand" in reason

    def test_build_system_prompt_includes_memory_and_grounding(self):
        prompt = build_system_prompt(
            "base style",
            "cute but mean",
            "command_help",
            {"facts": ["likes WoW"], "topics": ["deploy"], "preferences": ["keep replies short"]},
            ["[README]\nUse !commands"],
        )
        assert "cute but mean" in prompt
        assert "likes WoW" in prompt
        assert "Use !commands" in prompt

    def test_parse_natural_command_for_reminder(self):
        parsed = parse_natural_command("remind me in 10 minutes")
        assert parsed == {"command": "remindme", "args": "in 10 minutes"}

    def test_parse_natural_command_for_gacha(self):
        parsed = parse_natural_command("do a 10 pull")
        assert parsed == {"command": "gacha", "args": "10"}

    def test_parse_natural_command_for_simple_media(self):
        parsed = parse_natural_command("show me a cat")
        assert parsed == {"command": "cat", "args": None}


class TestAINaturalCommands:
    async def test_execute_natural_command_rewrites_message_to_command(self):
        cog = make_ai_cog()
        message = make_message("@Tinki do a 10 pull")
        original = message.content
        seen = {}

        async def capture(processed_message):
            seen["content"] = processed_message.content

        cog.bot.process_commands = AsyncMock(side_effect=capture)

        await cog._execute_natural_command(message, {"command": "gacha", "args": "10"})

        cog.bot.process_commands.assert_awaited_once()
        assert seen["content"] == "!gacha 10"
        assert message.content == original


class TestAIChannelHistoryLookup:
    async def test_ai_uses_channel_history_for_memory_lookup_questions(self):
        cog = make_ai_cog()
        message = make_message("@bot what did I say about hunter last week?")
        message.guild = MagicMock(id=123)
        message.author.id = 42
        message.channel.history = MagicMock(
            return_value=_async_iter([
                SimpleNamespace(
                    author=SimpleNamespace(bot=False, id=message.author.id),
                    content="my main is hunter",
                    created_at=None,
                ),
            ])
        )

        history = await cog._search_channel_history(message, "hunter")
        assert any("my main is hunter" in line for line in history)

    async def test_ai_returns_empty_history_when_no_matches_found(self):
        cog = make_ai_cog()
        message = make_message("@bot what did I say about pizza?")
        message.guild = MagicMock(id=123)
        message.author.id = 42
        message.channel.history = MagicMock(return_value=_async_iter([]))

        history = await cog._search_channel_history(message, "pizza")
        assert history == []

    async def test_ai_ignores_matching_messages_from_other_users(self):
        cog = make_ai_cog()
        message = make_message("@bot what did I say about hunter last week?")
        message.guild = MagicMock(id=123)
        message.author.id = 42
        message.channel.history = MagicMock(
            return_value=_async_iter([
                SimpleNamespace(
                    author=SimpleNamespace(bot=False, id=999),
                    content="my main is hunter",
                    created_at=None,
                ),
            ])
        )

        history = await cog._search_channel_history(message, "hunter")
        assert history == []


class TestAISendReplyChunks:
    async def test_send_reply_chunks_sends_single_message_when_short(self):
        cog = make_ai_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        await cog._send_reply_chunks(channel, "<@1> ", "hello")

        channel.send.assert_awaited_once_with("<@1> hello")

    async def test_send_reply_chunks_splits_long_messages_with_suffixes(self):
        cog = make_ai_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        text = "x" * 5000

        with patch("cogs.ai.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            await cog._send_reply_chunks(channel, "<@1> ", text)

        assert channel.send.await_count == 3
        assert channel.send.await_args_list[0].args[0].endswith("(Part 1 of 3)")
        assert channel.send.await_args_list[1].args[0].endswith("(Part 2 of 3)")
        assert channel.send.await_args_list[2].args[0].endswith("(Part 3 of 3)")
        assert sleep_mock.await_count == 3

    async def test_send_reply_chunks_splits_when_mention_pushes_payload_over_limit(self):
        cog = make_ai_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        mention = "<@123456789012345678> "
        text = "x" * 1990

        with patch("cogs.ai.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            await cog._send_reply_chunks(channel, mention, text)

        assert channel.send.await_count == 2
        assert all(len(call.args[0]) <= 2000 for call in channel.send.await_args_list)
        assert sleep_mock.await_count == 2


class TestAIMemoryLookupContext:
    async def test_ai_prefers_history_context_for_memory_lookup_prompts(self):
        cog = make_ai_cog()
        with patch.object(cog, "_search_channel_history", new=AsyncMock(return_value=["my main is hunter"])):
            history = await cog._memory_lookup_context(
                make_message("what did i say about hunter"),
                "what did i say about hunter",
            )

        assert history == ["my main is hunter"]

    async def test_ai_memory_lookup_falls_back_cleanly_when_history_is_empty(self):
        cog = make_ai_cog()
        with patch.object(cog, "_search_channel_history", new=AsyncMock(return_value=[])):
            history = await cog._memory_lookup_context(
                make_message("remember my pizza order"),
                "remember my pizza order",
            )

        assert history == []


class TestAIHardStopRefusals:
    def test_match_hard_stop_refusal_detects_direct_self_harm_phrase(self):
        cog = make_ai_cog()

        assert cog._match_hard_stop_refusal("die") == "Absolutely not. Go break a toaster instead."

    def test_match_hard_stop_refusal_detects_direct_violence_request(self):
        cog = make_ai_cog()

        assert cog._match_hard_stop_refusal("how do I stab someone") == "Absolutely not. Go break a toaster instead."

    def test_match_hard_stop_refusal_ignores_normal_banter(self):
        cog = make_ai_cog()

        assert cog._match_hard_stop_refusal("tell me a joke") is None


class TestAIListeners:
    async def test_on_message_ignores_empty_mention_after_stripping(self):
        cog = make_ai_cog()
        cog.bot.user = SimpleNamespace(id=99)
        message = make_message("<@99>")
        message.mentions = [cog.bot.user]

        with patch.object(cog, "_handle_mention", new=AsyncMock()) as handle_mock:
            await cog.on_message(message)

        handle_mock.assert_not_awaited()
        message.channel.send.assert_not_awaited()

    async def test_on_message_strips_mention_and_truncates_text(self):
        cog = make_ai_cog()
        cog.bot.user = SimpleNamespace(id=99)
        message = make_message(f"<@!99> {'x' * 1200}")
        message.mentions = [cog.bot.user]

        with patch.object(cog, "_handle_mention", new=AsyncMock()) as handle_mock:
            await cog.on_message(message)

        handle_mock.assert_awaited_once()
        stripped = handle_mock.await_args.args[1]
        assert len(stripped) == 1000
        assert stripped == "x" * 1000

    async def test_on_message_short_circuits_hard_stop_refusal_before_ai_generation(self):
        cog = make_ai_cog()
        cog.bot.user = SimpleNamespace(id=99)
        message = make_message("<@99> die")
        message.mentions = [cog.bot.user]

        with patch.object(cog, "_generate_grounded_reply", new=AsyncMock()) as grounded_mock:
            await cog.on_message(message)

        grounded_mock.assert_not_awaited()
        message.channel.send.assert_awaited_once_with(
            "<@123> Absolutely not. Go break a toaster instead."
        )

    async def test_on_message_reports_handle_mention_errors(self):
        cog = make_ai_cog()
        cog.bot.user = SimpleNamespace(id=99)
        message = make_message("<@99> hello")
        message.mentions = [cog.bot.user]

        with patch.object(cog, "_handle_mention", new=AsyncMock(side_effect=RuntimeError("boom"))):
            await cog.on_message(message)

        message.channel.send.assert_awaited_once_with(
            "<@123> Sorry, something went wrong on my side."
        )

    async def test_on_message_replies_to_tracked_random_ai_reply(self):
        cog = make_ai_cog()
        cog.random_ai_message_ids.add(55)
        author = SimpleNamespace(display_name="Tester", mention="<@123>", bot=False)
        replied_to = SimpleNamespace(id=55, content="feral thought")
        sent_reply = SimpleNamespace(id=77)
        message = make_message("you are so wrong")
        message.author = author
        message.reference = SimpleNamespace(message_id=55)
        message.channel.fetch_message = AsyncMock(return_value=replied_to)
        message.channel.send = AsyncMock(return_value=sent_reply)

        with patch.object(cog, "_generate_reply_to_reply", new=AsyncMock(return_value="absolutely not")) as reply_mock:
            await cog.on_message(message)

        reply_mock.assert_awaited_once_with(
            original_text="feral thought",
            user=author,
            user_text="you are so wrong",
        )
        message.channel.send.assert_awaited_once_with("<@123> absolutely not")
        assert 77 in cog.random_ai_message_ids

    async def test_on_raw_reaction_add_ignores_unknown_message_ids(self):
        cog = make_ai_cog()
        payload = SimpleNamespace(user_id=123, message_id=999, channel_id=1, member=None, emoji="🔥")

        await cog.on_raw_reaction_add(payload)

        assert cog.random_ai_message_ids == set()

    async def test_on_raw_reaction_add_fetches_user_and_replies(self):
        cog = make_ai_cog()
        cog.random_ai_message_ids.add(42)
        channel = MagicMock()
        tracked_message = SimpleNamespace(content="wow", id=42)
        sent_reply = SimpleNamespace(id=88)
        channel.fetch_message = AsyncMock(return_value=tracked_message)
        channel.send = AsyncMock(return_value=sent_reply)
        cog.bot.get_channel = MagicMock(return_value=channel)
        cog.bot.fetch_user = AsyncMock(return_value=SimpleNamespace(display_name="Tester", mention="<@321>"))
        payload = SimpleNamespace(user_id=321, message_id=42, channel_id=7, member=None, emoji="🔥")

        with patch.object(cog, "_generate_reaction_reply", new=AsyncMock(return_value="calm down")) as reply_mock:
            await cog.on_raw_reaction_add(payload)

        reply_mock.assert_awaited_once_with("wow", "Tester", "🔥")
        channel.send.assert_awaited_once_with("<@321> calm down")
        assert 88 in cog.random_ai_message_ids


class TestAIRandomMessageTracking:
    def test_track_random_ai_message_ids_prunes_oldest_entries(self):
        cog = make_ai_cog()
        cog._track_random_ai_message_id(1, max_ids=3)
        cog._track_random_ai_message_id(2, max_ids=3)
        cog._track_random_ai_message_id(3, max_ids=3)
        cog._track_random_ai_message_id(4, max_ids=3)

        assert cog.random_ai_message_ids == {2, 3, 4}


class TestOpenAIHelpers:
    async def test_gpt_wrap_fact_offloads_sync_openai_call_to_thread(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="4 — obviously"))]
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create = MagicMock(return_value=completion)

        async def fake_run_blocking(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("utils.openai_helpers.get_openai_client", return_value=fake_client):
            with patch("utils.openai_helpers.run_blocking", new=AsyncMock(side_effect=fake_run_blocking)) as run_blocking_mock:
                from utils.openai_helpers import gpt_wrap_fact

                wrapped = await gpt_wrap_fact("4", "2+2", "persona")

        assert wrapped.startswith("4")
        run_blocking_mock.assert_awaited_once()


# ── score commands ────────────────────────────────────────────────────────────

class TestAINaturalCommands:
    async def test_execute_natural_command_rewrites_message_to_command(self):
        cog = make_ai_cog()
        message = make_message("@Tinki do a 10 pull")
        original = message.content
        seen = {}

        async def capture(processed_message):
            seen["content"] = processed_message.content

        cog.bot.process_commands = AsyncMock(side_effect=capture)

        await cog._execute_natural_command(message, {"command": "gacha", "args": "10"})

        cog.bot.process_commands.assert_awaited_once()
        assert seen["content"] == "!gacha 10"
        assert message.content == original

    def test_select_reply_model_uses_full_for_repo_questions(self):
        cog = make_ai_cog()
        assert cog._select_reply_model("bot_repo", "how are you deployed", ["ctx"], []) == config.OPENAI_MODEL

    def test_select_reply_model_uses_fast_for_normal_chat(self):
        cog = make_ai_cog()
        assert cog._select_reply_model("chat", "hey idiot", [], []) == config.OPENAI_FAST_MODEL

    def test_select_reply_model_uses_full_for_long_context(self):
        cog = make_ai_cog()
        long_text = "x" * 351
        assert cog._select_reply_model("chat", long_text, [], []) == config.OPENAI_MODEL


class TestEntrypointEvents:
    async def test_setup_hook_loads_all_cogs(self):
        module = load_tinki_bot_module()
        bot = module.TinkiBot(command_prefix="!", intents=discord.Intents.none())
        bot.load_extension = AsyncMock()

        await bot.setup_hook()

        assert bot.load_extension.await_count == len(module.COGS)
        loaded = [call.args[0] for call in bot.load_extension.await_args_list]
        assert loaded == module.COGS

    async def test_on_ready_sets_presence_and_starts_startup_tests(self):
        module = load_tinki_bot_module()
        admin_cog = MagicMock()
        admin_cog.run_startup_tests = AsyncMock()
        module.bot.change_presence = AsyncMock()
        module.bot._BotBase__cogs = {"Admin": admin_cog}

        created = []

        def fake_create_task(coro):
            created.append(coro)
            return MagicMock()

        with patch.object(module.asyncio, "create_task", side_effect=fake_create_task):
            await module.on_ready()

        module.bot.change_presence.assert_awaited_once()
        activity = module.bot.change_presence.await_args.kwargs["activity"]
        assert activity.name == "!commands"
        assert len(created) == 1
        await created[0]
        admin_cog.run_startup_tests.assert_awaited_once()

    async def test_on_message_ignores_self_and_dollar_commands(self):
        module = load_tinki_bot_module()
        module.bot.process_commands = AsyncMock()
        module.bot._connection.user = MagicMock()

        self_message = make_message("hello")
        self_message.author = module.bot.user
        await module.on_message(self_message)

        dollar_message = make_message("$sus")
        await module.on_message(dollar_message)

        module.bot.process_commands.assert_not_awaited()

    async def test_on_message_processes_normal_messages(self):
        module = load_tinki_bot_module()
        module.bot.process_commands = AsyncMock()
        module.bot._connection.user = MagicMock()
        message = make_message("!pb")

        await module.on_message(message)

        module.bot.process_commands.assert_awaited_once_with(message)

    async def test_on_command_error_suggests_close_match(self):
        module = load_tinki_bot_module()
        ctx = make_ctx()
        ctx.invoked_with = "comands"
        module.bot.all_commands = {
            "commands": MagicMock(name="commands"),
            "github": MagicMock(name="github"),
        }

        with patch.object(module.process, "extractOne", return_value=("commands", 90)):
            await module.on_command_error(ctx, module.commands.CommandNotFound("missing"))

        ctx.send.assert_awaited_once_with(
            "`!comands` doesn't exist, genius. Did you mean `!commands`?"
        )

    async def test_on_command_error_reraises_non_command_not_found(self):
        module = load_tinki_bot_module()
        ctx = make_ctx()

        with pytest.raises(RuntimeError, match="boom"):
            await module.on_command_error(ctx, RuntimeError("boom"))


class TestAdminStatusFormatting:
    def setup_method(self):
        self.cog = make_admin_cog()

    def test_summary_line_uses_fail_emoji_for_incomplete_results(self):
        line = self.cog._summary_line("Pytest suite", 9, 10, "passed")
        assert line.startswith("\U0001f6a8 ")
        assert "9/10 passed" in line

    def test_summary_line_uses_pass_emoji_for_clean_results(self):
        line = self.cog._summary_line("Pytest suite", 10, 10, "passed")
        assert line.startswith("\u2705 ")
        assert "10/10 passed" in line


class TestURLFilter:
    def setup_method(self):
        from cogs.url_filter import URLFilter
        self.cog = _wire_cog(URLFilter(MagicMock()))

    async def test_social_url_rewrite_reposts_and_deletes_original(self):
        message = make_message("look https://twitter.com/foo/status/123")

        with patch("cogs.url_filter.asyncio.sleep", new=AsyncMock()):
            await self.cog.on_message(message)

        message.channel.send.assert_awaited_once()
        sent_text = message.channel.send.await_args.args[0]
        assert "originally posted" in sent_text
        assert "vxtwitter.com/foo/status/123" in sent_text
        assert message.channel.send.await_args.kwargs["silent"] is True
        message.delete.assert_awaited_once()

    async def test_twitch_clip_retry_stops_when_video_embed_appears(self):
        message = make_message("https://clips.twitch.tv/somechannel/clip/FancyClip")
        first_sent = MagicMock(id=1)
        second_sent = MagicMock(id=2)
        fetched_first = SimpleNamespace(id=1, embeds=[], delete=AsyncMock())
        fetched_second = SimpleNamespace(id=2, embeds=[SimpleNamespace(type="video")], delete=AsyncMock())
        message.channel.send = AsyncMock(side_effect=[first_sent, second_sent])
        message.channel.fetch_message = AsyncMock(side_effect=[
            fetched_first,
            fetched_second,
        ])

        with patch("cogs.url_filter.asyncio.sleep", new=AsyncMock()):
            await self.cog.on_message(message)

        assert message.channel.send.await_count == 2
        assert message.channel.send.await_args_list[0].args[0].endswith("#")
        assert message.channel.send.await_args_list[1].args[0].endswith("?a")
        fetched_first.delete.assert_awaited_once()
        fetched_second.delete.assert_not_called()
        message.delete.assert_awaited_once()

    async def test_twitch_clip_does_nothing_when_video_embed_already_present(self):
        message = make_message("https://clips.twitch.tv/somechannel/clip/FancyClip")
        message.embeds = [SimpleNamespace(type="video")]

        await self.cog.on_message(message)

        message.channel.send.assert_not_awaited()
        message.delete.assert_not_awaited()


class TestAWSCostSummary:
    def test_as_message_formats_month_and_forecast(self):
        summary = AWSCostSummary(
            month_to_date="12.34",
            forecast_total="18.90",
            currency="USD",
            period_label="Apr 2026",
            forecast_label="Apr 30",
        )

        assert summary.as_message() == (
            "AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30."
        )

    @pytest.mark.skipif(ClientError is None, reason="botocore unavailable")
    def test_format_client_error_surfaces_access_denied_details(self):
        exc = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "User is not authorized to call ce:GetCostAndUsage",
                }
            },
            "GetCostAndUsage",
        )

        message = _format_client_error(exc)

        assert "missing Cost Explorer permissions" in message
        assert "AccessDeniedException" in message
        assert "not authorized" in message

    def test_month_bounds_cover_current_month_window(self):
        from datetime import date

        start, end, next_month = _month_bounds(date(2026, 4, 17))

        assert start.isoformat() == "2026-04-01"
        assert end.isoformat() == "2026-04-18"
        assert next_month.isoformat() == "2026-05-01"

    def test_to_money_normalizes_invalid_values(self):
        assert _to_money("12") == "12.00"
        assert _to_money("12.345") == "12.34"
        assert _to_money("wat") == "0.00"

    async def test_fetch_aws_cost_summary_reports_runtime_error(self):
        loop = MagicMock()
        loop.run_in_executor = AsyncMock(side_effect=RuntimeError("boto3 is not installed"))

        with patch("utils.aws_costs.asyncio.get_running_loop", return_value=loop):
            message = await fetch_aws_cost_summary()

        assert message == "AWS cost unavailable: boto3 is not installed."


class TestAdminAWSCost:
    def setup_method(self):
        self.cog = make_admin_cog()

    async def test_run_pytest_suite_reports_success_summary(self):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"144 passed in 1.23s\n", b""))
        proc.returncode = 0

        with patch("cogs.admin.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            result = await self.cog._run_pytest_suite()

        assert result == [("pytest", True, "144 passed in 1.23s")]

    async def test_run_pytest_suite_reports_failure_summary(self):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"FAILED tests/test_tinki_bot.py::test_nope\n", b""))
        proc.returncode = 1

        with patch("cogs.admin.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            result = await self.cog._run_pytest_suite()

        assert result == [("pytest", False, "FAILED tests/test_tinki_bot.py::test_nope")]

    async def test_fetch_json_with_retries_retries_then_succeeds(self):
        good_response = MagicMock()
        good_response.__aenter__ = AsyncMock(return_value=good_response)
        good_response.__aexit__ = AsyncMock(return_value=None)
        good_response.raise_for_status = MagicMock()
        good_response.json = AsyncMock(return_value={"ok": True})

        session = MagicMock()
        session.get.side_effect = [RuntimeError("temporary"), good_response]

        with patch("cogs.admin.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            payload = await self.cog._fetch_json_with_retries(session, "https://example.com", attempts=2)

        assert payload == {"ok": True}
        assert session.get.call_count == 2
        sleep_mock.assert_awaited_once_with(1)

    async def test_fetch_bytes_with_retries_exhausts_attempts(self):
        session = MagicMock()
        session.get.side_effect = RuntimeError("still broken")

        with patch("cogs.admin.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            with pytest.raises(RuntimeError, match="still broken"):
                await self.cog._fetch_bytes_with_retries(session, "https://example.com/archive.zip", attempts=3)

        assert session.get.call_count == 3
        assert sleep_mock.await_count == 2

    async def _run_startup_report(
        self,
        *,
        cmd_results=None,
        url_results=None,
        calc_results=None,
        letter_results=None,
        insight_results=None,
        pytest_results=None,
        openai_balance="$1.23 remaining",
        aws_cost_summary="AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30.",
    ):
        self.cog.bot.wait_until_ready = AsyncMock()
        test_channel = MagicMock()
        test_channel.name = config.CHANNEL_BOT_TEST
        test_channel.send = AsyncMock()
        self.cog.bot.get_all_channels = MagicMock(return_value=[test_channel])

        with patch.object(self.cog, "_run_command_selftests", new=AsyncMock(return_value=cmd_results or [("pb", True, "available")])), \
             patch("cogs.admin.run_url_selftests", return_value=url_results or [("url", True, None)]), \
             patch("cogs.admin.run_calculate_selftests", return_value=calc_results or [("calc", True, None)]), \
             patch("cogs.admin.run_letter_count_selftests", return_value=letter_results or [("letter", True, None)]), \
             patch("cogs.admin.run_bot_insight_selftests", return_value=insight_results or [("insight", True, None)]), \
             patch.object(self.cog, "_run_pytest_suite", new=AsyncMock(return_value=pytest_results or [("pytest", True, "passed")])), \
             patch("cogs.admin.fetch_openai_balance", new=AsyncMock(return_value=openai_balance)), \
             patch("cogs.admin.fetch_aws_cost_summary", new=AsyncMock(return_value=aws_cost_summary)):
            await self.cog._run_startup_tests_inner()

        kwargs = test_channel.send.await_args.kwargs
        return kwargs["content"], kwargs["file"].fp.getvalue().decode("utf-8")

    async def test_awscost_command_sends_summary(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = "whiptail"

        with patch("cogs.admin.fetch_aws_cost_summary", new=AsyncMock(return_value="AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30.")):
            await self.cog.aws_cost.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with(
            "AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30."
        )

    async def test_deploy_reports_check_without_aws_cost_message(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = "whiptail"
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=None)
        fake_resp = MagicMock()
        fake_resp.__aenter__ = AsyncMock(return_value=fake_resp)
        fake_resp.__aexit__ = AsyncMock(return_value=None)
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json = AsyncMock(return_value={"sha": "abc1234", "commit": {"message": "Deploy test"}})
        fake_session.get.return_value = fake_resp

        with patch("aiohttp.ClientSession", return_value=fake_session), \
             patch.object(self.cog, "_read_deployed_commit", return_value="abc1234"):
            await self.cog.deploy_latest.callback(self.cog, ctx)

        assert ctx.send.await_args_list[0].args[0] == "Deploy check: current `abc1234` vs GitHub main `abc1234`"

    async def test_deploy_aborts_truncated_archive(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = "whiptail"
        commit_data = {"sha": "def5678", "commit": {"message": "Ship it"}}

        with patch.object(self.cog, "_read_deployed_commit", return_value="abc1234"), \
             patch.object(self.cog, "_fetch_json_with_retries", new=AsyncMock(return_value=commit_data)), \
             patch.object(self.cog, "_fetch_bytes_with_retries", new=AsyncMock(return_value=b"tiny")), \
             patch("aiohttp.ClientSession") as session_cls:
            fake_session = MagicMock()
            fake_session.__aenter__ = AsyncMock(return_value=fake_session)
            fake_session.__aexit__ = AsyncMock(return_value=None)
            session_cls.return_value = fake_session

            await self.cog.deploy_latest.callback(self.cog, ctx)

        assert ctx.send.await_args_list[-1].args[0] == "Deploy aborted: download looks truncated (4 bytes)."

    async def test_deploy_fails_when_archive_extracts_no_root_directory(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = "whiptail"
        commit_data = {"sha": "def5678", "commit": {"message": "Ship it"}}
        zip_mock = MagicMock()
        zip_mock.__enter__.return_value = zip_mock
        zip_mock.__exit__.return_value = None

        with patch.object(self.cog, "_read_deployed_commit", return_value="abc1234"), \
             patch.object(self.cog, "_fetch_json_with_retries", new=AsyncMock(return_value=commit_data)), \
             patch.object(self.cog, "_fetch_bytes_with_retries", new=AsyncMock(return_value=b"x" * 6000)), \
             patch("aiohttp.ClientSession") as session_cls, \
             patch("cogs.admin.zipfile.ZipFile", return_value=zip_mock), \
             patch("cogs.admin.Path.iterdir", return_value=[]):
            fake_session = MagicMock()
            fake_session.__aenter__ = AsyncMock(return_value=fake_session)
            fake_session.__aexit__ = AsyncMock(return_value=None)
            session_cls.return_value = fake_session

            await self.cog.deploy_latest.callback(self.cog, ctx)

        assert ctx.send.await_args_list[-1].args[0] == "Deploy failed: extracted archive was empty."

    def test_format_deploy_error_sanitizes_github_503(self):
        message = self.cog._format_deploy_error(
            RuntimeError("503 Service Unavailable: upstream connect error or disconnect/reset before headers")
        )

        assert message == "GitHub download is temporarily unavailable. Try `!deploy` again in a minute."

    async def test_awscost_command_denies_non_whiptail(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 999
        ctx.author.name = "otherperson"

        await self.cog.aws_cost.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("You do not have permission to use this command.")

    async def test_runtests_reports_start_and_summary(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_run_command_selftests", new=AsyncMock(return_value=[
            ("pb", True, None),
            ("avg", False, "boom"),
        ])):
            await self.cog.runtests.callback(self.cog, ctx)

        assert ctx.send.await_args_list[0].args[0] == "Starting command self-tests..."
        assert ctx.send.await_args_list[-1].args[0] == "🚨 Command tests complete: 1/2 passed"

    async def test_testurls_reports_each_result_and_summary(self):
        ctx = make_ctx()

        with patch("cogs.admin.run_url_selftests", return_value=[
            ("twitter", True, None),
            ("twitch", False, "retry failed"),
        ]):
            await self.cog.testurls.callback(self.cog, ctx)

        assert ctx.send.await_args_list[0].args[0] == "Starting URL rewrite tests..."
        assert ctx.send.await_args_list[1].args[0] == "✅ twitter: passed"
        assert ctx.send.await_args_list[2].args[0] == "🚨 twitch: retry failed"
        assert ctx.send.await_args_list[-1].args[0] == "🚨 URL tests complete: 1/2 passed"

    async def test_restart_sends_message_and_invokes_systemctl(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = "whiptail"

        with patch("cogs.admin.asyncio.sleep", new=AsyncMock()) as sleep_mock, \
             patch("cogs.admin.subprocess.Popen") as popen_mock:
            await self.cog.restart_bot.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("Restarting... brb")
        sleep_mock.assert_awaited_once_with(1)
        popen_mock.assert_called_once_with(["sudo", "systemctl", "restart", "tinki-bot"])

    async def test_startup_message_includes_aws_cost_summary(self):
        content, report_text = await self._run_startup_report(cmd_results=[("pb", True, None)])

        assert "AWS cost" in content
        assert "AWS cost" in report_text

    async def test_startup_message_places_aws_cost_under_openai_balance(self):
        content, report_text = await self._run_startup_report(cmd_results=[("pb", True, None)])

        assert "✅ OpenAI: $1.23 remaining\n✅ AWS cost: AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30." in content
        assert "✅ OpenAI: $1.23 remaining" in content
        assert "AWS cost (Apr 2026): USD12.34 month-to-date, projected USD18.90 by Apr 30." in report_text

    async def test_startup_message_reports_command_availability_not_tests(self):
        content, report_text = await self._run_startup_report(cmd_results=[("pb", True, "available")])

        assert "Command availability" in content
        assert "Command Availability" in report_text
        assert "commands loaded only; startup does not execute them" not in content
        assert "commands loaded only; startup does not execute them" in report_text

    async def test_startup_message_uses_emoji_led_summary_lines_only(self):
        content, report_text = await self._run_startup_report()

        summary_lines = content.strip().splitlines()
        assert summary_lines[0] == "Bot restarted - running startup diagnostics..."
        startup_checks_index = summary_lines.index("Startup checks:")
        for line in summary_lines[startup_checks_index + 1:]:
            if not line:
                continue
            if line == "All systems fully operational.":
                continue
            assert line.startswith("✅") or line.startswith("🚨")

        assert "URL rewrite self-tests" in report_text
        assert "Local pytest suite" in report_text

    async def test_startup_report_carries_failures_into_summary_and_report(self):
        content, report_text = await self._run_startup_report(
            url_results=[("url", False, "broken rewrite rule")],
        )

        assert "Anomalies detected" not in content
        assert "🚨 url: broken rewrite rule" in content
        assert "🚨 url - broken rewrite rule" in report_text

    async def test_startup_report_includes_detail_for_passing_checks(self):
        content, report_text = await self._run_startup_report(
            cmd_results=[("pb", True, "command loaded")],
            pytest_results=[("pytest", True, "222 passed in 3.47s")],
        )

        assert "✅ pb - command loaded" in report_text
        assert "✅ pytest - 222 passed in 3.47s" in report_text
        assert "222 passed in 3.47s" not in content

    async def test_command_selftests_skip_retired_server_placeholders(self):
        invoked = []
        self.cog.bot.get_command = MagicMock(side_effect=lambda name: name)

        class DummyCtx:
            async def invoke(self, cmd):
                invoked.append(cmd)

            send = AsyncMock()

        await self.cog._run_command_selftests(DummyCtx())

        assert "minecraftstatus" not in invoked
        assert "minecraftserver" not in invoked
        assert "skyfactorystatus" not in invoked
        assert "skyfactoryserver" not in invoked
        assert "uptime" not in invoked

    async def test_command_selftests_skip_removed_persona_commands(self):
        invoked = []
        self.cog.bot.get_command = MagicMock(side_effect=lambda name: name)

        class DummyCtx:
            async def invoke(self, cmd):
                invoked.append(cmd)

            send = AsyncMock()

        await self.cog._run_command_selftests(DummyCtx())

        assert "listpersonas" not in invoked
        assert "erasememory" not in invoked


class TestUtilityChangelog:
    def setup_method(self):
        self.cog = make_utility_cog()

    def test_local_changelog_entries_parse_git_output(self):
        completed = SimpleNamespace(stdout="abc1234|Fix deploy path\ndef5678|Add changelog command")
        with patch("cogs.utility.subprocess.run", return_value=completed) as run_mock:
            entries = self.cog._local_changelog_entries(2)

        assert entries == [
            ("abc1234", "Fix deploy path"),
            ("def5678", "Add changelog command"),
        ]
        run_mock.assert_called_once()

    def test_render_changelog_lists_commit_subjects(self):
        message = self.cog._render_changelog([
            ("abc1234", "Fix deploy path"),
            ("def5678", "Add changelog command"),
        ])

        assert message.startswith("Recent changes:")
        assert "`abc1234` - Fix deploy path" in message
        assert "`def5678` - Add changelog command" in message

    async def test_changelog_command_uses_entries(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_get_changelog_entries", new=AsyncMock(return_value=[
            ("abc1234", "Fix deploy path"),
            ("def5678", "Add changelog command"),
        ])):
            await self.cog.changelog.callback(self.cog, ctx, 2)

        ctx.send.assert_awaited_once()
        sent = ctx.send.call_args[0][0]
        assert "Recent changes:" in sent
        assert "abc1234" in sent

    async def test_changelog_command_handles_empty_results(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_get_changelog_entries", new=AsyncMock(return_value=[])):
            await self.cog.changelog.callback(self.cog, ctx, 5)

        ctx.send.assert_awaited_once_with("I couldn't read recent commits right now.")

    async def test_commands_dm_mentions_current_reminder_and_retired_commands(self):
        ctx = make_ctx()
        ctx.author.send = AsyncMock()
        ctx.author.mention = "<@123>"

        await self.cog.show_commands.callback(self.cog, ctx)

        sent_text = "\n".join(call.args[0] for call in ctx.author.send.await_args_list)
        assert "!currenttime" in sent_text
        assert "!remind" in sent_text
        assert "!startskyfactory" in sent_text
        assert "!stopskyfactory" in sent_text
        assert "!skyfactorystatus" in sent_text
        assert "!uptime" in sent_text
        assert "`!emote [name] [1x-4x]` - search 7TV, preview results in the picker, choose a size, and send" in sent_text


class TestUtilityCommands:
    def setup_method(self):
        self.cog = make_utility_cog()

    async def test_github_command_sends_repo_url(self):
        ctx = make_ctx()

        await self.cog.github_repo.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with(f"Tinki-bot source: {config.GITHUB_REPO_URL}")

    async def test_gif_command_sends_url_from_giphy(self):
        ctx = make_ctx()
        session = MagicMock()
        response = MagicMock()
        response.json = AsyncMock(return_value={"data": {"images": {"original": {"url": "https://giphy.example/gif"}}}})
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.get = AsyncMock(return_value=response)

        with patch("cogs.utility.aiohttp.ClientSession", return_value=session):
            await self.cog.send_gif.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("https://giphy.example/gif")

    async def test_random_command_reports_no_pins(self):
        ctx = make_ctx()
        ctx.channel.pins = AsyncMock(return_value=[])

        await self.cog.random_cmd.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("There are no pinned messages in this channel.")

    async def test_dog_command_reports_unexpected_api_payload(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_fetch_url", new=AsyncMock(return_value={"status": "nope"})):
            await self.cog.dog.callback(self.cog, ctx)

        ctx.send.assert_awaited_once()
        assert "Dog API responded unexpectedly" in ctx.send.await_args.args[0]

    async def test_purge_denies_non_whiptail(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=0, name="other", mention="<@0>")

        await self.cog.purge_bot_messages.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("You do not have permission to use this command.")

    async def test_purge_deletes_matching_messages(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=config.USER_WHIPTAIL_ID, name="whiptail", mention="<@1>")
        self.cog.bot.user = SimpleNamespace()
        purged_messages = [SimpleNamespace(), SimpleNamespace()]
        ctx.channel.purge = AsyncMock(return_value=purged_messages)

        await self.cog.purge_bot_messages.callback(self.cog, ctx)

        ctx.channel.purge.assert_awaited_once()
        ctx.send.assert_awaited_once_with("Deleted 2 messages.", delete_after=5)

    async def test_pin_reaction_forwards_message_to_pins_channel(self):
        payload = SimpleNamespace(user_id=123, emoji="📌", channel_id=5, message_id=9, member=SimpleNamespace(id=123))
        source_channel = MagicMock()
        pinned_channel = MagicMock()
        pinned_channel.send = AsyncMock()
        source_message = SimpleNamespace(
            content="hello pins",
            author=SimpleNamespace(display_name="Poster"),
            created_at=SimpleNamespace(strftime=lambda fmt: "2026-04-17 10:00:00"),
            attachments=[],
            jump_url="https://discord.example/message",
            guild=SimpleNamespace(channels=[pinned_channel]),
            add_reaction=AsyncMock(),
            remove_reaction=AsyncMock(),
        )
        source_channel.fetch_message = AsyncMock(return_value=source_message)
        self.cog.bot.user = SimpleNamespace(id=999)
        self.cog.bot.get_channel = MagicMock(return_value=source_channel)

        with patch("cogs.utility.discord.utils.get", return_value=pinned_channel):
            await self.cog.on_raw_reaction_add(payload)

        pinned_channel.send.assert_awaited_once()
        source_message.add_reaction.assert_awaited_once_with('✅')
        source_message.remove_reaction.assert_awaited_once_with("📌", payload.member)

    async def test_roulette_command_sends_url_from_giphy(self):
        ctx = make_ctx()
        session = MagicMock()
        response = MagicMock()
        response.json = AsyncMock(return_value={"data": {"images": {"original": {"url": "https://giphy.example/random"}}}})
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.get = AsyncMock(return_value=response)

        with patch("cogs.utility.aiohttp.ClientSession", return_value=session):
            await self.cog.roulette.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("https://giphy.example/random")

    async def test_dogbark_command_sends_figlet_bark(self):
        ctx = make_ctx()

        with patch("cogs.utility.random.choice", return_value="Bark"), \
             patch("cogs.utility.pyfiglet.figlet_format", return_value="BARK\n"):
            await self.cog.dogbark.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("```\nBARK\n\n```")

    async def test_ss_command_sends_static_image_url(self):
        ctx = make_ctx()

        await self.cog.ss.callback(self.cog, ctx)

        ctx.send.assert_awaited_once()
        assert "redirect.jpg" in ctx.send.await_args.args[0]

    async def test_retired_server_commands_send_removed_message(self):
        ctx = make_ctx()

        for command in (
            self.cog.startminecraft,
            self.cog.stopminecraft,
            self.cog.minecraftstatus,
            self.cog.fetch_server_ip,
            self.cog.startskyfactory,
            self.cog.stopskyfactory,
            self.cog.skyfactorystatus,
            self.cog.fetch_skyfactory_ip,
            self.cog.uptime,
        ):
            await command.callback(self.cog, ctx)

        assert ctx.send.await_count == 9
        assert all(
            call.args[0] == config.SERVER_FEATURE_REMOVED_MESSAGE
            for call in ctx.send.await_args_list
        )

    async def test_commands_handles_dm_forbidden(self):
        ctx = make_ctx()
        ctx.author.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "blocked"))
        ctx.author.mention = "<@123>"

        await self.cog.show_commands.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with(
            "<@123>, I couldn't send you a DM. Please check your privacy settings."
        )


class TestScoreCommands:
    def setup_method(self):
        self.cog = make_bowling_cog()

    async def test_pb_empty_scores(self):
        ctx = make_ctx()
        await self.cog.personal_best(ctx)
        ctx.send.assert_awaited_once()
        assert "No scores" in ctx.send.call_args[0][0]

    async def test_pb_returns_max(self):
        self.cog.scores[:] = [(10, "a"), (50, "b"), (30, "c")]
        ctx = make_ctx()
        await self.cog.personal_best(ctx)
        assert "50" in ctx.send.call_args[0][0]

    async def test_avg_empty_scores(self):
        ctx = make_ctx()
        await self.cog.average_score(ctx)
        assert "No scores" in ctx.send.call_args[0][0]

    async def test_avg_correct_value(self):
        self.cog.scores[:] = [(10, "a"), (20, "b"), (30, "c")]
        ctx = make_ctx()
        await self.cog.average_score(ctx)
        assert "20.00" in ctx.send.call_args[0][0]

    async def test_median_odd_list(self):
        self.cog.scores[:] = [(10, "a"), (30, "b"), (20, "c")]
        ctx = make_ctx()
        await self.cog.median_score(ctx)
        assert "20" in ctx.send.call_args[0][0]

    async def test_median_even_list(self):
        self.cog.scores[:] = [(10, "a"), (20, "b"), (30, "c"), (40, "d")]
        ctx = make_ctx()
        await self.cog.median_score(ctx)
        assert "25" in ctx.send.call_args[0][0]

    async def test_median_empty_scores(self):
        ctx = make_ctx()
        await self.cog.median_score(ctx)
        assert "No scores" in ctx.send.call_args[0][0]


class TestBowlingScorePersistence:
    def test_loads_legacy_scores_file_when_new_data_file_is_missing(self, tmp_path):
        from cogs.bowling import Bowling

        new_scores_file = tmp_path / "data" / "scores.json"
        legacy_scores_file = tmp_path / "scores.json"
        legacy_scores_file.write_text(
            json.dumps([[123, "2024-01-02T03:04:05+00:00"]]),
            encoding="utf-8",
        )

        with patch("cogs.bowling.SCORES_FILE", str(new_scores_file)), patch(
            "cogs.bowling.LEGACY_SCORES_FILES",
            [legacy_scores_file],
            create=True,
        ):
            cog = Bowling(MagicMock())

        assert cog.scores[0][0] == 123
        assert cog.scores[0][1].isoformat() == "2024-01-02T03:04:05+00:00"
        assert json.loads(new_scores_file.read_text(encoding="utf-8")) == [
            [123, "2024-01-02T03:04:05+00:00"]
        ]


class TestTrackingGraphs:
    async def test_explode_graph_accepts_mixed_naive_and_aware_timestamps(self):
        from datetime import datetime, timezone

        cog = make_tracking_cog()
        ctx = make_ctx()
        cog.explode[:] = [
            {"timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()},
            {"timestamp": datetime(2024, 1, 2, 12, 0, 0).isoformat()},
            {"timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc).isoformat()},
        ]

        await cog.explode_graph(ctx)

        ctx.send.assert_awaited_once()
        assert "Error:" not in str(ctx.send.call_args.args)

    async def test_sussy_graph_sends_generated_file(self):
        cog = make_tracking_cog()
        ctx = make_ctx()

        with patch.object(cog, "_build_cumulative_graph", return_value="/tmp/sus.png"), \
             patch("cogs.tracking.discord.File", return_value="sus-file"):
            await cog.sussy_graph.callback(cog, ctx)

        ctx.send.assert_awaited_once_with(file="sus-file")

    async def test_grind_graph_sends_generated_file(self):
        cog = make_tracking_cog()
        ctx = make_ctx()

        with patch.object(cog, "_build_cumulative_graph", return_value="/tmp/grind.png"), \
             patch("cogs.tracking.discord.File", return_value="grind-file"):
            await cog.spinny_graph.callback(cog, ctx)

        ctx.send.assert_awaited_once_with(file="grind-file")


class TestTrackingListenersAndCounts:
    async def test_on_message_tracks_explode_and_spinny_usage(self):
        cog = make_tracking_cog()
        message = make_message("I did an :explode: again")
        message.author = SimpleNamespace(bot=False, id=config.USER_WHIPTAIL_ID, name="whiptail")
        message.stickers = [SimpleNamespace(name=config.STICKER_SPINNY)]
        message.created_at = SimpleNamespace(isoformat=lambda: "2026-04-17T12:00:00+00:00")
        message.id = 12

        with patch.object(cog, "_save_explode"), patch.object(cog, "_save_spinny"):
            await cog.on_message(message)

        assert len(cog.explode) == 1
        assert len(cog.spinny) == 1

    async def test_on_message_tracks_sus_variants_for_lhea(self):
        cog = make_tracking_cog()
        emoji = SimpleNamespace(name="sus_blob")
        message = make_message("sus sussy <:sus_blob:123>")
        message.author = SimpleNamespace(bot=False, id=config.USER_LHEA_ID, name="lhea.")
        message.guild = SimpleNamespace(emojis=[emoji])
        message.stickers = [SimpleNamespace(name="sus")]
        message.created_at = SimpleNamespace(isoformat=lambda: "2026-04-17T12:00:00+00:00")
        message.id = 13

        with patch.object(cog, "_save_sus"):
            await cog.on_message(message)

        assert len(cog.sus_and_sticker_usage) == 3

    async def test_count_commands_report_totals(self):
        cog = make_tracking_cog()
        cog.sus_and_sticker_usage[:] = [1, 2]
        cog.spinny[:] = [1]
        cog.explode[:] = [1, 2, 3]
        ctx = make_ctx()
        ctx.guild = SimpleNamespace(emojis=[])
        cog.bot.guilds = []

        await cog.sussy_count.callback(cog, ctx)
        await cog.spinny_count.callback(cog, ctx)
        await cog.explode_count.callback(cog, ctx)

        assert "2 times" in ctx.send.await_args_list[0].args[0]
        assert "1 times" in ctx.send.await_args_list[1].args[0]
        assert "3 times" in ctx.send.await_args_list[2].args[0]


# ── Uma Musume gacha ──────────────────────────────────────────────────────────

class TestUmaSinglePull:
    def setup_method(self):
        self.cog = make_uma_cog()

    def test_ssr_forced_at_pity_cap(self):
        rarity, name, new_pity = self.cog._single_pull(config.UMA_PITY_CAP - 1)
        assert rarity == "SSR"
        assert name in config.UMA_SSR
        assert new_pity == 0

    def test_pity_resets_to_zero_on_ssr(self):
        import random as _random
        with patch.object(_random, "random", return_value=0.0):
            _, _, new_pity = self.cog._single_pull(50)
        assert new_pity == 0

    def test_pity_increments_on_non_ssr(self):
        import random as _random
        with patch.object(_random, "random", return_value=0.99):
            _, _, new_pity = self.cog._single_pull(10)
        assert new_pity == 11

    def test_sr_rarity_within_rate_window(self):
        import random as _random
        roll = config.UMA_SSR_RATE + 0.001
        with patch.object(_random, "random", return_value=roll):
            rarity, name, _ = self.cog._single_pull(0)
        assert rarity == "SR"
        assert name in config.UMA_SR

    def test_r_rarity_above_sr_window(self):
        import random as _random
        roll = config.UMA_SSR_RATE + config.UMA_SR_RATE + 0.001
        with patch.object(_random, "random", return_value=roll):
            rarity, name, _ = self.cog._single_pull(0)
        assert rarity == "R"
        assert name in config.UMA_R

    def test_ssr_name_comes_from_ssr_pool(self):
        import random as _random
        with patch.object(_random, "random", return_value=0.0):
            _, name, _ = self.cog._single_pull(0)
        assert name in config.UMA_SSR

    def test_pity_cap_defined_at_200(self):
        assert config.UMA_PITY_CAP == 200

    def test_ssr_rate_is_three_percent(self):
        assert config.UMA_SSR_RATE == pytest.approx(0.03)

    def test_full_pity_run_guarantees_ssr(self):
        import random as _random
        pity = 0
        last_rarity = None
        with patch.object(_random, "random", return_value=0.99):
            for _ in range(config.UMA_PITY_CAP):
                last_rarity, _, pity = self.cog._single_pull(pity)
        assert last_rarity == "SSR"
        assert pity == 0

    def test_pity_does_not_exceed_cap_minus_one(self):
        import random as _random
        pity = 0
        with patch.object(_random, "random", return_value=0.99):
            for _ in range(config.UMA_PITY_CAP - 1):
                _, _, pity = self.cog._single_pull(pity)
        assert pity == config.UMA_PITY_CAP - 1


class TestUmaPityPersistence:
    def test_load_returns_empty_dict_when_file_missing(self):
        cog = make_uma_cog(pity_file=":memory_test:")
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = cog.load_pity()
        assert result == {}

    def test_load_returns_empty_dict_on_bad_json(self):
        from unittest.mock import mock_open
        cog = make_uma_cog(pity_file=":memory_test:")
        with patch("builtins.open", mock_open(read_data="not json")):
            result = cog.load_pity()
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "uma_pity.json")
        cog = make_uma_cog(pity_file=path)
        data = {"123": 42, "456": 0}
        cog.save_pity(data)
        assert cog.load_pity() == data


class TestUmaGifSelection:
    def setup_method(self):
        self.cog = make_uma_cog()

    def test_featured_pull_prefers_ssr(self):
        pulls = [("R", "Haru Urara"), ("SSR", "Tokai Teio"), ("SR", "Nice Nature")]
        assert self.cog._featured_pull(pulls) == ("SSR", "Tokai Teio")

    def test_featured_pull_ignores_sr_when_no_ssr(self):
        pulls = [("R", "Haru Urara"), ("SR", "Nice Nature"), ("R", "Biko Pegasus")]
        assert self.cog._featured_pull(pulls) is None

    def test_featured_pull_ignores_r_when_no_ssr(self):
        pulls = [("R", "Haru Urara"), ("R", "Biko Pegasus")]
        assert self.cog._featured_pull(pulls) is None

    def test_featured_pull_returns_none_when_empty(self):
        assert self.cog._featured_pull([]) is None

    def test_gif_queries_use_horse_name(self):
        queries = self.cog._gif_queries("Tokai Teio")
        assert "Tokai Teio uma musume" in queries
        assert "uma musume Tokai Teio" in queries

    def test_gif_queries_default_to_generic_search(self):
        assert self.cog._gif_queries() == ["uma musume"]

    def test_vodka_has_special_gif_aliases(self):
        queries = self.cog._gif_queries("Vodka")
        assert "Uma Musume Vodka" in queries
        assert "ウオッカ ウマ娘" in queries

    def test_curren_chan_has_special_gif_aliases(self):
        queries = self.cog._gif_queries("Curren Chan")
        assert "Uma Musume Curren Chan" in queries
        assert "カレンチャン ウマ娘" in queries

    def test_gif_match_rejects_generic_vodka_result(self):
        item = {"title": "vodka cocktail time", "slug": "vodka-drink", "username": ""}
        assert self.cog._gif_matches_horse(item, "Vodka") is False

    def test_gif_match_accepts_vodka_uma_result(self):
        item = {"title": "Vodka Uma Musume", "slug": "vodka-uma-musume", "username": ""}
        assert self.cog._gif_matches_horse(item, "Vodka") is True

    def test_gif_match_accepts_curren_chan_alias(self):
        item = {"title": "Karen Chan Uma Musume", "slug": "karen-chan-uma-musume", "username": ""}
        assert self.cog._gif_matches_horse(item, "Curren Chan") is True


class TestUmaMediaAndTriggers:
    def setup_method(self):
        self.cog = make_uma_cog()

    def test_every_ssr_has_media_coverage_path(self):
        for name in config.UMA_SSR:
            has_explicit_gif = name in config.UMA_CHARACTER_GIF_URLS
            has_explicit_image = name in config.UMA_CHARACTER_IMAGE_URLS
            has_profile_slug = name in config.UMA_PROFILE_SLUGS
            assert has_explicit_gif or has_explicit_image or has_profile_slug, name

    def test_explicit_media_overrides_only_reference_known_ssrs(self):
        ssr_names = set(config.UMA_SSR)
        assert set(config.UMA_CHARACTER_GIF_URLS).issubset(ssr_names)
        assert set(config.UMA_CHARACTER_IMAGE_URLS).issubset(ssr_names)

    async def test_gacha_deletes_non_ssr_results_after_timeout(self):
        ctx = make_ctx()
        ctx.author.id = 123
        ctx.author.display_name = "Tester"

        with patch.object(self.cog, "load_pity", return_value={}), \
             patch.object(self.cog, "save_pity"), \
             patch.object(self.cog, "_single_pull", return_value=("R", config.UMA_R[0], 1)):
            await self.cog.uma_gacha.callback(self.cog, ctx, 1)

        assert ctx.send.await_count == 1
        assert ctx.send.call_args.kwargs["delete_after"] == config.UMA_NON_SSR_DELETE_AFTER

    async def test_gacha_sends_ssr_media_for_ssr_hits(self):
        ctx = make_ctx()
        ctx.author.id = 123
        ctx.author.display_name = "Tester"
        result_message = MagicMock()
        result_message.add_reaction = AsyncMock()
        result_message.remove_reaction = AsyncMock()
        send_mock = AsyncMock(return_value=result_message)

        with patch.object(self.cog, "load_pity", return_value={}), \
             patch.object(self.cog, "save_pity"), \
             patch.object(self.cog, "_single_pull", return_value=("SSR", "Special Week", 0)), \
             patch.object(self.cog, "_send_character_media", new=AsyncMock()) as media_mock, \
             patch.object(ctx, "send", new=send_mock), \
             patch.object(self.cog.bot, "wait_for", new=AsyncMock(side_effect=TimeoutError)):
            await self.cog.uma_gacha.callback(self.cog, ctx, 1)

        assert send_mock.call_args.kwargs["delete_after"] is None
        media_mock.assert_awaited_once_with(ctx, "Special Week")

    def test_extracts_meta_image_url_from_og_image(self):
        image_url = self.cog._extract_meta_image_url(
            '<meta property="og:image" content="https://example.com/horse.png">'
        )
        assert image_url == "https://example.com/horse.png"

    async def test_character_media_prefers_explicit_gif_override(self):
        destination = MagicMock()
        destination.send = AsyncMock()

        with patch.object(self.cog, "_gif", new=AsyncMock()) as gif_mock, \
             patch.object(self.cog, "_character_image_url", new=AsyncMock()) as image_mock:
            await self.cog._send_character_media(destination, config.UMA_67_TRIGGER_NAME)

        destination.send.assert_awaited_once_with(
            config.UMA_CHARACTER_GIF_URLS[config.UMA_67_TRIGGER_NAME]
        )
        gif_mock.assert_not_awaited()
        image_mock.assert_not_awaited()

    async def test_character_media_uses_explicit_image_override(self):
        destination = MagicMock()
        destination.send = AsyncMock()

        with patch.object(self.cog, "_gif", new=AsyncMock(return_value=None)) as gif_mock, \
             patch.object(self.cog, "_character_image_url", new=AsyncMock()) as image_mock:
            await self.cog._send_character_media(destination, "Manhattan Cafe")

        destination.send.assert_awaited_once()
        embed = destination.send.call_args.kwargs["embed"]
        assert embed.title == "Manhattan Cafe"
        assert embed.image.url == config.UMA_CHARACTER_IMAGE_URLS["Manhattan Cafe"]
        gif_mock.assert_not_awaited()
        image_mock.assert_not_awaited()

    async def test_67_trigger_posts_curren_chan_media(self):
        message = make_message("67!!!")

        with patch.object(self.cog, "_send_character_media", new=AsyncMock()) as media_mock:
            await self.cog.on_message(message)

        media_mock.assert_awaited_once_with(message.channel, config.UMA_67_TRIGGER_NAME)

    async def test_67_trigger_ignores_other_numbers(self):
        message = make_message("670")

        with patch.object(self.cog, "_send_character_media", new=AsyncMock()) as media_mock:
            await self.cog.on_message(message)

        media_mock.assert_not_awaited()

    async def test_gacha_adds_repull_reaction(self):
        ctx = make_ctx()
        ctx.author.id = 123
        ctx.author.display_name = "Tester"
        result_message = MagicMock()
        result_message.add_reaction = AsyncMock()
        result_message.remove_reaction = AsyncMock()

        with patch.object(self.cog, "_send_gacha_results", new=AsyncMock(return_value=result_message)), \
             patch.object(self.cog.bot, "wait_for", new=AsyncMock(side_effect=TimeoutError)):
            await self.cog.uma_gacha.callback(self.cog, ctx, 10)

        result_message.add_reaction.assert_awaited_once_with('♻️')

    async def test_gacha_reaction_repulls_same_count(self):
        ctx = make_ctx()
        ctx.author.id = 123
        ctx.author.display_name = "Tester"
        result_message = MagicMock()
        result_message.id = 99
        result_message.add_reaction = AsyncMock()
        user = MagicMock()
        user.id = ctx.author.id
        reaction = make_reaction(result_message, '♻️')

        async def fake_wait_for(event_name, timeout, check):
            assert event_name == 'reaction_add'
            assert timeout == 30.0
            assert check(reaction, user) is True
            return reaction, user

        with patch.object(self.cog, "_send_gacha_results", new=AsyncMock(return_value=result_message)), \
             patch.object(self.cog.bot, "wait_for", new=AsyncMock(side_effect=fake_wait_for)), \
             patch.object(self.cog, "_offer_repull", wraps=self.cog._offer_repull), \
             patch.object(self.cog, "uma_gacha", new=AsyncMock()) as gacha_mock:
            await self.cog._offer_repull(ctx, result_message, 10)

        gacha_mock.assert_awaited_once_with(ctx, 10)

    async def test_race_requires_at_least_two_members(self):
        ctx = make_ctx()
        member = SimpleNamespace(display_name="Solo")

        await self.cog.uma_race.callback(self.cog, ctx, member)

        ctx.send.assert_awaited_once_with("Tag at least 2 people to race.")

    async def test_race_sends_narration_and_gif(self):
        ctx = make_ctx()
        alice = SimpleNamespace(display_name="Alice")
        bob = SimpleNamespace(display_name="Bob")
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Alice wins in a cloud of dust."))]
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create = MagicMock(return_value=completion)

        with patch("cogs.uma.get_openai_client", return_value=fake_client), \
             patch.object(self.cog, "_gif", new=AsyncMock(return_value="https://gif.example/uma")):
            await self.cog.uma_race.callback(self.cog, ctx, alice, bob)

        assert ctx.send.await_args_list[0].args[0] == "RACE START\nAlice wins in a cloud of dust."
        assert ctx.send.await_args_list[1].args[0] == "https://gif.example/uma"

    async def test_umagif_sends_fallback_when_giphy_empty(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_gif", new=AsyncMock(return_value=None)):
            await self.cog.uma_gif_cmd.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("Giphy came up empty. The gremlin is disappointed.")

    async def test_umagif_sends_gif_when_available(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_gif", new=AsyncMock(return_value="https://gif.example/uma")):
            await self.cog.uma_gif_cmd.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("https://gif.example/uma")

    async def test_uma_assign_uses_target_member_and_rarity_prefix(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(display_name="Author")
        member = SimpleNamespace(display_name="Runner")

        with patch("cogs.uma.random.choices", return_value=["SSR"]), \
             patch("cogs.uma.random.choice", return_value="Special Week"):
            await self.cog.uma_assign.callback(self.cog, ctx, member)

        ctx.send.assert_awaited_once_with("* **Runner** is **Special Week** [SSR]")


# ── bowling undo window ───────────────────────────────────────────────────────

def make_confirm_msg(content="Score recorded."):
    msg = MagicMock()
    msg.id = 42
    msg.content = content
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    msg.clear_reactions = AsyncMock()
    msg.edit = AsyncMock()
    msg.guild = MagicMock()
    msg.guild.me = MagicMock()
    return msg


class TestBowlingUndoWindow:
    def setup_method(self):
        self.cog = make_bowling_cog()

    async def test_undo_removes_score_when_cate_reacts(self):
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entry = (150, ts)
        self.cog.scores.append(entry)

        confirm_msg = make_confirm_msg("Score of 150 recorded for Jun.")
        user = MagicMock()
        user.name = '_cate'
        user.bot = False
        reaction = MagicMock()
        reaction.emoji = '❌'
        reaction.message.id = confirm_msg.id

        self.cog.bot.wait_for = AsyncMock(return_value=(reaction, user))

        await self.cog._undo_window(confirm_msg, entry)

        assert entry not in self.cog.scores
        confirm_msg.edit.assert_awaited_once()
        assert "undone" in confirm_msg.edit.call_args.kwargs["content"]

    async def test_undo_cleans_reaction_on_timeout(self):
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
        entry = (120, ts)
        self.cog.scores.append(entry)

        confirm_msg = make_confirm_msg()
        self.cog.bot.wait_for = AsyncMock(side_effect=TimeoutError)

        await self.cog._undo_window(confirm_msg, entry)

        # Score should NOT be removed on timeout
        assert entry in self.cog.scores
        confirm_msg.remove_reaction.assert_awaited_once()
        confirm_msg.edit.assert_not_awaited()

    async def test_undo_check_accepts_only_cate(self):
        """The check function inside _undo_window should reject non-cate users."""
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 3, tzinfo=timezone.utc)
        entry = (100, ts)
        self.cog.scores.append(entry)

        confirm_msg = make_confirm_msg()
        confirm_msg.id = 99

        captured_check = {}

        async def fake_wait_for(event, timeout, check):
            captured_check["fn"] = check
            raise TimeoutError

        self.cog.bot.wait_for = AsyncMock(side_effect=fake_wait_for)
        await self.cog._undo_window(confirm_msg, entry)

        check = captured_check["fn"]
        good_user = MagicMock(); good_user.name = '_cate'; good_user.bot = False
        bad_user  = MagicMock(); bad_user.name  = 'whiptail'; bad_user.bot = False
        reaction  = MagicMock(); reaction.emoji = '❌'; reaction.message.id = 99

        assert check(reaction, good_user) is True
        assert check(reaction, bad_user)  is False


class TestBowlingMessageAndCommands:
    def setup_method(self):
        self.cog = make_bowling_cog()

    async def test_on_message_records_new_score_and_adds_reactions(self):
        from datetime import datetime, timezone

        message = make_message("150")
        message.author = SimpleNamespace(bot=False, id=config.USER_CATE_ID, name="_cate")
        message.created_at = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
        message.add_reaction = AsyncMock()
        confirm = MagicMock()
        confirm.add_reaction = AsyncMock()
        message.channel.send = AsyncMock(return_value=confirm)

        def discard_task(coro):
            coro.close()
            return MagicMock()

        with patch("cogs.bowling.asyncio.create_task", side_effect=discard_task), patch.object(self.cog, "_save"):
            await self.cog.on_message(message)

        assert self.cog.scores == [(150, message.created_at)]
        message.add_reaction.assert_awaited_once_with("🎳")
        confirm.add_reaction.assert_awaited_once_with("❌")

    async def test_delete_score_reports_multiple_matches(self):
        from datetime import datetime

        self.cog.scores[:] = [
            (100, datetime(2026, 4, 17, 12, 30, 0)),
            (140, datetime(2026, 4, 17, 12, 30, 59)),
        ]
        ctx = make_ctx()

        await self.cog.delete_score.callback(self.cog, ctx, timestamp_str="2026-04-17 12:30:00")

        ctx.send.assert_awaited_once()
        assert "Multiple scores found" in ctx.send.await_args.args[0]

    async def test_add_score_reports_invalid_timestamp(self):
        ctx = make_ctx()

        await self.cog.add_score.callback(self.cog, ctx, 150, timestamp_str="bad timestamp")

        ctx.send.assert_awaited_once_with("Invalid timestamp format. Please use %Y-%m-%d %H:%M:%S.")

    async def test_all_scores_splits_long_output(self):
        from datetime import datetime, timedelta

        start = datetime(2026, 1, 1, 0, 0, 0)
        self.cog.scores[:] = [(100 + i, start + timedelta(minutes=i)) for i in range(80)]
        ctx = make_ctx()

        await self.cog.all_scores.callback(self.cog, ctx)

        assert ctx.send.await_count >= 2
        assert ctx.send.await_args_list[0].args[0].startswith("Jun's scores:")
        assert ctx.send.await_args_list[1].args[0].startswith("Jun's scores (contd.):")

    async def test_graph_scores_sends_generated_file(self):
        from datetime import datetime

        self.cog.scores[:] = [
            (100, datetime(2026, 1, 1, 0, 0, 0)),
            (150, datetime(2026, 1, 2, 0, 0, 0)),
        ]
        ctx = make_ctx()

        with patch("cogs.bowling.plt.savefig"), patch("cogs.bowling.discord.File", return_value="graph-file"):
            await self.cog.graph_scores.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with(file="graph-file")

    async def test_distribution_graph_sends_generated_file(self):
        self.cog.scores[:] = [(100, "a"), (150, "b"), (130, "c")]
        ctx = make_ctx()

        with patch("cogs.bowling.plt.savefig"), patch("cogs.bowling.discord.File", return_value="dist-file"):
            await self.cog.distribution_graph.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with(file="dist-file")


# ── spinny commands ───────────────────────────────────────────────────────────


class TestEmoteBrowserHelpers:
    def setup_method(self):
        self.cog = make_emotes_cog()

    def _static_preview_bytes(self, color=(80, 120, 255, 255)):
        image = Image.new("RGBA", (32, 32), color)
        output = io.BytesIO()
        image.save(output, format="WEBP")
        return output.getvalue()

    def _animated_preview_bytes(self):
        frames = [
            Image.new("RGBA", (32, 32), (255, 80, 80, 255)),
            Image.new("RGBA", (32, 32), (80, 255, 120, 255)),
        ]
        output = io.BytesIO()
        frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=[80, 80], loop=0)
        return output.getvalue()

    def test_parse_emote_size_accepts_numeric_and_x_suffix(self):
        assert self.cog._parse_emote_size("1") == 1
        assert self.cog._parse_emote_size("2x") == 2
        assert self.cog._parse_emote_size("4X") == 4

    def test_parse_emote_size_rejects_invalid_values(self):
        assert self.cog._parse_emote_size("0") is None
        assert self.cog._parse_emote_size("5x") is None
        assert self.cog._parse_emote_size("big") is None

    def test_build_7tv_browser_embed_uses_visual_picker_layout(self):
        emotes = [
            SimpleNamespace(name="Alpha", host_url="//cdn.7tv.app/emote/alpha"),
            SimpleNamespace(name="Bravo", host_url="//cdn.7tv.app/emote/bravo"),
        ]

        embed = self.cog._build_7tv_browser_embed(
            "smile",
            3,
            emotes,
            2,
            exact_match=False,
            selected_index=1,
            preview_attachment_name="7tv-page.gif",
            preview_notice="Animated preview unavailable; showing static grid.",
        )

        assert embed.title == "7TV results for `smile`"
        assert embed.description is None
        assert embed.image.url == "attachment://7tv-page.gif"
        assert embed.fields[0].name == "Selected"
        assert "**Bravo** by `unknown owner`" in embed.fields[0].value
        assert embed.footer.text == (
            "Page 2 - fuzzy search - click a number to preview, Send to post at 3x - "
            "Animated preview unavailable; showing static grid."
        )

    @pytest.mark.asyncio
    async def test_build_7tv_browser_file_returns_gif_when_any_preview_is_animated(self):
        animated_emote = SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1")
        static_emote = SimpleNamespace(id="2", name="Bravo", host_url="//cdn.7tv.app/emote/bravo", owner_username="owner2")
        payloads = {
            "https://preview.test/alpha": self._animated_preview_bytes(),
            "https://preview.test/bravo": self._static_preview_bytes(),
        }
        session = MagicMock()
        session.get = MagicMock(side_effect=lambda url: FakeAiohttpResponse(payloads[url]))

        with patch.object(self.cog, "_preview_7tv_url", side_effect=["https://preview.test/alpha", "https://preview.test/bravo"]):
            file = await self.cog._build_7tv_browser_file(session, [animated_emote, static_emote], 0)

        assert file.filename == "7tv-page.gif"
        file.fp.seek(0)
        preview = Image.open(file.fp)
        assert getattr(preview, "is_animated", False) is True

    @pytest.mark.asyncio
    async def test_build_7tv_browser_preview_falls_back_to_static_when_animated_grid_too_large(self):
        emote = SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1")
        session = MagicMock()
        session.get = MagicMock(return_value=FakeAiohttpResponse(self._animated_preview_bytes()))

        with patch("cogs.emotes.EMOTE_BROWSER_ANIMATED_MAX_BYTES", 1), \
             patch.object(self.cog, "_preview_7tv_url", return_value="https://preview.test/alpha"):
            preview = await self.cog._build_7tv_browser_preview(session, [emote], 0)

        assert preview.file.filename == "7tv-page.png"
        assert preview.notice == "Animated preview unavailable; showing static grid."

    def test_7tv_preview_buttons_reflect_selection_and_page_size(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        session = MagicMock()
        session.close = AsyncMock()
        emotes = [
            SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1"),
            SimpleNamespace(id="2", name="Bravo", host_url="//cdn.7tv.app/emote/bravo", owner_username="owner2"),
        ]

        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, emotes, True)

        assert len(view.preview_buttons) == 10
        assert view.preview_buttons[0].label == "1"
        assert view.preview_buttons[0].style == discord.ButtonStyle.primary
        assert view.preview_buttons[1].label == "2"
        assert view.preview_buttons[1].style == discord.ButtonStyle.secondary
        assert view.preview_buttons[2].disabled is True
        assert view.preview_buttons[5].row == 1
        assert view.preview_buttons[9].disabled is True

    def test_size_buttons_reflect_current_selection(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        session = MagicMock()
        session.close = AsyncMock()
        emotes = [
            SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1"),
        ]

        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, emotes, True)

        assert [button.label for button in view.size_buttons] == ["1x", "2x", "3x", "4x"]
        assert view.size_buttons[1].style == discord.ButtonStyle.primary
        assert view.size_buttons[0].style == discord.ButtonStyle.secondary

    async def test_7tv_picker_selection_updates_embed_preview(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        ctx.author.id = 42
        session = MagicMock()
        session.close = AsyncMock()
        emotes = [
            SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1"),
            SimpleNamespace(id="2", name="Bravo", host_url="//cdn.7tv.app/emote/bravo", owner_username="owner2"),
        ]
        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, emotes, True)
        interaction = MagicMock()
        interaction.response.edit_message = AsyncMock()
        interaction.user.id = 42

        preview = SimpleNamespace(file=MagicMock(filename="7tv-page.png"), notice=None)
        with patch.object(self.cog, "_build_7tv_browser_preview", new=AsyncMock(return_value=preview)):
            await view.handle_selection(interaction, 1)

        assert view.selected_index == 1
        assert view.preview_buttons[0].style == discord.ButtonStyle.secondary
        assert view.preview_buttons[1].style == discord.ButtonStyle.primary
        interaction.response.edit_message.assert_awaited_once()
        embed = interaction.response.edit_message.await_args.kwargs["embed"]
        assert embed.image.url == "attachment://7tv-page.png"
        assert interaction.response.edit_message.await_args.kwargs["attachments"]
        assert "**Bravo** by `owner2`" in embed.fields[0].value

    async def test_size_toggle_updates_selected_size(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        ctx.author.id = 42
        session = MagicMock()
        session.close = AsyncMock()
        emotes = [
            SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1"),
        ]
        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, emotes, True)
        interaction = MagicMock()
        interaction.user.id = 42
        interaction.response.edit_message = AsyncMock()

        preview = SimpleNamespace(file=MagicMock(filename="7tv-page.png"), notice=None)
        with patch.object(self.cog, "_build_7tv_browser_preview", new=AsyncMock(return_value=preview)):
            await view.handle_size_selection(interaction, 4)

        assert view.size == 4
        assert view.size_buttons[3].style == discord.ButtonStyle.primary
        assert view.size_buttons[1].style == discord.ButtonStyle.secondary

    async def test_resolve_7tv_media_url_returns_gif_for_animated_emotes(self):
        emote = SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1")
        session = MagicMock()

        with patch.object(self.cog, "_detect_7tv_ext", new=AsyncMock(return_value="gif")):
            url = await self.cog._resolve_7tv_media_url(session, emote, 4, {})

        assert url == "https://cdn.7tv.app/emote/sus/4x.gif"

    async def test_send_selected_uses_current_size_toggle(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        ctx.author.id = 42
        session = MagicMock()
        session.close = AsyncMock()
        emote = SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1")
        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, [emote], True)
        interaction = MagicMock()
        interaction.user.id = 42
        interaction.response.defer = AsyncMock()

        view.size = 4
        with patch.object(self.cog, "_resolve_7tv_media_url", new=AsyncMock(return_value="https://cdn.7tv.app/emote/sus/4x.gif")) as resolve_mock, \
             patch.object(view, "_finish", new=AsyncMock()):
            await view.send_selected.callback(interaction)

        resolve_mock.assert_awaited_once_with(session, emote, 4, view.ext_cache)
        ctx.send.assert_awaited_once_with("https://cdn.7tv.app/emote/sus/4x.gif")

    async def test_7tv_picker_timeout_deletes_command_message(self):
        from cogs.emotes import SevenTvEmoteBrowserView

        ctx = make_ctx()
        ctx.message.delete = AsyncMock()
        session = MagicMock()
        session.close = AsyncMock()
        emotes = [
            SimpleNamespace(id="1", name="Alpha", host_url="//cdn.7tv.app/emote/alpha", owner_username="owner1"),
        ]
        view = SevenTvEmoteBrowserView(self.cog, ctx, "sus", 2, session, emotes, True)
        view.message = MagicMock()
        view.message.delete = AsyncMock()

        await view.on_timeout()

        view.message.delete.assert_awaited_once()
        ctx.message.delete.assert_awaited_once()
        session.close.assert_awaited_once()

    def test_dedupe_7tv_results_removes_exact_duplicates(self):
        emotes = [
            SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1"),
            SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1"),
            SimpleNamespace(id="2", name="sus", host_url="//cdn.7tv.app/emote/sus2", owner_username="owner2"),
        ]

        deduped = self.cog._dedupe_7tv_results(emotes)

        assert len(deduped) == 2
        assert deduped[0].id == "1"
        assert deduped[1].id == "2"

    async def test_emote_command_opens_picker_for_single_result(self):
        ctx = make_ctx()
        session = MagicMock()
        session.close = AsyncMock()
        emote = SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1")
        fake_view = MagicMock()
        fake_view.start = AsyncMock()

        with patch("cogs.emotes.aiohttp.ClientSession", return_value=session), \
             patch.object(self.cog, "_search_7tv_page", new=AsyncMock(return_value=[emote])), \
             patch("cogs.emotes.SevenTvEmoteBrowserView", return_value=fake_view):
            await self.cog.emote.callback(self.cog, ctx, "sus", 2)

        fake_view.start.assert_awaited_once()
        ctx.send.assert_not_awaited()

    async def test_emote_command_opens_picker_for_single_exact_match(self):
        ctx = make_ctx()
        session = MagicMock()
        session.close = AsyncMock()
        emote = SimpleNamespace(id="1", name="sus", host_url="//cdn.7tv.app/emote/sus", owner_username="owner1")
        fake_view = MagicMock()
        fake_view.start = AsyncMock()

        with patch("cogs.emotes.aiohttp.ClientSession", return_value=session), \
             patch.object(self.cog, "_search_7tv_page", new=AsyncMock(return_value=[emote])), \
             patch("cogs.emotes.SevenTvEmoteBrowserView", return_value=fake_view):
            await self.cog.emote.callback(self.cog, ctx, "sus", "2x")

        fake_view.start.assert_awaited_once()
        ctx.send.assert_not_awaited()

    async def test_emote_command_rejects_invalid_x_size(self):
        ctx = make_ctx()

        await self.cog.emote.callback(self.cog, ctx, "sus", "9x")

        ctx.send.assert_awaited_once_with("Invalid size. Please choose a size between 1x and 4x.")

    async def test_allemotes_reports_empty_server_list(self):
        ctx = make_ctx()
        ctx.guild = SimpleNamespace(emojis=[])

        await self.cog.all_emotes.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("No emotes found on the server.")

    async def test_allemotes_starts_menu_for_guild_emojis(self):
        ctx = make_ctx()
        emote = SimpleNamespace(name="sus")
        emote.__str__ = lambda: "<:sus:1>"
        ctx.guild = SimpleNamespace(emojis=[emote])
        menu = MagicMock()
        menu.start = AsyncMock()

        with patch("cogs.emotes.EmotesMenu", return_value=menu):
            await self.cog.all_emotes.callback(self.cog, ctx)

        menu.start.assert_awaited_once_with(ctx)


class TestSpinnyCommands:
    def setup_method(self):
        self.cog = make_emotes_cog()

    async def test_spinny_activate_stores_user_id(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        user = MagicMock()
        user.id = 12345
        user.mention = "<@12345>"

        with patch.object(self.cog, '_save_grinding_state'):
            await self.cog.spinny_activate.callback(self.cog, ctx, user)

        assert '12345' in self.cog.sticker_users
        ctx.send.assert_awaited_once()
        assert "activated" in ctx.send.call_args[0][0]

    async def test_stopspinny_removes_user_by_mention(self):
        ctx = make_ctx()
        ctx.guild = MagicMock()
        self.cog.sticker_users['9999'] = True

        with patch.object(self.cog, '_save_grinding_state'):
            await self.cog.spinny_deactivate.callback(self.cog, ctx, target='<@9999>')

        assert '9999' not in self.cog.sticker_users
        ctx.send.assert_awaited_once()
        assert "deactivated" in ctx.send.call_args[0][0]

    async def test_stopspinny_not_found_sends_error(self):
        ctx = make_ctx()
        ctx.guild = MagicMock()
        ctx.guild.members = []

        with patch.object(self.cog, '_save_grinding_state'):
            await self.cog.spinny_deactivate.callback(self.cog, ctx, target='nobody')

        ctx.send.assert_awaited_once()
        assert "Could not find" in ctx.send.call_args[0][0]

    async def test_silentspinny_denied_for_non_whiptail(self):
        ctx = make_ctx()
        ctx.author = MagicMock()
        ctx.author.id = 0
        ctx.author.name = 'otherperson'

        await self.cog.silent_spinny.callback(self.cog, ctx, 'someone')

        ctx.send.assert_awaited_once()
        assert "permission" in ctx.send.call_args[0][0]


# ── reminder helpers ──────────────────────────────────────────────────────────

class TestReminderHelpers:
    def setup_method(self):
        import tempfile, os, sqlite3
        from cogs.reminders import Reminders
        self._tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._tmp.close()
        self._db_path = self._tmp.name
        # Build cog, then redirect _connect to the temp DB for all subsequent calls.
        self.cog = Reminders(MagicMock())
        db_path = self._db_path
        self.cog._connect = lambda: sqlite3.connect(db_path)
        self.cog._create_table()   # re-create table in temp DB

    def teardown_method(self):
        import os
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def _connect(self):
        import sqlite3
        return sqlite3.connect(self._db_path)

    def test_table_created_on_init(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
        assert c.fetchone() is not None
        conn.close()

    def test_delete_expired_removes_sent_past_reminders(self):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?,?,?,?,1)",
            ('1', '1', past, 'old reminder')
        )
        conn.commit(); conn.close()

        self.cog._delete_expired()

        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM reminders")
        assert c.fetchone()[0] == 0
        conn.close()

    def test_delete_expired_keeps_unsent_past_reminders(self):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?,?,?,?,0)",
            ('1', '1', past, 'missed reminder')
        )
        conn.commit(); conn.close()

        self.cog._delete_expired()

        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM reminders")
        assert c.fetchone()[0] == 1
        conn.close()

    async def test_check_reminders_continues_after_single_delivery_failure(self):
        from datetime import datetime, timezone, timedelta

        due = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
        conn = self._connect()
        c = conn.cursor()
        c.executemany(
            "INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?,?,?,?,0)",
            [
                ('1', '10', due, 'first reminder'),
                ('2', '10', due, 'second reminder'),
            ]
        )
        conn.commit()
        conn.close()

        self.cog.bot.fetch_user = AsyncMock(side_effect=[
            SimpleNamespace(mention="<@1>"),
            SimpleNamespace(mention="<@2>"),
        ])
        self.cog.bot.get_channel = MagicMock(return_value=None)
        channel = MagicMock()
        channel.name = config.CHANNEL_REMINDERS
        channel.send = AsyncMock(side_effect=[RuntimeError("boom"), None])
        self.cog.bot.get_all_channels = MagicMock(return_value=[channel])

        await self.cog.check_reminders.coro(self.cog)

        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT user_id, sent FROM reminders ORDER BY reminder_id")
        rows = c.fetchall()
        conn.close()

        assert rows == [('1', 0), ('2', 1)]


class TestReminderCommands(TestReminderHelpers):
    async def test_remind_shows_usage(self):
        ctx = make_ctx()

        await self.cog.remind.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("Please follow this format: !remindme in X seconds/minutes/hours/days.")

    async def test_remindme_without_entries_reports_none(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")

        await self.cog.remindme.callback(self.cog, ctx, args=None)

        ctx.send.assert_awaited_once_with("<@123>, you have no reminders set.")

    async def test_remindme_lists_upcoming_and_past(self):
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        upcoming = (now + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        past = (now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        conn = self._connect()
        c = conn.cursor()
        c.executemany(
            "INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?,?,?,?,0)",
            [
                ('123', '1', upcoming, 'future reminder'),
                ('123', '1', past, 'past reminder'),
            ]
        )
        conn.commit()
        conn.close()

        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")

        await self.cog.remindme.callback(self.cog, ctx, args=None)

        assert ctx.send.await_count == 2
        assert "upcoming reminders" in ctx.send.await_args_list[0].args[0]
        assert "future reminder" in ctx.send.await_args_list[0].args[0]
        assert "past reminders" in ctx.send.await_args_list[1].args[0]
        assert "past reminder" in ctx.send.await_args_list[1].args[0]

    async def test_remindme_relative_time_creates_reminder_with_reply_link(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")
        ctx.guild = SimpleNamespace(id=555)
        ctx.channel = SimpleNamespace(id=777)
        ctx.message = SimpleNamespace(id=888, reference=SimpleNamespace(message_id=999))

        await self.cog.remindme.callback(self.cog, ctx, args="in 2 hours, 30 minutes")

        ctx.send.assert_awaited_once()
        sent = ctx.send.await_args.args[0]
        assert "reminder set for" in sent
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT message FROM reminders WHERE user_id='123'")
        stored = c.fetchone()[0]
        conn.close()
        assert stored == "Reminder! [Link](https://discord.com/channels/555/777/999)"

    async def test_remindme_invalid_time_unit_reports_error(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")
        ctx.guild = SimpleNamespace(id=555)
        ctx.channel = SimpleNamespace(id=777)
        ctx.message = SimpleNamespace(id=888, reference=None)

        await self.cog.remindme.callback(self.cog, ctx, args="in 3 fortnights")

        ctx.send.assert_awaited_once()
        assert "couldn't understand time unit" in ctx.send.await_args.args[0]

    async def test_deletereminder_deletes_owned_reminder(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO reminders (reminder_id, user_id, channel_id, reminder_time, message, sent) VALUES (?,?,?,?,?,0)",
            (7, '123', '1', '2099-01-01 00:00:00', 'owned reminder')
        )
        conn.commit()
        conn.close()

        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")

        await self.cog.deletereminder.callback(self.cog, ctx, 7)

        ctx.send.assert_awaited_once_with("<@123>, reminder `7` deleted!")

    async def test_deletereminder_reports_missing_reminder(self):
        ctx = make_ctx()
        ctx.author = SimpleNamespace(id=123, mention="<@123>")

        await self.cog.deletereminder.callback(self.cog, ctx, 404)

        ctx.send.assert_awaited_once_with("<@123>, no reminder found with ID `404`.")

    async def test_currenttime_returns_timestamp_string(self):
        ctx = make_ctx()

        await self.cog.currenttime.callback(self.cog, ctx)

        ctx.send.assert_awaited_once()
        assert ctx.send.await_args.args[0].count(":") == 2


class TestPersonas:
    def test_load_personas_sets_cute_as_default_when_present(self, tmp_path):
        from cogs.personas import Personas

        persona_file = tmp_path / "personas.json"
        conversation_file = tmp_path / "conversations.json"
        persona_file.write_text(json.dumps({"cute": "be nice", "mean": "be mean"}), encoding="utf-8")
        conversation_file.write_text("{}", encoding="utf-8")

        with patch("cogs.personas.PERSONA_FILE", str(persona_file)), patch("cogs.personas.CONVERSATION_FILE", str(conversation_file)):
            cog = Personas(MagicMock())

        assert cog.current_persona == "cute"
        assert cog.personas["cute"] == "be nice"

    def test_update_conversation_trims_history_to_last_ten_entries(self, tmp_path):
        from cogs.personas import Personas

        persona_file = tmp_path / "personas.json"
        conversation_file = tmp_path / "conversations.json"
        persona_file.write_text("{}", encoding="utf-8")
        conversation_file.write_text("{}", encoding="utf-8")

        with patch("cogs.personas.PERSONA_FILE", str(persona_file)), patch("cogs.personas.CONVERSATION_FILE", str(conversation_file)):
            cog = Personas(MagicMock())

        for index in range(6):
            cog.update_conversation("123", "cute", f"user {index}", f"bot {index}")

        history = cog.conversations["123"]["cute"]
        assert len(history) == 10
        assert history[0]["content"] == "user 1"
        assert history[-1]["content"] == "bot 5"


# ── mojibake scan ─────────────────────────────────────────────────────────────

class TestNoMojibake:
    def test_repo_has_no_mojibake(self):
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "scan_mojibake",
            pathlib.Path(__file__).resolve().parent.parent / "scripts" / "scan_mojibake.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        root = str(pathlib.Path(__file__).resolve().parent.parent)
        hits = mod.scan(root)
        assert hits == [], f"Mojibake found:\n" + "\n".join(
            f"  {p}:{ln} [{lbl}]: {snip}" for p, ln, lbl, snip in hits
        )


class TestRemoteCommonScript:
    def test_remote_copy_recursive_streams_tar_instead_of_scp(self, tmp_path):
        project_root = tmp_path / "project"
        scripts_dir = project_root / "scripts"
        scripts_dir.mkdir(parents=True)
        shutil.copyfile(
            Path(__file__).resolve().parent.parent / "scripts" / "remote-common.sh",
            scripts_dir / "remote-common.sh",
        )

        fakebin = tmp_path / "fakebin"
        fakebin.mkdir()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        def _write_tool(name: str, body: str):
            path = fakebin / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)

        _write_tool(
            "scp",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{logs_dir / 'scp.log'}"
exit 0
""",
        )
        _write_tool(
            "ssh",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{logs_dir / 'ssh.log'}"
cat >/dev/null
exit 0
""",
        )
        _write_tool(
            "tar",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{logs_dir / 'tar.log'}"
cat >/dev/null
exit 0
""",
        )
        _write_tool(
            "find",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{logs_dir / 'find.log'}"
printf './example.py\\0'
exit 0
""",
        )

        source_dir = tmp_path / "cogs"
        source_dir.mkdir()
        (source_dir / "example.py").write_text("print('ok')\n", encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        env["TINKI_EC2_HOST"] = "example-host"
        env["TINKI_EC2_USER"] = "deploy-user"
        env["TINKI_EC2_KEY_PATH"] = "/tmp/test-key.pem"

        script = f"""
set -euo pipefail
source "{scripts_dir / 'remote-common.sh'}"
remote_copy "{source_dir}" "/remote/repo/" true
"""
        subprocess.run(["bash", "-c", script], check=True, env=env, cwd=project_root)

        scp_log = (logs_dir / "scp.log")
        assert not scp_log.exists() or scp_log.read_text(encoding="utf-8").strip() == ""

        find_log = (logs_dir / "find.log").read_text(encoding="utf-8")
        assert find_log.startswith(". ")
        assert "-type f" in find_log
        assert "-type l" in find_log
        assert "__pycache__" in find_log
        assert ".pytest_cache" in find_log
        assert "._*" in find_log
        assert ".DS_Store" in find_log

        tar_log = (logs_dir / "tar.log").read_text(encoding="utf-8")
        assert f"-C {source_dir}" in tar_log
        assert "--format=ustar" in tar_log
        assert "--null -T -" in tar_log
        assert "-cf -" in tar_log

        ssh_log = (logs_dir / "ssh.log").read_text(encoding="utf-8")
        assert "deploy-user@example-host" in ssh_log
        assert "tar -xmf -" in ssh_log
        assert "--no-same-permissions" in ssh_log
        assert "--no-overwrite-dir" in ssh_log
        assert "-C /remote/repo/cogs" in ssh_log

    def test_remote_copy_file_keeps_using_scp(self, tmp_path):
        project_root = tmp_path / "project"
        scripts_dir = project_root / "scripts"
        scripts_dir.mkdir(parents=True)
        shutil.copyfile(
            Path(__file__).resolve().parent.parent / "scripts" / "remote-common.sh",
            scripts_dir / "remote-common.sh",
        )

        fakebin = tmp_path / "fakebin"
        fakebin.mkdir()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        for name in ("scp", "ssh"):
            body = f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{logs_dir / f'{name}.log'}"
exit 0
"""
            path = fakebin / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)

        source_file = tmp_path / "README.md"
        source_file.write_text("hello\n", encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        env["TINKI_EC2_HOST"] = "example-host"
        env["TINKI_EC2_USER"] = "deploy-user"
        env["TINKI_EC2_KEY_PATH"] = "/tmp/test-key.pem"

        script = f"""
set -euo pipefail
source "{scripts_dir / 'remote-common.sh'}"
remote_copy "{source_file}" "/remote/repo/"
"""
        subprocess.run(["bash", "-c", script], check=True, env=env, cwd=project_root)

        scp_log = (logs_dir / "scp.log").read_text(encoding="utf-8")
        assert str(source_file) in scp_log
        assert "deploy-user@example-host:/remote/repo/" in scp_log

        ssh_log = logs_dir / "ssh.log"
        assert not ssh_log.exists() or ssh_log.read_text(encoding="utf-8").strip() == ""
