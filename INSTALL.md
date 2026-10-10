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

- `OPENAI_MODEL` (default `gpt-6.1-sol`)
- `OPENAI_FAST_MODEL` (default `gpt-6-luna`)
- `AWS_COST_REGION`
- `USER_WHIPTAIL_ID` for the trusted operator who may run host-level admin commands
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
- runtime user: `tinki-bot`
- SSH/deploy user: `ec2-user`
- bot virtualenv runtime: Python `3.11`

On the hardened AL2023 host, `ec2-user` keeps limited passwordless sudo only for
`systemctl ... tinki-bot`, which keeps the checked-in deploy helpers working without leaving the
full host under `NOPASSWD: ALL`. The in-bot `!restart` and `!deploy` flows now terminate the
service process and let systemd bring it back via `Restart=always`, so they do not depend on sudo
from the `tinki-bot` runtime user.

On startup, the bot also self-heals the repo and virtualenv by restoring group-write permissions under
`/opt/apps/tinki-bot/repo` and `/opt/apps/tinki-bot/myenv`, then installing the pinned
`python-Levenshtein` package if that optional `fuzzywuzzy` speedup is missing. That keeps future
`ec2-user` deploys and maintenance installs from getting stuck on the hardened ownership model.

On the current `t3a.nano` host, an additional `/swapfile_tinki` swapfile is enabled to give
package installs and venv rebuilds enough headroom during maintenance work.

## Production Deploy

From this Windows machine:

```powershell
cd i:\botserver\tinki-bot
.\deploy-ec2.ps1
```

Before the first deploy, copy `deploy-ec2.local.ps1.example` to `deploy-ec2.local.ps1` and set your real EC2 host and SSH key path there, or set `TINKI_EC2_HOST` and `TINKI_EC2_KEY_PATH` in your local environment.

From macOS/Linux:

```bash
cd /path/to/tinki-bot
./deploy-ec2.sh
```

Before the first deploy on macOS/Linux, copy `deploy-ec2.local.sh.example` to `deploy-ec2.local.sh` and set your real EC2 host, user, and SSH key path there, or set `TINKI_EC2_HOST`, `TINKI_EC2_USER`, and `TINKI_EC2_KEY_PATH` in your shell environment.

For an OpenAI model upgrade without releasing other pending features, use:

```bash
TINKI_EC2_INSTANCE_ID=your-instance-id ./deploy-ec2.sh --models-only
```

This macOS/Linux option requires AWS CLI access to SSM `SendCommand` and
`GetCommandInvocation` on that instance. `TINKI_AWS_REGION` defaults to
`us-east-1`. The instance ID must identify the same host configured for SSH.
The helper sends committed `config.py`, `utils/openai_helpers.py`, and standalone
model tests, updates only the two OpenAI model variables in `/etc/tinki-bot.env`,
runs the live test suite with temporary test data, then restarts the service.
It checks the previous committed file hashes before writing and backs up code
and settings in a root-only `openai_models_*` directory, retaining three snapshots.
Failure restores the previous files and settings. `.deploy-model-commit` records
the model overlay; `.deploy-commit`, feature modules, entrypoint, and runtime data
are preserved. The normal deploy still releases the complete repository.

GPT-6 Luna uses `reasoning_effort=none` for quick replies. GPT-6.1 Sol uses `low`
for more involved replies and images. The shared OpenAI helper normalizes token
limits and removes incompatible sampling parameters when reasoning is enabled;
an older model environment override retains its existing request behavior.

For model rollback, restore the model files and `tinki-bot.env` from the printed
snapshot to the repo and `/etc/tinki-bot.env`, restore the old model marker if
present, remove repo files listed in `added-files.json`, and restart the service.
Keep the environment snapshot private; no runtime data restore is required.

To deploy automatic troubleshooting context without releasing other pending
features, use the same instance/region settings with `./deploy-ec2.sh --ai-only`.
This also updates only `cogs/ai.py`, `utils/troubleshooting_context.py`, and its
standalone tests. The full-release marker and other cogs stay intact; the overlay
is recorded in `.deploy-ai-commit`, and `ai_update_*` snapshots follow the same
rollback rules and three-snapshot retention. The helper selects the newest model
or AI marker for model-file hash checks, and the newest full or AI marker for
AI-feature hash checks. Payloads are compressed to stay within SSM request limits.

Troubleshooting context uses the existing Discord connection. Both requester and
bot need View Channel and Read Message History in every searched channel. The
invoking channel, a matching person's channel, and main chat names are preferred;
`CHANNEL_RANDOM_AI` identifies the main chat in this server. Scanning is bounded
to three channels, 1,500 messages in main/person channels (200 elsewhere), one year,
16 excerpts, and 12
seconds, with at most two concurrent searches. Access is rechecked before quoted
messages are passed to OpenAI. No new permission, persistent archive, scheduled
job, or dependency is required. Explicit requests not to search are respected.
Mentioned people are matched by Discord user ID, independently of wording near
"computer" or display-name changes.
Interactive troubleshooting keeps at most 100 temporary conversations, each with
the original reports and the last ten exchanges. They expire after 15 minutes of
inactivity and are cleared on restart. Anyone replying to the latest troubleshooting
answer in the same server/channel can continue without a ping. For two minutes
after a question, short relevant answers in normal chat also work if exactly one
active conversation matches. Each speaker is recorded with their answer.
Source permissions for the current speaker are checked before and after generating each answer;
loss of the original requester's access discards the conversation. A joining
participant without source access is denied without ending the original session.
No conversation or fetched report is
written to runtime data.
Older attempts/results receive reserved excerpt slots, and referenced earlier
questions are included when available in the scan. Reported attempts are kept
distinct from suggestions; capped/time-limited coverage must not be described
as a complete history search. Waiting for a lookup slot is capped at two seconds,
followed by the scan's own 12-second deadline. Partial reports are retained at
that deadline and still inform the reply. A statement that a check was not retried
recently does not erase a reported earlier failed attempt.

If you want `!awscost` and deploy-time AWS cost reporting, the bot runtime also needs AWS credentials with Cost Explorer access.

If you are migrating to a brand new EC2 host instead of doing a normal code deploy, copy the live runtime state too:

- `/opt/apps/tinki-bot/data`
- `/etc/tinki-bot.env`

The deploy scripts update code, but host migration still requires those runtime files to be restored on the new machine before cutover.

Repo-only branding art under `assets/branding/` is intentionally excluded from routine code deploys.

The channel historian (`!lore` and `!recap`) uses the existing Discord connection
and OpenAI account. Both the requester and bot need View Channel and Read Message
History in the invoking server channel/thread. It reads text on demand, sends a
bounded selection of excerpts to `OPENAI_FAST_MODEL`, and creates no separate
message archive or scheduled job. The normal deploy includes its new cog and
history helper; no database migration or new dependency is needed.

The in-bot `!deploy` command downloads the exact commit it checked on GitHub and
updates `.deploy-commit` only after dependency installation succeeds. If that step
fails, fix the reported dependency problem and retry `!deploy`; the failed attempt
will not be mistaken for a completed update. This remains an in-place code update,
so a failed attempt may have copied code or partially installed dependencies; it
does not provide an atomic rollback. The shell and PowerShell deploy helpers keep
their existing workflow.

For repeated remote maintenance from Windows, prefer the wrapper scripts in `scripts/` instead of building inline `plink` commands:

```powershell
.\scripts\Run-RemotePytest.ps1
.\scripts\Check-RemoteAwsCost.ps1
.\scripts\Setup-RemoteLowCostMonitoring.ps1 --alert-email you@example.com
.\scripts\Install-RemoteHostMetricsTimer.ps1
```

On macOS/Linux, use the shell wrappers:

```bash
./scripts/run-remote-pytest.sh
./scripts/check-remote-awscost.sh
./scripts/setup-remote-low-cost-monitoring.sh --alert-email you@example.com
./scripts/install-remote-host-metrics-timer.sh
```

## Low-Cost Monitoring Setup

To keep recurring monitoring cheap, the repo includes a small AWS-native setup:

1. Create the budget, SNS topic, and CloudWatch alarms:

```powershell
.\scripts\Setup-RemoteLowCostMonitoring.ps1 --alert-email you@example.com
```

Or on macOS/Linux:

```bash
./scripts/setup-remote-low-cost-monitoring.sh --alert-email you@example.com
```

2. Install the host-side timer that publishes only memory and disk metrics every five minutes:

```powershell
.\scripts\Install-RemoteHostMetricsTimer.ps1
```

Or on macOS/Linux:

```bash
./scripts/install-remote-host-metrics-timer.sh
```

3. Confirm the SNS subscription email before relying on alerts.

The setup script also reports whether the host still has the obvious cost flags:

- public IPv4 monthly charge still attached
- gp2 root volume that should likely move to gp3
- T3/T3a instance family that may be worth a future T4g validation pass

Expected AWS permissions:

- `cloudwatch:PutMetricAlarm`
- `cloudwatch:PutMetricData`
- `ec2:DescribeInstances`
- `ec2:DescribeVolumes`
- `sns:CreateTopic`
- `sns:Subscribe`
- `sns:ListSubscriptionsByTopic`
- `budgets:CreateBudget`
- `budgets:UpdateBudget`
- `budgets:CreateNotification`
- `budgets:DescribeBudget`
- `sts:GetCallerIdentity`

## Secret Scanning

This repo includes a lightweight secret scanner for both local commits and GitHub pushes.

1. Enable the local hook path once per clone:

```bash
git config core.hooksPath .githooks
```

2. Run the scanner manually when needed:

```bash
python3 scripts/scan_secrets.py
python3 scripts/scan_secrets.py --staged
```

GitHub Actions also runs the same scanner on push and pull request.

## Mac SSH Setup

If you want Cowork to open with EC2 access already available, use standard OpenSSH config instead of per-session flags:

1. Put the EC2 key in `~/.ssh/your-ec2-key.pem`
2. Restrict it:

```bash
chmod 600 ~/.ssh/your-ec2-key.pem
```

3. Add `~/.ssh/config`:

```sshconfig
Host tinki-ec2
  HostName your-ec2-host-or-ip
  User ec2-user
  IdentityFile ~/.ssh/your-ec2-key.pem
  IdentitiesOnly yes
  ServerAliveInterval 60
```

4. Add shell environment in `~/.zshrc` if you want the repo wrappers ready in every new terminal:

```bash
export TINKI_EC2_HOST=tinki-ec2
export TINKI_EC2_USER=ec2-user
export TINKI_EC2_KEY_PATH=~/.ssh/your-ec2-key.pem
```

5. Reload the shell and validate:

```bash
source ~/.zshrc
ssh tinki-ec2
```

## Production Rollback

Code rollback:

```bash
ls -lt /opt/apps/tinki-bot/repo/tinki-bot.py.backup_*
cp /opt/apps/tinki-bot/repo/tinki-bot.py.backup_YYYYMMDD_HHMMSS /opt/apps/tinki-bot/repo/tinki-bot.py
sudo systemctl restart tinki-bot
```

Data rollback:

```bash
ls -lt /opt/apps/tinki-bot/backup/data_backup_*.tar.gz
cd /opt/apps/tinki-bot
mv data data.bad_$(date +%Y%m%d_%H%M%S)
tar -xzf /opt/apps/tinki-bot/backup/data_backup_YYYYMMDD_HHMMSS.tar.gz
sudo systemctl restart tinki-bot
```
