---
name: orchestrator
version: 1.4.0
description: >-
  Coordinate T3 Code, cmux and CLI agents, hand off sessions and maintain model routing. Use for
  /orchestrator, /orchestrate, /handoff, handover, pickup prompts, parking notes,
  dispatching workers, fleet status, relaying comments or reviewing model routing.
fallback: If the current host has no orchestration tools, write the brief under $AGENT_NOTES/Sessions/Handoffs/ and report the path. If capacity cannot be read, report it as unread.
---

# Orchestrator

One skill owns coordination, handoff and model routing across T3 Code, cmux
and CLI subagents. Select the host with [hosts.md](references/hosts.md).
Resolve workflow and script paths from this skill directory.

**Requires** a configured routing table. The `cmux` skill is an optional
companion for dispatch into cmux workspaces. `scripts/resolve.py`
needs **PyYAML** (`python3 -m pip install --user PyYAML`); it is the one non-stdlib dependency in
this repository and it fails with that install line rather than a traceback.

## Configuration

| Variable | Default | Holds |
|---|---|---|
| `AGENT_NOTES` | `~/agent-notes` | Session notes in `Sessions/`, handoff briefs in `Sessions/Handoffs/` |

## Intake

Read the request first. Skip settled questions. Ask only for missing
information that changes the action: the worker goal, the receiver, or the
project path.

**Intent** - What is required?
- Status - inspect running work and report progress
- Dispatch - start a worker for the stated goal
- Handoff - continue, recycle, copy or park the current session
- Routing review - check preferences or prepare a proposed update
- settled by: status or "what are my agents doing" (Status); spawn or dispatch (Dispatch); handoff, handover, recycle, copy or park (Handoff); model routing or table check (Routing review)

A handoff goes straight to its workflow and needs no fleet scan. A relay names
its receiver and its message and goes straight to the status workflow.

## Workflows

| Request | Read |
|---|---|
| Status, coordination or relay | `workflows/status.md` |
| Start a worker | `workflows/dispatch.md` |
| Handoff, handover, pickup prompt, clipboard or park | `workflows/handoff.md` |
| Recycle a worker or the orchestrator | `workflows/recycle.md`, then `workflows/handoff.md` |
| Check routing, review route logs or propose new preferences | `workflows/routing-review.md` |
| Weekly Artificial Analysis ranking, or an alert from it | `workflows/routing-refresh.md` |

## Model routing table

This is the editable preference table. `scripts/resolve.py` reads these rows
directly. Choose the category with `references/routing-rules.md`; model IDs and
provider settings are in `references/routing-metadata.yaml`.

> **The rows below are a placeholder.** They carry no
> evidence and they name no real preference. `A-*` resolves to real Claude model
> IDs so a Claude-only reader can run `--tier` today. `B-*` resolves to
> deliberately invalid IDs, so a second provider you have not configured fails
> loudly instead of launching the wrong model. Edit both files before you spawn
> anything you care about.

<!-- routing-table:start -->
| Category | Name | Use when the task is to… | Default model | Effort | Backup model | Backup effort |
|---|---|---|---|---|---|---|
| finance | Finance & accounting | Build or check a financial model, databook, reconciliation, valuation or tax calculation | A-Large | xhigh | B-Large | xhigh |
| strategy | Strategy & economics | Write a plan, proposal, market sizing, competitor view, unit economics or investment thesis | A-Large | xhigh | B-Large | xhigh |
| legal | Legal | Read or mark up a contract, terms of business or regulation | A-Large | high | B-Large | high |
| writing | Writing | Draft or edit prose you present: memo, essay, post, speaker notes, fiction | A-Large | high | B-Large | high |
| visual | Visual | Make or fix how something looks: deck, slide, chart, page, image | A-Large | medium | B-Large | high |
| coding | Coding | Build or change software: skill, script, site code, scheduled job | A-Mid | high | B-Mid | high |
| systems | Systems debugging | Find why a machine, server or tool failed | A-Large | xhigh | B-Large | high |
| classification | Classification | Read each note and decide its properties, categories or links | A-Mid | medium | B-Mid | low |
| housekeeping | Housekeeping | Apply listed changes with no judgement: rename, move, given edits | A-Small | medium | B-Mid | medium |
| orchestrator | Orchestrator | Dispatch, relay, hand off | A-Large | high | B-Large | high |
| review | Review | Check finished work | Inherit reviewed category | - | Exclude builder | - |
<!-- routing-table:end -->

Three rules apply on top of the table. Presented work (finance, strategy,
legal, writing) uses max for the final look. Work the user steers through the
composer keeps its category one effort step lower. A failed first pass changes
to the backup model. Review inherits the reviewed category and excludes the
builder's provider. These preferences stay fixed when capacity is scarce:
scarcity changes the dispatched model, and never the table.

## Operating contract & verification

Read [`references/operating-contract.md`](references/operating-contract.md) for
required tool capabilities, what you must supply (`references/routing-metadata.yaml`),
startup retirement, capacity precedence, dispatch contract, operating rules,
ownership, host operations and verification test commands.
