# tinki-bot

Discord bot for server utilities, memes, reminders, emotes, and OpenAI-powered gremlin replies.

## Requirements

- Python 3.10+ recommended
- A Discord bot token
- A Giphy API key
- An OpenAI API key

## Project Files

- `tinki-bot.py` - main bot entrypoint
- `requirements.txt` - Python dependencies
- `.env.example` - environment variable template
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
- `OPENAI_MODEL` optional, defaults to `gpt-5.4-mini`
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
- SSH key currently used from this Windows machine: `I:\mybotserver.ppk`

From this Windows machine, deploy updated repo files with:

```powershell
.\deploy-ec2.ps1
```

That script now:

- backs up the live server copy of `tinki-bot.py`
- creates a timestamped archive of `/opt/apps/tinki-bot/data`
- uploads the tracked app files to the EC2 `repo/` directory
- restarts the systemd service

### Deploy Steps

Normal deploy flow:

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

## Notes

- The bot now stores runtime files in `data/` by default instead of `/opt/apps/...`.
- Minecraft and SkyFactory hosting controls have been retired. Their commands now return a removal notice.
- Do not commit secrets, local databases, generated json files, or virtual environments.
