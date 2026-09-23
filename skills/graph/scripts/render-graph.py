#!/usr/bin/env python3
"""Render a work graph from its state YAML.

Edit the YAML, run this. Never hand-edit the HTML — this overwrites it.

    render-graph.py <programme>.state.yaml     # render
    render-graph.py <programme>.state.yaml --check   # validate, write nothing
    render-graph.py <programme>.state.yaml --open    # render, then show it in cmux

Each programme owns a set of files beside its state file:

    <stem>.state.yaml   the state, hand-edited or agent-edited
    <stem>.html         the render, overwritten every run
    <stem>.events.jsonl the transition log, appended when a status moves

WHY THE DERIVE BLOCK EXISTS. The first two programmes typed their numbers into the
YAML. The third, a graph over a financial model, could not: it went stale three
times in two days, carrying a total after the model had moved on, then a count after
its source had grown. A graph that restates a number the model already holds will drift from it.
So a state file may declare `derive:` — JSON sources, optional Python hooks, and
checks that must hold — and any string in the file then behaves as a Python
f-string over that namespace.

A state file with no `derive:` block is left exactly as it was: no substitution is
attempted, so text containing braces cannot break, and the render is unchanged.
"""
import argparse, datetime, hashlib, importlib.util, json, pathlib, shutil, subprocess, sys
import urllib.parse

EXIT_OK, EXIT_ERROR, EXIT_WOULD_CHANGE = 0, 1, 5   # exit 5 after cog's --check

try:
    import yaml
except ImportError:                                          # pragma: no cover
    sys.exit("render-graph needs PyYAML: python3 -m pip install --user pyyaml")

LEFT, RIGHT = 160, 1180
FULL = RIGHT - LEFT
GAP_N, GAP_W = 12, 30
ROW_GAP, BAND_GAP = 38, 46
SPANS = {"full": FULL, "wide": 680, "mid": 480}
STAGE_CHAR_W = 7.7          # approx width of one letterspaced 10.5px cap, for the gutter
TEXT_KEYS = ("label", "sub", "note", "note2")
MAXLEN_DEFAULT = 46


# --------------------------------------------------------------------- derive
class DeriveError(SystemExit):
    pass


def load_sources(spec, base):
    """Load each JSON source into a namespace name. Paths are relative to the state file."""
    ns = {}
    for name, rel in (spec or {}).items():
        path = (base / rel).resolve()
        if not path.exists():
            raise DeriveError(f"derive source {name!r} not found: {path}")
        ns[name] = json.loads(path.read_text(encoding="utf-8"))
    return ns


def load_hooks(spec, base):
    """Call `module.py:function` hooks for values no JSON file holds.

    The hook's own directory goes on sys.path first, so a hook that imports a
    sibling (a counter that imports a shared `taxonomy` module) resolves the same way it
    does when run from its own folder.
    """
    ns = {}
    for name, ref in (spec or {}).items():
        rel, _, func = ref.partition(":")
        path = (base / rel).resolve()
        if not path.exists():
            raise DeriveError(f"derive hook {name!r} not found: {path}")
        sys.path.insert(0, str(path.parent))
        try:
            spec_ = importlib.util.spec_from_file_location(f"_hook_{name}", path)
            mod = importlib.util.module_from_spec(spec_)
            spec_.loader.exec_module(mod)
            if not hasattr(mod, func or "main"):
                raise DeriveError(f"derive hook {name!r}: {path.name} has no {func or 'main'}()")
            ns[name] = getattr(mod, func or "main")()
        finally:
            sys.path.pop(0)
    return ns


def subst(value, ns):
    """Evaluate every string in the tree as a Python f-string over `ns`.

    Encoded with json.dumps rather than repr so the literal is always
    double-quoted. Python 3.9 forbids reusing the enclosing quote inside an
    f-string expression, so expressions in a state file must use SINGLE quotes:
    write {CS['segments']['core']}, never {CS["segments"]["core"]}.
    """
    if isinstance(value, str):
        if "{" not in value:
            return value
        try:
            return eval("f" + json.dumps(value, ensure_ascii=False), dict(ns))  # noqa: S307
        except SyntaxError as exc:
            raise DeriveError(
                f"cannot evaluate {value!r}\n  {exc}\n"
                "  Expressions must use single quotes inside the braces on Python 3.9."
            )
        except Exception as exc:
            raise DeriveError(f"cannot evaluate {value!r}\n  {type(exc).__name__}: {exc}")
    if isinstance(value, list):
        return [subst(v, ns) for v in value]
    if isinstance(value, dict):
        return {k: subst(v, ns) for k, v in value.items()}
    return value


def run_checks(checks, ns, permissive=False):
    """Every check must be truthy. A breaking check stops the render.

    This is the guard the model-backed builders carried and the generic renderer lacked.
    A build that disagrees with the model it reports on should refuse to publish
    rather than publish quietly.

    A check is either a bare expression, or a mapping taking `on_fail: warn` and a
    `message`, after Sphinx-Needs' constraint severities. `--permissive` downgrades
    every break to a warning, so a half-finished edit can still be rendered while
    the strict run stays the one that gates.

    Returns the warnings, so the caller can report them.
    """
    warnings = []
    for item in checks or []:
        expr = item if isinstance(item, str) else item["expr"]
        on_fail = "break" if isinstance(item, str) else item.get("on_fail", "break")
        message = None if isinstance(item, str) else item.get("message")
        try:
            ok = eval(expr, dict(ns))                                   # noqa: S307
        except Exception as exc:
            raise DeriveError(f"check {expr!r} could not run: {type(exc).__name__}: {exc}")
        if ok:
            continue
        text = message or expr
        if on_fail == "break" and not permissive:
            raise DeriveError(f"CHECK FAILED — {text}\n  Nothing was written.")
        warnings.append(text)
    return warnings


# ---------------------------------------------------------------- staleness
def digest(paths):
    """One hash over a set of files: their names and their bytes."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.name).encode())
        h.update(p.read_bytes() if p.exists() else b"\0")
    return h.hexdigest()


def resolve(base, rel):
    """A path or a glob, relative to the state file."""
    hits = sorted(base.glob(rel))
    return hits if hits else ([base / rel] if (base / rel).exists() else [])


def staleness(nodes, base, prints_path, write):
    """Mark nodes whose inputs have moved since their output was last built.

    CONTENT HASHES RATHER THAN MTIMES. The first version compared modification
    times, which a git checkout resets: clone a repo and every file carries the
    same stamp, so a stale node reports clean. That is a false negative in the one
    guard whose whole job is catching drift. Fingerprints survive checkout, clone
    and vault sync, after Doorstop's suspect-link.

    The record is (inputs hash, output hash). Rebuilding the output re-blesses the
    node automatically, so nothing has to be marked fresh by hand.
    """
    prints = {}
    if prints_path.exists():
        try:
            prints = json.loads(prints_path.read_text(encoding="utf-8"))
        except ValueError:
            prints = {}
    n_stale, changed = 0, False
    for nd in nodes:
        out = nd.get("output")
        if not out:
            continue
        op = base / out
        nid = nd.get("id") or nd.get("label")
        if not op.exists():
            nd["status"] = "stale"
            n_stale += 1
            continue
        cur = {"inputs": digest(sum((resolve(base, r) for r in nd.get("inputs") or []), [])),
               "output": digest([op])}
        was = prints.get(nid)
        if was is None or was.get("output") != cur["output"]:
            # First sight, or the output has been rebuilt: take the current state as
            # the reference. A rebuild is the act that re-blesses the node.
            prints[nid], changed = cur, True
        elif was.get("inputs") != cur["inputs"]:
            nd["status"] = "stale"
            n_stale += 1
    if write and changed:
        prints_path.write_text(json.dumps(prints, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8")
    return n_stale


# ------------------------------------------------------------------- events
def known_statuses(events_path):
    """Replay the log; the last `to` recorded for a node is its known status."""
    known = {}
    if not events_path.exists():
        return known
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("node"):
            known[rec["node"]] = rec.get("to")
    return known


def log_transitions(events_path, nodes, actor):
    """Append one record per node whose status has moved since the log last saw it."""
    known = known_statuses(events_path)
    ts = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    new = []
    for nd in nodes:
        nid = nd.get("id")
        if not nid:
            continue
        was, now = known.get(nid), nd["status"]
        if was == now:
            continue
        # A node the log has never seen is either genuinely new or predates event
        # tracking. Say "first seen" rather than "added", because backfilling an
        # existing graph would otherwise date every node to the day it was adopted.
        new.append({"ts": ts, "node": nid, "from": was, "to": now, "actor": actor,
                    "note": (f"first seen by the renderer at {now}" if nid not in known
                             else f"status moved {was} → {now}")})
    if new:
        with events_path.open("a", encoding="utf-8") as fh:
            for rec in new:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return new


# ------------------------------------------------------------------- layout
def row_boxes(nodes):
    """Return [(x, w)] for one row, centred on the band."""
    n = len(nodes)
    if n == 1:
        w = SPANS.get(nodes[0].get("span", "mid"), SPANS["mid"])
        return [((LEFT + RIGHT - w) // 2, w)]
    gap = GAP_N if n >= 4 else GAP_W
    w = (FULL - gap * (n - 1)) // n
    return [(LEFT + i * (w + gap), w) for i in range(n)]


def row_height(nodes):
    return 40 + 19 * max(len([k for k in ("sub", "note", "note2") if nd.get(k)]) for nd in nodes)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw(nodes, y):
    """Emit one row's nodes; return (svg, [centres], height)."""
    boxes, h, out, cx = row_boxes(nodes), row_height(nodes), [], []
    for nd, (x, w) in zip(nodes, boxes):
        c = x + w // 2
        cx.append(c)
        out.append(f'  <g class="s-{nd["status"]}">')
        out.append(f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7"/>')
        for i, (key, klass) in enumerate(
            (("label", "nlab"), ("sub", "nsub"), ("note", "nown"), ("note2", "nown"))
        ):
            if nd.get(key):
                out.append(
                    f'    <text class="{klass}" x="{c}" y="{y + 25 + 19 * i}" '
                    f'text-anchor="middle">{nd[key]}</text>'
                )
        out.append("  </g>")
    return out, cx, h


def connect(prev_cx, prev_bottom, next_cx, next_top, cls="edge"):
    """Bus between two rows: fan in from prev, fan out to next."""
    mid = (prev_bottom + next_top) // 2
    lo, hi = min(prev_cx + next_cx), max(prev_cx + next_cx)
    p = [f'  <path class="{cls}" d="M{lo} {mid} H{hi}"/>'] if hi > lo else []
    for c in prev_cx:
        p.append(f'  <path class="{cls}" d="M{c} {prev_bottom} V{mid}"/>')
    for c in next_cx:
        p.append(f'  <path class="{cls}" d="M{c} {mid} V{next_top - 6}" marker-end="url(#ar)"/>')
    return p


def build_graph(layout):
    svg, labels, y = [], [], 40
    prev_cx = prev_bottom = None
    for band in layout:
        labels.append((y + 26, band["stage"]))
        # A stage titled with a leading "·" is an aside rather than a step, so the
        # bus into it is dashed, e.g. a blocked-on-data band.
        cls = "edge-dash" if str(band["stage"]).lstrip().startswith("·") else "edge"
        for ri, nodes in enumerate(band["rows"]):
            body, cx, h = draw(nodes, y)
            if prev_cx:
                svg += connect(prev_cx, prev_bottom, cx, y, cls)
            svg += body
            if band.get("seq_note") and len(nodes) == 4:
                a, b = cx[1], cx[2]
                svg.append(
                    f'  <path class="edge-dash" d="M{a + 62} {y + h // 2} H{b - 62}" '
                    f'marker-end="url(#ar)"/>'
                )
                svg.append(
                    f'  <text class="edgelab" x="{(a + b) // 2}" y="{y + h + 14}" '
                    f'text-anchor="middle">{band["seq_note"]}</text>'
                )
                y += 16
            prev_cx, prev_bottom = cx, y + h
            y += h + (ROW_GAP if ri < len(band["rows"]) - 1 else BAND_GAP)
    return svg, labels, y


def section(sec):
    t = sec["title"]
    if sec["kind"] == "list":
        items = "\n".join(f"  <li>{i}</li>" for i in sec["items"])
        return f'<h2>{t}</h2>\n<ul class="lim">\n{items}\n</ul>'
    if sec["kind"] == "callout":
        rows = "\n".join(
            f"    <tr><td>{a}</td><td>{b}</td></tr>" for a, b in sec["rows"]
        )
        return f'<h2>{t}</h2>\n<div class="callout">\n  <table>\n{rows}\n  </table>\n</div>'
    head = "".join(f"<th>{h}</th>" for h in sec["head"])
    rows = "\n".join(
        "    <tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in sec["rows"]
    )
    return (
        f'<h2>{t}</h2>\n<table class="grid">\n  <thead><tr>{head}</tr></thead>\n'
        f"  <tbody>\n{rows}\n  </tbody>\n</table>"
    )


CSS = """
  :root{--bg:#fbfaf8;--panel:#fff;--ink:#16181d;--muted:#5e6268;--line:#ddd9d3;
    --done-f:#e9f3ec;--done-s:#2f7d55;--done-t:#1d5a3c;
    --ready-f:#e7effe;--ready-s:#3978e5;--ready-t:#1b4c9c;
    --block-f:#f3f2f0;--block-s:#c2beb8;--block-t:#6b6862;
    --queue-f:#00000000;--queue-s:#ddd9d3;--queue-t:#87847e;
    --gate-f:#fdf4e3;--gate-s:#c08a2e;--gate-t:#875d12;
    --stale-f:#f5eefb;--stale-s:#8b5cb8;--stale-t:#653c8c;
    --fail-f:#fdefe9;--fail-s:#c65f36;--fail-t:#a8431a}
  @media (prefers-color-scheme:dark){:root{--bg:#0f1114;--panel:#15181c;--ink:#ecebe8;
    --muted:#9a978f;--line:#2b2e34;
    --done-f:#122a1e;--done-s:#4fae7c;--done-t:#8ad6ac;
    --ready-f:#101f38;--ready-s:#5b8fe8;--ready-t:#9dc0ff;
    --block-f:#191b1f;--block-s:#3c3f45;--block-t:#8a877f;
    --queue-f:#00000000;--queue-s:#2b2e34;--queue-t:#6f6c67;
    --gate-f:#291e0b;--gate-s:#c9932f;--gate-t:#e7c072;
    --stale-f:#1e1428;--stale-s:#9d6fc9;--stale-t:#c9a5e8;
    --fail-f:#2a150e;--fail-s:#d4744a;--fail-t:#e89468}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1300px;margin:0 auto;padding:34px 22px 80px}
  header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:26px}
  h1{font-size:26px;line-height:1.2;margin:0 0 6px;letter-spacing:-.015em;font-weight:620}
  .lede{color:var(--muted);margin:0 0 16px;max-width:70ch}.lede b{color:var(--ink)}
  .meta{display:flex;flex-wrap:wrap;gap:8px}
  .pill{font:12px/1 ui-monospace,Menlo,monospace;color:var(--muted);border:1px solid var(--line);
    border-radius:999px;padding:6px 11px;white-space:nowrap}.pill b{color:var(--ink);font-weight:600}
  .pill.hot{border-color:var(--ready-s);color:var(--ready-t)}
  .pill.hot b{color:var(--ready-t)}
  h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
    font-weight:640;margin:40px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
  .legend{display:flex;flex-wrap:wrap;gap:16px;margin:0 0 8px}
  .lg{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--muted)}
  .sw{width:13px;height:13px;border-radius:3px;border:1.5px solid}
  .scroll{overflow-x:auto;padding:4px 0 10px}
  svg.graph{display:block;min-width:1000px;width:100%;height:auto}
  .nlab{font:600 14.5px ui-sans-serif,-apple-system,sans-serif}
  .nsub{font:12px ui-monospace,Menlo,monospace}
  .nown{font:11.5px ui-sans-serif,-apple-system,sans-serif}
  .stage{font:600 10.5px ui-sans-serif,-apple-system,sans-serif;letter-spacing:.11em;fill:var(--muted)}
  .edge{stroke:var(--line);stroke-width:1.6;fill:none}
  .edge-dash{stroke:var(--line);stroke-width:1.6;fill:none;stroke-dasharray:5 4}
  .edgelab{font:11px ui-sans-serif,sans-serif;fill:var(--muted)}
  .s-done rect{fill:var(--done-f);stroke:var(--done-s)}
  .s-done .nlab{fill:var(--done-t)}.s-done .nsub,.s-done .nown{fill:var(--done-t);opacity:.8}
  .s-ready rect{fill:var(--ready-f);stroke:var(--ready-s);stroke-width:2}
  .s-ready .nlab{fill:var(--ready-t)}.s-ready .nsub,.s-ready .nown{fill:var(--ready-t);opacity:.85}
  .s-block rect{fill:var(--block-f);stroke:var(--block-s);stroke-dasharray:5 4}
  .s-block .nlab{fill:var(--block-t)}.s-block .nsub,.s-block .nown{fill:var(--block-t);opacity:.85}
  .s-queue rect{fill:var(--queue-f);stroke:var(--queue-s)}
  .s-queue .nlab{fill:var(--queue-t)}.s-queue .nsub,.s-queue .nown{fill:var(--queue-t);opacity:.9}
  .s-gate rect{fill:var(--gate-f);stroke:var(--gate-s);stroke-width:2.4}
  .s-gate .nlab{fill:var(--gate-t)}.s-gate .nsub,.s-gate .nown{fill:var(--gate-t);opacity:.9}
  .s-stale rect{fill:var(--stale-f);stroke:var(--stale-s);stroke-width:2.4;stroke-dasharray:3 3}
  .s-stale .nlab{fill:var(--stale-t)}.s-stale .nsub,.s-stale .nown{fill:var(--stale-t);opacity:.9}
  .s-fail rect{fill:var(--fail-f);stroke:var(--fail-s);stroke-width:2.4}
  .s-fail .nlab{fill:var(--fail-t)}.s-fail .nsub,.s-fail .nown{fill:var(--fail-t);opacity:.9}
  .callout{background:var(--fail-f);border:1px solid var(--fail-s);border-radius:8px;padding:16px 18px}
  .callout table{width:100%;border-collapse:collapse;font-size:12.9px}
  .callout td{padding:7px 10px 7px 0;vertical-align:top;border-bottom:1px solid var(--line)}
  .callout tr:last-child td{border-bottom:0}
  .callout td:first-child{color:var(--muted);white-space:nowrap;width:1%;padding-right:16px;font-weight:600}
  table.grid{width:100%;border-collapse:collapse;font-size:13px}
  table.grid th{text-align:left;font-size:11px;letter-spacing:.07em;text-transform:uppercase;
    color:var(--muted);font-weight:640;padding:0 12px 8px 0;border-bottom:1px solid var(--line)}
  table.grid td{padding:9px 12px 9px 0;border-bottom:1px solid var(--line);vertical-align:top}
  code{font:12.4px ui-monospace,Menlo,monospace;background:var(--block-f);padding:1.5px 5px;border-radius:4px}
  .lim{color:var(--muted);font-size:13px;padding-left:19px;margin:0}.lim li{margin-bottom:6px}
  footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
"""

LEGEND = [("done", "done"), ("ready", "in flight / waiting on you"), ("fail", "rejected"),
          ("block", "blocked"), ("queue", "queued"), ("gate", "gate — your explicit GO"),
          ("stale", "stale — inputs moved after the output was written")]


def palette_css(m):
    """Optional per-programme colour override, light and dark."""
    out = ""
    light, dark = m.get("palette"), m.get("palette_dark")
    if light:
        out += "\n  :root{" + "".join(f"--{k}:{v};" for k, v in light.items()) + "}"
    if dark:
        out += ("\n  @media (prefers-color-scheme:dark){:root{"
                + "".join(f"--{k}:{v};" for k, v in dark.items()) + "}}")
    return out


# --------------------------------------------------------------- text metrics
# ADVANCE WIDTHS PER 1px OF FONT-SIZE, for the faces the node boxes use.
#
# WHY THIS TABLE EXISTS. `maxlen` counted CHARACTERS against one budget shared by
# all three text rows. But `.nsub` is 12px MONOSPACE and `.nown` is 11.5px
# proportional sans, so at the 46-character budget a monospace sub sets 332px
# inside a 246px box — 35% over — and the check waved it through, because the
# budget was calibrated for the proportional face. One gate node
# shipped with its sub-line 0.2px inside its own border and nothing fired.
#
# WHY NOT SOMETHING COARSER. Measured on a live graph: a flat per-class
# constant carries ±13% spread, about 30px on a 240px budget. Five-bucket
# character classes were measured at up to 23.5px error. Per-key CHARACTER budgets
# derived from worst-case advance fail legitimate content, because a 29-character
# label sets 210.8px while a 45-character note sets 235.9px — only per-character
# widths separate those. This table predicts every rendered string across the
# three live graphs to within 1.7px.
#
# TO REGENERATE, in a browser on the target machine:
#   ctx.font = '100px ui-sans-serif,-apple-system,sans-serif'      # and '600 100px …'
#   [...Array(95)].map((_, i) => ctx.measureText(String.fromCharCode(32 + i)).width / 100)
# Font SIZE scales linearly — measured at 0px error — so one table per weight
# serves every size. WEIGHT does not: semibold/regular ratios run 0.96 to 1.34,
# which is why both are held.
#
# THE LIMIT, STATED PLAINLY. These are the metrics this machine resolves for
# `ui-sans-serif`. A Linux host renders a different face and the estimate drifts.
# That is why MARGIN_PX exists, and why this guard refuses rather than certifies.
_METRIC_CHARS = "".join(chr(i) for i in range(32, 127)) + "·×–—→−"

_W_REGULAR = (
    0.2778, 0.2778, 0.3550, 0.5562, 0.5562, 0.8892, 0.6670, 0.1909, 0.3330, 0.3330,
    0.3892, 0.5840, 0.2778, 0.3330, 0.2778, 0.2778, 0.5562, 0.5562, 0.5562, 0.5562,
    0.5562, 0.5562, 0.5562, 0.5562, 0.5562, 0.5562, 0.2778, 0.2778, 0.5840, 0.5840,
    0.5840, 0.5562, 1.0151, 0.6670, 0.6670, 0.7222, 0.7222, 0.6670, 0.6108, 0.7778,
    0.7222, 0.2778, 0.5000, 0.6670, 0.5562, 0.8330, 0.7222, 0.7778, 0.6670, 0.7778,
    0.7222, 0.6670, 0.6108, 0.7222, 0.6670, 0.9438, 0.6670, 0.6670, 0.6108, 0.2778,
    0.2778, 0.2778, 0.4692, 0.5562, 0.3330, 0.5562, 0.5562, 0.5000, 0.5562, 0.5562,
    0.2778, 0.5562, 0.5562, 0.2222, 0.2222, 0.5000, 0.2222, 0.8330, 0.5562, 0.5562,
    0.5562, 0.5562, 0.3330, 0.5000, 0.2778, 0.5562, 0.5000, 0.7222, 0.5000, 0.5000,
    0.5000, 0.3340, 0.2598, 0.3340, 0.5840, 0.2778, 0.5840, 0.5562, 1.0000, 1.0000,
    0.5840,
)
_W_SEMIBOLD = (
    0.2778, 0.3330, 0.4741, 0.5562, 0.5562, 0.8892, 0.7222, 0.2378, 0.3330, 0.3330,
    0.3892, 0.5840, 0.2778, 0.3330, 0.2778, 0.2778, 0.5562, 0.5562, 0.5562, 0.5562,
    0.5562, 0.5562, 0.5562, 0.5562, 0.5562, 0.5562, 0.3330, 0.3330, 0.5840, 0.5840,
    0.5840, 0.6108, 0.9751, 0.7222, 0.7222, 0.7222, 0.7222, 0.6670, 0.6108, 0.7778,
    0.7222, 0.2778, 0.5562, 0.7222, 0.6108, 0.8330, 0.7222, 0.7778, 0.6670, 0.7778,
    0.7222, 0.6670, 0.6108, 0.7222, 0.6670, 0.9438, 0.6670, 0.6670, 0.6108, 0.3330,
    0.2778, 0.3330, 0.5840, 0.5562, 0.3330, 0.5562, 0.6108, 0.5562, 0.6108, 0.5562,
    0.3330, 0.6108, 0.6108, 0.2778, 0.2778, 0.5562, 0.2778, 0.8892, 0.6108, 0.6108,
    0.6108, 0.6108, 0.3892, 0.5562, 0.3330, 0.6108, 0.5562, 0.7778, 0.5562, 0.5562,
    0.5000, 0.3892, 0.2798, 0.3892, 0.5840, 0.2778, 0.5840, 0.5562, 1.0000, 1.0000,
    0.5840,
)
if not len(_METRIC_CHARS) == len(_W_REGULAR) == len(_W_SEMIBOLD):   # pragma: no cover
    sys.exit("render-graph: the advance-width tables are out of step with _METRIC_CHARS")

SANS_REGULAR = dict(zip(_METRIC_CHARS, _W_REGULAR))
SANS_SEMIBOLD = dict(zip(_METRIC_CHARS, _W_SEMIBOLD))
MONO_ADVANCE = 0.6021          # 12px Menlo measured 7.225px for EVERY glyph in use
UNMEASURED = 0.62              # an unknown glyph is assumed wide, so it errs to refusing

# (table, font-size) per text row, mirroring the CSS: .nlab .nsub .nown
TEXT_METRICS = {
    "label": (SANS_SEMIBOLD, 14.5),
    "sub":   (None,          12.0),          # None = the monospace face
    "note":  (SANS_REGULAR,  11.5),
    "note2": (SANS_REGULAR,  11.5),
}
# Total horizontal breathing room a node must keep. Calibrated against a live
# graph: the broken node had 0.4px of total slack, and the tightest three
# legitimate ones had 10.2, 13.3 and 14.0. Eight separates them with room to spare.
MARGIN_PX = 8


def text_px(s, key):
    """Estimated rendered width of one node text row, in px."""
    table, size = TEXT_METRICS[key]
    if table is None:
        return len(s) * MONO_ADVANCE * size
    return sum(table.get(c, UNMEASURED) for c in s) * size


def check_lengths(layout, maxlen, on_fail="warn", permissive=False):
    """Catch node text that would overflow its own box. Returns the warnings.

    THE GUARD IS PIXELS, AND IT ALWAYS RUNS, because every node knows its own box
    width from `row_boxes` — the same function that draws it — so a `span: full`
    node is measured against a full-width budget and a quarter node against a
    quarter. That was why the old check had to be opt-in: one character budget
    could not describe both, and turning it on by default failed 40 legitimate
    nodes across the two existing graphs.

    IT WARNS RATHER THAN BREAKS BY DEFAULT, and the reason is measured. Turning it
    on as a hard refusal stops two live programmes rendering at all: the
    first graph measured had 45 of 179 text rows overflowing, the worst by 1,022px,
    and a second had 7. Those graphs are genuinely damaged — note
    text visibly bleeds across box borders into neighbouring nodes — but a guard
    that lands as a build failure on somebody else's programme is a guard nobody
    thanks you for. Set `meta.width_check: break` once a programme is clean, and it
    stays clean. `--permissive` downgrades that, as it does every other check.

    `meta.maxlen` survives as an optional house-style cap on verbosity. It is no
    longer the overflow guard, and it no longer has to be set for one to apply.
    """
    over, long = [], []
    for band in layout:
        for row in band["rows"]:
            for nd, (_x, box_w) in zip(row, row_boxes(row)):
                budget = box_w - MARGIN_PX
                for key in TEXT_METRICS:
                    if not nd.get(key):
                        continue
                    s = str(nd[key])
                    px = text_px(s, key)
                    if px > budget:
                        over.append((nd.get("label", "?"), key, px, budget, s))
                    if maxlen and key != "label" and len(s) > maxlen:
                        long.append((nd.get("label", "?"), key, len(s), s))
    # `meta.maxlen` KEEPS ITS OLD TEETH. It was always opt-in and always breaking, so
    # a programme that sets it has asked for a hard cap and must keep getting one.
    # Only the new pixel guard is warn-by-default.
    if long and not permissive:
        raise DeriveError(
            f"node text overflows the house cap (meta.maxlen = {maxlen} chars):\n"
            + "\n".join(f"    {lab:<34} {k:<5} {n:>3}  {v!r}" for lab, k, n, v in long)
            + "\n  Nothing was written.")
    if not over:
        return []
    msg = (f"node text would overflow its box ({len(over)} row(s)):\n" + "\n".join(
        f"    {lab:<34} {k:<5} {px:6.1f}px into {bud:.0f}px  {v!r}"
        for lab, k, px, bud, v in over))
    if on_fail == "break" and not permissive:
        raise DeriveError(msg + "\n  Nothing was written.")
    return [msg]


def show_in_cmux(path):
    """Open a rendered graph in the cmux browser pane.

    WHY THIS EXISTS. The renderer wrote the file and stopped, so every guard in this
    skill watches the numbers and nothing watches the page. Three defects in one
    graph were found only by looking — clipped stage labels, a footer naming the wrong
    state file, and a node whose text touched its own border. Making `render` mean
    `render and show me` is the cheap half of closing that gap; the other half is
    check_lengths measuring pixels.

    NEVER FATAL. Cron and pre-commit runs have no cmux and must still render, so every
    failure here reports and returns.
    """
    if not shutil.which("cmux"):
        print("  --open: cmux is not on PATH, so nothing was shown")
        return
    def cmux(*args, timeout=20):
        return subprocess.run(("cmux",) + args, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    try:
        if (status := cmux("browser", "status", timeout=10)) != "enabled":
            print(f"  --open: cmux browser reports {status!r}, so nothing was shown")
            return
        # Spaces and em dashes are ordinary in these filenames; quote() leaves "/" alone.
        url = "file://" + urllib.parse.quote(str(path))
        out = cmux("browser", "open", url, "--focus", "true")
        surface = next((t.split("=", 1)[1] for t in out.split() if t.startswith("surface=")), None)
        if not surface:
            print(f"  --open: {out or 'cmux browser open returned nothing'}")
            return
        # CONFIRM THE PAGE RATHER THAN ASSUMING IT. `open` returns once the surface
        # exists, which is before the document has parsed.
        cmux("browser", "--surface", surface, "wait", "--load-state", "complete",
             "--timeout-ms", "10000", timeout=25)
        title = cmux("browser", "--surface", surface, "get", "title", timeout=10)
        print(f"  opened in cmux {surface}: {title or '(no title)'}")
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"  --open: could not drive cmux ({exc}), so nothing was shown")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state", help="path to <programme>.state.yaml")
    ap.add_argument("--check", action="store_true",
                    help="validate and report; write nothing. Exits 5 if the render "
                         "would change or a node reads stale")
    ap.add_argument("--permissive", action="store_true",
                    help="downgrade breaking checks to warnings, for drafting")
    ap.add_argument("--actor", default="render-graph", help="actor recorded on logged transitions")
    ap.add_argument("--open", action="store_true", dest="open_",
                    help="after rendering, show the page in the cmux browser pane. "
                         "Never fatal: a run without cmux still renders")
    args = ap.parse_args(argv)
    if args.check and args.open_:
        # --check writes nothing, so opening would show whatever was on disk from the
        # last render. Showing a stale page under a flag named --check is the worst
        # possible combination, so it is refused rather than quietly ignored.
        return "--open cannot be combined with --check: there would be nothing new to show"

    state = pathlib.Path(args.state).expanduser().resolve()
    if not state.exists():
        return f"no such state file: {state}"
    stem = (state.name[: -len(".state.yaml")] if state.name.endswith(".state.yaml")
            else state.stem)
    base = state.parent
    out_path = base / f"{stem}.html"
    events_path = base / f"{stem}.events.jsonl"
    prints_path = base / f"{stem}.fingerprints.json"

    st = yaml.safe_load(state.read_text(encoding="utf-8"))

    # DERIVATION. Only a state file that asks for it gets substitution, so files
    # without a derive block cannot be broken by a stray brace in their prose.
    derived, warnings = {}, []
    if st.get("derive"):
        d = st["derive"]
        derived = {"today": datetime.date.today().isoformat()}
        derived.update(load_sources(d.get("sources"), base))
        derived.update(load_hooks(d.get("hooks"), base))
        warnings = run_checks(d.get("checks"), derived, args.permissive)
        st = {k: v for k, v in st.items() if k != "derive"}
        st = subst(st, derived)

    m = st["meta"]
    nodes = [n for b in st["layout"] for r in b["rows"] for n in r]
    warnings += check_lengths(st["layout"], int(m.get("maxlen") or 0),
                              str(m.get("width_check") or "warn").lower(), args.permissive)

    # MEASURED STATUS beats claimed status. A node declaring an output and inputs
    # reads `stale` when its inputs changed after the output was last built,
    # whatever the YAML says.
    n_stale = staleness(nodes, base, prints_path, write=not args.check)

    body, labels, height = build_graph(st["layout"])
    stage_svg = [
        f'  <text class="stage" x="150" y="{y}" text-anchor="end">{t}</text>' for y, t in labels
    ]
    # THE STAGE GUTTER IS SIZED TO THE LONGEST LABEL. Stage titles are right-anchored
    # at x=150, and a fixed viewBox starting at 0 silently clipped every label wider
    # than that: "2 · SURVEY RESULTS BY SITE" rendered as "URVEY RESULTS BY SITE", and
    # three other stages lost their numbers. It cost nothing at render time and only
    # showed up on the page, so the gutter is measured here instead.
    widest = max((len(str(t)) for _, t in labels), default=0) * STAGE_CHAR_W
    min_x = -max(0, int(widest + 12 - 150))
    hot = set(m.get("pills_hot") or [])
    pills = "\n    ".join(
        f'<span class="pill{" hot" if k in hot else ""}">{k} <b>{v}</b></span>'
        for k, v in m["pills"].items()
    )
    pills += f'\n    <span class="pill">updated <b>{m["updated"]}</b></span>'
    labels_by_status = dict(LEGEND) | (m.get("legend") or {})
    shown = {nd["status"] for nd in nodes}
    legend = "\n  ".join(
        f'<span class="lg"><i class="sw" style="background:var(--{k}-f);'
        f'border-color:var(--{k}-s)"></i>{labels_by_status[k]}</span>'
        for k, _ in LEGEND if k != "stale" or "stale" in shown
    )

    events = [] if args.check else log_transitions(events_path, nodes, args.actor)
    n_events = sum(1 for _ in events_path.open()) if events_path.exists() else 0

    html = f"""<!doctype html>
<html lang="en-GB">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{m['title']}</title>
<style>{CSS}{palette_css(m)}</style></head>
<body><div class="wrap">
<header>
  <h1>{m['title']}</h1>
  <p class="lede">{m['lede']}</p>
  <div class="meta">
    {pills}
  </div>
</header>

<h2>Graph</h2>
<div class="legend">
  {legend}
</div>
<div class="scroll">
<svg class="graph" viewBox="{min_x} 0 {1240 - min_x} {height}" role="img"
     aria-label="{m.get('aria', 'Dependency graph of a programme of work.')}">
  <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
    orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="currentColor"/></marker></defs>
  <g color="var(--line)">
{chr(10).join(stage_svg)}

{chr(10).join(body)}
  </g>
</svg>
</div>

{chr(10).join(chr(10) + section(s) for s in st.get('sections', []))}

<footer>
  Generated by <code>render-graph.py</code> from <code>{state.name}</code>
  ({n_events} transitions logged in <code>{events_path.name}</code>).
  Edit the YAML and rerun; this file is overwritten.
</footer>
</div></body></html>
"""
    for w in warnings:
        print(f"  WARNING — {w}")

    if args.check:
        # Exit 5 means "this would change", after cog's --check, so a cron or a
        # pre-commit hook can act on the code without parsing the output.
        drifted = not out_path.exists() or out_path.read_text(encoding="utf-8") != html
        print(f"check {state.name}: {len(nodes)} nodes, {len(st['layout'])} stages, "
              f"{n_stale} stale, {'render differs' if drifted else 'render current'} "
              f"— nothing written")
        return EXIT_WOULD_CHANGE if (drifted or n_stale) else EXIT_OK

    out_path.write_text(html, encoding="utf-8")
    print(f"rendered {out_path.name}: {len(nodes)} nodes, {len(st['layout'])} stages, "
          f"viewBox height {height}")
    if n_stale:
        print(f"  {n_stale} node(s) read STALE — inputs changed after the output was built")
    for rec in events:
        print(f"  logged {rec['node']}: {rec['from']} → {rec['to']}")
    if args.open_:
        show_in_cmux(out_path)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
