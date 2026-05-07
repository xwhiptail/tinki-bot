# HANDOFF.md

Use this file as the shared resume point between Codex and Claude Code.

## Current State

- Status: Tinki can now be mentioned with a Discord message link to reply directly to that linked message when it is in the current server, pasted links to Tinki-authored messages can be answered without an explicit mention, and OpenAI quota/rate-limit failures now produce a clear in-channel fallback instead of the generic error; Instagram URL rewrites target `vxinstagram.com`; the shell deploy helper overwrites existing repo files during recursive uploads on AL2023; new AL2023 host is live, hardened, and running Python 3.11; local macOS repo has a working `.venv` pytest setup, and the repo includes low-cost monitoring setup helpers for AWS Budgets, CloudWatch alarms, and host memory/disk metrics
- Active branch: `main`
- Default integration preference: verify changes, then merge locally into `main`; only keep branch or PR flow when explicitly requested
- Last known good verification: `python -m pytest -q` locally (`282 passed`) after adding OpenAI-unavailable fallbacks for AI replies, plus `python -m pytest --collect-only -q`, a focused AI listener/random-task slice, a mojibake scan, a temp `remote_copy` overwrite test after the deploy helper fix, and a remote post-deploy rewrite sanity check
- Next concrete task: resume the low-cost monitoring setup helpers when appropriate

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

- 2026-05-03: Instagram rewrite root cause was `eeinstagram.com` returning a redirect page back to Instagram for the repro reel, while `vxinstagram.com` returned video/player Open Graph metadata for the same URL. Updated `utils/url_rewriter.py`, `utils/selftests.py`, and `tests/test_tinki_bot.py`; full local pytest passed (`274 passed`).
- 2026-05-03: First `./deploy-ec2.sh` attempt failed during recursive `utils/` upload because remote GNU tar refused existing files with the helper's previous extraction flags. Updated `scripts/remote-common.sh` to pass `--overwrite`; verified by uploading a temp directory twice with `remote_copy` and reading back the replaced content.
- 2026-05-03: Deployed the Instagram rewrite fix to the live host; remote check rewrote the repro reel to `https://vxinstagram.com/reel/DXj7CbAjlCQ/?igsh=MTdtNTdwZnFajY5NA==` and `tinki-bot.service` reported active.
- 2026-05-03: Local pytest initially failed because `tests/test_tinki_bot.py::TestRemoteCommonScript::test_remote_copy_recursive_streams_tar_instead_of_scp` still asserted the old `--no-overwrite-dir` extraction flag. Updated it to assert `--overwrite`; full pytest passed (`274 passed`).
- 2026-05-05: Added AI listener support for `@Tinki-bot <Discord message link> [instruction]`. Tinki rejects links outside the current server, preserves hard-stop refusals before link handling, fetches accessible target messages, and replies directly to the linked message with `mention_author=False`. Updated README, `!commands`, command-test map, and pytest coverage; full local pytest passed (`277 passed`).
- 2026-05-05: Added AI listener support for bare pasted links to Tinki-authored Discord messages, so `<instruction> <Tinki Discord message link>` replies directly to the linked Tinki message without requiring a fresh mention. Links to non-Tinki messages stay silent unless Tinki is explicitly mentioned, and hard-stop refusals still short-circuit before AI generation. Updated README, `!commands`, command-test map, and pytest coverage; full local pytest passed (`280 passed`).
- 2026-05-07: Investigated live `@Tinki-bot hi` failures via `journalctl`; root cause was OpenAI `429 insufficient_quota`, not Discord/service downtime. Added a shared safe OpenAI completion wrapper so AI mention, reaction, reply, and linked-message generation return a clear quota/rate-limit fallback instead of throwing; random AI posting skips empty generation results. Updated command-test map and pytest coverage; full local pytest passed (`282 passed`).
- Live bot host is now `t3a.nano` AL2023 at `98.92.242.38`.
- Old host `52.91.60.81` has `tinki-bot.service` stopped and disabled.
- `deploy-ec2.local.sh` points at the new host.
- New host hardening: `tinki-bot.service` runs as service user `tinki-bot`; `ec2-user` only keeps limited passwordless sudo for `systemctl ... tinki-bot`, while in-bot `!restart`/`!deploy` now rely on `Restart=always` by terminating the service process instead of invoking sudo.
- Admin diagnostics now use a shared in-bot lock plus per-step timeouts, so startup diagnostics, `!runtests`, and `!testurls` no longer stack on top of each other and pin the `t3a.nano`.
- Startup `pytest -q` now uses a `35s` wall-clock timeout after a measured host run took about `21.5s` real time on the `t3a.nano`.
- Local and remote pytest noise is reduced by pinning `python-Levenshtein` for `fuzzywuzzy` and filtering the known third-party `matplotlib`/`pyparsing`, `discord.py audioop`, and pre-speedup `SequenceMatcher` warnings in `pytest.ini`.
- The live host venv is currently not writable by `ec2-user`, so the bot now also suppresses the optional `fuzzywuzzy` speedup warning at import time until the venv permissions are normalized.
- The bot runtime now self-heals `/opt/apps/tinki-bot/myenv` group-write permissions on startup and installs the pinned `python-Levenshtein` speedup package if it is missing.
- New admin command: `!statusreport` posts a concise EC2/runtime summary plus a `status_report.txt` attachment covering deploy commit, uptime, load, memory, swap, disk, Python runtime, and EC2 metadata when IMDS is available.
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
