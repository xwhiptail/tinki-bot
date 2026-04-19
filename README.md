<p align="center">
  <img src="assets/branding/tinki-banner.png" alt="Tinki-bot banner" width="100%">
</p>

<p align="center">
  <img src="assets/branding/tink.gif" alt="Tinki gif" width="160">
</p>

# tinki-bot

Discord bot for server utilities, memes, reminders, emotes, OpenAI-powered cute-snarky gnome replies, and Uma Musume gacha.

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
- `scripts/` - helper scripts for remote checks, AWS cost, low-cost monitoring setup, and repo maintenance

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
- `AWS_COST_REGION` optional, defaults to `us-east-1` for Cost Explorer queries
- `USER_WHIPTAIL_ID` optional, preferred trusted user ID for host-level admin commands like `!restart` and `!deploy`
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
- service user: `tinki-bot`
- SSH/deploy user: `ec2-user` with limited passwordless sudo for `systemctl ... tinki-bot`
- in-bot `!restart` / `!deploy` restarts: service self-terminates and systemd restarts it via `Restart=always`
- bot venv runtime: Python `3.11`
- runtime bootstrap: on startup the service user normalizes venv group-write permissions and installs the pinned `python-Levenshtein` speedup package if it is missing
- deploy helper on this Windows machine: `deploy-ec2.ps1`
- deploy helper on macOS/Linux: `./deploy-ec2.sh`
- local deploy config on this Windows machine: `deploy-ec2.local.ps1`
- local deploy config on macOS/Linux: `deploy-ec2.local.sh`

From this Windows machine, deploy updated repo files with:

```powershell
.\deploy-ec2.ps1
```

From macOS/Linux, deploy updated repo files with:

```bash
./deploy-ec2.sh
```

For recurring host checks, prefer the stable wrapper scripts over ad hoc `powershell -Command` + `plink` chains:

```powershell
.\scripts\Run-RemotePytest.ps1
.\scripts\Check-RemoteAwsCost.ps1
.\scripts\Check-RemoteAwsCost.ps1 -RestartService
.\scripts\Setup-RemoteLowCostMonitoring.ps1 --alert-email you@example.com
.\scripts\Install-RemoteHostMetricsTimer.ps1
```

On macOS/Linux, use the matching shell wrappers:

```bash
./scripts/run-remote-pytest.sh
./scripts/check-remote-awscost.sh
./scripts/check-remote-awscost.sh --restart-service
./scripts/setup-remote-low-cost-monitoring.sh --alert-email you@example.com
./scripts/install-remote-host-metrics-timer.sh
```

Create a local-only `deploy-ec2.local.ps1` from `deploy-ec2.local.ps1.example` and set the real host and SSH key path there, or use `TINKI_EC2_HOST` and `TINKI_EC2_KEY_PATH` in your local environment. Keep local deploy config out of git.

On macOS/Linux, create a local-only `deploy-ec2.local.sh` from `deploy-ec2.local.sh.example`, or set `TINKI_EC2_HOST`, `TINKI_EC2_USER`, and `TINKI_EC2_KEY_PATH` in your shell environment. Keep local deploy config out of git.

That script:

- backs up the live server copy of `tinki-bot.py`
- creates a timestamped archive of `/opt/apps/tinki-bot/data` under `/opt/apps/tinki-bot/backup`
- compares local `HEAD` against GitHub `main` and aborts if they differ
- shows the currently deployed commit from `/opt/apps/tinki-bot/repo/.deploy-commit`
- uploads the tracked app files to the EC2 `repo/` directory
- writes the deployed commit to `/opt/apps/tinki-bot/repo/.deploy-commit`
- restarts the systemd service

Repo-only branding art under `assets/branding/` is not part of the runtime deploy set.

### Deploy Steps

1. Edit the code locally.
2. Run on Windows:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

Or run on macOS/Linux:

```bash
cd /path/to/tinki-bot
./deploy-ec2.sh
```

3. The script will:

- create `tinki-bot.py.backup_YYYYMMDD_HHMMSS` in `/opt/apps/tinki-bot/repo`
- create `data_backup_YYYYMMDD_HHMMSS.tar.gz` in `/opt/apps/tinki-bot/backup`
- upload the current repo files
- restart `tinki-bot.service`

Host replacement reminder:

- normal deploys update code only
- when moving the bot to a new EC2 instance or rebuilding the host, also copy `/opt/apps/tinki-bot/data` and `/etc/tinki-bot.env`
- do not cut over a new host until those runtime files are present

4. If you want to verify manually on the server:

```bash
sudo systemctl status tinki-bot --no-pager
sudo journalctl -u tinki-bot -n 50 --no-pager
```

### Low-Cost Monitoring

The repo now includes a cheap default monitoring path intended to stay small on the monthly bill:

- `scripts/setup_low_cost_monitoring.py` creates or updates one SNS topic, a monthly AWS budget, and four CloudWatch alarms for EC2 status checks, CPU credits, memory, and disk.
- `scripts/publish_host_metrics.py` publishes only two custom metrics: `MemoryUsedPercent` and `DiskUsedPercent`.
- `scripts/install_host_metrics_timer.sh` installs a 5-minute systemd timer on the host so those custom metrics keep flowing without adding a full observability agent.

Preferred wrappers from this machine:

```powershell
.\scripts\Setup-RemoteLowCostMonitoring.ps1 --alert-email you@example.com
.\scripts\Install-RemoteHostMetricsTimer.ps1
```

```bash
./scripts/setup-remote-low-cost-monitoring.sh --alert-email you@example.com
./scripts/install-remote-host-metrics-timer.sh
```

Notes:

- confirm the SNS email subscription after the setup script runs, or the alarms will not reach your inbox
- the setup script prints the current EC2 cost posture, including public IPv4, root volume type, and whether a future T4g check is worth doing
- the setup script does not auto-modify the root volume or instance family; gp3 and T4g remain explicit follow-up decisions
- expected AWS permissions are `cloudwatch:PutMetricAlarm`, `cloudwatch:PutMetricData`, `ec2:DescribeInstances`, `ec2:DescribeVolumes`, `sns:CreateTopic`, `sns:Subscribe`, `sns:ListSubscriptionsByTopic`, `budgets:CreateBudget`, `budgets:UpdateBudget`, `budgets:CreateNotification`, `budgets:DescribeBudget`, and `sts:GetCallerIdentity`

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
ls -lt /opt/apps/tinki-bot/backup/data_backup_*.tar.gz
```

2. Restore one:

```bash
cd /opt/apps/tinki-bot
mv data data.bad_$(date +%Y%m%d_%H%M%S)
tar -xzf /opt/apps/tinki-bot/backup/data_backup_YYYYMMDD_HHMMSS.tar.gz
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
- `USER_WHIPTAIL_ID`

Do not store real secrets in the repo. The repo only contains the template:

- `.env.example`

If you use local CLI tooling that needs GitHub auth outside normal Git credential flows, store the token in a local environment variable such as `GITHUB_TOKEN` instead of committing it to repo files.

### Mac Quickstart

For Cowork or Codex on a Mac, set up standard OpenSSH once so the repo scripts can reuse it:

1. Put your EC2 key in `~/.ssh/` with restricted permissions:

```bash
chmod 600 ~/.ssh/your-ec2-key.pem
```

2. Add an SSH host entry in `~/.ssh/config`:

```sshconfig
Host tinki-ec2
  HostName your-ec2-host-or-ip
  User ec2-user
  IdentityFile ~/.ssh/your-ec2-key.pem
  IdentitiesOnly yes
  ServerAliveInterval 60
```

3. Either export the repo env vars in `~/.zshrc`:

```bash
export TINKI_EC2_HOST=tinki-ec2
export TINKI_EC2_USER=ec2-user
export TINKI_EC2_KEY_PATH=~/.ssh/your-ec2-key.pem
```

Or copy `deploy-ec2.local.sh.example` to `deploy-ec2.local.sh` and fill in the same values there.

4. Restart your terminal or reload your shell:

```bash
source ~/.zshrc
```

5. Validate the connection before opening Cowork:

```bash
ssh tinki-ec2
```

Once that is working, Cowork can just open the repo and use:

```bash
./deploy-ec2.sh
./scripts/run-remote-pytest.sh
./scripts/check-remote-awscost.sh
```

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

Tinki responds when mentioned (`@Tinki-bot`). She has a cute but snarky gnome personality powered by OpenAI. Math questions and letter-count questions are answered deterministically first, then wrapped with GPT flavor.

### Bowling score tracking

Commands: `!pb`, `!avg`, `!median`, `!all`, `!bowlinggraph`, `!bowlingdistgraph`, `!add`

### Uma Musume gacha

- `!gacha [1|10]` - simulate pulls at real SSR/SR/R rates (3% SSR, pity at 200)
- `!pity [@user]` - show current pity counter with progress bar
- `!uma [@user]` - assign a random horse girl to someone
- `!race @u1 @u2 ...` - GPT-narrated race between mentioned members

### Utility

- `!remindme` - set a reminder
- `!changelog [count]` - show recent commit summaries from local git or GitHub fallback
- `!awscost` - admin-only AWS month-to-date and projected monthly cost
- `!statusreport` - admin-only EC2/runtime status summary with an attached detail report
- `!restart` / `!deploy` - admin-only service control and self-update from GitHub

### Tests

Run locally with:

```bash
pytest
```

121 tests covering pure functions, isolated command helpers, and key admin/emote formatting helpers. No live Discord calls needed.

Startup diagnostics also run `pytest -q` on boot and report the result in `#bot-test`, alongside the command, URL, calculator, letter-count, bot-insight self-tests, OpenAI balance, and AWS month-to-date/projected cost summary. Failing sections are marked with `🚨` and clean sections with `✅`. The bot now allows only one in-process diagnostics run at a time and applies timeouts to heavy diagnostic steps so deploy-time startup checks do not pile up on the host; the startup pytest subprocess currently gets a `35s` wall-clock timeout to leave headroom for the `t3a.nano` EC2 host. Pytest cache-provider warnings are disabled in this repo so the startup run stays clean on Windows.

For infrastructure cost control outside the bot runtime, use the repo maintenance helpers in `scripts/` to set up free AWS Budgets alerts plus a small CloudWatch alarm set, rather than adding a paid third-party monitoring stack by default.

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

- `@Tinki-bot <message>` - get a reply from Tinki
- Tinki keeps lightweight memory of explicit user facts and preferences.
- For memory-style questions, Tinki can search recent accessible channel history instead of guessing.

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
- `!emote <name> [1x-4x]` - search 7TV via direct API calls, open a picker for up to 10 matches per page, preview animated emotes in the result grid, then pick a size and send
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
- `!changelog [count]` - show recent commit summaries
- `!commands` - DM the built-in command list
- `!purge` - purge bot messages and command messages, whiptail only

### Admin

- `!awscost` - show AWS month-to-date and projected monthly cost from Cost Explorer, whiptail/admin only
- `!statusreport` - show EC2/runtime status, including deploy commit, host pressure, uptime, and AWS cost, plus a text attachment with extra details, whiptail/admin only
- `!restart` - restart the bot service, admin only
- `!deploy` - compare current deployed commit to GitHub `main`, report AWS month-to-date and projected cost, sync the modular repo snapshot if newer, install dependencies, and restart, admin only
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
- For Windows-to-EC2 operations, prefer the checked-in wrapper scripts in `scripts/` instead of inline `plink`/bash/python command strings.
- For macOS/Linux-to-EC2 operations, prefer `./deploy-ec2.sh` and the shell wrappers in `scripts/` instead of ad hoc `ssh`/`scp` one-liners.
