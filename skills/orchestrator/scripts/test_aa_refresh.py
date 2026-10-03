#!/usr/bin/env python3
"""Fixture test for aa_refresh.py. Run: python3 skills/orchestrator/scripts/test_aa_refresh.py

Nothing here contacts Artificial Analysis: the page is built from invented records.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aa_refresh import hull, knee, label, rank, records, successors

HERE = Path(__file__).resolve().parent


def rec(slug, release, effort, ii, cost, fin, tb, deprecated_to=None, reasoning=True):
    return {"id": "00000000-0000-0000-0000-%012d" % (abs(hash(slug)) % 10**12), "slug": slug,
            "release": {"slug": release, "deprecatedTo": deprecated_to},
            "effort": {"slug": effort} if effort else None, "isReasoning": reasoning,
            "intelligenceIndex": ii, "capabilities": {"financeAndAccounting": fin},
            "terminalBench40": tb, "intelligenceIndexCostPerTask": {"cost": {"total": cost}}}


RECS = [
    rec("big-high", "big", "high", 50, 2.0, 55, 0.50),
    rec("big", "big", None, 56, 6.0, 60, 0.58),
    rec("cheap-high", "cheap", "high", 40, 0.2, 42, 0.30, deprecated_to="cheap-2"),
    rec("cheap-nr", "cheap", None, 20, 0.1, 21, 0.05, reasoning=False),
    rec("other-high", "other", "high", 48, 1.0, 50, 0.55),
]
HTML = "<script>self.__next_f.push([1,%s])</script>" % json.dumps(json.dumps({"models": RECS}, separators=(",", ":")))
META = {
    "providers": {"a": {"efforts": ["high", "max"]}, "b": {"efforts": ["high", "max"]}},
    "models": {
        "big": {"provider": "a", "display": "Big", "aa_release": "big"},
        "cheap": {"provider": "b", "display": "Cheap", "aa_release": "cheap"},
        "other": {"provider": "b", "display": "Other", "aa_release": "other", "aa_exclude": ["presented"]},
    },
    "aa": {"cost_per_point": {"presented": 0.5, "build": 0.1},
           "categories": {"finance": {"measure": ["capabilities.financeAndAccounting"], "class": "presented"},
                          "coding": {"measure": ["terminalBench40"], "class": "build"}}},
}


class AaRefreshTests(unittest.TestCase):
    def test_records_decode_flight_payload(self):
        self.assertEqual(set(records(HTML)), {r["slug"] for r in RECS})

    def test_knee_stops_when_a_point_costs_too_much(self):
        pts = hull([{"score": 40, "cost": 0.2}, {"score": 55, "cost": 2.0}, {"score": 60, "cost": 6.0}])
        self.assertEqual(knee(pts, 0.1)["score"], 40)  # 15 points for $1.80 is $0.12 a point
        self.assertEqual(knee(pts, 0.5)["score"], 55)  # the last 5 points cost $0.80 each

    def test_rank_applies_exclusion_backup_provider_and_scale(self):
        ranked = rank({r["slug"]: r for r in RECS}, META)
        fin = ranked["finance"]
        self.assertEqual((fin["first"]["model"], fin["first"]["effort"]), ("big", "high"))
        self.assertEqual(fin["backup"]["model"], "cheap")  # other is excluded from presented work
        self.assertNotIn("none", {c["effort"] for c in fin["hull"]})  # non-reasoning record dropped
        self.assertEqual(ranked["coding"]["first"]["score"], 55.0)  # 0-1 benchmark scaled to points

    def test_successor_reported(self):
        notes = successors({r["slug"]: r for r in RECS}, META)
        self.assertEqual(len(notes), 1)
        self.assertIn("cheap-2", notes[0])

    def test_models_without_aa_release_report_none(self):
        meta = json.loads(json.dumps(META))
        for m in meta["models"].values():
            m.pop("aa_release")
        ranked = rank({r["slug"]: r for r in RECS}, meta)
        self.assertEqual({label(r["first"]) for r in ranked.values()}, {"none"})
        self.assertEqual({label(r["backup"]) for r in ranked.values()}, {"none"})

    def test_one_provider_ranked_leaves_backup_none(self):
        meta = json.loads(json.dumps(META))
        meta["models"]["cheap"].pop("aa_release")
        meta["models"]["other"].pop("aa_release")
        fin = rank({r["slug"]: r for r in RECS}, meta)["finance"]
        self.assertEqual(fin["first"]["model"], "big")
        self.assertIsNone(fin["backup"])

    def test_shipped_metadata_runs_end_to_end(self):
        # The shipped placeholder fleet against a page with none of its releases:
        # every pick is "none", nothing crashes, and --quiet stays silent on a rerun.
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.html"
            page.write_text(HTML)
            cmd = [sys.executable, str(HERE / "aa_refresh.py"), "--html", str(page), "--out", tmp]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("| finance | presented | 0.75 | none | none |", first.stdout)
            self.assertEqual(len(list(Path(tmp).glob("*-aa-snapshot.json"))), 1)
            again = subprocess.run(cmd + ["--quiet", "--no-write"], capture_output=True, text=True)
            self.assertEqual((again.returncode, again.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
