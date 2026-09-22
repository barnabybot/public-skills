#!/usr/bin/env python3
"""Fixture test for resolve.py. Run: python3 skills/orchestrator/scripts/test_resolve.py

Every case runs against the placeholder table in ../SKILL.md and the invented
capacity fixtures in fixtures/. Nothing here contacts a provider or creates a
workspace. Edit the table and these expectations move with it — that coupling
is the point, because it is what stops the table and its documentation drifting
apart.
"""
from __future__ import annotations

import os
import json
import shlex
import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOLVE = HERE / "resolve.py"
CHECK = HERE / "check.py"
FIXTURES = HERE / "fixtures"
NOW = "2026-09-14T00:32:45Z"

A_LARGE = "claude-opus-5"
A_MID = "claude-sonnet-5"
A_SMALL = "claude-haiku-4-5-20251001"
B_LARGE = "REPLACE-WITH-YOUR-PROVIDER-B-LARGE-MODEL-ID"
B_MID = "REPLACE-WITH-YOUR-PROVIDER-B-MID-MODEL-ID"


def run(*args: str, fixture_dir: Path | None = None) -> tuple[int, dict, str]:
    env = dict(os.environ, ROUTING_NOW=NOW)
    env.pop("ROUTING_FIXTURE_DIR", None)
    if fixture_dir is not None:
        env["ROUTING_FIXTURE_DIR"] = str(fixture_dir)
    proc = subprocess.run([sys.executable, str(RESOLVE), *args],
                          capture_output=True, text=True, env=env)
    pairs = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, raw = line.split("=", 1)
            pairs[key] = "".join(shlex.split(raw)) if raw else ""
    return proc.returncode, pairs, proc.stderr


class ShippedDefaults(unittest.TestCase):
    """Both providers ship codexbar: null, so no row is ever capacity-checked."""

    def test_every_tier_resolves_with_capacity_unread(self):
        for tier, model, effort in [
            ("O", A_LARGE, "high"), ("A", A_SMALL, "medium"), ("B", A_MID, "high"),
            ("C", A_MID, "high"), ("D", A_LARGE, "high"), ("E", A_LARGE, "xhigh"),
            ("F", A_LARGE, "high"), ("V", A_LARGE, "medium"),
        ]:
            with self.subTest(tier=tier):
                rc, r, err = run("--tier", tier)
                self.assertEqual(rc, 0, err)
                self.assertEqual((r["ROUTE_MODEL"], r["ROUTE_EFFORT"]), (model, effort))
                self.assertIn("capacity unread", r["ROUTE_REASON"])

    def test_unconfigured_provider_reads_as_unread_not_as_failure(self):
        rc, r, err = run("--tier", "E")
        self.assertEqual(rc, 0, err)
        self.assertIn("no CodexBar provider", r["ROUTE_REASON"])

    def test_tier_letters_are_case_sensitive(self):
        rc, _, err = run("--tier", "e")
        self.assertEqual(rc, 2)
        self.assertIn("unknown tier", err.lower())

    def test_reason_reaches_the_route_line(self):
        rc, r, _ = run("--tier", "E", "--reason", "prior pass found no cause")
        self.assertEqual(rc, 0)
        self.assertIn("prior pass found no cause", r["ROUTE_LINE"])

    def test_list_tiers_names_every_row(self):
        proc = subprocess.run([sys.executable, str(RESOLVE), "--list-tiers"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for tier in "OABCDEFVR":
            self.assertIn(tier, proc.stdout)


class CapacityBehaviour(unittest.TestCase):
    """The shipped metadata sets codexbar: null, so no row is ever checked.

    These build a package whose providers DO name a meter, which is what a
    reader gets the moment they wire one in. Same resolver, same table.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.skill = root / "SKILL.md"
        self.skill.write_text((HERE.parent / "SKILL.md").read_text())
        (root / "references").mkdir()
        meta = (HERE.parent / "references/routing-metadata.yaml").read_text()
        meta = meta.replace("    codexbar: null\n    subscription: \"(your plan)\"",
                            "    codexbar: PROVIDER\n    subscription: \"(your plan)\"")
        # name each provider's meter entry after the provider itself
        meta = meta.replace("  provider_a:\n    agent: claude\n    codexbar: PROVIDER",
                            "  provider_a:\n    agent: claude\n    codexbar: provider_a")
        meta = meta.replace("  provider_b:\n    agent: codex\n    codexbar: PROVIDER",
                            "  provider_b:\n    agent: codex\n    codexbar: provider_b")
        (root / "references/routing-metadata.yaml").write_text(meta)
        self.assertNotIn("codexbar: PROVIDER", meta, "metadata rewrite missed a provider")

    def test_healthy_meter_holds_the_default(self):
        rc, r, err = run("--skill", str(self.skill), "--tier", "E", fixture_dir=FIXTURES)
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], A_LARGE)
        self.assertNotIn("unread", r["ROUTE_REASON"])

    def test_exhausted_default_takes_the_cross_provider_backup(self):
        rc, r, err = run("--skill", str(self.skill), "--tier", "E",
                         fixture_dir=FIXTURES / "scarce")
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], B_LARGE)
        self.assertIn("override", r["ROUTE_REASON"])
        self.assertIn("provider_a weekly 97% used", r["ROUTE_REASON"])

    def test_both_exhausted_exits_3_before_any_workspace(self):
        rc, r, err = run("--skill", str(self.skill), "--tier", "E",
                         fixture_dir=FIXTURES / "exhausted")
        self.assertEqual(rc, 3)
        self.assertIn("first A-Large", err)
        self.assertIn("backup B-Large", err)

    def test_missing_meter_data_dispatches_as_written(self):
        rc, r, err = run("--skill", str(self.skill), "--tier", "A", fixture_dir=HERE)
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], A_SMALL)
        self.assertIn("unread", r["ROUTE_REASON"])


class ExplicitModel(unittest.TestCase):
    def test_explicit_model_and_effort_bypass_the_table(self):
        rc, r, err = run("--model", A_LARGE, "--effort", "medium",
                         "--reason", "inherited from predecessor")
        self.assertEqual(rc, 0, err)
        self.assertEqual((r["ROUTE_MODEL"], r["ROUTE_EFFORT"]), (A_LARGE, "medium"))
        self.assertIn("inherited from predecessor", r["ROUTE_REASON"])

    def test_explicit_model_without_effort_says_so(self):
        rc, r, err = run("--model", A_LARGE)
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_EFFORT"], "unset")


class ReviewTier(unittest.TestCase):
    def test_review_inherits_the_tier_and_excludes_the_builder(self):
        rc, r, err = run("--tier", "R", "--of", "E", "--builder", "provider_a")
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], B_LARGE)

    def test_review_of_the_other_provider_comes_back(self):
        rc, r, err = run("--tier", "R", "--of", "E", "--builder", "provider_b")
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], A_LARGE)

    def test_review_without_of_is_refused(self):
        rc, _, err = run("--tier", "R")
        self.assertNotEqual(rc, 0)


class BadInput(unittest.TestCase):
    def test_unknown_tier_is_refused(self):
        rc, _, err = run("--tier", "Z")
        self.assertEqual(rc, 2)
        self.assertIn("unknown tier", err.lower())

    def test_bare_call_is_refused(self):
        rc, _, err = run()
        self.assertNotEqual(rc, 0)


class VisibleTable(unittest.TestCase):
    """The table in SKILL.md is the source of truth, and it is validated."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.skill = Path(self.temp.name) / "SKILL.md"
        self.skill.write_text((HERE.parent / "SKILL.md").read_text())
        (self.skill.parent / "references").mkdir()
        shutil.copy(HERE.parent / "references/routing-metadata.yaml",
                    self.skill.parent / "references/routing-metadata.yaml")

    def change(self, before, after):
        text = self.skill.read_text()
        self.assertIn(before, text)
        self.skill.write_text(text.replace(before, after))

    def test_editing_the_table_changes_the_dispatch(self):
        self.change("| A | Mechanical | A-Small | medium |", "| A | Mechanical | A-Large | high |")
        rc, r, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 0, err)
        self.assertEqual((r["ROUTE_MODEL"], r["ROUTE_EFFORT"]), (A_LARGE, "high"))

    def test_trailing_whitespace_is_tolerated(self):
        row = "| A | Mechanical | A-Small | medium | B-Mid | medium |"
        self.change(row, row + "  ")
        rc, r, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 0, err)
        self.assertEqual(r["ROUTE_MODEL"], A_SMALL)

    def test_same_provider_backup_is_rejected(self):
        self.change("| A | Mechanical | A-Small | medium | B-Mid | medium |",
                    "| A | Mechanical | A-Small | medium | A-Large | medium |")
        rc, _, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 2)
        self.assertIn("another provider", err)

    def test_missing_tier_fails_before_dispatch(self):
        self.change("| A | Mechanical | A-Small | medium | B-Mid | medium |", "")
        rc, _, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 2)
        self.assertIn("missing tiers: A", err)

    def test_invalid_effort_fails_before_dispatch(self):
        self.change("| A-Small | medium | B-Mid |", "| A-Small | ultra | B-Mid |")
        rc, _, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 2)
        self.assertIn("invalid effort", err)

    def test_duplicate_row_is_rejected(self):
        row = "| A | Mechanical | A-Small | medium | B-Mid | medium |"
        self.change(row, row + "\n" + row)
        rc, _, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 2)
        self.assertIn("duplicate or unknown tier", err)

    def test_unknown_model_name_is_rejected(self):
        self.change("| A | Mechanical | A-Small | medium |", "| A | Mechanical | Nonesuch | medium |")
        rc, _, err = run("--skill", str(self.skill), "--tier", "A")
        self.assertEqual(rc, 2)
        self.assertIn("unknown model", err)

    def test_check_warns_when_a_row_name_drifts_from_the_metadata(self):
        self.change("| A | Mechanical |", "| A | Renamed |")
        result = subprocess.run(
            [sys.executable, str(CHECK), "--skill", str(self.skill),
             "--no-live", "--no-log", "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "warn")
        self.assertTrue(any(row["check"] == "tier name" and "Renamed" in row["detail"]
                            for row in report["rows"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
