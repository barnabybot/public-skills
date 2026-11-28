#!/usr/bin/env python3
"""Hand a workflow agent its session assignment by integer index.

Agents are spawned by index 0..N-1 (the only thing passed through the LLM is the
integer N); each resolves its own session_id + digest_path from a fixed snapshot
on disk. This avoids passing UUIDs through model text, where they corrupt at scale.
"""
import json, sys, argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True, help="run directory (holds data/)")
ap.add_argument("--index", type=int, required=True)
a = ap.parse_args()

DATA = Path(a.root).expanduser() / "data"
items = json.loads((DATA / "missing-full.json").read_text())
if a.index < 0 or a.index >= len(items):
    print("")
    sys.exit(0)
sid = items[a.index]["session_id"]
print(json.dumps({"session_id": sid,
                  "digest_path": str((DATA / "digests" / f"{sid}.txt").resolve())}))
