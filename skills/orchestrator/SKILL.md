---
name: orchestrator
version: 2.0.0
disable-model-invocation: true
description: >-
  Coordinate multi-item queues, multi-repo work, parallel fan-outs and session
  handoffs. Explicit-only invocation. Use for /orchestrator, /orchestrate,
  /handoff, handover, pickup prompts, parking notes, fleet status, relaying
  comments or parallel worker dispatch.
fallback: >-
  If the current host has no orchestration tools, write a handoff brief under
  $AGENT_NOTES/Sessions/Handoffs/ and report the path. If model-routing
  preflight exits 3, report every skip reason and pause for a user ruling.
---

# Orchestrator

Coordinate multi-worker queues, multi-repo work and session handoffs. Resolve
paths from this directory. Model selection, preflight, provider health, circuit
breaker and takeover logic live in `../model-routing/` (`scripts/preflight.py`,
or your own thin front-door CLI such as `b route`). Optional `cmux` workspace
mechanics live in `../cmux/`.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/`, handoff briefs in `Sessions/Handoffs/` |

## Activation gate

Orchestration is explicit-only (`disable-model-invocation: true`). Run this
skill only when work meets one of these conditions:

- A multi-item queue with two or more independent deliverables.
- Coordinated changes spanning two or more repositories or machines.
- A parallel fan-out or cross-provider review batch.
- An explicit `/handoff`, fleet status check or peer relay request.

Single-item coding, research, writing or debugging work stays direct in the
matching domain skill with zero orchestration overhead.

## Intake

Read the request and skip settled questions. A handoff goes directly to its
workflow.

**Intent** - What action is required?
- Status - inspect open sessions, running threads and blockers
- Dispatch - delegate a multi-item queue or parallel fan-out via `model-routing`
- Handoff - continue, copy or park the current session
- settled by: status or agents doing (Status); spawn, dispatch or fan-out (Dispatch); handoff, handover, copy or park (Handoff)

## Workflows

| Request | Read |
|---|---|
| Fleet status, coordination and serialised gates | [Status](workflows/status.md) |
| Pointer-based worker dispatch | [Dispatch](workflows/dispatch.md) |
| Handoff, handover, copy or park | [Handoff](workflows/handoff.md) |

## Rules

- **Planner and script boundary.** Keep the orchestrator seat at task, dependency and handoff level. Call `../model-routing/scripts/preflight.py` (`preflight` and `takeover` with `--host t3|cmux|cli`) for every routing, health and takeover decision. Never maintain model tables or provider heuristics in prompts.
- **Thin-context pointer delegation.** Pass file paths, issue URLs, branch names and exact verification commands in worker briefs. Never paste large files, logs or diffs into a brief.
- **Serialised PR, CI, review and merge gates.** Implement in isolated worktrees, run local checks, open PRs, run independent cross-provider review on a fresh `delegate_task`, resolve findings, confirm green CI and wait for explicit merge approval before landing.
- **Handoff ceiling.** Interactive coordinators and long-lived top-level threads hand off at 30% context usage or 300k tokens, whichever comes first, writing briefs to `$AGENT_NOTES/Sessions/Handoffs/` and updating session notes in `$AGENT_NOTES/Sessions/`. Bounded `delegate_task` children and workflow workers are exempt and complete their single ticket.

Read [hosts](references/hosts.md) for host dispatch seams and
[worker behaviour](references/worker-behaviours.md) for required brief clauses.

## Failures and fallback

When a worker fails at launch or mid-flight, classify and divert through
`../model-routing/scripts/preflight.py takeover --host <t3|cmux|cli>` under its
2-hop cap and worktree salvage contract. Cancel unneeded child tasks with
`task_cancel`. If `preflight` or `takeover` exits `3`, preserve any partial
branch state, report the exact skip or escalation reasons and stop for a user
ruling.
