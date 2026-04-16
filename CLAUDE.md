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

## Bot Architecture

- Personality: `GREMLIN_SYSTEM_STYLE` constant — chaotic gnome shitposter, short replies, no therapy talk.
- AI mention handler: strips `<@ID>` and `<@!ID>` variants before processing. Falls through to OpenAI if no pure-function handler matches.
- Pure function handlers (deterministic, no GPT): `maybe_calculate_reply`, `maybe_count_letter_reply`. Both return a bare fact string; `gpt_wrap_fact` wraps it with personality using assistant prefill to prevent prompt leakage.
- URL rewriting: `rewrite_social_urls` maps Twitter/X/Instagram/TikTok/Reddit to fix-embed proxies.
- Graph PNGs: all saved to `DATA_DIR`, not the repo working directory.
- Uma Musume gacha: pity tracked per Discord user ID in `data/uma_pity.json`. SSR 3%, SR 18.75%, R 78.25%, hard pity at 200 pulls.

## Tests

```bash
pytest
```

48 tests in `tests/test_tinki_bot.py`. Covers `rewrite_social_urls`, `maybe_calculate_reply`, `maybe_count_letter_reply`, score commands, and persona commands. The module is loaded via `importlib` (hyphen in filename); `Bot.run` is patched to a no-op so the bot does not connect.

## Operational Rules

- Do not commit real secrets to the repo.
- Do not overwrite `/opt/apps/tinki-bot/data` during routine code deploys.
- Before risky server-side edits, back up `tinki-bot.py` and preserve data.
- Keep Minecraft/SkyFactory controls retired unless explicitly reintroduced.
- Prefer updating repo files locally and deploying via `deploy-ec2.ps1`, rather than editing directly on the EC2 instance.
- Deploy prunes backups to 3 most recent automatically — do not disable this.
- `!restart` and `!deploy` are admin-only Discord commands that control the live service.

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
