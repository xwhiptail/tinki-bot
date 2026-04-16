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
