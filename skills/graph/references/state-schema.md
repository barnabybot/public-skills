# The state-file schema

One YAML file per programme, named `<stem>.state.yaml`. Everything the graph shows
comes from it. Paths inside it are resolved relative to the file itself, so a state
file travels with the project it describes.

## `derive:` — optional

Present only when the graph reports numbers a model already holds. Absent, no string
in the file is touched, and prose containing `{` or `}` is safe.

| Key | Shape | Notes |
|---|---|---|
| `sources` | `{name: path.json}` | Loaded with `json.load` into `name`. |
| `hooks` | `{name: path.py:func}` | `func()` is called; its return value becomes `name`. The hook's own directory goes on `sys.path` first, so sibling imports resolve. |
| `checks` | `[expression \| mapping, …]` | Every one must be truthy. A failure prints `CHECK FAILED`, writes nothing, and exits 1. |

A check is either a bare expression or a mapping, after Sphinx-Needs' constraint
severities:

```yaml
checks:
  - "inv['surveyed'] > 50"               # breaks the build, the default
  - expr: "len(YR['total']) == 5"
    on_fail: warn                         # reports and carries on
    message: the yearly path is not five years long
```

`--permissive` downgrades every break to a warning, so a half-finished edit still
renders while the strict run stays the one that gates.

`today` is always in the namespace as an ISO date string.

Once `derive` is present, **every string in the file** is evaluated as a Python
f-string over that namespace. Strings with no `{` are passed through untouched.

```yaml
derive:
  sources:
    CS: model/cases.json
    YR: model/yearly.json
  hooks:
    inv: lib/inventory.py:counts
  checks:
    - "inv['surveyed'] > 50"
    - "abs(YR['total'][-1] - CS['target']) < 1"
```

### Quoting

The literal is encoded double-quoted before evaluation, and Python 3.9 forbids reusing
the enclosing quote inside an f-string expression. **Use single quotes inside braces.**

```yaml
sub: "USD{CS['segments']['core']/1e6:.1f}m"        # correct
sub: "USD{CS[\"segments\"][\"core\"]/1e6:.1f}m"    # SyntaxError on 3.9
```

Nested f-strings are fine as long as they use the inner quote:

```yaml
note: "{' · '.join(f'{v/1e6:.0f}' for v in YR['total'])}"
```

A YAML scalar beginning with `{` parses as a flow mapping, so quote any value that
starts with an expression.

## `meta:`

| Key | Required | Notes |
|---|---|---|
| `title` | yes | Page title and `<h1>`. |
| `lede` | yes | Standfirst. Inline HTML allowed. |
| `updated` | yes | Usually `"{today}"`. |
| `pills` | yes | `{label: value}`, rendered as a row of pills. `updated` is appended automatically. |
| `pills_hot` | no | List of pill labels to highlight. |
| `aria` | no | SVG `aria-label`. Describe the graph for a reader who cannot see it. |
| `maxlen` | no | Character budget for `sub`/`note`/`note2`. Opt-in: set it on four-wide layouts, leave it off where nodes use `span`. |
| `legend` | no | `{status: label}` overriding the default legend wording. |
| `palette`, `palette_dark` | no | `{token: value}` CSS variable overrides. |

## `layout:`

A list of stages, each with `rows`, each row a list of nodes.

```yaml
layout:
  - stage: 3 · YOUR GATES
    seq_note: then                 # optional label on a dashed link between nodes 2 and 3
    rows:
      - - id: gate-launch
          status: gate
          label: launch date
          sub: pilot or full rollout
          note: needs a human go
```

A stage whose title starts with `·` is an aside rather than a step, and the bus into it
is drawn dashed.

### Node keys

| Key | Notes |
|---|---|
| `id` | Required for event tracking. A node without one is drawn and never logged. |
| `status` | `done` `ready` `queue` `block` `gate` `fail` `stale`. |
| `label` | First line, bold. |
| `sub` | Second line, monospace. |
| `note`, `note2` | Third and fourth lines. |
| `span` | `mid` (480) · `wide` (680) · `full`. Single-node rows only. |
| `output` | Path this node produces. Enables stale detection. |
| `inputs` | Paths or globs this node consumes. |

### Node width

Rows divide the 1020px band evenly. Four nodes give 246px each, which is the width
`maxlen: 46` was calibrated against.

## `sections:`

Rendered under the graph in order.

```yaml
sections:
  - title: What locked
    kind: callout                  # two-column table in a tinted box
    rows: [[term, definition], …]

  - title: The gates
    kind: table
    head: [Gate, Question, What it moves]
    rows: [[…, …, …], …]

  - title: What this graph will not tell you
    kind: list
    items: […]
```

## Statuses that are measured rather than claimed

`stale` is never written by hand. A node with `output` reads stale when:

- the output does not exist, or
- its `inputs` have changed since the output was last built.

Everything else in `status:` is a claim by whoever last edited the file, and the
rendered page says so.

### Why hashes rather than mtimes

The first version compared modification times. A git checkout stamps every file with
the checkout time, so on a fresh clone the inputs and the output carry the same stamp
and a genuinely stale node reports clean. That is a false negative in the one guard
whose whole job is catching drift, and a false negative looks exactly like a pass.

`<stem>.fingerprints.json` records, per node, a hash of the inputs and a hash of the
output as they stood when the node was last built:

```json
{"dashboard": {"inputs": "9f2c…", "output": "41ab…"}}
```

- No record yet → take the current state as the reference, and read `done`.
- Output hash has changed → the output was rebuilt, so re-record and read `done`.
- Output unchanged, inputs changed → `stale`.

Rebuilding the output is the act that re-blesses the node, so nothing is ever marked
fresh by hand. `--check` reads the file and never writes it.

## The event log

`<stem>.events.jsonl`, append-only, one JSON object per line:

```json
{"ts":"2026-08-08T10:03:11+00:00","node":"survey","from":"queue","to":"done",
 "actor":"codex","note":"status moved queue → done"}
```

The renderer replays the log to find each node's last known status, then appends a
record for anything that has moved. An unchanged render appends nothing, so rerunning
is free. Agents may append their own richer records by hand; the renderer only reads
`node` and `to`.
