# Routing rules

The model table in `SKILL.md` is the only preference table. `scripts/resolve.py` reads it and the provider metadata, checks capacity, and returns the route. The cmux helper launches that route.

## Tiering a request

Inputs: the request's verb and object; whether done is machine-checkable (tests, a validator, a diff on named files); whether inputs are named or a plan is locked; whether the user will present, merge or rule on the output; the tier of the work being continued. First match wins.

1. **O** when the request names the orchestrator seat or the fleet. The role-handoff rule already makes the `orchestrator` skill load mandatory.
2. **R** when the verb is review, check, audit, critique or second opinion, on finished work. Pass `--tier R --of <tier of the work> --builder <provider>`; the builder is usually the session making the call, and its provider is excluded.
3. **V** when the object is appearance: look, layout, slide, palette, UI, render, or screenshots name done.
4. **F** when the output is a written judgement the user will present or rule on: spec, proposal, IC, final, last pass, argument, editorial, working prose from the first draft, or a brief that says the user reads and rules on it.
5. **A** when files or a glob are named, the instruction is explicit, and done is a diff you can check without running anything: rename across, apply to, run the script on. A rename across files nobody has listed is C until someone writes the list.
6. **B** when a plan or spec is locked in the brief and tests or a validator define done: implement the agreed, make the tests pass, build to spec. Bounded but long (a sweep with a locked plan) is B.
7. **E** when the request names architecture, a design decision, terminal investigation or difficult document reasoning, or when a debugging job has already failed a C pass: the brief or the session note says a prior pass found no cause.
8. **D** when the user says they will steer it through the composer (draft and I'll react, sketch, let's iterate), or the session note shows two or more correction rounds on one artefact. D is a mode of working. It is never a difficulty.
9. **C** for any other coding, a first structure of a page or deck, charts and slide first-pass, and any debugging whose difficulty is unknown until you are in it: work out why, flaky, investigate, with no prior pass. When a second pass has no cause the job is E: change the model. Raising effort keeps the wrong model in the seat.

Tie-breaks. A continuation inherits the tier of the work it continues unless the request narrows it. A tie between C and E is C. Any other tie takes the higher tier and says "tie" in the reason, so the route log can test whether that bias earns its cost.

A model or provider named in the request wins over the rule: pass `--model` and `--effort`, with `--reason "named in request"`. A provider whose allowance cannot be read is never an inferred route; it runs when named, with `--reason "manual budget"` and a budget line in the brief.

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

1. The tiering rule ties between two tiers that resolve to different providers.
2. The resolver exits 3: both providers exhausted, or a review with no provider left. Spending a reset credit is the user's call.
3. A recycle whose inherited provider is exhausted, because a silent provider swap breaks lineage.

## What the helper prints and writes

The helper's last line is the route line. Quote it in the confirmation.

```
route: tier E → B-Large · high (provider_b) | default A-Large · xhigh | override: provider_a weekly 99% used, resets Sat 19 Sep 17:00
```

It writes `model:` and `effort:` into the new session note's frontmatter and three lines under `## Progress`, directly below the spawned line. Pinned IDs in the note because they aggregate; display names in chat because a person reads them.

```
- 2026-09-22: workspace spawned.
- route default: tier E → claude-opus-5 · xhigh
- route dispatched: <the provider_b id you configured> · high
- route reason: override: provider_a weekly 99% used, resets Sat 19 Sep 17:00. Tier from "prior pass found no cause".
```

The confirmation line in chat, default held:

> Spawned **`🔧 validate-flaky`** on tier **E** → **A-Large · xhigh** (provider_a). Default held. Brief at `<path>`; note at `<path>`. The seat continues within the brief's authorisation.

Override:

> Spawned **`🔧 validate-flaky`** on tier **E** → **B-Large · high** (provider_b). Override: default A-Large · xhigh; provider_a weekly 99% used, resets Sat 19 Sep 17:00. Brief at `<path>`; note at `<path>`. The seat continues within the brief's authorisation.

Successor:

> Spawned **`🔍 routing-review-2`** as successor to **`🔍 routing-review`**, inherited **A-Large · high** (no re-route; provider_a weekly 14% used). Brief at `<path>`; note at `<path>`.

## Hard stops, put in the spawn prompt

Each tier's `stop` field in `references/routing-metadata.yaml` says what done
looks like for that tier. Put it in the brief. A seat that knows where to stop
hands back a smaller, sharper artefact than a seat that runs until it runs out.

Beyond the tier, each model in your table earns its own stops, and they are
yours to write because they describe models you run and not models we do. The
shape that has held up:

- **A weaker or cheaper seat** takes work whose plan is already locked and whose
  acceptance is testable. It does not take a new visual system, a last-pass
  prose job, or the coordinating seat.
- **A terminal or investigation seat** hands back a demonstrated cause. The
  write-up that follows is tier F, on whichever model writes best.
- **A visual seat** takes one track, does the work itself, and returns the
  artefact path with the viewports captured. It does not fan out.
- **A literal seat** needs the complete file list. Where it under-thinks,
  change tier rather than pad the prompt.
- **The strongest seat** takes the spec, the prose and the last look. A
  200-file mechanical pass is tier A, however good that model is.

Write yours into `references/worker-behaviours.md`, which ships with the same
shape and the same caveat.

## Two reviewers on tier R

When both non-builder providers have capacity, a review of tier E or F work may run as two R seats in parallel, one per provider, from the same neutral brief: what to review, stated broadly; no steer toward a fix; a concise report that says whether the work is safe to merge or publish and, where it is not, what is serious. The caller merges: dedupe, keep only findings that matter, tag each one with the providers that raised it and put the agreed findings first, then close with one line counting what was dropped as noise. Agreement between two reviewers is evidence and never proof. Nothing is fixed until the user rules on the shortlist. The route log and the record of shortlist against fixes are the instrument for telling whether the second reviewer earned its cost.

## Escalation

Diagnose missing inputs, broken tooling or a thin brief first. Then effort, one step at a time: high, then xhigh, then max. Some models score no better at max than at high, and a stalled seat on one of those changes model rather than effort - your route log is what tells you which of yours behave that way. A task that turns out to need a harder tier changes tier, because more effort on the wrong model keeps the wrong model in the seat.

## Revising preferences

Follow `workflows/routing-review.md`. The structural check validates the table and metadata; live checks report which installed IDs can be confirmed. Apply a preference change only after the user rules on the proposal.
