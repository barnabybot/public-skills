#!/usr/bin/env python3
"""Render a dependency graph from its state YAML.

Edit the YAML, run this. Never hand-edit the HTML — this overwrites it.

    render-graph.py <programme>.state.yaml     # render
    render-graph.py <programme>.state.yaml --check   # validate, write nothing
    render-graph.py <programme>.state.yaml --open    # render, then show it in cmux

Each programme owns a trio beside its state file:

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

EXIT_OK, EXIT_ERROR, EXIT_WOULD_CHANGE = 0, 1, 5

try:
    import yaml
except ImportError:                                          # pragma: no cover
    sys.exit("render-graph needs PyYAML: python3 -m pip install --user pyyaml")

LEFT, RIGHT = 160, 1180
FULL = RIGHT - LEFT
GAP_N, GAP_W = 12, 30
ROW_GAP, BAND_GAP = 38, 46
SPANS = {"full": FULL, "wide": 680, "mid": 480}
STAGE_CHAR_W = 7.7
TEXT_KEYS = ("label", "sub", "note", "note2")
MAXLEN_DEFAULT = 46


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
    write {CS['engine']['bau']}, never {CS["engine"]["bau"]}.
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
            prints[nid], changed = cur, True
        elif was.get("inputs") != cur["inputs"]:
            nd["status"] = "stale"
            n_stale += 1
    if write and changed:
        prints_path.write_text(json.dumps(prints, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8")
    return n_stale


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
MONO_ADVANCE = 0.6021
UNMEASURED = 0.62              # an unknown glyph is assumed wide, so it errs to refusing

TEXT_METRICS = {
    "label": (SANS_SEMIBOLD, 14.5),
    "sub":   (None,          12.0),
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
    on as a hard refusal stops existing programmes rendering at all. Some graphs
    are genuinely damaged, and their note text visibly bleeds across box borders
    into neighbouring nodes. A guard that lands as a build failure on somebody
    else's programme is a guard nobody thanks you for. Set
    `meta.width_check: break` once a programme is clean, and it stays clean.
    `--permissive` downgrades that, as it does every other check.

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



import html as _html
import re

V3_CSS = """:root {
  --p-scale: 1;
  --serif: 'Meta Serif Pro', 'Hiragino Sans', Georgia, 'Times New Roman', serif;
  --sans: 'Meta Pro', 'Hiragino Sans', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
  --meta: 'Meta Pro', 'Hiragino Sans', -apple-system, sans-serif;
  --symbol: 'Hiragino Sans', 'Apple Symbols', 'Segoe UI Symbol', sans-serif;
  --mono: 'JetBrains Mono', 'Hiragino Sans', ui-monospace, SFMono-Regular, Menlo, monospace;
  --bg: \x23F4F4F2;
  --surface: \x23EDEDEA;
  --card: \x23FFFFFF;
  --ink: \x233F3F3C;
  --prose: \x234A4A48;
  --muted: \x235F5F5B;
  --faint: \x236A6A66;
  --rule: \x23DDDDD9;
  --rule-strong: \x23C9C9C4;
  --coral: \x23E8483F;
  --coral-text: \x23C82118;
  --slate: \x233E4E54;
  --bg: \x23F3F6FA;
  --surface: \x23E9EEF5;
  --card: \x23FFFFFF;
  --ink: \x2314181F;
  --prose: \x232C3440;
  --muted: \x23526070;
  --faint: \x236E7D8F;
  --rule: \x23D8E1EB;
  --rule-strong: \x23B6C5D6;
  --coral: \x23D13B2E;
  --coral-text: \x23B8291E;
  --slate: \x23385A7C;
  --done-f: \x23FFFFFF;  --done-b: \x2368A384;  --done-badge-bg: \x23EAF5EE;  --done-badge-t: \x231F5C3B;
  --ready-f: \x23DFEEFF; --ready-b: \x23385A7C; --ready-badge-bg: \x23CBE2FC; --ready-badge-t: \x231A3A5C;
  --gate-f: \x23FFFFFF;  --gate-b: \x23C68B34;  --gate-badge-bg: \x23FBF1DF;  --gate-badge-t: \x236E460B;
  --block-f: \x23FAFBFD; --block-b: \x239A7B69; --block-badge-bg: \x23F3ECE8; --block-badge-t: \x235C4030;
  --queue-f: \x23FFFFFF; --queue-b: \x237496B4; --queue-badge-bg: \x23EBF2F8; --queue-badge-t: \x232D4D69;
  --fail-f: \x23FFFDFD;  --fail-b: \x23C45147;  --fail-badge-bg: \x23FBEAE8;  --fail-badge-t: \x23781E16;
  --stale-f: \x23FFFDFD; --stale-b: \x23C45147; --stale-badge-bg: \x23FBEAE8; --stale-badge-t: \x23781E16;
  --wire: \x236E90B0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: \x230B0E14;
    --surface: \x23121721;
    --card: \x23161C28;
    --ink: \x23EEF2F7;
    --prose: \x23C8D1DC;
    --muted: \x238B9BB0;
    --faint: \x2368778C;
    --rule: \x23232C3B;
    --rule-strong: \x23364459;
    --coral: \x23E85A4F;
    --coral-text: \x23F28B82;
    --slate: \x237CC4FA;
    --done-f: \x23161C28;  --done-b: \x234E9A74;  --done-badge-bg: \x23162E23;  --done-badge-t: \x2386EFAC;
    --ready-f: \x2318293E; --ready-b: \x237CC4FA; --ready-badge-bg: \x231E3A5F; --ready-badge-t: \x23BAE6FD;
    --gate-f: \x23161C28;  --gate-b: \x23D49B43;  --gate-badge-bg: \x232E2312;  --gate-badge-t: \x23FDE68A;
    --block-f: \x23141923; --block-b: \x239E8272; --block-badge-bg: \x2329211D; --block-badge-t: \x23E6CFC2;
    --queue-f: \x23161C28; --queue-b: \x235C7C99; --queue-badge-bg: \x231B2836; --queue-badge-t: \x23BAE6FD;
    --fail-f: \x23161C28;  --fail-b: \x23D9655B;  --fail-badge-bg: \x23301917;  --fail-badge-t: \x23FECACA;
    --stale-f: \x23161C28; --stale-b: \x23D9655B; --stale-badge-bg: \x23301917; --stale-badge-t: \x23FECACA;
    --wire: \x23587898;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: calc(15px * var(--p-scale));
  line-height: 1.48;
  -webkit-font-smoothing: antialiased;
}
main { max-width: 1480px; margin: 0 auto; padding: 20px 24px 56px; }
.proto-switcher {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  padding: 8px 14px; margin-bottom: 16px;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
  font-size: 12.5px;
}
.proto-switcher-links { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.proto-switcher a {
  color: var(--ink); text-decoration: none; padding: 5px 10px; border-radius: 6px;
  border: 1px solid var(--rule); background: var(--card); font-weight: 500;
}
.proto-switcher a:hover { border-color: var(--ink); }
.proto-switcher a.active {
  background: var(--ready-f); border-color: var(--ready-b); color: var(--ready-t); font-weight: 600;
}
header {
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
  gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--rule);
}
h1 {
  margin: 0;
  font-family: var(--serif);
  font-size: calc(28px * var(--p-scale));
  font-weight: 400;
  letter-spacing: -0.015em;
  line-height: 1.18;
}
.lede {
  margin: 6px 0 0; color: var(--muted); max-width: 72ch;
  font-family: var(--serif);
  font-size: calc(16px * var(--p-scale)); line-height: 1.52;
}
.pills {
  display: flex; flex-wrap: wrap; gap: 6px;
  font: 12px/1.25 ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
}
.pill {
  padding: 5px 9px; border: 1px solid var(--rule); border-radius: 6px;
  background: var(--surface); color: var(--muted);
}
.pill b { color: var(--ink); font-weight: 650; }
.toolbar {
  position: sticky; top: 8px; z-index: 30;
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
  margin: 14px 0; padding: 9px 12px;
  border: 1px solid var(--rule-strong); border-radius: 8px;
  background: var(--card);
}
.filters, .actions, .views { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.filter-btn, .act-btn, .view-btn {
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 11px; border: 1.5px solid var(--rule-strong); border-radius: 8px;
  background: var(--card); color: var(--ink);
  font: inherit; font-size: 12.5px; font-weight: 500;
  transition: background .12s ease, border-color .12s ease, box-shadow .12s ease;
}
.filter-btn:hover, .act-btn:hover, .view-btn:hover { border-color: var(--slate); }
.filter-btn.active, .act-btn.active, .view-btn.active {
  background: var(--ink); color: var(--card); border-color: var(--ink); font-weight: 600;
}
.sw { width: 9px; height: 9px; border-radius: 999px; display: inline-block; flex-shrink: 0; }
.fb-frontier { border-color: rgba(184, 41, 30, 0.45); }
.fb-frontier .sw { background: var(--coral-text); }
.fb-frontier.active { background: var(--coral-text); color: \x23fff; border-color: var(--coral-text); }
.fb-frontier.active .sw { background: \x23fff; }
.fb-gate { border-color: rgba(198, 139, 52, 0.55); }
.fb-gate .sw { background: var(--gate-b); }
.fb-gate.active { background: var(--gate-b); color: \x23fff; border-color: var(--gate-b); }
.fb-gate.active .sw { background: \x23fff; }
.fb-ready { border-color: rgba(56, 90, 124, 0.55); background: var(--ready-f); }
.fb-ready .sw { background: var(--ready-b); }
.fb-ready.active { background: var(--ready-b); color: \x23fff; border-color: var(--ready-b); }
.fb-ready.active .sw { background: \x23fff; }
.fb-block { border-color: rgba(154, 123, 105, 0.6); border-style: dashed; }
.fb-block .sw { background: var(--block-b); }
.fb-block.active { background: var(--block-b); color: \x23fff; border-color: var(--block-b); border-style: solid; }
.fb-block.active .sw { background: \x23fff; }
.fb-queue { border-color: rgba(116, 150, 180, 0.6); }
.fb-queue .sw { background: var(--queue-b); }
.fb-queue.active { background: var(--queue-b); color: \x23fff; border-color: var(--queue-b); }
.fb-queue.active .sw { background: \x23fff; }
.fb-done { border-color: rgba(104, 163, 132, 0.55); }
.fb-done .sw { background: var(--done-b); }
.fb-done.active { background: var(--done-b); color: \x23fff; border-color: var(--done-b); }
.fb-done.active .sw { background: \x23fff; }
.cnt { font: 11px/1 var(--mono); font-variant-numeric: tabular-nums; color: var(--muted); }
.filter-btn.active .cnt { color: inherit; opacity: 0.9; }
.search-input {
  padding: 5px 10px; border: 1px solid var(--rule); border-radius: 6px;
  background: var(--bg); color: var(--ink); font: inherit; font-size: 12.5px; width: 175px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.workspace.inspector-open {
  grid-template-columns: minmax(0, 1fr) 360px;
}
@media (max-width: 980px) {
  .workspace.inspector-open { grid-template-columns: minmax(0, 1fr); }
  .inspector {
    position: fixed !important;
    top: auto !important;
    bottom: 12px;
    left: 12px;
    right: 12px;
    max-height: 54vh !important;
    z-index: 60;
    box-shadow: 0 -8px 28px rgba(0, 0, 0, 0.22);
  }
}
.canvas-card {
  border: 1px solid var(--rule);
  border-radius: 10px;
  background: var(--card);
  padding: 14px 16px 20px;
}
.canvas-hint {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
  padding: 2px 4px 12px; border-bottom: 1px solid var(--rule); margin-bottom: 16px;
  font-size: 12.5px; color: var(--muted);
}
.graph-board {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
svg.edge-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 2;
  overflow: visible;
}
.stage-block {
  position: relative;
  display: grid;
  grid-template-columns: 185px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
  padding-top: 14px;
  border-top: 1px dashed var(--rule);
}
.stage-block:first-of-type { border-top: 0; padding-top: 0; }
@media (max-width: 780px) {
  .stage-block { grid-template-columns: minmax(0, 1fr); gap: 10px; }
}
.stage-gutter {
  position: relative;
  z-index: 3;
  cursor: pointer;
  padding: 8px 10px;
  border: 1px solid var(--rule);
  border-radius: 8px;
  background: var(--surface);
  transition: border-color .12s ease;
}
.stage-gutter:hover { border-color: var(--ink); }
.stage-title {
  font-size: calc(12.5px * var(--p-scale));
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
}
.stage-meta {
  margin-top: 4px;
  font: 11.5px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.stage-bar-track {
  height: 4px; border-radius: 2px; background: var(--rule); margin-top: 6px; overflow: hidden;
}
.stage-bar-fill { height: 100%; background: var(--done-b); }
.stage-rows {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.stage-collapsed-pill {
  position: relative; z-index: 3;
  cursor: pointer;
  padding: 10px 14px;
  border: 1px dashed var(--rule-strong);
  border-radius: 8px;
  background: var(--surface);
  color: var(--muted);
  font-size: calc(13px * var(--p-scale));
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
}
.stage-collapsed-pill:hover { border-color: var(--ink); color: var(--ink); }
.node-row {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 16px;
  align-items: stretch;
}
.node-wrap {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.node-card {
  position: relative;
  cursor: pointer;
  border-radius: 12px;
  padding: 13px 16px;
  border: 1.75px solid var(--queue-b);
  background: var(--card);
  color: var(--ink);
  transition: transform .12s ease, opacity .15s ease, box-shadow .15s ease, border-color .15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.node-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.07);
}
.node-card.selected {
  box-shadow: 0 0 0 2.5px var(--slate), 0 8px 20px rgba(15, 23, 42, 0.12);
}
.node-wrap.dimmed { opacity: 0.16; }
.node-card.st-done  { background: var(--done-f);  border-color: var(--done-b); }
.node-card.st-ready { background: var(--ready-f); border-color: var(--ready-b); border-width: 2px; }
.node-card.st-queue { background: var(--queue-f); border-color: var(--queue-b); }
.node-card.st-block { background: var(--block-f); border-color: var(--block-b); border-style: dashed; }
.node-card.st-gate  { background: var(--gate-f);  border-color: var(--gate-b); }
.node-card.st-fail  { background: var(--fail-f);  border-color: var(--fail-b); }
.node-card.st-stale { background: var(--stale-f); border-color: var(--stale-b); }
.node-card.is-frontier {
  background: var(--ready-f);
  border-color: var(--slate);
  border-width: 2px;
}
.node-card.has-folded-branch {
  box-shadow: 4px 4px 0 -1px var(--card), 4px 4px 0 0.75px var(--done-b), 8px 8px 0 -1px var(--card), 8px 8px 0 0.75px var(--done-b);
  margin-right: 8px;
  margin-bottom: 6px;
}
.node-top {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; min-width: 0;
}
.node-label {
  font-family: var(--meta);
  font-size: calc(16px * var(--p-scale));
  font-weight: 500;
  color: var(--ink);
  letter-spacing: -0.01em;
  line-height: 1.28;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.node-badges {
  display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
}
.badge {
  font: 10.5px/1.2 var(--mono);
  font-weight: 600;
  padding: 2.5px 6px;
  border-radius: 5px;
  border: 1px solid var(--rule-strong);
  background: var(--surface);
  color: var(--muted);
  text-transform: lowercase;
  letter-spacing: 0.01em;
}
.badge-st-done  { background: var(--done-badge-bg);  color: var(--done-badge-t);  border-color: rgba(104, 163, 132, 0.4); }
.badge-st-ready { background: var(--ready-badge-bg); color: var(--ready-badge-t); border-color: rgba(56, 90, 124, 0.4); }
.badge-st-gate  { background: var(--gate-badge-bg);  color: var(--gate-badge-t);  border-color: rgba(198, 139, 52, 0.45); }
.badge-st-block { background: var(--block-badge-bg); color: var(--block-badge-t); border-color: rgba(154, 123, 105, 0.45); }
.badge-st-queue { background: var(--queue-badge-bg); color: var(--queue-badge-t); border-color: rgba(116, 150, 180, 0.45); }
.badge-st-stale, .badge-st-fail { background: var(--fail-badge-bg); color: var(--fail-badge-t); border-color: rgba(196, 81, 71, 0.45); }
.badge-frontier {
  background: var(--coral-text); color: \x23fff; border-color: var(--coral-text);
  text-transform: uppercase; font-weight: 700; letter-spacing: 0.03em;
}
.badge-branch {
  cursor: pointer;
  background: var(--card);
  color: var(--slate);
  border: 1.5px solid var(--slate);
  padding: 2.5px 8px;
  font-weight: 700;
}
.badge-branch:hover {
  background: var(--slate); color: var(--card);
}
.node-sub {
  font-family: var(--mono);
  font-size: calc(12.2px * var(--p-scale));
  font-weight: 400;
  color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.node-note {
  font: calc(11.3px * var(--p-scale))/1.35 var(--mono);
  color: var(--faint);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-top: 1px;
}
.branch-drawer {
  margin-top: 12px;
  padding: 16px 18px;
  border: 2px dotted var(--wire);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.42);
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.branch-drawer-hdr {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  font-family: var(--meta);
  font-size: 14px; font-weight: 500; color: var(--ink);
}
.branch-drawer-hdr .branch-tag {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--muted);
}
.dep-edge {
  fill: none;
  stroke: var(--wire);
  stroke-width: 1.85;
  stroke-dasharray: 2 5;
  stroke-linecap: round;
  opacity: 0.78;
  transition: opacity .15s ease, stroke-width .15s ease;
}
.dep-edge.same-row { opacity: 0.9; stroke-width: 2; }
.dep-edge.dimmed { opacity: 0.08 !important; }
.dep-edge.hi-up { stroke: var(--slate) !important; stroke-dasharray: none !important; stroke-width: 2.5 !important; opacity: 1 !important; }
.dep-edge.hi-down { stroke: var(--coral) !important; stroke-dasharray: none !important; stroke-width: 2.5 !important; opacity: 1 !important; }
.dep-dot { fill: var(--wire); opacity: 0.78; }
.dep-dot.dimmed { opacity: 0.08 !important; }
.dep-dot.hi-up { fill: var(--slate) !important; opacity: 1 !important; }
.dep-dot.hi-down { fill: var(--coral) !important; opacity: 1 !important; }
.inspector {
  position: sticky; top: 64px;
  border: 1px solid var(--rule-strong); border-radius: 10px;
  background: var(--card); padding: 16px;
  max-height: calc(100vh - 84px); overflow-y: auto;
}
.inspector h2 { margin: 0 0 4px; font-family: var(--serif); font-weight: 400; font-size: calc(18px * var(--p-scale)); line-height: 1.25; }
.insp-kv { margin: 10px 0; padding-top: 10px; border-top: 1px solid var(--rule); font-size: calc(13.5px * var(--p-scale)); }
.insp-k { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 4px; }
.chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.chip {
  cursor: pointer; padding: 3px 8px; border-radius: 5px;
  border: 1px solid var(--rule); background: var(--surface);
  font: 12px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace;
}
.chip:hover { border-color: var(--ink); }
.triage-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 12px; }
.triage-card { border: 1px solid var(--rule); border-radius: 8px; background: var(--card); padding: 14px; cursor: pointer; }
.triage-card:hover { border-color: var(--ink); }
.sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
}
.sec-card {
  border: 1px solid var(--rule);
  border-radius: 10px;
  background: var(--card);
  overflow: hidden;
}
.sec-card.callout-sec {
  background: var(--ready-f);
  border-color: var(--ready-b);
}
.sec-summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 13px 18px;
  font-size: calc(13.5px * var(--p-scale));
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
  background: var(--surface);
  border-bottom: 1px solid transparent;
  user-select: none;
}
.sec-card[open] > .sec-summary {
  border-bottom-color: var(--rule);
}
.sec-card.callout-sec > .sec-summary {
  background: rgba(62, 78, 84, 0.08);
  color: var(--ready-t);
}
.sec-summary::-webkit-details-marker { display: none; }
.sec-body {
  padding: 14px 18px 18px;
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: calc(14px * var(--p-scale));
  line-height: 1.5;
  table-layout: auto;
}
th, td {
  text-align: left;
  vertical-align: top;
  padding: 10px 14px 10px 0;
  border-bottom: 1px solid var(--rule);
  overflow-wrap: break-word;
}
th:last-child, td:last-child { padding-right: 0; }
tr:last-child td { border-bottom: 0; }
th {
  font-size: calc(11.5px * var(--p-scale));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 650;
  padding-bottom: 8px;
}
th:first-child, td:first-child {
  font-weight: 600;
  width: clamp(92px, 22%, 175px);
  max-width: 175px;
  padding-right: 16px;
  color: var(--ink);
  white-space: normal;
}
.callout-sec td:first-child {
  width: 1%;
  max-width: none;
  white-space: nowrap;
  padding-right: 14px;
}
.cell-sub {
  font-size: calc(12.5px * var(--p-scale));
  font-weight: 400;
  color: var(--muted);
  display: inline-block;
  margin-top: 2px;
  line-height: 1.38;
}
td:has(> code) {
  min-width: 135px;
}
@media (max-width: 760px) {
  main { padding: 14px 14px 40px; }
  .toolbar { position: static; padding: 8px 10px; }
  .search-input { width: 100%; }
  .stage-block { grid-template-columns: minmax(0, 1fr); gap: 10px; }
  .node-row { grid-template-columns: minmax(0, 1fr) !important; gap: 10px; }
  .node-wrap { grid-column: 1 / -1 !important; }
  .sec-summary { padding: 11px 14px; font-size: 12.5px; }
  .sec-body { padding: 10px 14px 14px; }
  th:first-child, td:first-child {
    width: 28%;
    max-width: 125px;
    padding-right: 12px;
  }
  .callout-sec td:first-child {
    width: 1%;
    max-width: 135px;
    white-space: normal;
    overflow-wrap: normal;
    padding-right: 12px;
  }
}
ul.lim {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: calc(14px * var(--p-scale));
  line-height: 1.55;
  max-width: 88ch;
}
code {
  font: calc(12px * var(--p-scale))/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--surface);
  padding: 2px 6px;
  border-radius: 4px;
  overflow-wrap: break-word;
  word-break: break-word;
}
footer { margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--rule); color: var(--faint); font-size: 12.5px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }"""

V3_JS = """(function() {
  const DATA = window.GRAPH_DATA;
  const NODES = DATA.nodes;
  const STAGES = DATA.stages;
  const EDGES = DATA.edges;
  let activeFilter = 'all';
  let searchQuery = '';
  let selectedId = null;
  let hoveredId = null;
  let edgeMode = 'dag';
  let fontScale = 1.0;
  const collapsedStages = new Set();
  const collapsedBranches = new Set();
  Object.values(NODES).forEach(n => {
    if (n.children && n.children.length && n.collapsed !== false) {
      collapsedBranches.add(n.id);
    }
  });
  function esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function spanCols(nd, rowLen) {
    if (rowLen === 1) {
      if (nd.span === 'full') return 12;
      if (nd.span === 'wide') return 10;
      if (nd.span === 'mid') return 8;
      return 7;
    }
    return Math.max(3, Math.floor(12 / rowLen));
  }
  function renderNodeCard(nd, rowLen, isChild) {
    const hasKids = nd.children && nd.children.length > 0;
    const isFolded = hasKids && collapsedBranches.has(nd.id);
    const cols = isChild ? Math.max(6, Math.floor(12 / rowLen)) : spanCols(nd, rowLen);
    const kidList = hasKids ? nd.children.flat() : [];
    const kidDone = kidList.filter(k => (NODES[k.id] || k).status === 'done').length;
    const effSt = nd.effective_status || nd.status;
    const isFront = Boolean(nd.is_frontier && effSt !== 'done');
    const badges = [];
    if (isFront) {
      badges.push(`<span class="badge badge-frontier" title="All upstream dependencies are done">frontier</span>`);
    }
    if (nd.role === 'checker') {
      badges.push(`<span class="badge" title="Independent checker / verification job">checker</span>`);
    }
    badges.push(`<span class="badge badge-st-${esc(effSt)}" title="Status: ${esc(effSt)}">${esc(effSt)}</span>`);
    if (hasKids) {
      const icon = isFolded ? '▸' : '▾';
      const label = isFolded ? `${icon} +${kidList.length} branch (${kidDone}/${kidList.length})` : `${icon} fold ${kidList.length}`;
      badges.push(`<button type="button" class="badge badge-branch" data-toggle-branch="${esc(nd.id)}">${label}</button>`);
    }
    let drawerHtml = '';
    if (hasKids && !isFolded) {
      const childRowsHtml = nd.children.map(crow => {
        const cards = crow.map(c => renderNodeCard(NODES[c.id] || c, crow.length, true)).join('');
        return `<div class="node-row">${cards}</div>`;
      }).join('');
      drawerHtml = `<div class="branch-drawer">
        <div class="branch-drawer-hdr">
          <span>${esc(nd.branch_label || (nd.id + ' Sub-Branch'))}</span>
          <span class="branch-tag">${kidDone}/${kidList.length} done · <button type="button" class="act-btn" style="padding:2px 8px;font-size:11px;margin-left:4px" data-toggle-branch="${esc(nd.id)}">fold</button></span>
        </div>
        ${childRowsHtml}
      </div>`;
    }
    const metaParts = [];
    if (nd.note) metaParts.push(nd.note);
    if (nd.note2) metaParts.push(nd.note2);
    else if (nd.owner) metaParts.push(`Owner: ${nd.owner}`);
    if (nd.dependencies && nd.dependencies.length) {
      metaParts.push(`Needs: ${nd.dependencies.join(', ')}`);
    }
    const metaLine = metaParts.join(' · ');
    return `<div class="node-wrap" id="wrap-${esc(nd.id)}" data-node-id="${esc(nd.id)}" style="grid-column: span ${cols}">
      <article class="node-card st-${esc(effSt)} ${isFront ? 'is-frontier' : ''} ${isFolded ? 'has-folded-branch' : ''} ${selectedId === nd.id ? 'selected' : ''}" id="card-${esc(nd.id)}" data-select-node="${esc(nd.id)}">
        <div class="node-top">
          <div class="node-label" title="${esc(nd.label)}">${esc(nd.label)}</div>
          <div class="node-badges">${badges.join('')}</div>
        </div>
        ${nd.sub ? `<div class="node-sub" title="${esc(nd.sub)}">${esc(nd.sub)}</div>` : ''}
        ${metaLine ? `<div class="node-note" title="${esc(metaLine)}">${esc(metaLine)}</div>` : ''}
      </article>
      ${drawerHtml}
    </div>`;
  }
  function renderBoard() {
    const board = document.getElementById('graph-board');
    if (!board) return;
    const html = STAGES.map((st, idx) => {
      const isCollapsed = collapsedStages.has(idx);
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      const bodyHtml = isCollapsed
        ? `<div class="stage-collapsed-pill" id="stage-pill-${idx}" data-toggle-stage="${idx}">
             <span><b>▸ ${esc(st.title)}</b> — ${st.done}/${st.total} done (${pct}%) · Nodes: ${esc(st.node_ids.join(', '))}</span>
             <span class="badge">expand stage</span>
           </div>`
        : `<div class="stage-rows">
             ${st.rows.map(row => `<div class="node-row">${row.map(nid => renderNodeCard(NODES[nid], row.length, false)).join('')}</div>`).join('')}
           </div>`;
      return `<section class="stage-block" data-stage-idx="${idx}">
        <div class="stage-gutter" data-toggle-stage="${idx}" title="Click to fold/unfold stage">
          <div class="stage-title">
            <span>${isCollapsed ? '▸' : '▾'} ${esc(st.short_title)}</span>
          </div>
          <div class="stage-meta">${st.done}/${st.total} done (${pct}%)</div>
          <div class="stage-bar-track"><div class="stage-bar-fill" style="width:${pct}%"></div></div>
        </div>
        ${bodyHtml}
      </section>`;
    }).join('');
    board.innerHTML = `<svg class="edge-layer" id="edge-layer"></svg>` + html;
    applyFilterState();
    drawEdges();
    setTimeout(drawEdges, 30);
  }
  function resolveVisibleAnchor(nid) {
    let el = document.getElementById('card-' + nid);
    if (el && el.getBoundingClientRect().width > 0) return el;
    const nd = NODES[nid];
    if (nd && nd.parent_id) {
      let pel = document.getElementById('card-' + nd.parent_id);
      if (pel && pel.getBoundingClientRect().width > 0) return pel;
    }
    if (nd && nd.stage_idx !== undefined && collapsedStages.has(nd.stage_idx)) {
      let sel = document.getElementById('stage-pill-' + nd.stage_idx);
      if (sel && sel.getBoundingClientRect().width > 0) return sel;
    }
    return null;
  }
  function roundedOrthoDown(x1, y1, x2, y2) {
    if (Math.abs(x2 - x1) < 6) {
      return `M ${x1} ${y1} L ${x2} ${y2}`;
    }
    const spanY = y2 - y1;
    const ym = spanY > 34 ? Math.round(y2 - 10) : Math.round((y1 + y2) / 2);
    const r = Math.max(2, Math.min(8, Math.floor(Math.abs(x2 - x1) / 2), Math.floor(Math.abs(ym - y1) - 1), Math.floor(Math.abs(y2 - ym) - 1)));
    const sx = x2 > x1 ? 1 : -1;
    return `M ${x1} ${y1} L ${x1} ${ym - r} Q ${x1} ${ym} ${x1 + sx * r} ${ym} L ${x2 - sx * r} ${ym} Q ${x2} ${ym} ${x2} ${ym + r} L ${x2} ${y2}`;
  }
  function drawEdges() {
    const svg = document.getElementById('edge-layer');
    const board = document.getElementById('graph-board');
    if (!svg || !board) return;
    const br = board.getBoundingClientRect();
    if (br.width < 10) return;
    svg.setAttribute('viewBox', `0 0 ${Math.round(br.width)} ${Math.round(br.height)}`);
    let defs = `<defs>
      <marker id="arr-base" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto"><path d="M 1.5,1.5 L 8,5 L 1.5,8.5" fill="none" stroke="var(--wire)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker>
      <marker id="arr-up" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto"><path d="M 1.5,1.5 L 8,5 L 1.5,8.5" fill="none" stroke="var(--slate)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></marker>
      <marker id="arr-down" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto"><path d="M 1.5,1.5 L 8,5 L 1.5,8.5" fill="none" stroke="var(--coral)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></marker>
    </defs>`;
    const focusId = hoveredId || selectedId;
    const paths = [];
    const seen = new Set();
    EDGES.forEach(e => {
      const isDirectFocus = focusId && (
        e.from === focusId || e.to === focusId ||
        (NODES[focusId] && (NODES[focusId].parent_id === e.from || NODES[focusId].parent_id === e.to))
      );
      if (edgeMode === 'focused' && !isDirectFocus) return;
      const uNode = NODES[e.from] || {};
      const vNode = NODES[e.to] || {};
      const stageDist = Math.abs((vNode.stage_idx || 0) - (uNode.stage_idx || 0));
      if (edgeMode === 'dag' && !focusId && (stageDist > 1 || vNode.parent_id === e.from)) return;
      const uEl = resolveVisibleAnchor(e.from);
      const vEl = resolveVisibleAnchor(e.to);
      if (!uEl || !vEl || uEl === vEl) return;
      const key = uEl.id + '->' + vEl.id;
      if (seen.has(key)) return;
      seen.add(key);
      const ur = uEl.getBoundingClientRect();
      const vr = vEl.getBoundingClientRect();
      const sameRow = Math.abs(ur.top - vr.top) < 28;
      const vertGap = vr.top - ur.bottom;
      if (edgeMode === 'dag' && !focusId) {
        const isCleanSameRow = sameRow && vr.left > ur.right - 12;
        const isCleanNextRow = !sameRow && vertGap >= -4 && vertGap <= 68;
        if (!isCleanSameRow && !isCleanNextRow) return;
      }
      let d = '';
      let ox = 0, oy = 0;
      if (sameRow && vr.left > ur.right - 12) {
        const x1 = Math.round(ur.right - br.left + 2);
        const y1 = Math.round(ur.top + Math.min(ur.height, vr.height) * 0.5 - br.top);
        const x2 = Math.round(vr.left - br.left - 3);
        ox = x1; oy = y1;
        d = `M ${x1} ${y1} L ${x2} ${y1}`;
      } else if (vertGap >= -8) {
        const x1 = Math.round(ur.left + ur.width/2 - br.left);
        const y1 = Math.round(ur.bottom - br.top + 2);
        const x2 = Math.round(vr.left + vr.width/2 - br.left);
        const y2 = Math.round(vr.top - br.top - 3);
        ox = x1; oy = y1;
        d = roundedOrthoDown(x1, y1, x2, y2);
      } else {
        const x1 = Math.round(ur.left + 24 - br.left);
        const y1 = Math.round(ur.top - br.top - 2);
        const x2 = Math.round(vr.left + 24 - br.left);
        const y2 = Math.round(vr.bottom - br.top + 3);
        ox = x1; oy = y1;
        d = `M ${x1} ${y1} C ${x1 - 28} ${(y1 + y2)/2}, ${x2 - 28} ${(y1 + y2)/2}, ${x2} ${y2}`;
      }
      let cls = 'dep-edge' + (sameRow ? ' same-row' : '');
      let dotCls = 'dep-dot';
      let marker = 'url(\x23arr-base)';
      if (focusId) {
        if (e.to === focusId || (NODES[focusId] && NODES[focusId].parent_id === e.to)) {
          cls += ' hi-up'; dotCls += ' hi-up'; marker = 'url(\x23arr-up)';
        } else if (e.from === focusId || (NODES[focusId] && NODES[focusId].parent_id === e.from)) {
          cls += ' hi-down'; dotCls += ' hi-down'; marker = 'url(\x23arr-down)';
        } else {
          cls += ' dimmed'; dotCls += ' dimmed';
        }
      }
      paths.push(`<circle cx="${ox}" cy="${oy}" r="2.5" class="${dotCls}"/><path d="${d}" class="${cls}" marker-end="${marker}"/>`);
    });
    svg.innerHTML = defs + paths.join('');
  }
  function matchesFilter(nd) {
    const st = nd.effective_status || nd.status;
    if (activeFilter === 'action') return ['gate', 'ready', 'stale', 'fail', 'block'].includes(st);
    if (activeFilter === 'frontier') return Boolean(nd.is_frontier);
    if (activeFilter !== 'all' && st !== activeFilter) return false;
    if (searchQuery) {
      const hay = `${nd.id} ${nd.label} ${nd.sub||''} ${nd.note||''} ${nd.owner||''} ${nd.acceptance||''}`.toLowerCase();
      return hay.includes(searchQuery);
    }
    return true;
  }
  function applyFilterState() {
    document.querySelectorAll('.node-wrap').forEach(el => {
      const id = el.getAttribute('data-node-id');
      const nd = NODES[id];
      if (!nd) return;
      el.classList.toggle('dimmed', !matchesFilter(nd));
    });
  }
  function selectNode(id) {
    selectedId = id;
    const ws = document.getElementById('workspace');
    const insp = document.getElementById('inspector');
    document.querySelectorAll('.node-card').forEach(c => {
      c.classList.toggle('selected', c.id === 'card-' + id);
    });
    if (!id || !NODES[id]) {
      ws.classList.remove('inspector-open');
      insp.style.display = 'none';
      drawEdges();
      return;
    }
    ws.classList.add('inspector-open');
    insp.style.display = 'block';
    const nd = NODES[id];
    const deps = (nd.dependencies || []).map(d => `<span class="chip" data-select-node="${esc(d)}">⇠ ${esc(d)} (${esc((NODES[d]||{}).status||'?')})</span>`).join('');
    const outs = (nd.dependents || []).map(d => `<span class="chip" data-select-node="${esc(d)}">⇢ ${esc(d)} (${esc((NODES[d]||{}).status||'?')})</span>`).join('');
    const kids = (nd.children || []).flat().map(k => `<div class="chip" data-select-node="${esc(k.id)}">${esc(k.id)} · ${esc(k.label)} (${esc(k.status)})</div>`).join('');
    insp.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
        <div>
          <span class="badge">${esc(nd.effective_status || nd.status)}</span>
          ${nd.is_frontier ? '<span class="badge badge-frontier">FRONTIER</span>' : ''}
          <h2 style="margin-top:6px">${esc(nd.label)}</h2>
        </div>
        <button type="button" class="act-btn" id="close-insp">✕</button>
      </div>
      <div style="color:var(--muted);font-size:13px;margin-top:2px">${esc(nd.stage || '')} · ID: <code>${esc(nd.id)}</code></div>
      ${nd.sub ? `<div class="insp-kv"><div class="insp-k">Summary</div><div>${esc(nd.sub)}</div></div>` : ''}
      ${nd.note ? `<div class="insp-kv"><div class="insp-k">Operational Note</div><div><code>${esc(nd.note)}</code></div></div>` : ''}
      ${nd.owner ? `<div class="insp-kv"><div class="insp-k">Owner / Custodian</div><div>${esc(nd.owner)}</div></div>` : ''}
      ${nd.acceptance ? `<div class="insp-kv"><div class="insp-k">Acceptance / Release Condition</div><div>${esc(nd.acceptance)}</div></div>` : ''}
      ${kids ? `<div class="insp-kv"><div class="insp-k">Foldable Branch Nodes (${(nd.children||[]).flat().length})</div><div class="chip-list">${kids}</div></div>` : ''}
      <div class="insp-kv"><div class="insp-k">Upstream Dependencies (${(nd.dependencies||[]).length})</div><div class="chip-list">${deps || '<span style="color:var(--faint)">None (root / unblocked)</span>'}</div></div>
      <div class="insp-kv"><div class="insp-k">Downstream Dependents (${(nd.dependents||[]).length})</div><div class="chip-list">${outs || '<span style="color:var(--faint)">None (terminal output)</span>'}</div></div>
      ${nd.output ? `<div class="insp-kv"><div class="insp-k">Output Artifact</div><div><code>${esc(nd.output)}</code></div></div>` : ''}
    `;
    document.getElementById('close-insp').onclick = () => selectNode(null);
    requestAnimationFrame(drawEdges);
  }
  document.addEventListener('click', e => {
    const brBtn = e.target.closest('[data-toggle-branch]');
    if (brBtn) {
      e.stopPropagation();
      const bid = brBtn.getAttribute('data-toggle-branch');
      if (collapsedBranches.has(bid)) collapsedBranches.delete(bid);
      else collapsedBranches.add(bid);
      renderBoard();
      return;
    }
    const stBtn = e.target.closest('[data-toggle-stage]');
    if (stBtn) {
      const sidx = Number(stBtn.getAttribute('data-toggle-stage'));
      if (collapsedStages.has(sidx)) collapsedStages.delete(sidx);
      else collapsedStages.add(sidx);
      renderBoard();
      return;
    }
    const selBtn = e.target.closest('[data-select-node]');
    if (selBtn) {
      const nid = selBtn.getAttribute('data-select-node');
      if (NODES[nid] && NODES[nid].parent_id && collapsedBranches.has(NODES[nid].parent_id)) {
        collapsedBranches.delete(NODES[nid].parent_id);
        renderBoard();
      }
      selectNode(nid);
    }
  });
  document.addEventListener('mouseover', e => {
    const card = e.target.closest('.node-card');
    const nid = card ? card.getAttribute('data-select-node') : null;
    if (nid !== hoveredId) {
      hoveredId = nid;
      drawEdges();
    }
  });
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.getAttribute('data-filter');
      applyFilterState();
    };
  });
  const sInput = document.getElementById('search-input');
  if (sInput) {
    sInput.oninput = () => {
      searchQuery = sInput.value.trim().toLowerCase();
      applyFilterState();
    };
  }
  document.getElementById('btn-fold-done').onclick = () => {
    STAGES.forEach((st, idx) => {
      if (st.done === st.total && st.total > 0) collapsedStages.add(idx);
    });
    Object.values(NODES).forEach(n => {
      if (n.children && n.children.length) collapsedBranches.add(n.id);
    });
    renderBoard();
  };
  document.getElementById('btn-expand-all').onclick = () => {
    collapsedStages.clear();
    collapsedBranches.clear();
    renderBoard();
  };
  document.getElementById('btn-edge-mode').onclick = function() {
    edgeMode = edgeMode === 'dag' ? 'focused' : 'dag';
    this.textContent = edgeMode === 'dag' ? 'Edges: All Dependencies' : 'Edges: Hover/Selected Only';
    drawEdges();
  };
  document.getElementById('btn-font-up').onclick = () => {
    fontScale = Math.min(1.3, +(fontScale + 0.08).toFixed(2));
    document.documentElement.style.setProperty('--p-scale', fontScale);
    requestAnimationFrame(drawEdges);
  };
  document.getElementById('btn-font-down').onclick = () => {
    fontScale = Math.max(0.85, +(fontScale - 0.08).toFixed(2));
    document.documentElement.style.setProperty('--p-scale', fontScale);
    requestAnimationFrame(drawEdges);
  };
  window.addEventListener('resize', () => requestAnimationFrame(drawEdges));
  renderBoard();
})();"""


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def extract_table_metadata(sections, known_ids):
    """Auto-extract dependencies, owners, and release conditions from sections tables."""
    extracted = {}
    for sec in sections or []:
        title = str(sec.get("title", "")).lower()
        if "dependenc" not in title:
            continue
        for row in sec.get("rows", []) or []:
            if not isinstance(row, list) or len(row) < 2:
                continue
            c0 = str(row[0])
            parts = re.split(r"<br\s*/?>", c0, maxsplit=1)
            head_raw = strip_tags(parts[0])
            nid = head_raw.split("·")[0].strip().split()[0].strip() if head_raw else ""
            if nid not in known_ids:
                continue
            needs_raw = strip_tags(parts[1]) if len(parts) > 1 else ""
            deps = []
            for tok in re.findall(r"[A-Za-z0-9_-]+", needs_raw):
                if tok in known_ids and tok != nid and tok not in deps:
                    deps.append(tok)
            c1 = str(row[1])
            m_strong = re.search(r"<strong>(.*?)</strong>", c1, re.S)
            owner = strip_tags(m_strong.group(1)) if m_strong else ""
            cond = strip_tags(re.sub(r"<strong>.*?</strong>", "", c1, flags=re.S))
            extracted[nid] = {"dependencies": deps, "owner": owner, "acceptance": cond}
    return extracted


def format_cell(val, col_idx):
    s = str(val).replace("overflow-wrap:anywhere", "overflow-wrap:break-word")
    if col_idx == 0 and "<br>" in s:
        head, tail = s.split("<br>", 1)
        s = f'{head}<br><span class="cell-sub">{tail}</span>'
    return s


def render_section_v3(sec, idx):
    t = str(sec.get("title", "Section"))
    kind = str(sec.get("kind", "table"))
    is_open = "open" if (kind == "callout" or idx < 2) else ""
    cls = "sec-card callout-sec" if kind == "callout" else "sec-card"
    if kind == "list":
        items = "\n".join(f"  <li>{i}</li>" for i in (sec.get("items") or []))
        count_lbl = f"{len(sec.get('items') or [])} items"
        body = f'<ul class="lim">\n{items}\n</ul>'
    elif kind == "callout":
        rows = "\n".join(f"  <tr><td>{format_cell(a, 0)}</td><td>{format_cell(b, 1)}</td></tr>" for a, b in (sec.get("rows") or []))
        count_lbl = f"{len(sec.get('rows') or [])} notes"
        body = f"<table>\n{rows}\n</table>"
    else:
        head = "".join(f"<th>{h}</th>" for h in (sec.get("head") or []))
        rows = "\n".join(
            "  <tr>" + "".join(f"<td>{format_cell(c, ci)}</td>" for ci, c in enumerate(r)) + "</tr>"
            for r in (sec.get("rows") or [])
        )
        count_lbl = f"{len(sec.get('rows') or [])} rows"
        body = f'<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>'
    return (
        f'<details class="{cls}" {is_open}>\n'
        f'  <summary class="sec-summary"><span>{t}</span><span class="badge" style="white-space:nowrap;flex-shrink:0">{count_lbl}</span></summary>\n'
        f'  <div class="sec-body">{body}</div>\n'
        f'</details>'
    )


def detect_role(nd):
    if nd.get("role"):
        return str(nd["role"])
    hay = f"{nd.get('label','')} {nd.get('note','')} {nd.get('owner','')}".lower()
    if any(k in hay for k in ("checker", "review", "recheck", "verify", "sceptic", "qa")):
        return "checker"
    return "worker"


def iter_all_nodes(layout):
    def _walk_rows(rows):
        for r in rows or []:
            row_list = r if isinstance(r, list) else [r]
            for nd in row_list:
                if isinstance(nd, dict):
                    yield nd
                    if nd.get("children"):
                        yield from _walk_rows(nd["children"])
    for band in layout or []:
        yield from _walk_rows(band.get("rows") or [])


def build_v3_page(st, state_name, events_name, n_events):
    meta = st.get("meta", {})
    stages_raw = st.get("layout", [])
    sections = st.get("sections", [])

    nodes_map = {}
    stages_out = []
    auto_seq = [0]

    def register_node(nd, st_title, st_idx, parent_id=None):
        auto_seq[0] += 1
        nid = str(nd.get("id") or f"node_{auto_seq[0]}")
        status = str(nd.get("status", "queue"))
        eff_st = "stale" if (nd.get("stale") and status == "done") else status
        kids_rows = []
        for crow in nd.get("children", []) or []:
            crow_list = crow if isinstance(crow, list) else [crow]
            reg_crow = [register_node(c, st_title, st_idx, parent_id=nid) for c in crow_list]
            kids_rows.append(reg_crow)

        rec = {
            "id": nid,
            "status": status,
            "effective_status": eff_st,
            "label": str(nd.get("label", nid)),
            "sub": str(nd.get("sub", "")),
            "note": str(nd.get("note", "")),
            "note2": str(nd.get("note2", "")),
            "owner": str(nd.get("owner", "")),
            "acceptance": str(nd.get("acceptance", "")),
            "output": str(nd.get("output", "")),
            "inputs": nd.get("inputs", []) or [],
            "span": nd.get("span"),
            "collapsed": nd.get("collapsed", True),
            "branch_label": nd.get("branch_label", ""),
            "stage": st_title,
            "stage_idx": st_idx,
            "parent_id": parent_id,
            "dependencies": list(nd.get("dependencies", []) or []),
            "dependents": [],
            "children": kids_rows,
            "role": detect_role(nd),
        }
        nodes_map[nid] = rec
        return rec

    for s_idx, st_block in enumerate(stages_raw):
        st_title = str(st_block.get("stage", f"Stage {s_idx}"))
        short_t = st_title.split("—")[0].strip()
        row_ids_list = []
        stage_node_ids = []
        for row in st_block.get("rows", []) or []:
            r_ids = []
            for nd in row:
                rec = register_node(nd, st_title, s_idx, None)
                r_ids.append(rec["id"])
                stage_node_ids.append(rec["id"])
            row_ids_list.append(r_ids)
        done_cnt = sum(1 for i in stage_node_ids if nodes_map[i]["effective_status"] == "done")
        stages_out.append({
            "title": st_title,
            "short_title": short_t,
            "rows": row_ids_list,
            "node_ids": stage_node_ids,
            "done": done_cnt,
            "total": len(stage_node_ids),
        })

    known_ids = set(nodes_map.keys())
    table_meta = extract_table_metadata(sections, known_ids)

    for nid, rec in nodes_map.items():
        tmeta = table_meta.get(nid, {})
        if not rec["dependencies"] and tmeta.get("dependencies"):
            rec["dependencies"] = tmeta["dependencies"]
        if not rec["owner"] and tmeta.get("owner"):
            rec["owner"] = tmeta["owner"]
        if not rec["acceptance"] and tmeta.get("acceptance"):
            rec["acceptance"] = tmeta["acceptance"]
        if not rec["dependencies"] and rec["note"]:
            m_dep = re.search(r"(?:Depends|after)\s*:?\s*([A-Za-z0-9_,\s/-]+)", rec["note"])
            if m_dep:
                for tok in re.findall(r"[A-Za-z0-9_-]+", m_dep.group(1)):
                    if tok in known_ids and tok != nid and tok not in rec["dependencies"]:
                        rec["dependencies"].append(tok)
        rec["role"] = detect_role(rec)

    edges = []
    any_deps = any(len(n["dependencies"]) > 0 for n in nodes_map.values())
    if any_deps:
        for nid, rec in nodes_map.items():
            for dep in rec["dependencies"]:
                if dep in nodes_map:
                    edges.append({"from": dep, "to": nid})
                    if nid not in nodes_map[dep]["dependents"]:
                        nodes_map[dep]["dependents"].append(nid)
    else:
        for st_item in stages_out:
            prev_row = None
            for row in st_item["rows"]:
                if prev_row and len(prev_row) == 1:
                    for cur in row:
                        edges.append({"from": prev_row[0], "to": cur})
                prev_row = row

    for nid, rec in nodes_map.items():
        eff = rec["effective_status"]
        if eff not in ("ready", "gate", "queue") or "conditional" in rec["label"].lower() or "held" in rec["sub"].lower():
            rec["is_frontier"] = False
        else:
            deps = [d for d in rec["dependencies"] if d in nodes_map]
            rec["is_frontier"] = all(nodes_map[d]["effective_status"] == "done" for d in deps) and (
                len(deps) > 0 or eff == "ready"
            )

    counts = {"all": len(nodes_map), "frontier": 0, "action": 0}
    for st_key in ("gate", "ready", "stale", "block", "queue", "done", "fail"):
        counts[st_key] = 0
    for rec in nodes_map.values():
        eff = rec["effective_status"]
        counts[eff] = counts.get(eff, 0) + 1
        if rec["is_frontier"]:
            counts["frontier"] += 1
        if eff in ("gate", "ready", "stale", "block", "fail"):
            counts["action"] += 1

    hot = set(meta.get("pills_hot") or [])
    pills_list = [
        f'<span class="pill{" hot" if k in hot else ""}">{esc(str(k))}: <b>{esc(str(v))}</b></span>'
        for k, v in (meta.get("pills") or {}).items()
    ]
    if meta.get("updated") and "updated" not in (meta.get("pills") or {}):
        pills_list.append(f'<span class="pill">updated: <b>{esc(str(meta["updated"]))}</b></span>')
    pills_html = "\n      ".join(pills_list)

    sections_html = "\n".join(render_section_v3(s, idx) for idx, s in enumerate(sections))
    sr_groups = "\n".join(
        f'  <g class="s-{rec["effective_status"]}"><title>{esc(nid)}: {esc(rec["label"])}</title></g>'
        for nid, rec in nodes_map.items()
    )
    payload = json.dumps({"nodes": nodes_map, "stages": stages_out, "edges": edges}, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta.get("title", "Work Graph"))}</title>
<style>{V3_CSS}{palette_css(meta)}</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>{esc(meta.get("title", "Work Graph"))}</h1>
      <p class="lede">{meta.get("lede", "")}</p>
    </div>
    <div class="pills">
      {pills_html}
    </div>
  </header>

  <section class="toolbar" aria-label="Graph filters and dynamic branch controls">
    <div class="filters">
      <button type="button" class="filter-btn active" data-filter="all">All <span class="cnt">{counts['all']}</span></button>
      <button type="button" class="filter-btn fb-frontier" data-filter="frontier"><span class="sw"></span>Frontier <span class="cnt">{counts['frontier']}</span></button>
      <button type="button" class="filter-btn" data-filter="action">Needs Action <span class="cnt">{counts['action']}</span></button>
      <button type="button" class="filter-btn fb-gate" data-filter="gate"><span class="sw"></span>Gate <span class="cnt">{counts['gate']}</span></button>
      <button type="button" class="filter-btn fb-ready" data-filter="ready"><span class="sw"></span>Ready <span class="cnt">{counts['ready']}</span></button>
      <button type="button" class="filter-btn fb-block" data-filter="block"><span class="sw"></span>Block <span class="cnt">{counts['block']}</span></button>
      <button type="button" class="filter-btn fb-queue" data-filter="queue"><span class="sw"></span>Queue <span class="cnt">{counts['queue']}</span></button>
      <button type="button" class="filter-btn fb-done" data-filter="done"><span class="sw"></span>Done <span class="cnt">{counts['done']}</span></button>
    </div>
    <div class="actions">
      <input type="search" id="search-input" class="search-input" placeholder="Search id, owner, note…">
      <button type="button" class="act-btn" id="btn-fold-done">Fold Done Stages</button>
      <button type="button" class="act-btn" id="btn-expand-all">Expand All Branches</button>
      <button type="button" class="act-btn" id="btn-edge-mode">Edges: All Dependencies</button>
      <button type="button" class="act-btn" id="btn-font-down" title="Decrease font scale">A−</button>
      <button type="button" class="act-btn" id="btn-font-up" title="Increase font scale">A+</button>
    </div>
  </section>

  <div class="workspace" id="workspace">
    <div class="canvas-card">
      <div class="canvas-hint">
        <span><b>Interactive DAG:</b> Click any <b>stage gutter</b> to fold a stage · Click <b>▸ +N branch</b> on a stacked card to expand/collapse sub-branches · Click any node to inspect full details &amp; trace dependencies.</span>
        <span><b>FRONTIER</b> = all upstream dependencies <code>done</code></span>
      </div>
      <div class="graph-board" id="graph-board" aria-label="{esc(meta.get('aria', 'Dependency graph of the programme workflow.'))}"></div>
    </div>
    <aside class="inspector" id="inspector" style="display:none" aria-label="Node inspector"></aside>
  </div>

  <svg class="sr-status-index" style="display:none" aria-hidden="true">
{sr_groups}
  </svg>

  <section class="sections">{sections_html}</section>

  <footer>
    <span>Generated by <code>render-graph.py</code> from <code>{esc(state_name)}</code> ({n_events} transitions logged in <code>{esc(events_name)}</code>). Edit the YAML and rerun; this file is overwritten.</span>
    <span>Updated {esc(str(meta.get("updated", "")))}</span>
  </footer>
</main>
<script>window.GRAPH_DATA = {payload};</script>
<script>{V3_JS}</script>
</body>
</html>
"""


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
    nodes = list(iter_all_nodes(st["layout"]))
    warnings += check_lengths(st["layout"], int(m.get("maxlen") or 0),
                              str(m.get("width_check") or "warn").lower(), args.permissive)

    n_stale = staleness(nodes, base, prints_path, write=not args.check)

    events = [] if args.check else log_transitions(events_path, nodes, args.actor)
    n_events = sum(1 for _ in events_path.open()) if events_path.exists() else 0

    html = build_v3_page(st, state.name, events_path.name, n_events)

    for w in warnings:
        print(f"  WARNING — {w}")

    if args.check:
        drifted = not out_path.exists() or out_path.read_text(encoding="utf-8") != html
        print(f"check {state.name}: {len(nodes)} nodes, {len(st['layout'])} stages, "
              f"{n_stale} stale, {'render differs' if drifted else 'render current'} "
              f"— nothing written")
        return EXIT_WOULD_CHANGE if (drifted or n_stale) else EXIT_OK

    out_path.write_text(html, encoding="utf-8")
    print(f"rendered {out_path.name}: {len(nodes)} nodes, {len(st['layout'])} stages")
    if n_stale:
        print(f"  {n_stale} node(s) read STALE — inputs changed after the output was built")
    for rec in events:
        print(f"  logged {rec['node']}: {rec['from']} → {rec['to']}")
    if args.open_:
        show_in_cmux(out_path)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
