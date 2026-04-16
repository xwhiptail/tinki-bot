<p align="center">
  <img src="assets/branding/tinki-banner.png" alt="Tinki-bot banner" width="100%">
</p>

<p align="center">
  <img src="assets/branding/tinki-avatar.png" alt="Tinki avatar" width="160">
</p>

# tinki-bot

Discord bot for server utilities, memes, reminders, emotes, OpenAI-powered gremlin replies, and Uma Musume gacha.

## Requirements

- Python 3.10+ recommended for local development
- A Discord bot token
- A Giphy API key
- An OpenAI API key

## Project Files

- `tinki-bot.py` - thin bot entrypoint and cog loader
- `config.py` - shared config, file paths, patterns, and constants
- `cogs/` - Discord bot features split by domain
- `utils/` - deterministic helpers, OpenAI helpers, and self-tests
- `tests/` - local pytest suite for pure functions and isolated command helpers
- `requirements.txt` - Python dependencies
- `.env.example` - environment variable template
- `assets/branding/` - repo art for README, GitHub social preview, and bot branding
- `data/` - local runtime data directory for sqlite/json files
- `INSTALL.md` - local setup and production install notes
- `CLAUDE.md` - repo context for Claude-style agents
- `AGENTS.md` - generic agent guidance for this repo

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` or otherwise set the environment variables:

- `DISCORD`
- `GIPHY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` optional, defaults to `gpt-5.4`
- `TINKI_DATA_DIR` optional, defaults to `./data`

4. Run the bot:

```bash
python tinki-bot.py
```

## EC2 Deployment

Current server layout:

- app root: `/opt/apps/tinki-bot`
- code: `/opt/apps/tinki-bot/repo`
- data: `/opt/apps/tinki-bot/data`
- service: `tinki-bot.service`
- service unit file: `/etc/systemd/system/tinki-bot.service`
- live secrets file: `/etc/tinki-bot.env`
- deploy helper on this Windows machine: `deploy-ec2.ps1`
- local deploy config on this Windows machine: `deploy-ec2.local.ps1`

From this Windows machine, deploy updated repo files with:

```powershell
.\deploy-ec2.ps1
```

Create a local-only `deploy-ec2.local.ps1` from `deploy-ec2.local.ps1.example` and set the real host there. Keep that file out of git.

That script:

- backs up the live server copy of `tinki-bot.py`
- creates a timestamped archive of `/opt/apps/tinki-bot/data`
- uploads the tracked app files to the EC2 `repo/` directory
- restarts the systemd service

### Deploy Steps

1. Edit the code locally.
2. Run:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

3. The script will:

- create `tinki-bot.py.backup_YYYYMMDD_HHMMSS` in `/opt/apps/tinki-bot/repo`
- create `data_backup_YYYYMMDD_HHMMSS.tar.gz` in `/opt/apps/tinki-bot`
- upload the current repo files
- restart `tinki-bot.service`

4. If you want to verify manually on the server:

```bash
sudo systemctl status tinki-bot --no-pager
sudo journalctl -u tinki-bot -n 50 --no-pager
```

### Rollback

If a deploy breaks the bot, SSH to the server and roll back the code file:

1. List recent backups:

```bash
ls -lt /opt/apps/tinki-bot/repo/tinki-bot.py.backup_*
```

2. Restore the version you want:

```bash
cp /opt/apps/tinki-bot/repo/tinki-bot.py.backup_YYYYMMDD_HHMMSS /opt/apps/tinki-bot/repo/tinki-bot.py
```

3. Restart the service:

```bash
sudo systemctl restart tinki-bot
sudo systemctl status tinki-bot --no-pager
```

If data was damaged and you need to restore the data snapshot:

1. List recent data backups:

```bash
ls -lt /opt/apps/tinki-bot/data_backup_*.tar.gz
```

2. Restore one:

```bash
cd /opt/apps/tinki-bot
mv data data.bad_$(date +%Y%m%d_%H%M%S)
tar -xzf data_backup_YYYYMMDD_HHMMSS.tar.gz
sudo systemctl restart tinki-bot
```

### Secrets And Runtime Files

Live production secrets on EC2 are stored in:

- `/etc/tinki-bot.env`

That file currently provides:

- `DISCORD`
- `GIPHY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `TINKI_DATA_DIR`

Do not store real secrets in the repo. The repo only contains the template:

- `.env.example`

Live runtime data on EC2 is stored in:

- `/opt/apps/tinki-bot/data/reminders.db`
- `/opt/apps/tinki-bot/data/conversations.json`
- `/opt/apps/tinki-bot/data/personas.json`
- `/opt/apps/tinki-bot/data/scores.json`
- `/opt/apps/tinki-bot/data/sus_and_sticker_usage.json`
- `/opt/apps/tinki-bot/data/explode.json`
- `/opt/apps/tinki-bot/data/spinny.json`
- `/opt/apps/tinki-bot/data/uma_pity.json`

## Features

### AI replies

Tinki responds when mentioned (`@Tinki-bot`). She has a chaotic gremlin personality powered by OpenAI. Math questions and letter-count questions are answered deterministically first, then wrapped with GPT flavor.

### Bowling score tracking

Commands: `!pb`, `!avg`, `!median`, `!all`, `!bowlinggraph`, `!bowlingdistgraph`, `!add`

### Uma Musume gacha

- `!gacha [1|10]` - simulate pulls at real SSR/SR/R rates (3% SSR, pity at 200)
- `!pity [@user]` - show current pity counter with progress bar
- `!uma [@user]` - assign a random horse girl to someone
- `!race @u1 @u2 ...` - GPT-narrated race between mentioned members

### Utility

- `!remindme` - set a reminder
- `!restart` / `!deploy` - admin-only service control and self-update from GitHub

### Tests

Run locally with:

```bash
pytest
```

61 tests covering pure functions and isolated command helpers. No live Discord calls needed.

## Notes

- Runtime files live in `data/` by default (set `TINKI_DATA_DIR` to override).
- Minecraft and SkyFactory commands are retired and return a removal notice.
- Do not commit secrets, local databases, generated JSON files, or virtual environments.
- Deploy backups are pruned to the 3 most recent automatically.
