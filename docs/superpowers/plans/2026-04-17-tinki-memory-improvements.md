# Tinki Memory Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Tinki's ability to remember user-provided facts and retrieve relevant past Discord messages cheaply when users ask memory-style questions.

**Architecture:** Extend the existing `ai_memory.json` fact/topic pipeline for stronger long-term recall, then add a lightweight on-demand Discord history retrieval path in `cogs/ai.py` for memory-oriented prompts. Keep retrieval bounded to recent accessible channel history with simple keyword scoring and explicit fallback when nothing relevant is found.

**Tech Stack:** Python, discord.py, existing `cogs/ai.py` AI flow, existing `utils/ai_brain.py` memory helpers, pytest

---

## File Structure

- Modify: `utils/ai_brain.py`
  - Expand memory intent detection and fact extraction so direct statements are captured more reliably.
  - Add reusable helpers for deciding when a message should trigger Discord history lookup.
- Modify: `cogs/ai.py`
  - Add on-demand channel history retrieval and ranking.
  - Feed retrieved history into prompt construction only for memory-style questions.
  - Preserve the current fast path for ordinary chat.
- Modify: `tests/test_tinki_bot.py`
  - Add failing tests first for improved fact extraction, memory-intent routing, and fallback behavior.
- Modify: `README.md`
  - Briefly document that Tinki can recall explicit user facts and search recent channel history on memory-style questions.

### Task 1: Strengthen memory-intent and fact extraction

**Files:**
- Modify: `utils/ai_brain.py`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_classify_intent_marks_memory_lookup_questions():
    assert classify_intent("didn't i tell you my main is hunter?") == "memory_lookup"


def test_extract_user_facts_captures_preference_style_statements():
    facts = extract_user_facts("my main is hunter and my favorite spec is marksman")
    assert any("main hunter" in fact.lower() for fact in facts)
    assert any("favorite spec marksman" in fact.lower() for fact in facts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'memory_lookup_questions or preference_style_statements' -q`
Expected: FAIL because `classify_intent` does not return `memory_lookup` and fact extraction misses one or both phrases.

- [ ] **Step 3: Write minimal implementation**

```python
# in utils/ai_brain.py
if any(token in lowered for token in (
    "remember", "didn't i tell you", "what did i say", "you remember", "what happened with",
)):
    return "memory_lookup"

FACT_PATTERNS = (
    ...,
    re.compile(r"\bmy main is ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bmy favorite ([a-z0-9 _-]{2,20}) is ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bi hate ([a-z0-9 ,_'/-]{2,60})", re.IGNORECASE),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'memory_lookup_questions or preference_style_statements' -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add utils/ai_brain.py tests/test_tinki_bot.py
git commit -m "Improve memory intent and fact extraction"
```

### Task 2: Add bounded Discord history lookup for memory questions

**Files:**
- Modify: `cogs/ai.py`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ai_uses_channel_history_for_memory_lookup_questions():
    cog = make_ai_cog()
    message = make_message("@bot what did I say about hunter last week?")
    message.guild = MagicMock(id=123)
    message.channel.history = MagicMock(return_value=_async_iter([
        SimpleNamespace(author=SimpleNamespace(bot=False, id=message.author.id), content="my main is hunter", created_at=datetime.now(timezone.utc)),
    ]))
    
    history = await cog._search_channel_history(message, "hunter")
    assert any("my main is hunter" in line for line in history)


async def test_ai_returns_empty_history_when_no_matches_found():
    cog = make_ai_cog()
    message = make_message("@bot what did I say about pizza?")
    message.guild = MagicMock(id=123)
    message.channel.history = MagicMock(return_value=_async_iter([]))

    history = await cog._search_channel_history(message, "pizza")
    assert history == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'channel_history_for_memory_lookup or empty_history_when_no_matches' -q`
Expected: FAIL because `_search_channel_history` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# in cogs/ai.py
async def _search_channel_history(self, message, query: str, limit: int = 4, scan_limit: int = 250):
    matches = []
    async for entry in message.channel.history(limit=scan_limit):
        if getattr(entry.author, "bot", False):
            continue
        score = score_overlap(query, getattr(entry, "content", ""))
        if score <= 0:
            continue
        stamp = getattr(entry, "created_at", None)
        matches.append((score, stamp, getattr(entry, "content", "")))
    matches.sort(key=lambda item: (-item[0], item[1] or 0), reverse=False)
    return [content for _, _, content in matches[:limit]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'channel_history_for_memory_lookup or empty_history_when_no_matches' -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cogs/ai.py tests/test_tinki_bot.py
git commit -m "Add bounded Discord history lookup for memory questions"
```

### Task 3: Thread memory lookup into reply generation safely

**Files:**
- Modify: `cogs/ai.py`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ai_prefers_history_context_for_memory_lookup_prompts():
    cog = make_ai_cog()
    with patch.object(cog, "_search_channel_history", new=AsyncMock(return_value=["my main is hunter"])):
        history = await cog._memory_lookup_context(make_message("what did i say about hunter"), "what did i say about hunter")
    assert history == ["my main is hunter"]


async def test_ai_memory_lookup_falls_back_cleanly_when_history_is_empty():
    cog = make_ai_cog()
    with patch.object(cog, "_search_channel_history", new=AsyncMock(return_value=[])):
        history = await cog._memory_lookup_context(make_message("remember my pizza order"), "remember my pizza order")
    assert history == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'prefers_history_context_for_memory_lookup or memory_lookup_falls_back_cleanly' -q`
Expected: FAIL because `_memory_lookup_context` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# in cogs/ai.py
async def _memory_lookup_context(self, message, text: str) -> List[str]:
    if classify_intent(text) != "memory_lookup":
        return []
    return await self._search_channel_history(message, text)

# in on_message mention path
history_context = self._relevant_history(history, text)
if intent == "memory_lookup":
    looked_up = await self._memory_lookup_context(message, text)
    if looked_up:
        history_context = looked_up + history_context[:2]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_tinki_bot.py -k 'prefers_history_context_for_memory_lookup or memory_lookup_falls_back_cleanly' -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cogs/ai.py tests/test_tinki_bot.py
git commit -m "Use Discord history for memory lookup prompts"
```

### Task 4: Document the new memory behavior and run regression verification

**Files:**
- Modify: `README.md`
- Test: `tests/test_tinki_bot.py`

- [ ] **Step 1: Update docs**

```md
### Personas And AI

- `@Tinki-bot <message>` - get a reply from Tinki
- Tinki keeps lightweight memory of direct facts and preferences.
- For memory-style questions, Tinki can search recent accessible channel history instead of guessing.
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 3: Review diff**

Run: `git diff -- cogs/ai.py utils/ai_brain.py tests/test_tinki_bot.py README.md`
Expected: only memory-related changes.

- [ ] **Step 4: Commit**

```bash
git add cogs/ai.py utils/ai_brain.py tests/test_tinki_bot.py README.md
git commit -m "Improve Tinki memory recall"
```

## Self-Review

- Spec coverage: covers stronger fact extraction, memory-intent detection, bounded Discord history lookup, safe fallback, and docs.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: plan uses `memory_lookup` intent, `_search_channel_history`, and `_memory_lookup_context` consistently.
