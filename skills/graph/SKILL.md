---
name: graph
version: 1.2.0
description: >-
  Track a programme of work as a dependency graph of tasks and their status. Use for /graph,
  work graphs, project state, what is left to do, node status, blocked or stale work, gates
  awaiting a decision, and agent transition logs. NOT for charts or data visualisation.
fallback: >-
  If Python or PyYAML is unavailable, read the state YAML directly and report the graph as
  text. Group nodes by stage and status, then report ready, gated, blocked and stale work.
  Never hand-edit the rendered HTML; leave it stale and say so.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
---

# /graph work-graph renderer

One programme of work, one YAML state file and one interactive HTML graph. Agents edit
the state; the page is derived from it. The render also maintains a transition log and a
fingerprint record beside the state file. Never hand-edit the HTML, because the next render
overwrites it.

```bash
R=scripts/render-graph.py                         # relative to this skill
python3 $R <programme>.state.yaml                 # render
python3 $R <programme>.state.yaml --open          # render, then show it in cmux
python3 $R <programme>.state.yaml --check         # validate, write nothing, exit 5 on drift
python3 $R <programme>.state.yaml --frontier      # list unblocked frontier nodes read-only
python3 $R <programme>.state.yaml --frontier --json  # machine-readable frontier and overlaps
python3 $R <programme>.state.yaml --permissive    # breaking checks become warnings
python3 $R <programme>.state.yaml --actor codex   # attribute logged transitions
python3 scripts/selftest.py                       # smoke tests, run after any change
```

**T3 Code.** Render without `--open`. To show the graph in the conversation,
pass the rendered HTML to `html_preview` then `html_render`. Use these display
tools without starting a server or opening a cmux pane.

**Look at the page in cmux.** `--open` renders and then opens the file in the cmux browser
pane, waits for the load to complete and prints the page title back. Use it whenever
a human is going to read the result. It is never fatal. A run with no cmux on PATH
prints one line and still renders, so cron and pre-commit are unaffected. It
refuses to combine with `--check`, which writes nothing and would therefore show a
stale page.

This exists because the checks in this skill guard the numbers and nothing guards the
layout. Every layout defect found so far was found by looking: clipped stage labels, a
footer naming the wrong state file, an overflowing node, and a node whose sub-line sat
0.2px inside its own border.

Each programme owns a set of files beside its state file:

| File | What it is |
|---|---|
| `<stem>.state.yaml` | The state. Hand- or agent-edited. The only file anyone writes. |
| `<stem>.html` | The render. Overwritten every run. |
| `<stem>.events.jsonl` | Transition log, appended when a node's status moves. |
| `<stem>.fingerprints.json` | Content hashes behind the `stale` status. Machine-managed. |

Exit codes: `0` fine · `1` a check broke or the file is malformed · `5` (`--check` only)
the render would change or a node reads stale. This follows the `cog --check` convention;
`cog` is not required.

## Where a state file lives

**A state file lives with the project it describes**, because `derive:` resolves its
sources relative to the state file. Keep the trio together and keep it beside the work.
For example, use `docs/<programme>.state.yaml` in a project repository.

A vault needs **Settings → Files & Links → Detect all file extensions** turned on, or the
`.state.yaml` and `.jsonl` files are invisible in its file explorer.

Needs Python 3.9+ and PyYAML (`python3 -m pip install --user pyyaml`). `--open` also needs
[cmux](https://cmux.com); without it, open the HTML in any browser.

## Interactive graph

The rendered page draws a dependency DAG across stages. It provides:

- explicit dependency edges, with an optional all-edges or focused view;
- a frontier filter for nodes whose upstream dependencies are done;
- foldable stages, search, status filters and an inspector for each node;
- foldable child branches declared with `children`;
- owner, acceptance condition, output and dependency details in the inspector.

Click a node to inspect it, a stage gutter to fold its stage, or a branch badge to expand
its child nodes. These controls are local to the generated HTML and need no server.

## Conventions, schema & frontier runbook

Read [`references/conventions.md`](references/conventions.md) for statuses,
`derive:` / `checks:`, content-hash staleness and editing habits. Read
[`references/state-schema.md`](references/state-schema.md) for the YAML schema
and `--frontier --json` contract. When draining a graph to the next gate, read
[`references/run-frontier.md`](references/run-frontier.md) first.
