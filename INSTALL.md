# INSTALL.md

## Local Setup

1. Create a virtual environment.

```bash
python -m venv .venv
```

2. Activate it.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Set environment variables using `.env.example` as the template.

Required:

- `DISCORD`
- `GIPHY`
- `OPENAI_API_KEY`

Optional:

- `OPENAI_MODEL`
- `OPENAI_FAST_MODEL`
- `TINKI_DATA_DIR`
- `GITHUB_TOKEN` for local GitHub-authenticated tooling; not used by the bot runtime

5. Run the bot.

```bash
python tinki-bot.py
```

## Production Install Layout

EC2 directories:

- `/opt/apps/tinki-bot/repo`
- `/opt/apps/tinki-bot/data`

Secrets:

- `/etc/tinki-bot.env`

Service:

- `/etc/systemd/system/tinki-bot.service`

## Production Deploy

From this Windows machine:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

Before the first deploy, copy `deploy-ec2.local.ps1.example` to `deploy-ec2.local.ps1` and set your real EC2 host there, or set `TINKI_EC2_HOST` in your local environment.

## Production Rollback

Code rollback:

```bash
ls -lt /opt/apps/tinki-bot/repo/tinki-bot.py.backup_*
cp /opt/apps/tinki-bot/repo/tinki-bot.py.backup_YYYYMMDD_HHMMSS /opt/apps/tinki-bot/repo/tinki-bot.py
sudo systemctl restart tinki-bot
```

Data rollback:

```bash
ls -lt /opt/apps/tinki-bot/data_backup_*.tar.gz
cd /opt/apps/tinki-bot
mv data data.bad_$(date +%Y%m%d_%H%M%S)
tar -xzf data_backup_YYYYMMDD_HHMMSS.tar.gz
sudo systemctl restart tinki-bot
```
