# AGENTS.md

## Repo Overview

This repo is a single-file Discord bot with supporting deploy and setup docs.

Primary files:

- `tinki-bot.py`
- `requirements.txt`
- `deploy-ec2.ps1`
- `README.md`
- `INSTALL.md`
- `CLAUDE.md`
- `HANDOFF.md`

## What Matters

- Production code runs from `/opt/apps/tinki-bot/repo/tinki-bot.py`
- Production data lives in `/opt/apps/tinki-bot/data`
- Production secrets live in `/etc/tinki-bot.env`
- The systemd service is `tinki-bot.service`

## Editing Guidance

- Keep secrets out of source control.
- Do not reintroduce hardcoded `/opt/apps/...` paths in code when local-relative or env-driven paths are available.
- Do not make deploy changes that overwrite runtime data by default.
- Update `README.md` and `INSTALL.md` when deploy or operational steps change.
- If changing bot commands, keep the command list in sync.
- If adding or changing bot commands or listeners, add or update pytest coverage in `tests/test_tinki_bot.py` and refresh `docs/command-test-map.md`.

## Deploy Guidance

Normal deploys should go through:

```powershell
.\deploy-ec2.ps1
```

On macOS/Linux, use:

```bash
./deploy-ec2.sh
```

Avoid ad hoc file uploads unless fixing an emergency.

For Windows-to-EC2 maintenance tasks, prefer the checked-in wrapper scripts in `scripts/`
over inline `powershell -Command` or nested `plink`/bash/python one-liners.

For macOS/Linux-to-EC2 maintenance tasks, prefer `deploy-ec2.sh` and the shell wrappers in
`scripts/` over ad hoc `ssh`/`scp` one-liners.

## High-Risk Areas

- `tinki-bot.py` is monolithic, so small edits can have wide impact.
- The bot uses live Discord/OpenAI credentials on the EC2 instance.
- The service must keep reading `/etc/tinki-bot.env`.

## Safe Defaults

- Prefer additive docs and small code changes.
- Back up the live server script before risky changes.
- Preserve rollback paths in docs and scripts.
- Default to verified local merges into `main` after focused testing. Use branch or PR flow only when the user asks for it or when temporary isolation is genuinely helpful.

## Normal Flow

For ordinary repo work, follow this order unless the user explicitly asks for something different:

1. Pull or otherwise sync from the real remote branch first.
2. Check `git status --short --branch`.
3. Read `HANDOFF.md`, then the relevant repo instructions before changing code.
4. Inspect the smallest relevant code path and the matching tests before editing.
5. Make the smallest focused change that solves the task.
6. Run the narrowest relevant test first; run `python -m pytest` when the change is broad or touches shared behavior.
7. If user-facing text or emojis changed, scan for mojibake before finishing.
8. Update docs when commands, deploy flow, setup, or operational behavior changed. When command behavior changes, update tests and `docs/command-test-map.md` in the same pass.
9. Review `git diff` before committing.
10. Commit the change and merge it locally into `main` unless the user explicitly asks to keep it on a branch.
11. Push the updated `main` branch unless the user explicitly says not to push yet.
12. Push the committed change to GitLab as part of the normal release flow when that mirror is in use on this machine.
13. Deploy the change to the bot with `.\deploy-ec2.ps1` when the user wants it live.
14. On macOS/Linux, use `./deploy-ec2.sh` when the user wants the change live.
15. For repeated host checks, prefer wrapper scripts such as `.\scripts\Run-RemotePytest.ps1`, `.\scripts\Check-RemoteAwsCost.ps1`, `./scripts/run-remote-pytest.sh`, and `./scripts/check-remote-awscost.sh`.

## Cross-Agent Handoff

- `HANDOFF.md` is the shared resume file for both Codex and Claude Code.
- At the start of work, pull or otherwise sync from the real remote branch before making changes.
- After making repo changes, prefer merging locally into `main` before handing the task off, unless the user explicitly asks to keep a separate branch.
- Push merged `main` before handing the task off, unless the user explicitly says not to push yet.
- Before switching tools, update `HANDOFF.md` with current status, next step, tests run, and any active stash.
- Prefer handing work off as a commit on `main`, not as unstaged local edits.
- If you must stash work, use a descriptive stash message and record it in `HANDOFF.md`.
- Never create local branches with names that look like remote refs, such as `origin/main`.
