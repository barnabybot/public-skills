---
name: orchestrator
version: 1.3.1
description: >-
  Coordinate cmux agents, hand off sessions and maintain model routing. Use for
  /orchestrator, /orchestrate, /handoff, handover, pickup prompts, parking notes,
  dispatching workers, fleet status, relaying comments or reviewing model routing.
fallback: If cmux is unavailable, write the brief under $AGENT_NOTES/Sessions/Handoffs/ and report the path. If capacity cannot be read, report it as unread.
---

# Orchestrator

One skill owns coordination, handoff and model routing. `cmux` supplies the
workspace commands. Resolve workflow and script paths from this skill directory.

**Requires** the `cmux` skill for anything that spawns. `scripts/resolve.py`
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
| review | Review | Check finished work | Inherit reviewed category | — | Exclude builder | — |
<!-- routing-table:end -->

Three rules apply on top of the table. Presented work (finance, strategy,
legal, writing) uses max for the final look. Work the user steers through the
composer keeps its category one effort step lower. A failed first pass changes
to the backup model. Review inherits the reviewed category and excludes the
builder's provider. These preferences stay fixed when capacity is scarce:
scarcity changes the dispatched model, and never the table.

## What you must supply

The rule generalises. The table does not. Four things are yours:

1. **Model IDs**, in `references/routing-metadata.yaml`. Replace every
   `REPLACE-WITH-...` value with an ID your CLI accepts. Pin full IDs, because
   aliases like `opus` and `sonnet` re-resolve to whatever the current
   generation ships and a seat pinned to an alias changes model under you.
2. **Which model sits in which category**, in the marked table above. Start from the
   shape, then let the route logs tell you which rows earn their seat.
3. **A second provider.** The resolver refuses a table whose backup shares a
   provider with its default, because a same-provider backup fails at exactly
   the moment you need it. If you genuinely run one provider, that refusal is
   the skill telling you the backup column is decoration.
4. **A capacity meter**, if you want one. Both providers ship `codexbar: null`,
   so capacity reads as unread and every row dispatches as written. Point
   `codexbar` at the provider name your meter reports and the same resolver
   starts taking the backup on exhaustion. `references/routing-rules.md`
   describes the states it distinguishes.

## Dispatch contract

Choose the category, then call the cmux helper:

```bash
<path-to>/skills/cmux/scripts/spawn-workspace.sh "<name>" \
  --tier systems --reason "prior pass found no cause" \
  --cwd "$HOME/code/<repo>" --worktree \
  --prompt-file "$AGENT_NOTES/Sessions/Handoffs/YYYY-MM-DD <slug>.md"
```

The helper reads this package's resolver, checks capacity, sets model and
effort, and writes the route to the session note. An exhausted default takes
its eligible backup; no eligible capacity returns exit 3 before a workspace is
created. Quote the returned route and verify the worker's model, effort and
cwd.

For a successor, preserve the predecessor's `--model`, `--effort` and cwd. A
model the user names explicitly also uses `--model` and `--effort`. See
`references/worker-behaviours.md` for runtime-specific limits.

## Operating rules

- One workspace per goal. Use workspace names in reports and IDs in tool calls.
- A handoff or handover opens a new workspace. Clipboard and park require an
  explicit request.
- Write the brief under `$AGENT_NOTES/Sessions/Handoffs/` before delivery. Keep
  session records under `$AGENT_NOTES/Sessions/`.
- Carry existing authorisation into the brief. Ask only for an unresolved
  decision or a required approval.
- Inspect workers without changing focus. Submit only messages the conversation
  authorised; composer suggestions carry no authority. `workflows/status.md`
  has the tells for telling one from the other.
- Check evidence before reporting completion. A worker's zero is a measurement
  and needs a coverage statement: what the instrument looked for, and what it
  did not.
- Close workers with `cmux/scripts/close-workspace.sh`, so their notes close
  too.

## Ownership

This skill owns the routing table, the category rule, the resolver and their
checks. Routing is dispatch policy, and the seat that dispatches keeps the
policy. Splitting the table from the rule that reads it gives one table two
owners, which is how a table and its documentation drift apart.

## Verification

```bash
python3 scripts/check.py --no-live --no-log     # after editing the table
python3 scripts/test_resolve.py                 # after changing routing code
python3 scripts/test_aa_refresh.py              # after changing the AA refresh
```

All three run against fixtures, so none creates a workspace or contacts a
provider. `workflows/routing-refresh.md` proposes table changes weekly from
Artificial Analysis.
