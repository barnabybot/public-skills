---
name: model-routing
version: 1.0.0
description: >-
  Route tasks to the best eligible model across hosts (T3 Code, cmux and CLI),
  run preflight checks, manage provider circuit breakers and automated 2-hop
  takeovers, and maintain the routing catalogue. Use for /model-routing, model
  routing, preflight, provider health, circuit breaker, takeover or routing
  table checks.
fallback: >-
  If live host capabilities cannot be read, run scripts/preflight.py preflight
  with --no-live for static catalogue ordering, report unread checks explicitly
  and hold when zero eligible providers remain.
---

# Model Routing

Own the stdlib routing catalogue, host adapters (`--host t3 | cmux | cli`),
provider circuit breaker (`~/.cache/model-routing/health.json`) and automated
2-hop takeover. Resolve paths from this directory. Multi-worker dispatch and
session handoffs live in `../orchestrator/`.

## Intake

Read the request and skip settled questions.

**Action** - What routing operation is needed?
- Preflight - resolve ordered targets for a category or explicit model (`--host t3 | cmux | cli`)
- Health & takeover - inspect, record or clear circuit breaker trips, or plan automated takeover
- Routing review - check catalogue alignment or propose a table update
- settled by: preflight, route or pick model (Preflight); health, failure, trip or takeover (Health & takeover); review, check or table update (Routing review)

## Workflows

| Request | Read |
|---|---|
| Category rules, tool gates and review exclusion | [Routing rules](references/routing-rules.md) |
| Check catalogue alignment or propose a revision | [Routing review](workflows/routing-review.md) |

## CLI (`scripts/preflight.py`)

Runs strictly on the Python standard library with zero `PyYAML` dependency.
Optionally symlink it onto `PATH` or front it with a personal Home Repo CLI
(for example `b route`).

```bash
python3 scripts/preflight.py preflight --category coding --host t3 --capabilities /path/to/capabilities.json --json
python3 scripts/preflight.py preflight --category coding --host cmux --json
python3 scripts/preflight.py preflight --category coding --host cli --json
python3 scripts/preflight.py takeover --category coding --host t3 --failed-provider provider_a --error "HTTP 403 geo-block" --attempt 0 --json
python3 scripts/preflight.py health --json
python3 scripts/preflight.py record-failure --provider provider_a --error "HTTP 403 geo-block" --json
python3 scripts/preflight.py clear-health --provider provider_a --json
```

Host adapters:

- `t3` (default): emits `delegate_target` (`providerInstanceId`, `driverKind`, `model`, `options`, optional `environmentId`) and `isolation` (`shared` on linked environments, `worktree` locally), intersected with `--capabilities` when supplied.
- `cmux`: emits `agent`, `model`, `effort`, `cli_flags` and `cli_flags_str`.
- `cli`: emits a host-neutral `target` (`provider`, `model`, `effort`).

## Model preferences

Edit defaults and backups here and keep [routing-catalog.json](references/routing-catalog.json)
aligned. The placeholder rows below route `A-*` to sample `provider_a` IDs and
`B-*` to intentionally invalid IDs so an unconfigured second provider fails
loudly instead of launching the wrong model. Edit both files before dispatching
real work.

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

## Failures and fallback

`preflight` exits `0` with ordered eligible targets, `2` on invalid input and
`3` when zero eligible targets remain. On deterministic provider failures
(`http_403_geoblock`, `auth_expired`, `model_unavailable`, `quota_exhausted`,
`session_open_failure`, `linked_env_worktree_rejected`), run `takeover` to
record a 20-minute trip, enforce the 2-hop cap, preserve partial worktrees and
hold review tasks if all non-builder providers have tripped. Validate edits
with `python3 scripts/check.py --no-live --no-log`.
