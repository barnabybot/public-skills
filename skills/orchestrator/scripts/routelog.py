#!/usr/bin/env python3
"""python3 scripts/routelog.py — aggregate the route log written on session notes.

Reads every session note under $AGENT_NOTES/Sessions, takes the three
route lines the spawn helper writes (default, dispatched, reason) and the
note's status, and prints dispatches per tier, the override rate and the
outcome by tier. This is the only evidence that exists for the tiers no
public board measures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
from routing_log import append_evidence, vault_root

FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
ROUTE = re.compile(r"^- route (default|dispatched|reason): (.*)$", re.M)
TIER = re.compile(r"^tier ([^ ]+(?: of [^ ]+)?) → (.*)$")


def notes(since: date):
    root = vault_root() / "Sessions"
    for path in sorted(root.glob("*.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2}) ", path.name)
        if not m or date.fromisoformat(m.group(1)) < since:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        routes = dict(ROUTE.findall(text))
        if "default" not in routes:
            continue
        front = FRONT.match(text)
        status = re.search(r"^status: *(\S+)", front.group(1), re.M).group(1) if front else "?"
        yield path.name, routes, status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default=(date.today() - timedelta(days=30)).isoformat())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    since = date.fromisoformat(args.since)
    per_tier: dict[str, dict] = defaultdict(lambda: {"dispatches": 0, "overrides": 0, "status": defaultdict(int), "dispatched": defaultdict(int)})
    total = overrides = 0
    for name, routes, status in notes(since):
        m = TIER.match(routes["default"])
        tier, default_seat = (m.group(1), m.group(2)) if m else ("?", routes["default"])
        row = per_tier[tier]
        row["dispatches"] += 1
        row["status"][status] += 1
        row["dispatched"][routes.get("dispatched", "?")] += 1
        total += 1
        if routes.get("dispatched") and routes["dispatched"] != default_seat:
            row["overrides"] += 1
            overrides += 1
    if args.json:
        print(json.dumps({"since": args.since, "dispatches": total, "overrides": overrides,
                          "tiers": {k: {"dispatches": v["dispatches"], "overrides": v["overrides"],
                                        "status": dict(v["status"]), "dispatched": dict(v["dispatched"])}
                                    for k, v in per_tier.items()}}, indent=2))
    else:
        print(f"route log since {args.since}: {total} dispatches, {overrides} overridden")
        for tier, v in sorted(per_tier.items()):
            seats = ", ".join(f"{s} ×{n}" for s, n in sorted(v["dispatched"].items()))
            outcomes = ", ".join(f"{s} {n}" for s, n in sorted(v["status"].items()))
            print(f"  tier {tier:<8} {v['dispatches']:>3} dispatched, {v['overrides']:>2} overridden | {seats} | {outcomes}")
        if total == 0:
            print("  (no route lines yet; the helper writes them on every spawn)")
    if not args.no_log:
        append_evidence("log", "ok", f"since {args.since}: {total} dispatches, {overrides} overridden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
