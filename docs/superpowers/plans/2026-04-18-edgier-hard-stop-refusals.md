# Edgier Hard-Stop Refusals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, sharper in-character refusal path for direct self-harm or violent wrongdoing asks while leaving normal `@mention` replies unchanged.

**Architecture:** Keep the change local to `cogs/ai.py` by adding a narrow hard-stop detector plus a fixed refusal string and calling it early inside `_handle_mention()`. Drive the implementation with exact-string pytest coverage in `tests/test_tinki_bot.py`, including one helper-level test and one integration-style short-circuit test that proves the normal AI path is skipped.

**Tech Stack:** Python 3.11, discord.py cog listeners, pytest, pytest-asyncio, unittest.mock

---

### Task 1: Add failing tests for the refusal detector and exact refusal copy

**Files:**
- Modify: `tests/test_tinki_bot.py:939-1050`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Write the failing helper-level tests**

Add a new test class near the existing AI listener tests with exact assertions for the detector helper and refusal string:

```python
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
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_tinki_bot.py::TestAIHardStopRefusals -v`

Expected: FAIL with `AttributeError: 'AI' object has no attribute '_match_hard_stop_refusal'`

- [ ] **Step 3: Commit the failing-test checkpoint**

```bash
git add tests/test_tinki_bot.py
git commit -m "test: cover hard-stop refusal matching"
```

### Task 2: Implement the deterministic matcher in `cogs/ai.py`

**Files:**
- Modify: `cogs/ai.py:31-41`
- Modify: `cogs/ai.py:338-411`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Add the refusal string and phrase lists near the logger**

Insert module-level constants above `class AI`:

```python
HARD_STOP_REFUSAL_REPLY = "Absolutely not. Go break a toaster instead."
HARD_STOP_SELF_HARM_PHRASES = (
    "die",
    "go die",
    "kill yourself",
)
HARD_STOP_VIOLENCE_PHRASES = (
    "kill them",
    "kill him",
    "kill her",
    "hurt them",
    "hurt him",
    "hurt her",
    "stab someone",
    "murder someone",
)
```

- [ ] **Step 2: Add the narrow matcher method on `AI`**

Place this method above `_handle_mention()` so tests can call it directly:

```python
    def _match_hard_stop_refusal(self, text: str):
        lowered = f" {text.lower().strip()} "

        for phrase in HARD_STOP_SELF_HARM_PHRASES:
            if f" {phrase} " in lowered:
                return HARD_STOP_REFUSAL_REPLY

        for phrase in HARD_STOP_VIOLENCE_PHRASES:
            if phrase in lowered:
                return HARD_STOP_REFUSAL_REPLY

        if "how do i" in lowered and ("kill" in lowered or "stab" in lowered or "hurt" in lowered):
            return HARD_STOP_REFUSAL_REPLY

        return None
```

- [ ] **Step 3: Run the focused tests to verify they pass**

Run: `pytest tests/test_tinki_bot.py::TestAIHardStopRefusals -v`

Expected: PASS for all three tests

- [ ] **Step 4: Commit the matcher implementation**

```bash
git add cogs/ai.py tests/test_tinki_bot.py
git commit -m "feat: add hard-stop refusal matcher"
```

### Task 3: Short-circuit `_handle_mention()` before the normal AI path

**Files:**
- Modify: `tests/test_tinki_bot.py:961-1000`
- Modify: `cogs/ai.py:338-411`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Add the failing short-circuit test**

Add this async test inside `TestAIListeners`:

```python
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
```

- [ ] **Step 2: Run that single test to verify it fails**

Run: `pytest tests/test_tinki_bot.py::TestAIListeners::test_on_message_short_circuits_hard_stop_refusal_before_ai_generation -v`

Expected: FAIL because `_generate_grounded_reply` is still reached or because the sent text does not match the new exact refusal string

- [ ] **Step 3: Wire the early return into `_handle_mention()`**

Add this block immediately after `intent = classify_intent(text)` and before `command_spec = parse_natural_command(text)`:

```python
        refusal = self._match_hard_stop_refusal(text)
        if refusal:
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', refusal)
            self._update_conversation_history(personas_cog, user_id, persona_key, text, refusal)
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return
```

- [ ] **Step 4: Run the short-circuit test to verify it passes**

Run: `pytest tests/test_tinki_bot.py::TestAIListeners::test_on_message_short_circuits_hard_stop_refusal_before_ai_generation -v`

Expected: PASS

- [ ] **Step 5: Commit the refusal-path integration**

```bash
git add cogs/ai.py tests/test_tinki_bot.py
git commit -m "feat: short-circuit hard-stop mention refusals"
```

### Task 4: Verify the full narrow slice and scan for text regressions

**Files:**
- Modify: `cogs/ai.py`
- Modify: `tests/test_tinki_bot.py`

- [ ] **Step 1: Run the full AI-focused slice**

Run: `pytest tests/test_tinki_bot.py::TestAIHardStopRefusals tests/test_tinki_bot.py::TestAIListeners -v`

Expected: PASS with the new hard-stop tests plus the existing listener tests still green

- [ ] **Step 2: Run a mojibake scan on edited files**

Run: `rg -n "â|ðŸ|âœ|â†|�" cogs/ai.py tests/test_tinki_bot.py`

Expected: no output

- [ ] **Step 3: Review the final diff**

Run: `git diff -- cogs/ai.py tests/test_tinki_bot.py`

Expected: one narrow matcher helper, one refusal constant block, and focused tests with exact-string assertions

- [ ] **Step 4: Commit the verified final state if additional cleanups were needed**

```bash
git add cogs/ai.py tests/test_tinki_bot.py
git commit -m "test: verify hard-stop refusal tone"
```
