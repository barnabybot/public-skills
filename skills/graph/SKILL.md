---
name: graph
version: 1.0.0
description: >-
  Track a programme of work as a dependency graph of tasks and their status. Use for /graph,
  work graphs, project state, what is left to do, node status, blocked or stale work, gates
  awaiting a decision, and agent transition logs. NOT for charts or data visualisation.
fallback: >-
  If Python or PyYAML is unavailable, read the state YAML directly and report the graph as
  text — nodes by stage with their status, then what is ready, gated, blocked and stale.
  Never hand-edit the rendered HTML; leave it stale and say so.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
---

# /graph — the work-graph renderer

One programme of work, one YAML state file, one rendered HTML graph, one append-only
event log. Agents edit the state; the picture is derived from it. Nobody hand-edits
the HTML, because the next render overwrites it.

```bash
R=scripts/render-graph.py                        # relative to this skill
python3 $R <programme>.state.yaml                # render
python3 $R <programme>.state.yaml --open         # render, then show it in cmux
python3 $R <programme>.state.yaml --check        # validate, write nothing, exit 5 on drift
python3 $R <programme>.state.yaml --permissive   # breaking checks become warnings
python3 $R <programme>.state.yaml --actor codex  # attribute logged transitions
python3 scripts/selftest.py                      # 26 assertions, run after any change
```

**Look at the page.** `--open` renders and then opens the file in the cmux browser
pane, waits for the load to complete and prints the page title back. Use it whenever
a human is going to read the result. It is never fatal — a run with no cmux on PATH
prints one line and still renders, so cron and pre-commit are unaffected — and it
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
the render would change or a node reads stale (the same convention as `cog --check`;
cog is not required).

## Where a state file lives

**A state file lives with the project it describes**, because `derive:` resolves its
sources relative to the state file. Keep the files together and keep them beside the
work, for example `docs/<programme>.state.yaml` in the project repository.

In an Obsidian vault, turn on **Settings → Files & Links → Detect all file extensions**,
or the `.state.yaml` and `.jsonl` files are invisible in the file explorer.

Needs Python 3.9+ and PyYAML (`python3 -m pip install --user pyyaml`). `--open` also needs
[cmux](https://www.cmux.dev); without it, open the HTML in any browser.

## Statuses

`done` · `ready` · `queue` · `block` · `gate` · `fail` · `stale`

`gate` means an explicit human GO is needed. `stale` is never written by hand — see
below. Everything else is a claim by whoever edited the file.

## The two things that stop a graph lying

**Derived numbers.** A graph that restates a figure a model already holds will drift
from it. One model-backed graph went stale three times in two days that way, carrying a total
after the model had moved on, then a count after its source had grown. So a
state file may declare `derive:`, after which every string in the file behaves as a
Python f-string over the loaded sources, and `checks:` must all hold or nothing is
written.

**Measured staleness.** A node declaring `output:` and `inputs:` reads `stale` when its
inputs changed after the output was last built, whatever `status:` claims. This is the
guard for a rendered document sitting beside model files it no longer agrees with.

Staleness compares **content hashes, never modification times.** A git checkout stamps
every file with the checkout time, so an mtime comparison reports clean on a fresh
clone — a false negative in the one guard whose job is catching drift. Rebuilding the
output re-blesses the node automatically; nothing is marked fresh by hand.

A state file with no `derive:` block gets no substitution at all, so prose containing
braces is safe and existing graphs render unchanged.

## Schema

Full reference: `references/state-schema.md`. The short version:

```yaml
derive:                                   # optional
  sources: {CS: model/cases.json}         # JSON, paths relative to the state file
  hooks:   {inv: lib/inventory.py:counts} # module:function -> any value
  checks:                                 # all must be truthy or the build refuses
    - "inv['sites'] >= 12"
    - expr: "inv['surveyed'] > 400"       # or a mapping, to warn instead of break
      on_fail: warn
      message: the survey is thinner than the report claims

meta:
  title: …
  lede: …                                 # HTML allowed
  updated: "{today}"
  maxlen: 46                              # optional; opt-in house cap on verbosity
  width_check: break                      # optional; default warn. Pixel overflow guard
  pills: {plan: "USD{CS['total']/1e6:.0f}m"}
  pills_hot: [plan]                       # optional; highlights a pill

layout:
  - stage: 0 · SETTLED                    # a leading "·" makes the bus into it dashed
    rows:
      - - id: survey                      # id is required for event tracking
          status: done
          label: site survey
          sub: "{inv['surveyed']} surveyed"
          note: every ruling on the record
          output: report.html             # optional, enables stale detection
          inputs: [model/cases.json]

sections:                                 # kind: callout | table | list
  - {title: …, kind: list, items: […]}
```

**Expressions must use single quotes inside the braces.** Python 3.9 forbids reusing
the enclosing quote inside an f-string, and the literal is double-quoted:
write `{CS['segments']['core']}`, never `{CS["segments"]["core"]}`.

## Conventions

- **Node text is measured in pixels, always.** Every node knows its own box width from
  `row_boxes`, so a `span: full` node is checked against a full-width budget and a
  quarter node against a quarter. It **warns** by default; set `meta.width_check: break`
  once a programme is clean and it stays clean. `--permissive` downgrades that.
- `meta.maxlen` is an optional house-style cap on verbosity, still opt-in and still
  breaking. It is no longer the overflow guard.
- **Why the guard changed.** `maxlen` counted characters against one budget shared by
  all three text rows, but `.nsub` is 12px monospace and `.nown` is 11.5px proportional
  sans. At 46 characters a monospace sub sets 332px into a 246px box and the check
  passed it. When the pixel guard first ran, two live graphs overflowed, one on 45 of
  179 rows, with note text visibly crossing into neighbouring boxes. That is why the new guard warns instead of breaking: it would otherwise stop
  those programmes rendering at all.
- Set `--actor` to whoever moved the work: `claude-code`, `codex`, `workspace:19`,
  or your own name. It lands in the event log and is how a multi-day programme reads back.
- Keep `gate` nodes hand-set. A gate is a judgement, and deriving one would defeat it.
- After a status edit, rerun the renderer so the transition is logged. An unchanged
  render logs nothing, so rerunning is always safe.
