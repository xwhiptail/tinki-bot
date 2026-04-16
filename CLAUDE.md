# CLAUDE.md

This repository contains a Discord bot deployed to a single EC2 instance.

## Purpose

- Main bot entrypoint: `tinki-bot.py`
- Live GitHub repo: `https://github.com/xwhiptail/tinki-bot`
- Primary deploy target: a single EC2 instance configured locally for deploys

## Important Paths

Local workspace:

- `tinki-bot.py` - main bot code
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

The deploy script currently:

- backs up `/opt/apps/tinki-bot/repo/tinki-bot.py`
- snapshots `/opt/apps/tinki-bot/data`
- uploads repo files to `/opt/apps/tinki-bot/repo`
- restarts `tinki-bot.service`

## Operational Rules

- Do not commit real secrets to the repo.
- Do not overwrite `/opt/apps/tinki-bot/data` during routine code deploys.
- Before risky server-side edits, back up `tinki-bot.py` and preserve data.
- Keep Minecraft/SkyFactory controls retired unless explicitly reintroduced.
- Prefer updating repo files locally and deploying, rather than editing directly on the EC2 instance.

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
