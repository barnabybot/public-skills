# Orchestrator operating contract

Required tool capabilities, user-supplied routing configuration, startup retirement, capacity precedence, dispatch contract, operating rules, ownership, host operations and verification commands.

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

## Startup retirement

Inside cmux, before fleet work in a fresh orchestrator seat:

1. Identify the caller with `cmux identify --json --id-format both`.
2. Run `python3 ../cmux/scripts/group_header.py ensure --workspace <caller-UUID>`. Keep a reserved blank group header permanently, including when the group would otherwise be empty. Stop if repair fails.
3. Retire finished predecessors with `scripts/retire_predecessors.py`. A Codex seat that returns `confirmation_required` uses the cmux idle-exit procedure. Do not close a workspace `group_header.py before-close` marks `retained-header`.

## Capacity before preference

Read capacity before the table's preference. `--request` carries authorisation, required tools and an optional one-task `bounded_preference`. A provider absent from `authorisation.providers` is excluded. `"capacity": "required"` refuses an unread meter. A Codex-shaped `native` block on the meter uses pace versus reset across every returned account window. `--route-out` writes a bundle; `--resolved-route` reuses it for a fast cross-model handoff without a second capacity read. Confirm the predecessor surface with `scripts/runtime_adapters.py` when `stamp_surface.py` wrote one.

## Dispatch contract

Choose the category. In T3 Code, follow [native dispatch](references/hosts.md#dispatch-in-t3-code).
In a CLI, use its supported subagent tools. Inside cmux, call the helper:

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
- Inside cmux, close workers with `cmux/scripts/close-workspace.sh` so their
  notes close too. In T3 Code, cancel unneeded owned tasks with `task_cancel`
  and update notes directly.
- A live-page push runs `scripts/live_push_gate.py --note <session-note>` before
  the push. The note records `Preview:` for the Thin-Slice: an existing
  filesystem path, a `file://` URL, or an `http` or `https` loopback URL
  (`127.0.0.1`, `localhost`, or `::1`) with a path. The default edit is inject
  or update in place. `Change: replace` or `Change: remove` also records `Go:`
  and `Provenance: direct`. `relay` and `build` fail that tag.

## Ownership

This skill owns the routing table, the category rule, the resolver and their
checks. Routing is dispatch policy, and the seat that dispatches keeps the
policy. Splitting the table from the rule that reads it gives one table two
owners, which is how a table and its documentation drift apart.

## Host operations

Use [native dispatch](references/hosts.md#dispatch-in-t3-code) in T3 Code.
Apply terminal inventory, group repair, stall checks and workspace closure only
inside cmux. CLI subagents use their host's supported tools.

Classify the latest direct author line with `python3 scripts/author_build_intent.py classify`
before spawning an orchestrator successor. Build or stop-spawning language
continues or dispatches a writer. Explicit orchestrator handoff allows succession.

## Verification

```bash
python3 scripts/check.py --no-live --no-log        # after editing the table
python3 scripts/test_author_build_intent.py       # after changing author intent
python3 scripts/test_resolve.py                    # after changing routing code
python3 scripts/test_aa_refresh.py                 # after changing the AA refresh
python3 scripts/test_retire_predecessors.py        # after changing predecessor retirement
python3 scripts/test_continuation_check.py         # after changing continuation gates
python3 scripts/test_stall_check.py                # after changing stall detection
python3 scripts/test_live_push_gate.py             # after changing the live-push gate
python3 scripts/test_accept_surfaces.py            # after changing acceptance checks
python3 scripts/test_route_request.py              # after changing request gates or route bundles
python3 scripts/test_codex_capacity.py             # after changing Codex pace versus reset
python3 scripts/test_runtime_adapters.py           # after changing the surface stamp reader
```

The fixture checks create no workspace and contact no provider. `workflows/routing-refresh.md` proposes table changes weekly from Artificial Analysis.
