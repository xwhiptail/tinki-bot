# HANDOFF.md

Use this file as the shared resume point between Codex and Claude Code.

## Current State

- Status: new AL2023 host is live, hardened, and running Python 3.11; repo still has local unpushed security-hardening edits
- Active branch: `main`
- Last known good verification: `python -m pytest` locally and `python -m pytest -q` on the new EC2 host under Python 3.11 (`234 passed`)
- Next concrete task: if doing future host migration or rebuild work, copy `/opt/apps/tinki-bot/data` and `/etc/tinki-bot.env` before cutover

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
10. Commit and push before handing off, unless the user said not to push.
11. Push to GitLab too when that mirror is part of the normal release path on this machine.
12. Deploy to the bot with `.\deploy-ec2.ps1` when the user wants the change live.

## Cross-Agent Git Rules

- Start by pulling or syncing from the real remote branch.
- After making repo changes, push them before handing the task off unless the user explicitly says not to push yet.
- Prefer a real branch or a real commit over unstaged local changes.
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
- New host hardening: `tinki-bot.service` runs as service user `tinki-bot`; `ec2-user` only keeps limited passwordless sudo for `systemctl ... tinki-bot`.
- Remote wrapper scripts now use `/opt/apps/tinki-bot/myenv/bin/python` instead of the retired `python3.8` path.
- New host runtime upgrade: `/opt/apps/tinki-bot/myenv/bin/python` is now Python `3.11.14`; previous venv backup is kept at `/opt/apps/tinki-bot/myenv.py39.20260418_175337`.
- Host maintenance headroom: `/swapfile_tinki` is enabled and persisted in `/etc/fstab` to avoid OOM kills during `dnf` and venv rebuilds on the `t3a.nano`.
- Future host replacement work must restore both `/opt/apps/tinki-bot/data` and `/etc/tinki-bot.env`, not just repo code.
