# Routing rules

The model table in `SKILL.md` and the ranked fallback chains in
`references/routing-catalog.json` form the single routing specification.
`scripts/preflight.py` reads `routing-catalog.json`, checks enabled providers,
active circuit breakers and optional live host capabilities, and returns
host-shaped targets for `--host t3`, `--host cmux` or `--host cli`.

## Required tool capabilities

Determine tool requirements before choosing a category. These rules precede
provider preferences and fallback order:

- Image generation or editing requires an exposed image-generation tool.
  Confirm the receiver exposes it before launching.
- Desktop UI automation requires connected OS accessibility or computer-use
  tools. Confirm those tools on the receiver before launching.
- Record required tools in the brief. If a receiver lacks a required tool, stop
  and hand back the task.

HTML, CSS, charts and slide layout use the `visual` category.

## Choosing a category

Read the request verb, its object and the output the user will receive. Take
the first matching category:

1. **orchestrator** when the request names the orchestrator seat or fleet coordination.
2. **review** when the verb is review, check, audit, critique or second opinion on finished work. Pass `--category review --of <category> --builder <provider>`. The builder provider is always excluded.
3. **visual** when appearance defines done (layout, slide, palette, UI, render, chart look, screenshots).
4. **writing** when the output is prose to present or publish (executive summary, memo, essay, post, speaker notes, editorial pass, fiction).
5. **finance** when the work is numbers (databook, model, reconciliation, valuation, financial tables, tax).
6. **legal** when the object is a contract, terms of business, RFP terms or regulation.
7. **strategy** when the output is a business or market argument (plan, proposal, market sizing, competitor view, unit economics, thesis).
8. **classification** when each item needs content judgement (assign YAML properties, categories, topics or links across notes).
9. **housekeeping** when files or a glob are listed explicitly and the edit needs no judgement (rename, move, mechanical edits).
10. **systems** when a machine, server or tool failed with an unknown cause, or a prior coding pass found no cause.
11. **coding** for all other software builds, fixes or refactors.

Split multi-output requests into separate dispatches. Financial tables use
`finance`; narrative memo prose uses `writing`.

Two modifiers apply after category selection:

- **Final pass.** `finance`, `strategy`, `legal` and `writing` run their final pass at `max` effort when supported.
- **Steered iteration.** When the user iterates turn by turn, step effort down by one level.

## Fallback chains, preflight and circuit breaker

Every category defines a ranked fallback chain across at least two distinct
providers in `references/routing-catalog.json`. Disabled or `explicit_only`
providers stay out of default chains until enabled or requested via `--model`.

`scripts/preflight.py preflight` checks enabled providers, active short-TTL
circuit breaker trips in `~/.cache/model-routing/health.json`, and on
`--host t3` live capabilities and linked-environment `shared` isolation. Hard
launch or mid-flight failures divert automatically through
`scripts/preflight.py takeover --host <t3|cmux|cli>` under the 2-hop cap.

## Independent review

When two non-builder providers are eligible, reviews of `systems`, `finance`,
`strategy`, `legal` or `writing` work may run two reviewers in parallel from
the same neutral brief. Deduplicate findings, tag each by provider, and report
coverage alongside every zero count. Fallback never selects the builder
provider; hold and ask the user if all non-builder providers trip.

## Revising preferences

Follow `workflows/routing-review.md`. Apply catalogue and table updates only
after explicit user approval. Validate changes with
`python3 scripts/check.py --no-live --no-log`.
