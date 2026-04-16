"""
Pytest suite for pure functions and isolated command helpers in tinki-bot.

Install test deps (once):
    pip install pytest pytest-asyncio

Run:
    pytest
"""
import importlib.util
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── load module (hyphen in filename prevents normal import) ──────────────────

def _load_bot():
    import discord.ext.commands
    # Prevent bot.run(TOKEN) at module bottom from actually connecting
    discord.ext.commands.Bot.run = lambda *a, **kw: None

    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tinki-bot.py"))
    spec = importlib.util.spec_from_file_location("tinki_bot", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tinki_bot"] = mod
    spec.loader.exec_module(mod)
    return mod

tb = _load_bot()

# ── helpers ──────────────────────────────────────────────────────────────────

def make_ctx():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    return ctx


# ── rewrite_social_urls ──────────────────────────────────────────────────────

class TestRewriteSocialUrls:
    def test_twitter_rewritten_to_vxtwitter(self):
        out = tb.rewrite_social_urls("https://twitter.com/foo/status/123")
        assert "vxtwitter.com/foo/status/123" in out
        assert "//twitter.com" not in out

    def test_twitter_preserves_user_and_status(self):
        out = tb.rewrite_social_urls("https://www.twitter.com/alice/status/999")
        assert "alice" in out
        assert "999" in out

    def test_x_com_rewritten_to_fixvx(self):
        out = tb.rewrite_social_urls("https://x.com/user/status/1")
        assert "fixvx.com" in out
        assert "//x.com" not in out

    def test_instagram_rewritten_to_eeinstagram(self):
        out = tb.rewrite_social_urls("https://www.instagram.com/p/abc123/")
        assert "eeinstagram.com" in out
        assert "//www.instagram.com" not in out

    def test_tiktok_rewritten_to_tnktok(self):
        out = tb.rewrite_social_urls("https://www.tiktok.com/@user/video/1")
        assert "tnktok.com" in out
        assert "tiktok.com" not in out

    def test_reddit_rewritten_to_rxddit(self):
        out = tb.rewrite_social_urls("https://www.reddit.com/r/python/comments/abc/")
        assert "rxddit.com" in out
        assert "reddit.com" not in out

    def test_github_url_unchanged(self):
        msg = "see https://github.com/some/repo for details"
        assert tb.rewrite_social_urls(msg) == msg

    def test_plain_text_unchanged(self):
        msg = "no links here at all"
        assert tb.rewrite_social_urls(msg) == msg

    def test_surrounding_text_preserved(self):
        out = tb.rewrite_social_urls("hey https://twitter.com/x/status/1 lol")
        assert out.startswith("hey ")
        assert out.endswith(" lol")

    def test_multiple_social_urls_in_one_message(self):
        msg = "https://twitter.com/a/status/1 and https://instagram.com/p/2/"
        out = tb.rewrite_social_urls(msg)
        assert "vxtwitter.com" in out
        assert "eeinstagram.com" in out
        assert "//twitter.com" not in out
        assert "//www.instagram.com" not in out


# ── maybe_calculate_reply ────────────────────────────────────────────────────

class TestMaybeCalculateReply:
    def test_bare_addition(self):
        r = tb.maybe_calculate_reply("2 + 2")
        assert r is not None and "4" in r

    def test_what_is_prefix_stripped(self):
        r = tb.maybe_calculate_reply("what is 10 + 5")
        assert r is not None and "15" in r

    def test_whats_prefix_stripped(self):
        r = tb.maybe_calculate_reply("what's 3 + 3")
        assert r is not None and "6" in r

    def test_calculate_prefix_stripped(self):
        r = tb.maybe_calculate_reply("calculate 3 * 7")
        assert r is not None and "21" in r

    def test_x_as_multiplication(self):
        r = tb.maybe_calculate_reply("3x4")
        assert r is not None and "12" in r

    def test_subtraction(self):
        r = tb.maybe_calculate_reply("100 - 37")
        assert r is not None and "63" in r

    def test_float_division(self):
        r = tb.maybe_calculate_reply("10 / 4")
        assert r is not None and "2.5" in r

    def test_large_number_comma_formatted(self):
        r = tb.maybe_calculate_reply("1000000 + 1")
        assert r is not None and "1,000,001" in r

    def test_trailing_question_mark_ok(self):
        r = tb.maybe_calculate_reply("5 + 5?")
        assert r is not None and "10" in r

    def test_plain_text_returns_none(self):
        assert tb.maybe_calculate_reply("hello world") is None

    def test_words_with_digits_returns_none(self):
        assert tb.maybe_calculate_reply("give me 5 reasons") is None

    def test_division_by_zero_returns_none(self):
        assert tb.maybe_calculate_reply("5 / 0") is None

    def test_result_has_gnome_flavour(self):
        r = tb.maybe_calculate_reply("1 + 1")
        assert r is not None and "gnome" in r.lower()


# ── maybe_count_letter_reply ─────────────────────────────────────────────────

class TestMaybeCountLetterReply:
    def test_count_r_in_strawberry(self):
        r = tb.maybe_count_letter_reply("how many r's in strawberry")
        assert r is not None and "3" in r

    def test_count_s_in_mississippi(self):
        r = tb.maybe_count_letter_reply("how many s's in mississippi")
        assert r is not None and "4" in r

    def test_singular_time_when_count_is_one(self):
        r = tb.maybe_count_letter_reply("how many b's in cob")
        assert r is not None
        assert " time" in r and "times" not in r

    def test_plural_times_when_count_gt_one(self):
        r = tb.maybe_count_letter_reply("how many l's in hello")
        assert r is not None and "times" in r

    def test_zero_occurrences(self):
        r = tb.maybe_count_letter_reply("how many z's in apple")
        assert r is not None and "0" in r

    def test_trailing_question_mark_stripped(self):
        r = tb.maybe_count_letter_reply("how many e's in cheese?")
        assert r is not None and "3" in r

    def test_unrelated_message_returns_none(self):
        assert tb.maybe_count_letter_reply("what time is it") is None

    def test_no_match_returns_none(self):
        assert tb.maybe_count_letter_reply("tell me something") is None

    def test_result_has_gnome_flavour(self):
        r = tb.maybe_count_letter_reply("how many t's in butter")
        assert r is not None and "gnome" in r.lower()

    def test_with_the_word_phrasing(self):
        r = tb.maybe_count_letter_reply("how many letter e's in the word sleep")
        assert r is not None and "2" in r


# ── score commands ────────────────────────────────────────────────────────────

class TestScoreCommands:
    def setup_method(self):
        tb.scores.clear()

    async def test_pb_empty_scores(self):
        ctx = make_ctx()
        await tb.personal_best.callback(ctx)
        ctx.send.assert_awaited_once()
        assert "No scores" in ctx.send.call_args[0][0]

    async def test_pb_returns_max(self):
        tb.scores[:] = [(10, "a"), (50, "b"), (30, "c")]
        ctx = make_ctx()
        await tb.personal_best.callback(ctx)
        assert "50" in ctx.send.call_args[0][0]

    async def test_avg_empty_scores(self):
        ctx = make_ctx()
        await tb.average_score.callback(ctx)
        assert "No scores" in ctx.send.call_args[0][0]

    async def test_avg_correct_value(self):
        tb.scores[:] = [(10, "a"), (20, "b"), (30, "c")]
        ctx = make_ctx()
        await tb.average_score.callback(ctx)
        assert "20.00" in ctx.send.call_args[0][0]

    async def test_median_odd_list(self):
        tb.scores[:] = [(10, "a"), (30, "b"), (20, "c")]
        ctx = make_ctx()
        await tb.median_score.callback(ctx)
        assert "20" in ctx.send.call_args[0][0]

    async def test_median_even_list(self):
        tb.scores[:] = [(10, "a"), (20, "b"), (30, "c"), (40, "d")]
        ctx = make_ctx()
        await tb.median_score.callback(ctx)
        assert "25" in ctx.send.call_args[0][0]

    async def test_median_empty_scores(self):
        ctx = make_ctx()
        await tb.median_score.callback(ctx)
        assert "No scores" in ctx.send.call_args[0][0]


# ── persona commands ──────────────────────────────────────────────────────────

class TestPersonaCommands:
    def setup_method(self):
        tb.personas.clear()
        tb.current_persona = None

    async def test_create_persona_stores_it(self):
        ctx = make_ctx()
        with patch.object(tb, "save_personas"):
            await tb.create_persona.callback(ctx, "pirate", persona_description="talks like a pirate")
        assert tb.personas.get("pirate") == "talks like a pirate"

    async def test_create_persona_confirms_in_message(self):
        ctx = make_ctx()
        with patch.object(tb, "save_personas"):
            await tb.create_persona.callback(ctx, "robot", persona_description="beep boop")
        assert "robot" in ctx.send.call_args[0][0]

    async def test_switch_to_existing_persona(self):
        tb.personas["pirate"] = "arr"
        ctx = make_ctx()
        await tb.switch_persona.callback(ctx, "pirate")
        assert tb.current_persona == "pirate"
        ctx.send.assert_awaited_once()

    async def test_switch_to_missing_persona(self):
        ctx = make_ctx()
        await tb.switch_persona.callback(ctx, "ghost")
        assert "not found" in ctx.send.call_args[0][0].lower()
        assert tb.current_persona is None

    async def test_list_personas_when_empty(self):
        ctx = make_ctx()
        await tb.list_personas.callback(ctx)
        assert "No personas" in ctx.send.call_args[0][0]

    async def test_list_personas_shows_all_names(self):
        tb.personas["pirate"] = "arr"
        tb.personas["robot"] = "beep"
        ctx = make_ctx()
        await tb.list_personas.callback(ctx)
        msg = ctx.send.call_args[0][0]
        assert "pirate" in msg and "robot" in msg

    async def test_current_persona_when_none_active(self):
        ctx = make_ctx()
        await tb.current_persona_cmd.callback(ctx)
        assert "No specific persona" in ctx.send.call_args[0][0]

    async def test_current_persona_shows_active_name(self):
        tb.personas["pirate"] = "arr"
        tb.current_persona = "pirate"
        ctx = make_ctx()
        await tb.current_persona_cmd.callback(ctx)
        assert "pirate" in ctx.send.call_args[0][0]
