#!/usr/bin/env python3
"""python3 scripts/aa_refresh.py — rank fleet models per category from Artificial Analysis.

Reads every model record that an AA model page embeds, keeps the fleet models
named in routing-metadata.yaml (`aa_release`), and for each category in the
`aa` block finds the efficient model-and-effort settings, then the knee: step
up while each extra index point costs no more than the class's cost_per_point.
Writes a dated report and a JSON snapshot under $AGENT_NOTES/Ops/orchestrator/aa/.
Proposes only; the table in SKILL.md changes after the user rules.

    aa_refresh.py [--html FILE] [--out DIR] [--no-write] [--quiet]

Exit 0 picks and successors match the last snapshot; 4 a pick changed or a
new successor appeared (the scheduler alerts); 1 fetch or parse failure.
--quiet prints nothing on exit 0, so a scheduler that mails any output stays
silent until something changed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML is not in the standard library.
    sys.exit(
        "aa_refresh.py needs PyYAML to read references/routing-metadata.yaml.\n"
        "Install it with:  pip install PyYAML\n"
    )

HERE = Path(__file__).resolve().parent
METADATA = HERE.parent / "references" / "routing-metadata.yaml"
from routing_log import vault_root


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def records(html: str) -> dict[str, dict]:
    """Decode the Next.js flight payload and return model records by slug."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    text = "".join(json.loads(f'"{c}"') for c in chunks)
    dec, out = json.JSONDecoder(), {}
    for m in re.finditer(r'\{"id":"[0-9a-f-]{36}","slug":"', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if "intelligenceIndex" in obj and "release" in obj:
            out[obj["slug"]] = obj
    return out


def measure(rec: dict, keys: list[str]) -> float | None:
    vals = []
    for key in keys:
        val = rec
        for part in key.split("."):
            val = (val or {}).get(part) if isinstance(val, dict) else None
        if val is None:
            return None
        # Index fields are 0-100; single benchmarks such as terminalBench40 are 0-1.
        vals.append(val if key.startswith(("capabilities", "intelligenceIndex")) else val * 100)
    return sum(vals) / len(vals)


def candidates(recs: dict, meta: dict, keys: list[str], cls: str) -> list[dict]:
    out = []
    for key, m in meta["models"].items():
        release = m.get("aa_release")
        if not release or cls in (m.get("aa_exclude") or []):
            continue
        if meta["providers"][m["provider"]].get("inferred") is False:
            continue
        for rec in recs.values():
            if rec["release"]["slug"] != release:
                continue
            cost = (((rec.get("intelligenceIndexCostPerTask") or {}).get("cost")) or {}).get("total")
            score = measure(rec, keys)
            # AA's base record is the top effort; a non-reasoning record has none.
            effort = (rec.get("effort") or {}).get("slug") or ("max" if rec.get("isReasoning") else "none")
            if cost is None or score is None or effort not in meta["providers"][m["provider"]]["efforts"]:
                continue
            out.append({"model": key, "display": m["display"], "provider": m["provider"],
                        "effort": effort, "score": round(score, 1), "cost": round(cost, 2)})
    return out


def hull(cands: list[dict]) -> list[dict]:
    """Efficient settings, cheapest first, with falling points per dollar."""
    front = sorted((c for c in cands if not any(
        d["score"] >= c["score"] and d["cost"] <= c["cost"] and d != c for d in cands)),
        key=lambda c: (c["cost"], -c["score"]))
    out: list[dict] = []
    for c in front:
        while len(out) >= 2:
            a, b = out[-2], out[-1]
            if (b["score"] - a["score"]) * (c["cost"] - a["cost"]) <= (c["score"] - a["score"]) * (b["cost"] - a["cost"]):
                out.pop()
            else:
                break
        out.append(c)
    return out


def knee(points: list[dict], limit: float) -> dict | None:
    if not points:
        return None
    pick = points[0]
    for nxt in points[1:]:
        gain = nxt["score"] - pick["score"]
        if gain <= 0 or (nxt["cost"] - pick["cost"]) / gain > limit:
            break
        pick = nxt
    return pick


def rank(recs: dict, meta: dict) -> dict:
    aa, out = meta["aa"], {}
    for name, cat in aa["categories"].items():
        cls, limit = cat["class"], aa["cost_per_point"][cat["class"]]
        cands = candidates(recs, meta, cat["measure"], cls)
        points = hull(cands)
        first = knee(points, limit)
        backup = knee(hull([c for c in cands if first and c["provider"] != first["provider"]]), limit)
        out[name] = {"class": cls, "limit": limit, "first": first, "backup": backup, "hull": points}
    return out


def successors(recs: dict, meta: dict) -> list[str]:
    notes = []
    for m in meta["models"].values():
        rel = next((r["release"] for r in recs.values() if r["release"]["slug"] == m.get("aa_release")), None)
        if rel and rel.get("deprecatedTo"):
            notes.append(f"{m['display']} ({m['aa_release']}): AA lists successor `{rel['deprecatedTo']}`. Check the CLI offers it before routing to it.")
    return notes


def label(c: dict | None) -> str:
    return "none" if not c else f"{c['display']} · {c['effort']} ({c['score']}, ${c['cost']:.2f})"


def report(ranked: dict, notes: list[str], changed: list[str], today: str, source: str) -> str:
    lines = [
        "---", f"created: {today}", "type: routing-evidence", f"source: {source}",
        "description: Weekly Artificial Analysis ranking of fleet models per routing category. Proposal input only.",
        "---", "", f"# AA routing refresh, {today}", "",
        "Score is the category's AA measure. Cost is AA's US$ per Intelligence Index task. The pick is the knee: "
        "the last efficient step whose extra points each cost no more than the class limit.", "",
        "| Category | Class | Limit $/pt | Pick | Backup (other provider) |", "|---|---|---|---|---|",
    ]
    for name, r in ranked.items():
        lines.append(f"| {name} | {r['class']} | {r['limit']:.2f} | {label(r['first'])} | {label(r['backup'])} |")
    lines += ["", "## Changed since the last snapshot", ""] + ([f"- {c}" for c in changed] or ["- None."])
    lines += ["", "## Successor models", ""] + ([f"- {n}" for n in notes] or ["- None."])
    lines += ["", "## Efficient settings per category", ""]
    for name, r in ranked.items():
        lines.append(f"- **{name}:** " + "; ".join(f"{c['display']} {c['effort']} {c['score']} ${c['cost']:.2f}" for c in r["hull"]))
    lines += ["", "Categories with no AA measure (writing, visual, orchestrator, review) keep their table rows; "
              "see workflows/routing-refresh.md for the Arena cross-check and the classification sample test."]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path, help="read a saved AA model page instead of fetching")
    ap.add_argument("--out", type=Path, help="evidence directory (default $AGENT_NOTES/Ops/orchestrator/aa)")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print nothing when picks and successors are unchanged")
    args = ap.parse_args()
    meta = yaml.safe_load(METADATA.read_text(encoding="utf-8"))
    source = str(args.html) if args.html else meta["aa"]["source"]
    try:
        recs = records(args.html.read_text(encoding="utf-8") if args.html else fetch(source))
    except (OSError, ValueError) as exc:
        print(f"[ERROR: AA fetch failed: {exc}]")
        return 1
    if not recs:
        print("[ERROR: AA page carried no model records; the page format may have changed]")
        return 1
    ranked = rank(recs, meta)
    notes = successors(recs, meta)
    out_dir = args.out or vault_root() / "Ops/orchestrator/aa"
    today = date.today().isoformat()
    picks = {k: [label(v["first"]).split(" (")[0], label(v["backup"]).split(" (")[0]] for k, v in ranked.items()}
    prior = sorted(out_dir.glob("*-aa-snapshot.json")) if out_dir.exists() else []
    prior = [p for p in prior if not p.name.startswith(today)]
    changed, known = [], []
    if prior:
        last = json.loads(prior[-1].read_text(encoding="utf-8"))
        old, known = last.get("picks", {}), last.get("successors", [])
        changed = [f"{k}: {old.get(k)} → {v}" for k, v in picks.items() if old.get(k) != v]
    new_notes = [n for n in notes if n not in known]
    text = report(ranked, notes, changed, today, source)
    status = 4 if changed or new_notes else 0
    if status or not args.quiet:
        print(text)
    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{today} AA routing refresh.md").write_text(text, encoding="utf-8")
        (out_dir / f"{today}-aa-snapshot.json").write_text(json.dumps(
            {"date": today, "picks": picks, "successors": notes, "ranked": ranked}, indent=1), encoding="utf-8")
    return status


if __name__ == "__main__":
    sys.exit(main())
