# codex.md

Read this file first when starting Codex work in this repository. Then read
`HANDOFF.md` for the current state, followed by `AGENTS.md` and `CLAUDE.md`
when the task touches code, deployment, or live operations.

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
- `deploy-ec2.sh` - macOS/Linux deploy helper
- `deploy-ec2.ps1` - Windows deploy helper
- `scripts/remote-common.sh` - shared shell helpers for SSH + remote bash
- `scripts/remote-common.ps1` - shared PowerShell helpers for PuTTY + remote bash
- `scripts/run-remote-pytest.sh` - stable wrapper for host-side pytest from macOS/Linux
- `scripts/Run-RemotePytest.ps1` - stable wrapper for host-side pytest from Windows
- `scripts/check-remote-awscost.sh` - stable wrapper for host-side AWS cost checks from macOS/Linux
- `scripts/Check-RemoteAwsCost.ps1` - stable wrapper for host-side AWS cost checks from Windows
- `requirements.txt` - Python dependencies
- `.env.example` - local environment variable template
- `data/` - local development runtime data directory

Production server:

- app root: `/opt/apps/tinki-bot`
- deployed code: `/opt/apps/tinki-bot/repo`
- runtime data: `/opt/apps/tinki-bot/data`
- live secrets: `/etc/tinki-bot.env`
- systemd unit: `/etc/systemd/system/tinki-bot.service`

## Startup Checklist

For ordinary repo work, use this order unless the user explicitly asks for
something different:

1. Pull or otherwise sync from the real remote branch.
2. Check `git status --short --branch`.
3. Read `HANDOFF.md`, then re-check `AGENTS.md` and `CLAUDE.md` if the task touches shared workflow or live operations.
4. Inspect the smallest relevant code path and matching tests before editing.
5. Make the smallest focused change that solves the task.
6. Run the narrowest relevant test first; run `.venv/bin/python -m pytest -q` when the change is broad or shared.
7. If user-facing text, labels, or emojis changed, run a mojibake scan before finishing.
8. Update docs if commands, setup, deploy flow, or operational behavior changed.
9. Review `git diff`.
10. Commit the change and merge it locally into `main` unless the user explicitly asks to keep it on a branch.
11. Push the updated `main` branch unless the user explicitly says not to push yet.
12. Deploy only when the user wants the change live or the task is explicitly live-ops recovery.

## Deployment Notes

Preferred deploy flow from macOS/Linux:

```bash
./deploy-ec2.sh
```

Preferred deploy flow from Windows:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

Local deploy host configuration should live in `deploy-ec2.local.sh`,
`deploy-ec2.local.ps1`, or the `TINKI_EC2_HOST` environment variable, not in
committed repo files.

The deploy script:

- backs up `/opt/apps/tinki-bot/repo/tinki-bot.py`
- snapshots `/opt/apps/tinki-bot/data`
- compares local `HEAD` with GitHub `main` before uploading
- reports the currently deployed commit from `/opt/apps/tinki-bot/repo/.deploy-commit`
- uploads repo files to `/opt/apps/tinki-bot/repo`
- writes the deployed commit to `/opt/apps/tinki-bot/repo/.deploy-commit`
- restarts `tinki-bot.service`

For repeated remote checks, prefer the wrapper scripts in `scripts/` over ad hoc
`ssh`, `scp`, `powershell -Command`, nested `plink`, or nested one-liners.

## Project Structure

```text
tinki-bot.py          entry point - bot setup, cog loading, on_message, on_command_error
config.py             all constants, DATA_DIR, paths, UMA data, URL patterns
utils/
  calculator.py       maybe_calculate_reply + AST eval helpers
  current_awareness.py live/current source snippets for fresh questions
  letter_counter.py   maybe_count_letter_reply
  link_context.py     compact page context for addressed public links
  url_rewriter.py     rewrite_social_urls
  openai_helpers.py   get_openai_client, GPT wrapping, OpenAI failure handling
  selftests.py        URL, calculation, and letter-count self-tests
cogs/
  bowling.py          Bowling cog - score data + commands + on_message score detection
  uma.py              Uma cog - gacha, pity, race, uma assign
  personas.py         Personas cog - persona/conversation data + commands
  reminders.py        Reminders cog - sqlite DB + commands + check_reminders loop
  emotes.py           Emotes cog - $ commands, !emote, !allemotes, spinny handling
  tracking.py         Tracking cog - sus/explode/spinny tracking + graph commands
  ai.py               AI cog - addressed AI replies, link/image context, reaction replies
  utility.py          Utility cog - cat, dog, gif, roulette, purge, retired server stubs
  admin.py            Admin cog - restart, deploy, runtests, testurls, startup diagnostics
  url_filter.py       URLFilter cog - URL rewrites and Twitch clip embed fix
```

## Bot Architecture

- Personality: `GREMLIN_SYSTEM_STYLE` in `config.py` - cutesy gnome energy with a soft grunge side, short replies, no therapy talk.
- AI listener: `cogs/ai.py`. Tinki should only wake when addressed by an actual ping or by saying `Tinki`/`Tinki-bot`.
- Discord message links: addressed messages can make Tinki reply directly to accessible linked messages in the current server.
- Public web links: addressed messages can fetch compact page title/description context via `utils/link_context.py`.
- Image attachments: addressed image attachments are sent to the vision-capable OpenAI model.
- Fresh/current questions: `utils/current_awareness.py` adds current date/time and source snippets for current gaming/world questions.
- Pure function handlers: `utils/calculator.py` and `utils/letter_counter.py` return bare facts before GPT flavor wrapping.
- URL rewriting: `utils/url_rewriter.py`, triggered by `cogs/url_filter.py`.
- Graph PNGs: all saved to `DATA_DIR`, not the repo working directory.
- Cog data: each cog loads its own persistent data in `cog_load()` and exposes `_save()` helpers. Avoid global mutable state.

## Tests

Use the repo-local virtualenv on this machine:

```bash
.venv/bin/python -m pytest -q
```

Tests import directly from `utils/` modules and instantiate cog classes without a
live Discord connection. `_wire_cog(cog)` sets `cmd.cog` on each `Command` so
direct method calls work in tests.

Startup diagnostics in `cogs/admin.py` also run `pytest -q` and post the result
to `#bot-test` with the other startup self-tests. `pytest.ini` disables the
cache provider so cache-path noise does not pollute deploy or startup output.

## Encoding And Mojibake

- Treat mojibake as a regression. Broken text from mis-decoded punctuation or emoji means bytes were decoded or saved with the wrong encoding.
- Preserve UTF-8 when editing files with user-facing strings.
- When changing bot replies, embeds, labels, command help text, or docs, scan edited files for garbled byte-sequence artifacts before finishing.
- Prefer plain ASCII in source strings unless a real emoji or non-ASCII character is intentional.
- If a change touches user-facing text behavior, add or update a test in `tests/test_tinki_bot.py` that asserts the expected final string.
- If a file already contains mojibake, fix it as part of the same change rather than preserving the broken text.

## Cross-Agent Handoff

- `HANDOFF.md` is the canonical place to leave resume notes for either Claude Code or Codex.
- At the start of work, pull or otherwise sync from the real remote branch before making changes.
- After making repo changes, prefer merging locally into `main` before handing the task off, unless the user explicitly asks to keep a separate branch.
- Push merged `main` before handing the task off, unless the user explicitly says not to push yet.
- Before switching tools, update `HANDOFF.md` with the current task, next concrete step, tests run, and any active stash.
- Prefer handing work off as a commit on `main` rather than as unstaged local changes.
- If work must be stashed, use a descriptive stash message and record it in `HANDOFF.md`.
- Do not create local branches named like remote refs such as `origin/main`.

## Operational Rules

- Do not commit real secrets to the repo.
- Do not overwrite `/opt/apps/tinki-bot/data` during routine code deploys.
- Before risky server-side edits, back up `tinki-bot.py` and preserve data.
- Keep Minecraft/SkyFactory controls retired unless explicitly reintroduced.
- Prefer updating repo files locally and deploying via checked-in deploy helpers rather than editing directly on EC2.
- Deploy prunes backups to 3 most recent automatically; do not disable this.
- `!restart` and `!deploy` are admin-only Discord commands that control the live service.
- `!deploy` compares `/opt/apps/tinki-bot/repo/.deploy-commit` to GitHub `main` and skips the deploy when already current.

## Common Checks

Server health:

```bash
source ./scripts/remote-common.sh
remote_bash <<'EOF'
systemctl is-active tinki-bot || true
systemctl status tinki-bot --no-pager -l || true
journalctl -u tinki-bot -n 80 --no-pager -o short-iso || true
EOF
```

Rollback code on the server:

```bash
ls -lt /opt/apps/tinki-bot/repo/tinki-bot.py.backup_*
cp /opt/apps/tinki-bot/repo/tinki-bot.py.backup_YYYYMMDD_HHMMSS /opt/apps/tinki-bot/repo/tinki-bot.py
sudo systemctl restart tinki-bot
```
