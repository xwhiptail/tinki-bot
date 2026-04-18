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
`systemctl ... tinki-bot` so `!restart`, `!deploy`, and the checked-in deploy helpers still work
without leaving the full host under `NOPASSWD: ALL`.

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

If you want `!awscost` and deploy-time AWS cost reporting, the bot runtime also needs AWS credentials with Cost Explorer access.

If you are migrating to a brand new EC2 host instead of doing a normal code deploy, copy the live runtime state too:

- `/opt/apps/tinki-bot/data`
- `/etc/tinki-bot.env`

The deploy scripts update code, but host migration still requires those runtime files to be restored on the new machine before cutover.

For repeated remote maintenance from Windows, prefer the wrapper scripts in `scripts/` instead of building inline `plink` commands:

```powershell
.\scripts\Run-RemotePytest.ps1
.\scripts\Check-RemoteAwsCost.ps1
```

On macOS/Linux, use the shell wrappers:

```bash
./scripts/run-remote-pytest.sh
./scripts/check-remote-awscost.sh
```

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
