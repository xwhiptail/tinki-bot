# HANDOFF.md

Use this file as the shared resume point between Codex and Claude Code.

## Current State

- Status: new AL2023 host is live, hardened, and running Python 3.11; local macOS repo now has a working `.venv` pytest setup, the deploy helper is adjusted for the hardened host ownership model, and the repo now includes low-cost monitoring setup helpers for AWS Budgets, CloudWatch alarms, and host memory/disk metrics
- Active branch: `main`
- Default integration preference: verify changes, then merge locally into `main`; only keep branch or PR flow when explicitly requested
- Last known good verification: `python -m pytest -q` locally (`248 passed`) and `python scripts/publish_host_metrics.py --help` plus `python scripts/setup_low_cost_monitoring.py --help`
- Next concrete task: deploy the new `scripts/` helpers, run remote low-cost monitoring setup with a real alert email, then install the host metrics timer on the EC2 box

## Resume Checklist

1. Pull or otherwise sync from the real remote branch before making changes.
2. `git status --short --branch`
3. Read this file, then read `AGENTS.md` and `CLAUDE.md`
4. If the task touches runtime behavior, run the narrowest relevant test first
5. If commands or listeners changed, update `tests/test_tinki_bot.py` and `docs/command-test-map.md` before handing off

## Normal Flow

Use this as the default workflow unless the user says otherwise:

1. Sync from remote.
2. Check status.
3. Read handoff and repo instructions.
4. Inspect the smallest relevant code path and tests.
5. Make the smallest focused change.
6. Run the narrowest relevant test first; run full `python -m pytest` when the change is broad.
7. If text or emoji output changed, run the mojibake scan.
8. Update docs when behavior, commands, setup, or deploy flow changed. Keep command-related edits paired with test updates and a refreshed `docs/command-test-map.md`.
9. Review the diff.
10. Commit the change and merge it locally into `main` unless the user explicitly asks to keep it on a branch.
11. Push the updated `main` branch before handing off, unless the user said not to push.
12. Push to GitLab too when that mirror is part of the normal release path on this machine.
13. Deploy to the bot with `.\deploy-ec2.ps1` when the user wants the change live.

## Cross-Agent Git Rules

- Start by pulling or syncing from the real remote branch.
- After making repo changes, prefer merging locally into `main` before handing the task off unless the user explicitly asks to keep a separate branch.
- Push merged `main` before handing the task off unless the user explicitly says not to push yet.
- Prefer a real commit on `main` over unstaged local changes.
- If work is not ready to commit, use a named stash and record it here.
- Do not create local branches named like remote refs such as `origin/main`.
- Before handing work from one tool to the other, update this file with:
  - what changed
  - what is still pending
  - what tests passed
  - whether a stash exists

## Active Stashes

- None

## Notes For Next Agent

- Live bot host is now `t3a.nano` AL2023 at `98.92.242.38`.
- Old host `52.91.60.81` has `tinki-bot.service` stopped and disabled.
- `deploy-ec2.local.sh` points at the new host.
- New host hardening: `tinki-bot.service` runs as service user `tinki-bot`; `ec2-user` only keeps limited passwordless sudo for `systemctl ... tinki-bot`, while in-bot `!restart`/`!deploy` now rely on `Restart=always` by terminating the service process instead of invoking sudo.
- Admin diagnostics now use a shared in-bot lock plus per-step timeouts, so startup diagnostics, `!runtests`, and `!testurls` no longer stack on top of each other and pin the `t3a.nano`.
- Local and remote pytest noise is reduced by pinning `python-Levenshtein` for `fuzzywuzzy` and filtering the known third-party `matplotlib`/`pyparsing`, `discord.py audioop`, and pre-speedup `SequenceMatcher` warnings in `pytest.ini`.
- The live host venv is currently not writable by `ec2-user`, so the bot now also suppresses the optional `fuzzywuzzy` speedup warning at import time until the venv permissions are normalized.
- Remote wrapper scripts now use `/opt/apps/tinki-bot/myenv/bin/python` instead of the retired `python3.8` path.
- New host runtime upgrade: `/opt/apps/tinki-bot/myenv/bin/python` is now Python `3.11.14`; previous venv backup is kept at `/opt/apps/tinki-bot/myenv.py39.20260418_175337`.
- Host maintenance headroom: `/swapfile_tinki` is enabled and persisted in `/etc/fstab` to avoid OOM kills during `dnf` and venv rebuilds on the `t3a.nano`.
- Future host replacement work must restore both `/opt/apps/tinki-bot/data` and `/etc/tinki-bot.env`, not just repo code.
- Local macOS testing uses repo-local `.venv`; run `. .venv/bin/activate && pytest -q`.
- `scripts/remote-common.sh` now streams recursive uploads with tar instead of `scp -r`, excluding cache junk and macOS metadata files.
- `deploy-ec2.sh` treats remote cache cleanup as best-effort so deploys stay quiet on the hardened `tinki-bot` ownership model.
- New low-cost monitoring helpers:
  - `scripts/setup_low_cost_monitoring.py` creates or updates the SNS topic, CloudWatch alarms, and monthly AWS budget
  - `scripts/publish_host_metrics.py` publishes memory/disk metrics
  - `scripts/install_host_metrics_timer.sh` installs a 5-minute systemd timer on the host
  - remote wrappers exist for both shell and PowerShell flows
- The monitoring setup prints public IPv4, root volume, and T4g follow-up notes, but does not auto-modify the instance family or root volume type.
