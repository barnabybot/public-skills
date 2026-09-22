---
name: orchestrator
version: 1.1.0
description: >-
  Coordinate cmux agents and maintain model routing. Use for /orchestrator,
  /orchestrate, orchestrator mode, dispatching workers, fleet status, relaying
  comments or reviewing model routing.
fallback: If cmux is unavailable, write the brief under $AGENT_NOTES/Sessions/Handoffs/ and report the path. If capacity cannot be read, report it as unread.
---

# Orchestrator

One skill owns coordination and model routing. `cmux` supplies the workspace
commands; `handoff` carries session succession. Resolve workflow and script
paths from this skill directory.

**Requires** the `cmux` skill for anything that spawns. `scripts/resolve.py`
needs **PyYAML** (`pip install PyYAML`); it is the one non-stdlib dependency in
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
- Routing review - check preferences or prepare a proposed update
- settled by: status or "what are my agents doing" (Status); spawn or dispatch (Dispatch); model routing or table check (Routing review)

A handoff goes to the `handoff` skill and needs no fleet scan. A relay names
its receiver and its message and goes straight to the status workflow.

## Workflows

| Request | Read |
|---|---|
| Status, coordination or relay | `workflows/status.md` |
| Start a worker | `workflows/dispatch.md` |
| Recycle a worker or the orchestrator | `workflows/recycle.md` |
| Check routing, review route logs or propose new preferences | `workflows/routing-review.md` |
| Hand off, park, or write a pickup prompt | the `handoff` skill |

## Model routing table

This is the editable preference table. `scripts/resolve.py` reads these rows
directly. Choose the tier with `references/routing-rules.md`; model IDs and
provider settings are in `references/routing-metadata.yaml`.

> **The rows below are a placeholder.** They carry no
> evidence and they name no real preference. `A-*` resolves to real Claude model
> IDs so a Claude-only reader can run `--tier` today. `B-*` resolves to
> deliberately invalid IDs, so a second provider you have not configured fails
> loudly instead of launching the wrong model. Edit both files before you spawn
> anything you care about.

<!-- routing-table:start -->
| Tier | Work | Default model | Effort | Backup model | Backup effort |
|---|---|---|---|---|---|
| O | Orchestrator | A-Large | high | B-Large | high |
| A | Mechanical | A-Small | medium | B-Mid | medium |
| B | Bounded | A-Mid | high | B-Mid | high |
| C | Everyday | A-Mid | high | B-Mid | high |
| D | Iterative | A-Large | high | B-Large | high |
| E | Hard | A-Large | xhigh | B-Large | high |
| F | Consequential | A-Large | high | B-Large | high |
| V | Visual | A-Large | medium | B-Large | high |
| R | Review | Inherit reviewed tier | — | Exclude builder | — |
<!-- routing-table:end -->

Review (R) inherits the reviewed tier and excludes the builder's provider. F
uses max for the final look. These preferences stay fixed when capacity is
scarce: scarcity changes the dispatched model, and never the table.

## What you must supply

The rule generalises. The table does not. Four things are yours:

1. **Model IDs**, in `references/routing-metadata.yaml`. Replace every
   `REPLACE-WITH-...` value with an ID your CLI accepts. Pin full IDs, because
   aliases like `opus` and `sonnet` re-resolve to whatever the current
   generation ships and a seat pinned to an alias changes model under you.
2. **Which model sits in which tier**, in the marked table above. Start from the
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

Choose the tier, then call the cmux helper:

```bash
<path-to>/skills/cmux/scripts/spawn-workspace.sh "<name>" \
  --tier E --reason "prior pass found no cause" \
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

This skill owns the routing table, the tiering rule, the resolver and their
checks. Routing is dispatch policy, and the seat that dispatches keeps the
policy. Splitting the table from the rule that reads it gives one table two
owners, which is how a table and its documentation drift apart.

## Verification

```bash
python3 scripts/check.py --no-live --no-log     # after editing the table
python3 scripts/test_resolve.py                 # after changing routing code
```

Both run against the fixtures in `scripts/fixtures/`, so neither creates a
workspace or contacts a provider.
