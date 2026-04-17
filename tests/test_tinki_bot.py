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

# ── helpers ──────────────────────────────────────────────────────────────────

def make_ctx():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    return ctx


def make_message(content):
    message = MagicMock()
    message.content = content
    message.author = MagicMock()
    message.author.bot = False
    message.channel = MagicMock()
    message.channel.send = AsyncMock()
    return message


def make_reaction(message, emoji):
    reaction = MagicMock()
    reaction.message = message
    reaction.emoji = emoji
    return reaction


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

    def test_classify_intent_detects_general_question(self):
        assert classify_intent("why is gold ship so cursed?") == "question_answer"

    def test_extract_user_facts_finds_simple_profile_facts(self):
        facts = extract_user_facts("my name is Matt and I like WoW")
        assert "Matt" in facts[0]
        assert any("WoW" in fact for fact in facts)

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
