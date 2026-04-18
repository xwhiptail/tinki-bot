# Cute Snarky Gnome Identity Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Tinki explicitly framed as a cute but snarky gnome by removing goblin/gremlin drift from prompts, user-facing copy, and live persisted identity text.

**Architecture:** Make the repo change in two tight code slices: first update the visible copy and exact tests, then refine the core prompt text while preserving the existing short, teasing style. After the repo is green and deployed, patch the two live JSON files on the host in place so saved history and the `cute` persona stop reintroducing the old wording.

**Tech Stack:** Python 3.11/3.14, discord.py cogs, pytest, JSON persistence, checked-in SSH deploy helpers

---

### Task 1: Update the visible gnome/gremlin strings and exact tests

**Files:**
- Modify: `cogs/uma.py:360-366`
- Modify: `tests/test_tinki_bot.py:2345-2352`
- Modify: `README.md:11`
- Modify: `README.md:290`
- Modify: `CLAUDE.md:88`

- [ ] **Step 1: Write the failing exact-string test for the UMA fallback**

Replace the existing UMA fallback assertion with the new exact line:

```python
    async def test_umagif_sends_fallback_when_giphy_empty(self):
        ctx = make_ctx()

        with patch.object(self.cog, "_gif", new=AsyncMock(return_value=None)):
            await self.cog.uma_gif_cmd.callback(self.cog, ctx)

        ctx.send.assert_awaited_once_with("Giphy came up empty. The gnome is annoyed.")
```

- [ ] **Step 2: Run the narrow test to verify it fails**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestUmaCommands::test_umagif_sends_fallback_when_giphy_empty -v`

Expected: FAIL because `cogs/uma.py` still sends `The gremlin is disappointed.`

- [ ] **Step 3: Implement the minimal copy updates**

Apply these exact repo text changes:

```python
# cogs/uma.py
        else:
            await ctx.send('Giphy came up empty. The gnome is annoyed.')
```

```md
# README.md
Discord bot for server utilities, memes, reminders, emotes, OpenAI-powered cute-snarky gnome replies, and Uma Musume gacha.
...
Tinki responds when mentioned (`@Tinki-bot`). She has a cute but snarky gnome personality powered by OpenAI. Math questions and letter-count questions are answered deterministically first, then wrapped with GPT flavor.
```

```md
# CLAUDE.md
- Personality: `GREMLIN_SYSTEM_STYLE` constant in `config.py` - cute but snarky gnome energy, short replies, no therapy talk.
```

- [ ] **Step 4: Run the narrow test to verify it passes**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestUmaCommands::test_umagif_sends_fallback_when_giphy_empty -v`

Expected: PASS

- [ ] **Step 5: Commit the visible copy slice**

```bash
git add cogs/uma.py tests/test_tinki_bot.py README.md CLAUDE.md
git commit -m "fix: remove gremlin wording from visible gnome copy"
```

### Task 2: Tighten the core AI prompt wording without changing behavior shape

**Files:**
- Modify: `config.py:54-71`
- Modify: `cogs/ai.py:191-207`
- Modify: `cogs/ai.py:248-254`

- [ ] **Step 1: Add a failing focused test for the system style text**

Add this test near the other config/prompt helpers:

```python
    def test_gremlin_system_style_keeps_gnome_identity_without_gremlin_words(self):
        assert "cute but snarky gnome" in config.GREMLIN_SYSTEM_STYLE
        assert "gremlin" not in config.GREMLIN_SYSTEM_STYLE.lower()
        assert "goblin" not in config.GREMLIN_SYSTEM_STYLE.lower()
```

- [ ] **Step 2: Run that single test to verify it fails**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestAIBrain::test_gremlin_system_style_keeps_gnome_identity_without_gremlin_words -v`

Expected: FAIL because the prompt text still contains `GREMLIN_SYSTEM_STYLE` content that does not include the new identity wording

- [ ] **Step 3: Update the prompt strings minimally**

Replace the text content, but keep the constant name for this pass:

```python
# config.py
GREMLIN_SYSTEM_STYLE = (
    "You are Tinki, a cute but snarky gnome Hunter from Azeroth (World of Warcraft) who moonlights as a Discord bot. "
    "You are tiny, scrappy, and dangerously skilled with engineering gadgets and a bow. "
    "You speak with the cheerful confidence of someone who has survived every raid wipe and still insists "
    "their explosive trap build is completely fine. "
    "You love tinkering, breaking things, and occasionally setting yourself on fire by accident (>w<). "
    "Sprinkle in cute Japanese-style emotes naturally when the vibe calls for it "
    "(>w<, uwu, ('oДo'), ('･ω･`), (ʔ•ᗜ•ʔ), (っ˘ω˘ς), o(〃＾▽＾〃)o, etc.) "
    "— not every sentence, just when it lands. "
    "Keep replies short (1–3 sentences). "
    "Be playful and teasing — roast people like a friend who also carries the whole party. "
    "Do NOT be cringe-wholesome, give therapy talk, safety PSAs, or say things like "
    "'it's important to talk to someone'. "
    "No slurs, no bigotry, no attacks on real-world trauma, health issues, or protected traits "
    "(race, gender, sexuality, religion, etc.). "
    "Banter should feel like trash talk between guildmates, not genuine harassment."
)
```

```python
# cogs/ai.py
"Could be a hot take about Azeroth, a tinkering disaster, a Hunter complaint, "
"a roast of gamers, or pure tiny-engineer chaos. "
...
{"role": "user", "content": "Give me one snarky gnome hunter thought."},
...
"Make it sound like a sharp-tongued gnome roasting their take. 1-2 sentences. No serious advice."
```

- [ ] **Step 4: Run the focused prompt test to verify it passes**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestAIBrain::test_gremlin_system_style_keeps_gnome_identity_without_gremlin_words -v`

Expected: PASS

- [ ] **Step 5: Run the related shared slice**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestUmaCommands::test_umagif_sends_fallback_when_giphy_empty tests/test_tinki_bot.py::TestAIHardStopRefusals -v`

Expected: PASS

- [ ] **Step 6: Commit the prompt cleanup**

```bash
git add config.py cogs/ai.py tests/test_tinki_bot.py
git commit -m "fix: keep tinki identity explicitly gnome"
```

### Task 3: Update persona-loading expectations and deploy-facing docs

**Files:**
- Modify: `tests/test_tinki_bot.py:3118-3131`
- Modify: `docs/command-test-map.md` only if command-path coverage text changes are needed

- [ ] **Step 1: Add or update the persona loader test fixture content**

Use a gnome-consistent `cute` persona in the existing loader test:

```python
        persona_file.write_text(json.dumps({
            "cute": "cute but snarky gnome engineer"
        }), encoding="utf-8")
```

Keep the exact assertion aligned with the new value:

```python
        assert cog.personas["cute"] == "cute but snarky gnome engineer"
```

- [ ] **Step 2: Run the persona-focused test to verify it passes**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest tests/test_tinki_bot.py::TestPersonas::test_load_personas_sets_cute_as_default_when_present -v`

Expected: PASS

- [ ] **Step 3: Commit the persona/test cleanup if it changed**

```bash
git add tests/test_tinki_bot.py
git commit -m "test: align cute persona with gnome identity"
```

### Task 4: Full local verification and mojibake scan

**Files:**
- Modify: `config.py`
- Modify: `cogs/ai.py`
- Modify: `cogs/uma.py`
- Modify: `tests/test_tinki_bot.py`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full local suite**

Run: `/Users/matthew/Developers/tinki-bot/.venv/bin/python -m pytest -q`

Expected: PASS

- [ ] **Step 2: Scan edited files for mojibake regressions**

Run: `rg -n "â|ðŸ|âœ|â†|�" config.py cogs/ai.py cogs/uma.py tests/test_tinki_bot.py README.md CLAUDE.md`

Expected: no new output beyond intentional reference examples already present in docs

- [ ] **Step 3: Review the final diff**

Run: `git diff -- config.py cogs/ai.py cogs/uma.py tests/test_tinki_bot.py README.md CLAUDE.md`

Expected: only identity wording changes plus exact-string test updates

- [ ] **Step 4: Commit the verified repo state if needed**

```bash
git add config.py cogs/ai.py cogs/uma.py tests/test_tinki_bot.py README.md CLAUDE.md
git commit -m "docs: verify cute snarky gnome identity cleanup"
```

### Task 5: Deploy and patch the live persisted identity data

**Files:**
- Modify on host: `/opt/apps/tinki-bot/data/personas.json`
- Modify on host: `/opt/apps/tinki-bot/data/conversations.json`
- Verify on host: `/opt/apps/tinki-bot/repo/.deploy-commit`

- [ ] **Step 1: Deploy the updated repo to the host**

Run: `./deploy-ec2.sh`

Expected: service restart output with the new commit shown as deployed

- [ ] **Step 2: Patch the live `cute` persona in place**

Run this exact remote edit:

```bash
bash -lc 'source scripts/remote-common.sh; remote_bash <<'"'"'EOF'"'"'
python3 - <<'"'"'PY'"'"'
from pathlib import Path
import json
path = Path("/opt/apps/tinki-bot/data/personas.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["cute"] = "You are a cute but snarky gnome engineer from the World of Warcraft universe. You are happy to help with any question, but you tease people like a guildmate while doing it. You often add Japanese ASCII emojis when they fit."
path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
PY
EOF'
```

- [ ] **Step 3: Patch the saved `tiny goblin` conversation line in place**

Run this exact remote edit:

```bash
bash -lc 'source scripts/remote-common.sh; remote_bash <<'"'"'EOF'"'"'
python3 - <<'"'"'PY'"'"'
from pathlib import Path
import json
path = Path("/opt/apps/tinki-bot/data/conversations.json")
data = json.loads(path.read_text(encoding="utf-8"))
for user_convos in data.values():
    for history in user_convos.values():
        for entry in history:
            if entry.get("role") == "assistant" and "tiny goblin blush" in entry.get("content", ""):
                entry["content"] = "Aww, you’re making this tiny gnome blush o(〃＾▽＾〃)o I love you too—now quit standing there and help me loot the good stuff, yeah?"
path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
PY
EOF'
```

- [ ] **Step 4: Verify the live data edits landed**

Run:

```bash
bash -lc 'source scripts/remote-common.sh; remote_bash <<'"'"'EOF'"'"'
grep -n "tiny gnome blush" /opt/apps/tinki-bot/data/conversations.json
grep -n "cute but snarky gnome engineer" /opt/apps/tinki-bot/data/personas.json
EOF'
```

Expected: both `grep` commands print one matching line

- [ ] **Step 5: Run remote pytest after deploy**

Run: `./scripts/run-remote-pytest.sh`

Expected: PASS on the host

- [ ] **Step 6: Commit any repo-side follow-up only if the deployment verification required a repo change**

```bash
git add .
git commit -m "fix: finalize live gnome identity cleanup"
```
