---
name: hygiene
version: 0.3.0
description: >-
  Post-event and weekly full repository hygiene sweep covering Git state, local
  hooks, binary ratchets, code-comment burn-down and ADR extraction, 150-run CI
  speed and cost audits, architecture debt triage, and agent safety and
  blast-radius audits across one or more repos. Use for /hygiene, post-event
  hygiene, full repo hygiene check, comment ratchet burn-down, CI and
  architecture audits, or agent safety and blast-radius audits.
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
- Full pass (default) — All five pillars below.
- Focused — Run one named pillar (`git`, `comments`, `ci`, `architecture`, or `safety`).
- settled by: a named pillar or "full hygiene".

**Writes** — Read-only or acting?
- Audit only (default) — Read-only brief with ranked zero-risk quick wins and small PR proposals.
- Apply approved slice — Execute only explicitly approved fixes in isolated branches or worktrees.
- settled by: "audit", "check", "report" (Audit only).

## Five Hygiene Pillars

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
   - When the target repository contains frontend web code (`astro.config.*`, `src/**/*.astro`, `src/**/*.css`, or browser JS), run `npx --yes modern-web-guidance@latest legacy-scan . --json` during Phase 1 discovery. Filter findings with its `keepWhen` / `dropWhen` rubrics and a Safari / iOS Safari Baseline Widely Available check. Surface only verified wins as optional small PRs. Never auto-edit, and never wire the scanner into `<9s` git hooks because `npx` requires network access.
   - Produce one grade (`GREEN`, `AMBER`, or `RED`), a **Zero-Risk Quick Wins** list, and a ranked list of **Proposed Small PRs**.
5. **Agent safety and blast-radius audit**
   - Load and follow [workflows/safety-audit.md](workflows/safety-audit.md) verbatim.
   - Audit the repository and dev setup across all 11 checks without printing secret values, rank fixes by blast radius (top 3 first), separate in-repo fixes from manual steps, and wait for approval before changing files.

## Multi-Repo Subagent Fan-Out

When sweeping multiple repositories, launch one read-only subagent per repository
in parallel using the same five-pillar checklist. Dirty working trees remain
untouched during discovery. Aggregate every report into one cross-repo
scorecard, and optionally append one summary row to `$HYGIENE_EVIDENCE_LOG` or
`$AGENT_NOTES/Audits/`.

## Commands

```bash
python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150
python3 scripts/ci_audit.py --repo <owner>/<repo> --limit 150 --json
python3 scripts/ci_audit.py --repo <owner>/<repo> --dry-run --json
```
