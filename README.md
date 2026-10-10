<p align="center">
  <img src="assets/branding/tinki-banner.png" alt="Tinki-bot banner" width="100%">
</p>

<p align="center">
  <img src="assets/branding/tink.gif" alt="Tinki gif" width="160">
</p>

# tinki-bot

Discord bot for server utilities, memes, reminders, emotes, OpenAI-powered cute alt baddie gnome replies, and Uma Musume gacha.

## Branding

<p align="center">
  <img src="assets/branding/tinki-character-art-1.png" alt="Tinki character art 1" width="32%">
  <img src="assets/branding/tinki-character-art-2.png" alt="Tinki character art 2" width="32%">
  <img src="assets/branding/tinki-character-art-3.png" alt="Tinki character art 3" width="32%">
</p>

<p align="center">
  <img src="assets/branding/tinki-profile-sassy-fishnet.png" alt="Tinki sassy Discord profile art with fishnet top" width="32%">
  <img src="assets/branding/tinki-profile-sassy-smirk.png" alt="Tinki sassy Discord profile art with smirk" width="32%">
</p>

Additional repo art and usage notes live in [`assets/README.md`](assets/README.md).

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
- `assets/README.md` - gallery and notes for repo art assets
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
- `OPENAI_MODEL` optional, defaults to `gpt-6.1-sol` for involved questions and images
- `OPENAI_FAST_MODEL` optional, defaults to `gpt-6-luna` for routine mention replies
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
- runtime bootstrap: on startup the service user normalizes repo/venv group-write permissions and installs the pinned `python-Levenshtein` speedup package if it is missing
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

To upgrade only the OpenAI models while other features are still pending, run
`TINKI_EC2_INSTANCE_ID=your-instance-id ./deploy-ec2.sh --models-only` on
macOS/Linux. This needs AWS CLI SSM access, checks the previous committed model
files, preserves feature modules and runtime data, runs the live tests, and
updates only the model files and the two model settings in `/etc/tinki-bot.env`.
See `INSTALL.md` for requirements and rollback. Quick replies use GPT-6 Luna with
reasoning disabled; more involved replies and images use GPT-6.1 Sol at low
reasoning effort.

`./deploy-ec2.sh --ai-only` uses the same safeguards for an AI-context release.
It also sends the AI listener, troubleshooting-context helper, and its standalone
tests, while preserving the entrypoint and other feature modules. It records
`.deploy-ai-commit` and keeps root-only `ai_update_*` rollback snapshots.

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

For a model-only release, use the root-only `openai_models_*` snapshot printed by
the deploy. It contains the previous configuration, OpenAI helper, entrypoint,
environment file, previous model marker if present, and a list of added files.
Restore those files to their original locations, remove files listed in
`added-files.json`, and restart `tinki-bot`. Keep the environment snapshot private.
The model deploy automatically restores its files and settings if tests or the
service restart fail. It keeps the three most recent model snapshots.

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

Tinki responds only when directly addressed with an actual `@Tinki-bot` ping or the word `Tinki`/`Tinki-bot` in the message. Generic chatter like `the bot is dead` or `she ain't working` stays silent unless the message also names or pings Tinki. Simple named bot-status chatter like `Tinki is dead/alive/dumb` gets a short deterministic self-status reply before OpenAI. She also responds directly to linked Discord messages when the message text includes an actual Tinki mention before an accessible message link in the current server. Link previews that mention Tinki do not count as speaking to her. She has a cutesy gnome personality with cute alt baddie energy, powered by OpenAI, with explicit expertise in World of Warcraft and Final Fantasy XIV/FFXIV. Math questions and letter-count questions are answered deterministically first, then wrapped with GPT flavor.
Direct hush requests like `Tinki shut up` or `@Tinki-bot be quiet` stay silent instead of being treated as alive/up status chatter.
AI prompts include the current America/New_York and UTC date/time. Fresh/current/recent questions about gaming or world events, including common game aliases like `RoR2`, trigger a short cached web lookup, source snippets are ranked with official game sources preferred when available, and clear source-backed direct answers are validated before Tinki replies so stale model memory cannot override the lookup. Feed requests use at most four connections and an eight-second overall budget; a failed source does not discard results from other sources. Released/live questions are treated separately from announced/upcoming/next-news questions. When Tinki is addressed, regular public web links are fetched for compact page title/description context, and image attachments are passed to the vision-capable model for direct inspection. Link fetching checks resolved IP addresses before connecting, rejects private destinations at every redirect, and caps each link lookup at six seconds including redirects.

Addressed computer-troubleshooting questions automatically gather symptoms and prior attempts
from the invoking channel, a matching person's channel, and the main chat
(`CHANNEL_RANDOM_AI`, `main`, or `general`), when both requester and bot can read
their history. A mentioned person is matched by their Discord user ID even when
the request says "help @Lhea with ongoing computer issues".
Searches stay in the current server: at most three channels,
up to 1,500 messages each in the main/person channel (200 elsewhere), one year,
16 short excerpts, and 30 seconds. Older attempted checks and results get reserved
space so repeated recent crash reports cannot bury them. Replies to earlier
troubleshooting questions include the quoted question when it is in the scan.
Tinki uses GPT-6.1 Sol to reason from those symptoms and link the source messages.
She checks reported prior attempts/results before suggesting another step and
avoids repeating a failed check unless there is a specific reason to retest it.
Suggestions alone are not treated as completed steps. A capped or timed-out
scan is partial history, and Tinki must not claim to have checked everything.
Reports already fetched remain usable when the scan times out. A search waits
at most two seconds for one of the two lookup slots before reporting it is busy.
She gives a brief summary and asks one focused question at a time, then offers
one practical check based on the answer. Use Discord's **Reply** on her latest
troubleshooting question to continue without another ping. Anyone in the channel can
reply with symptoms, results, or an error screenshot; `stop`, `done`, or `fixed`
ends the conversation. A short answer matching the pending question also works
in ordinary chat for two minutes after the question, when there is one matching
active conversation. Each person's access to the quoted sources is rechecked.
Follow-ups retain the original reports and up to ten
exchanges in temporary memory, expire after 15 minutes of inactivity, and stay
in the same server and channel, with the speaker recorded for each answer. Source access is checked again on
each turn. Restarting Tinki clears these conversations.
Retrieved reports and derived troubleshooting answers are not saved to AI memory
or conversation files. Ordinary unaddressed messages stay silent; there is no
background scanning. For example: `Tinki, can you diagnose Lhea's computer problems?`

Explicitly naming or pinging Tinki in a Discord reply also works for ordinary messages, with up to 2,000 characters of the referenced message included as quoted context. If Discord cannot fetch the reference, Tinki still handles the addressed request. Automatic reply pings alone stay silent except for replies to her latest active troubleshooting question.
Requests for erotic or spicy writing are deterministically deflected into a playful public tease before any OpenAI call.
Known context traps like calculator `DRG` versus Final Fantasy `DRG` are answered deterministically so repeated false corrections or retroactive context switches cannot flip the answer.
Stored facts and recent chat history are treated as low-confidence hints. Tinki only injects remembered facts/topics when they overlap the current request, keeps fallback memory for explicit memory-lookup questions, and avoids saving "no, you're wrong" correction bait as future topic context.

### Channel historian

Tinki can investigate the current channel's stories and inside jokes, or catch you
up on recent conversations. She includes links to the original messages and the
dates covered by her search.

- `!lore toaster` - trace a topic through this channel's messages and nearby replies
- `!lore before:2025-01-01 toaster` - investigate an earlier slice of history, before that date at midnight UTC
- `!recap` or `!recap 7` - recap the last seven days; choose 1-30 days
- `Tinki, explain the toaster incident` - ask for lore naturally
- `Tinki, what's the lore behind toaster?` - another way to ask
- `Tinki, what did I miss this week?` - ask for a channel recap

History is fetched from Discord when asked. There is no separate message archive,
background indexing, or scheduled posting. A request stays in its originating
server channel or thread; both the requester and Tinki must be able to view that
channel and read its history. Bot messages and commands are excluded.

Each lookup reads at most 2,000 messages with a 20-second retrieval budget. Up to
24 source excerpts (about 500 characters each) are sent to the configured
`OPENAI_FAST_MODEL` for one summary. Recaps sample larger conversations and say so;
older topics can be explored with `before:YYYY-MM-DD`. "Earliest found" means the
earliest evidence in that search, not a proven origin. Source links are built from
Discord message IDs; if the summary is unavailable or has invalid citations,
Tinki shows actual excerpts instead. Replies stay in Discord as normal, but the
historian does not save a separate archive or add its evidence to AI memory.

Searches are limited to one per channel every 30 seconds and two at a time across
the bot. No new paid service or dependency is required; successful AI summaries
use the existing OpenAI account.

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

Local tests cover pure functions, isolated command helpers, and key admin/emote formatting helpers. No live Discord calls needed.

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
- Messages that say `Tinki` or `Tinki-bot` - get an automatic reply without pinging her
- `@Tinki-bot <Discord message link> [instruction]` - have Tinki reply directly to a linked message she can access in the current server
- Addressed messages with public web links or image attachments - get link/image context included in the AI reply
- Tinki keeps lightweight memory of explicit user facts and preferences, but only uses remembered context when it is relevant or explicitly requested.
- For memory-style questions, Tinki can search recent accessible channel history instead of guessing.

### Reminders

- `!remind` - show reminder usage help
- `!remindme in ...` - create a reminder
- `!remindme` - list your upcoming and missed reminders
- `!deletereminder <id>` - delete a reminder by ID
- `!currenttime` - show the current server time

### Channel History

- `!lore <topic>` - investigate channel lore with original-message citations
- `!lore before:YYYY-MM-DD <topic>` - search earlier history in this channel
- `!recap [days]` - recap this channel's last 1-30 days, default 7

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
- `!deploy` - compare the recorded deployed commit to GitHub `main`, download that exact commit if newer, sync the modular repo snapshot, install dependencies, record success, and restart, admin only. A dependency-install failure leaves the previous commit marker intact so the same update can be retried.
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
- Model-only releases are tracked separately in `.deploy-model-commit`; the full-release marker remains unchanged.
- Normal repo flow is documented in `AGENTS.md`, `CLAUDE.md`, and `HANDOFF.md`: sync first, make the smallest focused change, run relevant tests, push, then deploy with `.\deploy-ec2.ps1` when you want the change live.
- For Windows-to-EC2 operations, prefer the checked-in wrapper scripts in `scripts/` instead of inline `plink`/bash/python command strings.
- For macOS/Linux-to-EC2 operations, prefer `./deploy-ec2.sh` and the shell wrappers in `scripts/` instead of ad hoc `ssh`/`scp` one-liners.
