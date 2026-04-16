"""
Pytest suite for pure functions and isolated command helpers in tinki-bot.

Install test deps (once):
    pip install pytest pytest-asyncio

Run:
    pytest
"""
import sys
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.url_rewriter import rewrite_social_urls
from utils.calculator import maybe_calculate_reply
from utils.letter_counter import maybe_count_letter_reply
import config

# ── helpers ──────────────────────────────────────────────────────────────────

def make_ctx():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    return ctx


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


# ── score commands ────────────────────────────────────────────────────────────

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


# ── persona commands ──────────────────────────────────────────────────────────

class TestPersonaCommands:
    def setup_method(self):
        self.cog = make_personas_cog()

    async def test_create_persona_stores_it(self):
        ctx = make_ctx()
        with patch.object(self.cog, "save_personas"):
            await self.cog.create_persona(ctx, "pirate", persona_description="talks like a pirate")
        assert self.cog.personas.get("pirate") == "talks like a pirate"

    async def test_create_persona_confirms_in_message(self):
        ctx = make_ctx()
        with patch.object(self.cog, "save_personas"):
            await self.cog.create_persona(ctx, "robot", persona_description="beep boop")
        assert "robot" in ctx.send.call_args[0][0]

    async def test_switch_to_existing_persona(self):
        self.cog.personas["pirate"] = "arr"
        ctx = make_ctx()
        await self.cog.switch_persona(ctx, "pirate")
        assert self.cog.current_persona == "pirate"
        ctx.send.assert_awaited_once()

    async def test_switch_to_missing_persona(self):
        ctx = make_ctx()
        await self.cog.switch_persona(ctx, "ghost")
        assert "not found" in ctx.send.call_args[0][0].lower()
        assert self.cog.current_persona is None

    async def test_list_personas_when_empty(self):
        ctx = make_ctx()
        await self.cog.list_personas(ctx)
        assert "No personas" in ctx.send.call_args[0][0]

    async def test_list_personas_shows_all_names(self):
        self.cog.personas["pirate"] = "arr"
        self.cog.personas["robot"] = "beep"
        ctx = make_ctx()
        await self.cog.list_personas(ctx)
        msg = ctx.send.call_args[0][0]
        assert "pirate" in msg and "robot" in msg

    async def test_current_persona_when_none_active(self):
        ctx = make_ctx()
        await self.cog.current_persona_cmd(ctx)
        assert "No specific persona" in ctx.send.call_args[0][0]

    async def test_current_persona_shows_active_name(self):
        self.cog.personas["pirate"] = "arr"
        self.cog.current_persona = "pirate"
        ctx = make_ctx()
        await self.cog.current_persona_cmd(ctx)
        assert "pirate" in ctx.send.call_args[0][0]


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
