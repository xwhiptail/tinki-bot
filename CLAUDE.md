# CLAUDE.md

This repository contains a Discord bot deployed to a single EC2 instance.

## Purpose

- Main bot entrypoint: `tinki-bot.py`
- Live GitHub repo: `https://github.com/xwhiptail/tinki-bot`
- Primary deploy target: a single EC2 instance configured locally for deploys

## Important Paths

Local workspace:

- `tinki-bot.py` - thin entrypoint and cog loader
- `config.py` - shared constants, paths, patterns, and defaults
- `cogs/` - feature modules grouped by domain
- `utils/` - deterministic helpers, OpenAI wrappers, and self-tests
- `tests/` - local pytest suite
- `HANDOFF.md` - shared Codex/Claude resume file
- `assets/branding/` - avatar, banner, and branding assets
- `deploy-ec2.ps1` - Windows deploy helper
- `requirements.txt` - Python dependencies
- `.env.example` - local environment variable template
- `data/` - local development runtime data directory

Production server:

- app root: `/opt/apps/tinki-bot`
- deployed code: `/opt/apps/tinki-bot/repo`
- runtime data: `/opt/apps/tinki-bot/data`
- live secrets: `/etc/tinki-bot.env`
- systemd unit: `/etc/systemd/system/tinki-bot.service`

## Deployment Notes

Preferred deploy flow from this Windows machine:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

Local deploy host configuration should live in `deploy-ec2.local.ps1` or the `TINKI_EC2_HOST` environment variable, not in committed repo files.

The deploy script:

- backs up `/opt/apps/tinki-bot/repo/tinki-bot.py`
- snapshots `/opt/apps/tinki-bot/data`
- compares local `HEAD` with GitHub `main` before uploading
- reports the currently deployed commit from `/opt/apps/tinki-bot/repo/.deploy-commit`
- uploads repo files to `/opt/apps/tinki-bot/repo`
- writes the deployed commit to `/opt/apps/tinki-bot/repo/.deploy-commit`
- restarts `tinki-bot.service`

## Project Structure

```text
tinki-bot.py          entry point - bot setup, cog loading, on_message, on_command_error
config.py             all constants, DATA_DIR, paths, UMA data, URL patterns
utils/
  calculator.py       maybe_calculate_reply + AST eval helpers
  letter_counter.py   maybe_count_letter_reply
  url_rewriter.py     rewrite_social_urls
  openai_helpers.py   get_openai_client, gpt_wrap_fact, fetch_openai_balance
  selftests.py        run_url_selftests, run_calculate_selftests, run_letter_count_selftests
cogs/
  bowling.py          Bowling cog - score data + commands + on_message score detection
  uma.py              Uma cog - gacha, pity, race, uma assign
  personas.py         Personas cog - persona/conversation data + commands
  reminders.py        Reminders cog - sqlite DB + commands + check_reminders loop
  emotes.py           Emotes cog - $ commands, !emote, !allemotes, spinny grinding
  tracking.py         Tracking cog - sus/explode/spinny tracking + graph commands
  ai.py               AI cog - @mention handler, random AI posting, reaction replies
  utility.py          Utility cog - cat, dog, gif, roulette, purge, retired server stubs
  admin.py            Admin cog - restart, deploy, runtests, testurls, startup diagnostics
  url_filter.py       URLFilter cog - URL rewrites and Twitch clip embed fix
```

## Bot Architecture

- Personality: `GREMLIN_SYSTEM_STYLE` constant in `config.py` - chaotic gremlin shitposter, short replies, no therapy talk.
- AI mention handler: in `cogs/ai.py`. Strips `<@ID>` and `<@!ID>` variants. Falls through to OpenAI if no pure-function handler matches. Accesses persona data via `bot.cogs['Personas']`.
- Pure function handlers (deterministic, no GPT): `utils/calculator.py` -> `maybe_calculate_reply`, `utils/letter_counter.py` -> `maybe_count_letter_reply`. Both return a bare fact string; `gpt_wrap_fact` wraps it with personality using assistant prefill to prevent prompt leakage.
- URL rewriting: `utils/url_rewriter.py` -> `rewrite_social_urls`. Triggered by `cogs/url_filter.py` on_message listener.
- Graph PNGs: all saved to `DATA_DIR`, not the repo working directory.
- Uma Musume gacha: in `cogs/uma.py`. Pity stored in `cog.pity_file` (default `data/uma_pity.json`). SSR 3%, SR 18.75%, R 78.25%, hard pity at 200 pulls.
- Cog data: each cog loads its own persistent data in `cog_load()` and exposes `_save()` helpers. No global mutable state.

## Tests

```bash
pytest
```

67 tests in `tests/test_tinki_bot.py`. Tests import directly from `utils/` modules and instantiate cog classes without a live Discord connection. `_wire_cog(cog)` sets `cmd.cog` on each `Command` so direct method calls work in tests.

Startup diagnostics in `cogs/admin.py` also run `pytest -q` and post the result to `#bot-test` with the other startup self-tests. `pytest.ini` disables the cache provider so Windows cache-path noise does not pollute deploy or startup output.

## Encoding And Mojibake

- Treat mojibake as a regression. Broken text like `â€”`, `â†’`, `ðŸ`, or `âœ¨` means bytes were decoded or saved with the wrong encoding.
- Preserve UTF-8 when editing files with user-facing strings. Do not re-save source or docs in a way that corrupts existing text.
- When changing bot replies, embeds, labels, command help text, or docs, scan the edited file for garbled byte-sequence artifacts before finishing.
- Prefer plain ASCII in source strings unless a real emoji or non-ASCII character is intentional. If non-ASCII text is intentional, keep it exact.
- If a change touches user-facing text behavior, add or update a test in `tests/test_tinki_bot.py` that asserts the exact expected final string, so mojibake fails the test instead of slipping through on a loose substring match.
- If a file already contains mojibake, fix it as part of the same change rather than preserving the broken text.

## Cross-Agent Handoff

- `HANDOFF.md` is the canonical place to leave resume notes for either Claude Code or Codex.
- At the start of work, pull or otherwise sync from the real remote branch before making changes.
- After making repo changes, push them before handing the task off, unless the user explicitly says not to push yet.
- Before switching tools, update `HANDOFF.md` with the current task, next concrete step, tests run, and any active stash.
- Prefer handing work off on a branch or committed state rather than as unstaged local edits.
- If work must be stashed, use a descriptive stash message and record the stash entry in `HANDOFF.md`.
- Do not create local branches named like remote refs such as `origin/main`; that makes later fetch/rebase/push flows ambiguous.

## Operational Rules

- Do not commit real secrets to the repo.
- Do not overwrite `/opt/apps/tinki-bot/data` during routine code deploys.
- Before risky server-side edits, back up `tinki-bot.py` and preserve data.
- Keep Minecraft/SkyFactory controls retired unless explicitly reintroduced.
- Prefer updating repo files locally and deploying via `deploy-ec2.ps1`, rather than editing directly on the EC2 instance.
- Deploy prunes backups to 3 most recent automatically - do not disable this.
- `!restart` and `!deploy` are admin-only Discord commands that control the live service.
- `!deploy` compares `/opt/apps/tinki-bot/repo/.deploy-commit` to GitHub `main` and skips the deploy when already current.

## Common Checks

Server health:

```bash
sudo systemctl status tinki-bot --no-pager
sudo journalctl -u tinki-bot -n 50 --no-pager
```

Rollback code:

```bash
ls -lt /opt/apps/tinki-bot/repo/tinki-bot.py.backup_*
cp /opt/apps/tinki-bot/repo/tinki-bot.py.backup_YYYYMMDD_HHMMSS /opt/apps/tinki-bot/repo/tinki-bot.py
sudo systemctl restart tinki-bot
```
