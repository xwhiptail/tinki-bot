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

## Deploy Guidance

Normal deploys should go through:

```powershell
.\deploy-ec2.ps1
```

Avoid ad hoc file uploads unless fixing an emergency.

## High-Risk Areas

- `tinki-bot.py` is monolithic, so small edits can have wide impact.
- The bot uses live Discord/OpenAI credentials on the EC2 instance.
- The service must keep reading `/etc/tinki-bot.env`.

## Safe Defaults

- Prefer additive docs and small code changes.
- Back up the live server script before risky changes.
- Preserve rollback paths in docs and scripts.

## Cross-Agent Handoff

- `HANDOFF.md` is the shared resume file for both Codex and Claude Code.
- At the start of work, pull or otherwise sync from the real remote branch before making changes.
- After making repo changes, push them before handing the task off, unless the user explicitly says not to push yet.
- Before switching tools, update `HANDOFF.md` with current status, next step, tests run, and any active stash.
- Prefer handing work off on a branch or commit, not as unstaged local edits.
- If you must stash work, use a descriptive stash message and record it in `HANDOFF.md`.
- Never create local branches with names that look like remote refs, such as `origin/main`.
