# Cute Snarky Gnome Identity Cleanup Design

Date: 2026-04-18

## Goal

Keep Tinki's identity anchored as a cute but snarky gnome while removing prompt and persisted-data drift that makes her describe herself as a goblin or otherwise lean into a gremlin persona.

## Scope

In scope:

- Update runtime prompt text that currently pushes goblin-adjacent or gremlin wording.
- Update persisted server data that can feed old identity text back into replies.
- Keep Tinki short, teasing, cute, and explicitly gnome-coded.
- Add or update exact-string pytest coverage for any changed user-facing strings.

Out of scope:

- Rewriting Tinki's overall personality from scratch.
- Changing command structure or deploy flow.
- Purging all conversation history.
- Editing unrelated docs beyond identity wording that directly describes the bot.

## Current Findings

Live host findings:

- `/opt/apps/tinki-bot/data/conversations.json` contains a saved assistant line with `tiny goblin`.
- `/opt/apps/tinki-bot/data/personas.json` contains a `cute` persona that describes Tinki as a female gnome.
- `/opt/apps/tinki-bot/repo/config.py` anchors Tinki as a gnome, but the surrounding style name and wording still use `GREMLIN_SYSTEM_STYLE`.
- `/opt/apps/tinki-bot/repo/cogs/ai.py` includes prompt text such as `pure chaotic gnome energy` and `feral gnome`.
- `/opt/apps/tinki-bot/repo/cogs/uma.py` has a user-facing fallback line: `The gremlin is disappointed.`

The strongest source of literal `goblin` replies is the saved conversation history because that history is re-used during AI responses.

## Recommended Approach

Use a targeted identity cleanup:

1. Keep Tinki explicitly gnome.
2. Replace literal `goblin` and `gremlin` drift in prompts and user-facing copy.
3. Patch the specific persisted identity text in live data instead of wiping history wholesale.

This is safer than a broad personality rewrite and more effective than prompt-only cleanup because it handles both code and live memory.

## Code Changes

### Prompt And Reply Text

Update prompt text in:

- `config.py`
- `cogs/ai.py`
- `cogs/uma.py`

Guidelines:

- Keep `cute`, `snarky`, `short`, and `guildmate roast` behavior.
- Preserve `gnome` identity.
- Remove `goblin`, `gremlin`, and overly feral framing.
- Prefer wording like `cute but snarky gnome`, `tiny engineer menace`, or `gnome hunter` over goblin-adjacent terms.

### Naming

If practical without causing noisy churn, rename `GREMLIN_SYSTEM_STYLE` to something identity-neutral or gnome-specific. If that rename would ripple too broadly for a narrow change, keep the constant name for now and update only the string contents.

## Persisted Data Changes

Patch the live server files:

- `/opt/apps/tinki-bot/data/conversations.json`
- `/opt/apps/tinki-bot/data/personas.json`

Changes:

- Replace the saved `tiny goblin` assistant reply text with a gnome-consistent line.
- Update the `cute` persona so it describes Tinki as a cute but snarky gnome engineer.

Do not delete unrelated history. Keep the intervention minimal and targeted.

## Testing

Add or update pytest coverage for:

- any changed user-facing fallback string in `cogs/uma.py`
- any helper or prompt-facing strings already covered by exact assertions

Testing does not need to simulate live JSON mutation directly if the repo code and direct file edits are straightforward, but the final implementation should verify the live data files were actually updated on the host when deployed.

## Risks And Mitigations

Risk: over-correcting and flattening Tinki's personality.
Mitigation: keep snark, brevity, and playful roast energy unchanged.

Risk: old saved history still leaks identity drift.
Mitigation: patch the specific live `conversations.json` entry rather than relying on prompt updates alone.

Risk: noisy refactor from renaming style constants.
Mitigation: treat symbol renaming as optional and only do it if the diff stays small.

## Implementation Notes

Likely touched repo files:

- `config.py`
- `cogs/ai.py`
- `cogs/uma.py`
- `tests/test_tinki_bot.py`
- `README.md`
- `CLAUDE.md`

Likely touched live server files after deploy:

- `/opt/apps/tinki-bot/data/conversations.json`
- `/opt/apps/tinki-bot/data/personas.json`

This should remain a single focused implementation plan because the work is tightly related and small in scope.
