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
- `OPENAI_FAST_MODEL` optional, defaults to `gpt-5.4-mini` for routine mention replies
- `TINKI_DATA_DIR` optional, defaults to `./data`
- `GITHUB_TOKEN` optional local tooling fallback for GitHub access; not used by the bot runtime

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
- compares local `HEAD` against GitHub `main` and aborts if they differ
- shows the currently deployed commit from `/opt/apps/tinki-bot/repo/.deploy-commit`
- uploads the tracked app files to the EC2 `repo/` directory
- writes the deployed commit to `/opt/apps/tinki-bot/repo/.deploy-commit`
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
- `OPENAI_FAST_MODEL`
- `TINKI_DATA_DIR`

Do not store real secrets in the repo. The repo only contains the template:

- `.env.example`

If you use local CLI tooling that needs GitHub auth outside normal Git credential flows, store the token in a local environment variable such as `GITHUB_TOKEN` instead of committing it to repo files.

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

114 tests covering pure functions, isolated command helpers, and key admin/emote formatting helpers. No live Discord calls needed.

Startup diagnostics also run `pytest -q` on boot and report the result in `#bot-test`, alongside the command, URL, calculator, letter-count, and bot-insight self-tests. Failing sections are marked with `🚨` and clean sections with `✅`. Pytest cache-provider warnings are disabled in this repo so the startup run stays clean on Windows.

## Commands

### Bowling

- `!pb` - show Jun's personal best score
- `!avg` - show Jun's average score
- `!median` - show Jun's median score
- `!all` - list all saved bowling scores
- `!add <score> <YYYY-MM-DD HH:MM:SS>` - manually add a bowling score
- `!delete <YYYY-MM-DD HH:MM:SS>` - delete a bowling score by timestamp
- `!bowlinggraph` - generate the bowling score trend graph
- `!bowlingdistgraph` - generate the bowling score distribution graph

### Personas And AI

- `!listpersonas` - list available personas
- `!erasememory [count]` - erase saved conversation memory for the active persona
- `@Tinki-bot <message>` - get a reply from Tinki

### Reminders

- `!remind` - show reminder usage help
- `!remindme in ...` - create a reminder
- `!remindme` - list your upcoming and missed reminders
- `!deletereminder <id>` - delete a reminder by ID
- `!currenttime` - show the current server time

### Emotes And Stickers

- `$<emote_name> [count]` - send a named emote as the bot
- `$randomemote [count]` - send a random emote as the bot
- `!allemotes` - list the current server's emotes
- `!emote <name> [1-4]` - search 7TV via direct API calls and choose from a paged picker before sending the selected emote size
- `!spinny @user` - enable SPINNY sticker grinding for a user
- `!stopspinny @user|username` - disable SPINNY sticker grinding
- `!silentspinny <username>` - enable silent grinding by username for whiptail only

### Tracking And Stats

- `!sussy` - show total sus usage
- `!sussygraph` - graph sus usage over time
- `!explode` - show total explode usage
- `!explodegraph` - graph explode usage over time
- `!grindcount` - show total SPINNY grind count
- `!grindgraph` - graph SPINNY grinding over time

### Utility

- `!gif` - post a random bowling gif
- `!random` - post a random pinned message
- `!roulette` - post a random gif
- `!cat` - post a random cat image
- `!dog` - post a random dog image
- `!dogbark` - post a random bark in ASCII art
- `!ss` - post the redirect image
- `!github` - link the source repository
- `!commands` - DM the built-in command list
- `!purge` - purge bot messages and command messages, whiptail only

### Admin

- `!restart` - restart the bot service, admin only
- `!deploy` - compare current deployed commit to GitHub `main`, sync the modular repo snapshot if newer, install dependencies, and restart, admin only
- `!runtests` - run command smoke tests with `✅`/`🚨` status output, admin only
- `!testurls` - run URL rewrite self-tests with `✅`/`🚨` status output, admin only

### Uma Musume

- `!gacha [1|10]` - simulate pulls with pity tracking
- `!pity [@user]` - show pity counter and progress bar
- `!uma [@user]` - assign a random horse girl
- `!race @user1 @user2 ...` - generate a narrated race
- `!umagif` - post a random Uma Musume gif

### Retired Server Commands

- `!startminecraft` - retired placeholder
- `!stopminecraft` - retired placeholder
- `!minecraftstatus` - retired placeholder
- `!minecraftserver` - retired placeholder
- `!startskyfactory` - retired placeholder
- `!stopskyfactory` - retired placeholder
- `!skyfactorystatus` - retired placeholder
- `!skyfactoryserver` - retired placeholder
- `!uptime` - retired placeholder

## Notes

- Runtime files live in `data/` by default (set `TINKI_DATA_DIR` to override).
- Minecraft and SkyFactory commands are retired and return a removal notice.
- Do not commit secrets, local databases, generated JSON files, or virtual environments.
- Deploy backups are pruned to the 3 most recent automatically.
- Deploy state is tracked in `/opt/apps/tinki-bot/repo/.deploy-commit`.
- Normal repo flow is documented in `AGENTS.md`, `CLAUDE.md`, and `HANDOFF.md`: sync first, make the smallest focused change, run relevant tests, push, then deploy with `.\deploy-ec2.ps1` when you want the change live.
