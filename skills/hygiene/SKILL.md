---
name: hygiene
version: 0.2.0
description: >-
  Post-event and weekly full repository hygiene sweep covering Git state, local
  hooks, binary ratchets, code-comment burn-down and ADR extraction, 150-run CI
  speed and cost audits, and architecture debt triage across one or more repos.
  Use for /hygiene, post-event hygiene, full repo hygiene check, comment ratchet
  burn-down, or cross-repo CI and architecture audits.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, AskUserQuestion
---

# Hygiene

Run a structured post-event or weekly hygiene sweep across one repository or a
fleet of repositories. Keep commit and push hooks under 9 seconds; reserve this
workflow for post-milestone and weekly reviews.

Phase 1 is strictly read-only. Inspect state, produce one ranked triage brief,
and wait for approval before editing code, opening issues, or pushing PRs.

## Intake

Skip fields already settled by the request.

**Scope** — Which repositories?
- Current repository — Audit the active checkout only.
- Fleet sweep — Fan out one read-only subagent per sibling repository under `~/Repos/*`, skipping mirror-only checkouts except for parity checks.
- settled by: a named repository path or "all repos" / "fleet".

**Depth** — Which pillars?
- Full pass (default) — All four pillars below.
- Focused — Run one named pillar (`git`, `comments`, `ci`, or `architecture`).
- settled by: a named pillar or "full hygiene".

**Writes** — Read-only or acting?
- Audit only (default) — Read-only brief with ranked zero-risk quick wins and small PR proposals.
- Apply approved slice — Execute only explicitly approved fixes in isolated branches or worktrees.
- settled by: "audit", "check", "report" (Audit only).

## Four Hygiene Pillars

1. **Git, hooks, binary ratchet, and instruction drift**
   - Inspect `git status`, ahead/behind default branch, stale branches, and inactive worktrees.
   - Verify `core.hooksPath`, `<9s` pre-commit and pre-push hooks, binary ratchet baselines, and `AGENTS.md` / `CLAUDE.md` length or retired paths.
2. **Code-comment burn-down and ratchet**
   - Load and follow [workflows/comment-burndown.md](workflows/comment-burndown.md) verbatim.
   - Apply the full four-category audit, ratchet lint rule, repeatable repo-local skill setup, and lines-shed estimate for the target scope.
3. **150-run CI speed and cost audit**
   - Run `python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150 --json`, then load and follow [workflows/ci-speed.md](workflows/ci-speed.md) verbatim.
   - Measure waiting, setup, and running at p50 and p95, enforce all budgets and honesty rules, and separate autonomous PRs from one monthly-cost approval list.
4. **Architecture and debt triage**
   - Inspect the last 15 commits and core module boundaries for shallow wrappers, boundary leaks, duplicated helpers, dead files, and untested critical paths.
   - Produce one grade (`GREEN`, `AMBER`, or `RED`), a **Zero-Risk Quick Wins** list, and a ranked list of **Proposed Small PRs**.

## Multi-Repo Subagent Fan-Out

When sweeping multiple repositories, launch one read-only subagent per repository
in parallel using the same four-pillar checklist. Dirty working trees remain
untouched during discovery. Aggregate every report into one cross-repo
scorecard, and optionally append one summary row to `$HYGIENE_EVIDENCE_LOG` or
`$AGENT_NOTES/Audits/`.

## Commands

```bash
python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150
python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150 --json
python3 scripts/ci_audit.py --repo <owner>/<repo> --dry-run --json
```
