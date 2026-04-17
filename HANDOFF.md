# HANDOFF.md

Use this file as the shared resume point between Codex and Claude Code.

## Current State

- Status: idle
- Active branch: `main`
- Last known good verification: `python -m pytest`
- Next concrete task: none

## Resume Checklist

1. Pull or otherwise sync from the real remote branch before making changes.
2. `git status --short --branch`
3. Read this file, then read `AGENTS.md` and `CLAUDE.md`
4. If the task touches runtime behavior, run the narrowest relevant test first

## Normal Flow

Use this as the default workflow unless the user says otherwise:

1. Sync from remote.
2. Check status.
3. Read handoff and repo instructions.
4. Inspect the smallest relevant code path and tests.
5. Make the smallest focused change.
6. Run the narrowest relevant test first; run full `python -m pytest` when the change is broad.
7. If text or emoji output changed, run the mojibake scan.
8. Update docs when behavior, commands, setup, or deploy flow changed.
9. Review the diff.
10. Commit and push before handing off, unless the user said not to push.

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

- None
