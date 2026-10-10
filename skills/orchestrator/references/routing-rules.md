# Routing rules

The model table in `SKILL.md` is the only preference table. `scripts/resolve.py` reads it and the provider metadata, checks capacity, and returns the route. The cmux helper launches that route.

## Required tool capabilities

Check the tools required by the task before choosing its category. Image
generation and image editing need a runtime with an exposed image generation
tool. Mac app interaction needs connected Computer Use tools; prefer Codex
Desktop when available. A model name alone does not establish tool access.

Confirm the receiving runtime has the tool before launch and require it to
check again at pickup. Record the tool in the brief and route reason. Use an
explicit configured model and effort for this route. Any capacity fallback
must provide the same tool. If an inherited or user-named model conflicts with
the requirement, resolve the conflict before dispatch. HTML, chart and slide
layout continues through the normal visual category.


## Choosing a category

The category names the work. Read the request's verb, its object and the output the user will receive, then take the first match:

1. **orchestrator** when the request names the orchestrator seat or the fleet. The role-handoff rule already makes the `orchestrator` skill load mandatory.
2. **review** when the verb is review, check, audit, critique or second opinion, on finished work. Pass `--tier review --of <category of the work> --builder <provider>`; the builder is usually the session making the call, and its provider is excluded.
3. **visual** when the object is appearance: look, layout, slide, palette, UI, render, chart look, or screenshots define done.
4. **writing** when the output is prose the user will present or publish: executive summary, memo text, essay, post, speaker notes, editorial pass, fiction.
5. **finance** when the work is numbers: databook, model, reconciliation, valuation, tax, or a PDF extraction for any of these.
6. **legal** when the object is a contract, terms of business or regulation.
7. **strategy** when the output is an argument about a business or market: plan, proposal, market sizing, competitor view, unit economics, investment thesis, or desk research for any of these.
8. **classification** when each item needs a judgement on its content: assign properties, categories, topics or links across notes.
9. **housekeeping** when files or a glob are named and the instruction needs no judgement: rename, move, apply a given edit. A rename across files nobody has listed is coding until someone writes the list.
10. **systems** when something on a machine, server or tool has failed and the cause is unknown, or when a coding pass found no cause.
11. **coding** for any other work that builds or changes software.

A request with two outputs is two dispatches: a report's numbers are finance and its text is writing.

Three rules apply after the category:

- **Final look.** finance, strategy, legal and writing run the last pass at max.
- **Steered work.** When the user will steer through the composer (draft and I'll react, sketch, let's iterate), keep the category and go one effort step lower for faster turns: `--model` and `--effort` with `--reason "steered"`.
- **Failed first pass.** Change to the backup model. Raising effort keeps the wrong model in the seat.

Tie-breaks. A continuation inherits the category of the work it continues unless the request narrows it. Any other tie takes the category whose default costs more and says "tie" in the reason, so the route log can test whether that bias earns its cost.

A model or provider named in the request wins over the rule: pass `--model` and `--effort`, with `--reason "named in request"`. A provider whose allowance cannot be read is never an inferred route; it runs when named, with `--reason "manual budget"` and a budget line in the brief.

Old tier letters (O, A to F, V, R) and the words `basic`, `moderate` and `complex` still resolve through `legacy_tiers` in the metadata, with a deprecation note in the route.

## Capacity

`resolve.py` shells out to a usage meter for each candidate provider, in order, with a timeout from the metadata. The shipped integration is [CodexBar](https://github.com/steipete/codexbar): `codexbar usage --provider <p> --format json`. Always scope the read to one provider - an unscoped read has hung for minutes. The meter reports used percent, and every reason quotes it as used.

**A provider with `codexbar: null` in the metadata is never read, and its row dispatches as written with the reason "capacity unread".** That is the shipped default for both providers, so this whole section is inert until you wire a meter in. Nothing else changes when you do.

Windows read: the long window (`usage.secondary`), the short window (`usage.primary`), and a model's own scoped window where the metadata names one in `scoped_window`. `scripts/fixtures/` shows the JSON shape the resolver expects.

- **Exhausted**: used at or above `exhausted_used_percent` on any governing window with more than `exhausted_min_hours_to_reset` to that window's reset. The row's cross-provider backup is dispatched. The reason names the window, the figure and the reset time.
- **Tight**: `pace.secondary.willLastToReset` is false. The row is dispatched as written and the reason carries the word tight.
- **Unread**: the meter errors, times out, or has no entry for that provider. The row is dispatched as written and the reason says capacity unread. A provider that is always unread is never an inferred route.
- **Nothing left**: every candidate is exhausted or excluded. The resolver exits 3 and prints the candidates with their states. The helper stops before any cmux call.

Scarcity changes the dispatched model. It never changes the table. Where a provider offers a limit-reset credit and the meter shows one, spending it is the user's call, and the reason names it whenever that provider is the block.

## The three questions

Nothing about model, effort, provider, capacity or root is asked. The confirmation line is the catch for a bad route, and a spawned seat reads the brief and its existing authorisation, which is the second catch before any tool call. Three cases earn one `AskUserQuestion`, with the candidate rows as options, each labelled model and effort:

1. The category rule ties between two categories that resolve to different providers.
2. The resolver exits 3: both providers exhausted, or a review with no provider left. Spending a reset credit is the user's call.
3. A recycle whose inherited provider is exhausted, because a silent provider swap breaks lineage.

## What the helper prints and writes

The helper's last line is the route line. Quote it in the confirmation.

```
route: tier systems → B-Large · high (provider_b) | default A-Large · xhigh | override: provider_a weekly 99% used, resets Sat 19 Sep 17:00
```

It writes `model:` and `effort:` into the new session note's frontmatter and three lines under `## Progress`, directly below the spawned line. Pinned IDs in the note because they aggregate; display names in chat because a person reads them.

```
- 2026-09-22: workspace spawned.
- route default: tier systems → claude-opus-5-5 · xhigh
- route dispatched: <the provider_b id you configured> · high
- route reason: override: provider_a weekly 99% used, resets Sat 19 Sep 17:00. Category from "prior pass found no cause".
```

The confirmation line in chat, default held:

> Spawned **`🔧 validate-flaky`** on **systems** → **A-Large · xhigh** (provider_a). Default held. Brief at `<path>`; note at `<path>`. The seat continues within the brief's authorisation.

Override:

> Spawned **`🔧 validate-flaky`** on **systems** → **B-Large · high** (provider_b). Override: default A-Large · xhigh; provider_a weekly 99% used, resets Sat 19 Sep 17:00. Brief at `<path>`; note at `<path>`. The seat continues within the brief's authorisation.

Successor:

> Spawned **`🔍 routing-review-2`** as successor to **`🔍 routing-review`**, inherited **A-Large · high** (no re-route; provider_a weekly 14% used). Brief at `<path>`; note at `<path>`.

## Hard stops, put in the spawn prompt

Each category's `stop` field in `references/routing-metadata.yaml` says what done
looks like for that category. Put it in the brief. A seat that knows where to stop
hands back a smaller, sharper artefact than a seat that runs until it runs out.

Beyond the category, each model in your table earns its own stops, and they are
yours to write because they describe models you run and not models we do. The
shape that has held up:

- **A weaker or cheaper seat** takes work whose plan is already locked and whose
  acceptance is testable. It does not take a new visual system, a last-pass
  prose job, or the coordinating seat.
- **A terminal or investigation seat** hands back a demonstrated cause. The
  write-up that follows is writing, on whichever model writes best.
- **A visual seat** takes one track, does the work itself, and returns the
  artefact path with the viewports captured. It does not fan out.
- **A literal seat** needs the complete file list. Where it under-thinks,
  change model rather than pad the prompt.
- **The strongest seat** takes the spec, the prose and the last look. A
  200-file mechanical pass is housekeeping, however good that model is.

Write yours into `references/worker-behaviours.md`, which ships with the same
shape and the same caveat.

## Two reviewers on review

When both non-builder providers have capacity, a review of systems, finance, strategy, legal or writing work may run as two review seats in parallel, one per provider, from the same neutral brief: what to review, stated broadly; no steer toward a fix; a concise report that says whether the work is safe to merge or publish and, where it is not, what is serious. The caller merges: dedupe, keep only findings that matter, tag each one with the providers that raised it and put the agreed findings first, then close with one line counting what was dropped as noise. Agreement between two reviewers is evidence and never proof. Nothing is fixed until the user rules on the shortlist. The route log and the record of shortlist against fixes are the instrument for telling whether the second reviewer earned its cost.

## Escalation

Diagnose missing inputs, broken tooling or a thin brief first. Then effort, one step at a time: high, then xhigh, then max. Some models score no better at max than at high, and a stalled seat on one of those changes model rather than effort - your route log is what tells you which of yours behave that way. A task that turns out to belong to another category changes category, because more effort on the wrong model keeps the wrong model in the seat.

## Revising preferences

Follow `workflows/routing-review.md`. The structural check validates the table and metadata; live checks report which installed IDs can be confirmed. Apply a preference change only after the user rules on the proposal.
