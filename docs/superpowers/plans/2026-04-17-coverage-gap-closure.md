# Coverage Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the highest-value automated test coverage gaps in the Discord bot without changing intended runtime behavior.

**Architecture:** Extend the existing pytest suite in focused batches and introduce only minimal production seams when a branch cannot be exercised cleanly in tests. Keep all behavior-preserving refactors narrow and local to the affected module so the bot remains operationally identical while becoming easier to validate.

**Tech Stack:** Python 3, pytest, pytest-asyncio, discord.py mocks, unittest.mock

---

### Task 1: Entrypoint and URL/Admin Coverage

**Files:**
- Modify: `tests/test_tinki_bot.py`
- Modify: `tinki-bot.py`
- Test: `tests/test_tinki_bot.py`

- [ ] Add failing tests for the entrypoint event handlers and command suggestion behavior.
- [ ] Run only the new entrypoint tests and confirm they fail for the expected missing seam or uncovered behavior.
- [ ] Add the smallest import-safe seam in `tinki-bot.py` needed to test the module without auto-running the bot.
- [ ] Add failing tests for social rewrite deletion and Twitch clip retry behavior in `URLFilter`.
- [ ] Run the URL filter slice and confirm the new tests fail first, then pass after minimal fixes if needed.
- [ ] Add failing tests for admin pytest/deploy retry and failure branches, then implement only the minimal changes needed for stable assertions.

### Task 2: AI Flow Coverage

**Files:**
- Modify: `tests/test_tinki_bot.py`
- Modify: `cogs/ai.py`
- Modify: `utils/openai_helpers.py`
- Test: `tests/test_tinki_bot.py`

- [ ] Add failing tests for reply chunking, mention stripping, mention-empty no-op, exception fallback, reply-to-random-message, and raw reaction branches.
- [ ] Run the focused AI test slice and verify the failures are real behavior gaps, not test harness mistakes.
- [ ] Add the smallest production changes needed to preserve behavior while making these async flows deterministic under test.
- [ ] Add helper tests for `gpt_wrap_fact` and any AI fallback branch touched by the new scenarios.

### Task 3: Commands, Listeners, and Helper Branches

**Files:**
- Modify: `tests/test_tinki_bot.py`
- Modify: `cogs/reminders.py`
- Modify: `cogs/utility.py`
- Modify: `cogs/bowling.py`
- Modify: `cogs/tracking.py`
- Modify: `cogs/personas.py`
- Modify: `utils/aws_costs.py`
- Test: `tests/test_tinki_bot.py`

- [ ] Add failing tests for reminder parsing/listing/deletion/current-time flows and only then patch production code if a seam is missing.
- [ ] Add failing tests for utility command success/error branches and the 📌 forwarding listener.
- [ ] Add failing tests for bowling live ingestion, add/delete/all-scores chunking, and graph command behavior.
- [ ] Add failing tests for tracking listener persistence and count/graph command outputs.
- [ ] Add failing tests for persona load/save/history truncation and AWS helper branch formatting.

### Task 4: Verification

**Files:**
- Modify: `tests/test_tinki_bot.py`

- [ ] Run focused pytest slices after each batch and fix any regressions before moving on.
- [ ] Run `python3 -m pytest -q` and confirm the full suite is green.
- [ ] Review the diff to confirm changes stayed focused on coverage closure and testability seams.
