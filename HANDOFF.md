# HANDOFF.md

Use this file as the shared resume point between Codex and Claude Code.

## Current State

- Status: Tinki can now be mentioned with a Discord message link to reply directly to that linked message when it is in the current server, plain-text messages that clearly talk about Tinki/the bot can wake her without a ping, simple bot-status chatter like dead/alive/dumb gets a deterministic self-status reply before OpenAI, generated replies get final cleanup for old creature-label drift, pasted Discord message links and preview-surfaced mentions after a link no longer count as speaking to Tinki, erotic/spicy writing requests are deterministically deflected into a playful public tease before OpenAI, calculator-vs-Final-Fantasy `DRG` context and context-switch bait are answered deterministically before OpenAI, her core prompt now makes her a cutesy gnome with a soft grunge side and explicit expertise in World of Warcraft and Final Fantasy XIV/FFXIV, AI prompts include current America/New_York and UTC date/time plus cached live source snippets for fresh/recent gaming/world questions including RoR2/DLC phrasing, current-source snippets prefer official game sources when available, released/live questions are distinguished from announced/upcoming/next-news questions, remembered facts/recent history are treated as low-confidence hints that require relevance unless the user explicitly asks for memory lookup, correction-bait chatter is not saved as future topic context, and source-backed direct answers are validated before Tinki replies so stale model memory cannot override the lookup; OpenAI insufficient-quota failures produce a distinct out-of-money response; GPT-5 chat completion calls use `max_completion_tokens`; Instagram URL rewrites target `vxinstagram.com`; the shell deploy helper overwrites existing repo files during recursive uploads on AL2023; new AL2023 host is live, hardened, and running Python 3.11; local macOS repo has a working `.venv` pytest setup, and the repo includes low-cost monitoring setup helpers for AWS Budgets, CloudWatch alarms, and host memory/disk metrics
- Active branch: `main`
- Default integration preference: verify changes, then merge locally into `main`; only keep branch or PR flow when explicitly requested
- Last known good verification: `.venv/bin/python -m pytest -q` locally (`337 passed`) after tightening memory/history relevance and correction-bait handling, plus focused regression coverage, collect-only, `TestNoMojibake`, and `git diff --check`
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
- 2026-05-07: Split OpenAI failure copy so `insufficient_quota`, current-quota, and billing-detail errors return "My OpenAI coin purse is empty..." while other OpenAI failures keep the generic rate-limit/unavailable fallback. Updated command-test map and pytest coverage; full local pytest passed (`283 passed`).
- 2026-05-07: Tightened "speak when spoken to" behavior so Discord message-link previews and reply pings do not count as Tinki mentions. Only actual `<@Tinki>` text triggers AI mention handling or linked-message replies; explicit mentions in tracked random-AI replies still work after stripping the mention token. Updated README, `!commands`, command-test map, and pytest coverage; full local pytest passed (`284 passed`).
- 2026-05-07: Tightened the Discord message-link gate again so a bot mention token that appears after the first Discord message link is ignored, covering preview-surfaced mentions in pasted links. Also normalized GPT-5 chat completion calls from `max_tokens` to `max_completion_tokens` after live OpenAI logs showed a 400 unsupported-parameter error. Updated README, command-test map, and pytest coverage; full local pytest passed (`286 passed`) and a remote GPT-5-mini sanity call returned 200 OK.
- 2026-05-07: Added a deterministic erotic/spicy request trap in the AI mention path. Requests for erotic writing or spicy writing get a playful public roast before any OpenAI generation, while normal food uses such as "spicy ramen" still route through regular AI handling. Updated README, command-test map, and pytest coverage; full local pytest passed (`289 passed`).
- 2026-05-08: Added deterministic `DRG` context handling so calculator questions and calculator-context corrections always answer `Degrees, Radians, and Gradians`, Final Fantasy context answers `Dragoon`, and "you hallucinated calculator" style denials are checked against conversation history before OpenAI. Updated README, command-test map, and pytest coverage; full local pytest passed (`293 passed`).
- 2026-05-08: Tightened `DRG` handling again for "I was talking about Final Fantasy" context-switch bait after a calculator-context exchange, so Tinki keeps the original receipt while acknowledging the Final Fantasy meaning. Also updated the core prompt to make her explicitly expert in World of Warcraft and Final Fantasy XIV/FFXIV. Updated README, command-test map, and pytest coverage; full local pytest passed (`295 passed`).
- 2026-05-08: Added current-awareness context for AI replies. Prompts now include America/New_York and UTC date/time, fresh gaming/world questions fetch cached source snippets from RSS/search feeds, and live lookup failures explicitly tell the model not to invent facts or ask for dates already provided. The AoE4 May 7 sanity fetch returned official Age of Empires/Xbox feed snippets for Yue Fei's Legacy and the Jin Dynasty civilization. Updated README, command-test map, and pytest coverage; full local pytest passed (`303 passed`).
- 2026-05-08: After the current-awareness deploy first failed to add the new `utils/current_awareness.py` file because remote repo subdirectories were not group-writable, runtime bootstrap was extended to normalize `/opt/apps/tinki-bot/repo` permissions on startup too. Updated README/INSTALL/HANDOFF and runtime-bootstrap coverage; full local pytest passed (`304 passed`).
- 2026-05-08: Hardened current-awareness against stale model answers. The feed fetcher no longer stops after old Google News items before checking official game feeds, FFXIV current-expansion lookups include the official Dawntrail page, source context can include direct answer hints, and grounded reply validation/fallback rejects stale AoE4 "Ottomans" answers and FFXIV "Evercold is current" answers when sources resolve them. Updated README, command-test map, and pytest coverage; full local pytest passed (`312 passed`).
- 2026-05-08: Extended the current-awareness guard to "most recent" game questions after the live bot treated Resident Evil Requiem as only announced and called Resident Evil 4 Remake the newest released entry. "Most recent Resident Evil game" now triggers live context, pulls Capcom's Requiem press release directly, adds a released direct-answer hint, and rejects stale RE4 fallback drafts. Updated README, command-test map, and pytest coverage; full local pytest passed (`317 passed`).
- 2026-05-08: Softened Tinki's core personality prompt from harsher snark/roast language to cutesy gnome energy with a soft grunge side. Random thoughts, reaction replies, and reply-to-reply prompts now ask for playful teasing and scuffed-edge quips instead of roast-first language. Updated README and prompt coverage.
- 2026-05-08: Added automatic AI wake-up for plain-text messages that clearly talk about Tinki/the bot without a ping. The matcher covers direct Tinki names, `the/this/that/our/your bot`, and narrow bot-status pronoun phrases like `she ain't working`, while still ignoring Discord-link preview text and unrelated `bot lane` chatter. Updated README, `!commands`, command-test map, and listener coverage.
- 2026-05-08: Tightened the plain-text Tinki/the-bot wake-up behavior for screenshot-style status chatter. Dead/broken, dumb/useless, and alive/back comments now get deterministic self-status replies before OpenAI, and the core prompt now explicitly keeps Tinki gnome-coded without old creature-label drift. Updated README, command-test map, and focused coverage.
- 2026-05-08: Hardened the screenshot regressions where OpenAI could still emit old creature labels and RoR2 DLC questions did not trigger live context. Generated AI replies now sanitize old creature-label drift unless the text is clearly factual game/race context, and current-awareness recognizes `RoR2`/`Risk of Rain 2` plus DLC/release-date phrasing. Updated README, command-test map, and focused coverage.
- 2026-05-08: Tightened memory/history behavior so Tinki does not overfit stale context or correction bait. Saved facts/topics now require query overlap unless the user is explicitly asking for a memory lookup, general recent history no longer falls back to stale last messages, and user correction bait like "that's wrong"/"I never said" does not become future topic context. Updated README, command-test map, and focused coverage; full local pytest passed (`337 passed`).
- Live bot host is now `t3a.nano` AL2023 at `98.92.242.38`.
- Old host `52.91.60.81` has `tinki-bot.service` stopped and disabled.
- `deploy-ec2.local.sh` points at the new host.
- New host hardening: `tinki-bot.service` runs as service user `tinki-bot`; `ec2-user` only keeps limited passwordless sudo for `systemctl ... tinki-bot`, while in-bot `!restart`/`!deploy` now rely on `Restart=always` by terminating the service process instead of invoking sudo.
- Admin diagnostics now use a shared in-bot lock plus per-step timeouts, so startup diagnostics, `!runtests`, and `!testurls` no longer stack on top of each other and pin the `t3a.nano`.
- Startup `pytest -q` now uses a `35s` wall-clock timeout after a measured host run took about `21.5s` real time on the `t3a.nano`.
- Local and remote pytest noise is reduced by pinning `python-Levenshtein` for `fuzzywuzzy` and filtering the known third-party `matplotlib`/`pyparsing`, `discord.py audioop`, and pre-speedup `SequenceMatcher` warnings in `pytest.ini`.
- The live host venv is currently not writable by `ec2-user`, so the bot now also suppresses the optional `fuzzywuzzy` speedup warning at import time until the venv permissions are normalized.
- The bot runtime now self-heals `/opt/apps/tinki-bot/repo` and `/opt/apps/tinki-bot/myenv` group-write permissions on startup and installs the pinned `python-Levenshtein` speedup package if it is missing.
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
