# Running a graph frontier

Load this runbook only when asked to run, execute or drain a programme graph.
Keep orchestration routing in `orchestrator` and verification discipline in
your project's `AGENTS.md`.

## Pre-flight

1. Query the current frontier read-only:

   ```bash
   python3 scripts/render-graph.py <programme>.state.yaml --frontier --json
   ```

2. Check context pointers. Read `meta.spec` and any existing `meta.notes`
   before dispatching workers. If the graph covers an unfamiliar codebase and
   has no `meta.notes`, run one read-only exploration pass first and save
   concise findings under `~/Scratch/YYYY-MM-DD/<programme>-notes.md` so
   downstream workers start warm via pointer.
3. Choose the workspace mode:
   - **Code repository.** Create or check out one `integration_branch` (record
     it in `meta.integration_branch`). Avoid opening a separate PR per node
     unless requested.
   - **Markdown vault.** Edit notes directly in place with zero git branches or
     PRs. Respect the destination vault's `AGENTS.md` and boundary rules.

## Concurrency and shared state

- **Single writer for graph state.** Only the coordinator edits
  `<programme>.state.yaml` and runs `render-graph.py`. Workers never modify the
  state YAML, HTML or event log.
- **Check `overlap_warnings` before parallelising.** If two actionable nodes
  declare overlapping `touches` (or share files like `global.css`, `SKILL.md`
  or a shared schema), serialise those lanes. Parallelise only disjoint work.
- **Worktree wave sequencing.** When workers run in isolated worktrees branched
  from the parent checkout's current commit, merge and commit wave 1 onto the
  integration branch before spawning wave 2 when wave 2 depends on wave 1.

## The drain loop

Repeat until `actionable` is empty:

1. Run `render-graph.py <programme>.state.yaml --frontier --json`.
2. Stop immediately if `actionable` is empty. Report remaining `gates` (and any
   `block`, `fail` or `stale` nodes) concisely to the user.
3. Select the largest conflict-free subset of `actionable` nodes (no overlapping
   `touches` or shared write targets).
4. Dispatch each selected node in a fresh context window using `orchestrator`
   routing and capacity checks. Give each worker sparse pointers:
   - The node's `id`, `label`, `acceptance` checklist and `touches` scope.
   - Paths to `meta.spec`, `meta.notes` and any node-level `spec`.
   - Exact test and verification commands for the acceptance criteria.
5. As each worker finishes, verify its diff and test evidence, merge its branch
   onto the integration branch (in a code repo), and update that node's status
   to `done` in `<programme>.state.yaml`.
6. Rerun `render-graph.py <programme>.state.yaml --actor <actor>` so
   transitions log to `.events.jsonl` and fingerprints refresh.
7. Watch context usage. If the coordinator reaches 30% context or 300k tokens,
   stop launching new waves, rerun `render-graph.py`, write a handoff brief
   under `$AGENT_NOTES/Sessions/Handoffs/`, and let the successor pick up from
   the same `.state.yaml` with zero lost state.

## Closing a wave before a human gate

For code repositories, once every agent-owned node before a `gate` is `done`:

1. Run one independent cross-provider review pass (excluding the builder's
   provider) across the integration branch diff.
2. Fix confirmed issues in a fresh worker (or directly for small edits) and
   rerun the test suite.
3. Clean up finished worker worktrees, rerun `render-graph.py`, and pause at
   the `gate` node with a concise decision brief (diff summary, test evidence
   and open question).
