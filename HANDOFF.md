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
