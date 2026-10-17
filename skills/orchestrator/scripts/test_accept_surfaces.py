#!/usr/bin/env python3
"""Tests for accept_surfaces.py.

Run: python3 cross-cutting/orchestrator/scripts/test_accept_surfaces.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "accept_surfaces.py"
FIXTURES = HERE / "fixtures" / "accept"
R98 = FIXTURES / "r98-grid-miss.json"
EVERY = FIXTURES / "every-surface.json"
CHART_NA = FIXTURES / "chart-na.json"


def run(args: list[str], stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def write_record(directory: Path, body: object) -> Path:
    path = directory / "record.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


class AcceptSurfacesTests(unittest.TestCase):
    def test_r98_grid_miss_names_grid(self) -> None:
        fixture = json.loads(R98.read_text(encoding="utf-8"))
        self.assertEqual(fixture["surfaces"]["headline"]["state"], "checked")
        self.assertNotIn("grid", fixture["surfaces"])
        proc = run(["check", "--record", str(R98)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing surface: grid", proc.stderr)
        self.assertNotIn("list", proc.stderr)
        self.assertNotIn("chart", proc.stderr)
        self.assertNotIn("report", proc.stderr)
        self.assertIn("fail  grid: no recorded check and no N/A reason", proc.stdout)
        self.assertIn("ok    list: checked", proc.stdout)

    def test_r98_json_names_only_grid(self) -> None:
        proc = run(["check", "--json", "--record", str(R98)])
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["missing"], ["grid"])
        self.assertFalse(payload["ok"])
        self.assertIn("missing surface: grid", proc.stderr)

    def test_every_surface_passes(self) -> None:
        proc = run(["check", "--record", str(EVERY)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        for name in ("grid", "list", "chart", "report"):
            self.assertIn(f"ok    {name}: checked", proc.stdout)

    def test_explicit_na_reason_passes(self) -> None:
        proc = run(["check", "--record", str(CHART_NA), "--json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["missing"], [])
        self.assertTrue(payload["ok"])
        chart = next(row for row in payload["surfaces"] if row["surface"] == "chart")
        self.assertEqual(chart["detail"], "na")

    def test_headline_alone_names_every_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_record(
                Path(tmp),
                {"surfaces": {"headline": {"state": "checked", "note": "Title matches the brief."}}},
            )
            proc = run(["check", "--record", str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing surfaces: grid, list, chart, report", proc.stderr)

    def test_empty_note_and_empty_reason_name_the_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_record(
                Path(tmp),
                {
                    "surfaces": {
                        "grid": {"state": "checked", "note": "   "},
                        "list": {"state": "checked", "note": "Rows match the source."},
                        "chart": {"state": "na", "reason": ""},
                        "report": {"state": "checked", "note": "Totals match the grid."},
                    }
                },
            )
            proc = run(["check", "--json", "--record", str(path)])
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["missing"], ["grid", "chart"])
        self.assertIn("missing surfaces: grid, chart", proc.stderr)

    def test_unknown_state_names_the_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_record(
                Path(tmp),
                {
                    "surfaces": {
                        "grid": {"state": "seen"},
                        "list": {"state": "checked", "note": "Rows match the source."},
                        "chart": {"state": "na", "reason": "This page has no chart."},
                        "report": {"state": "checked", "note": "Totals match the grid."},
                    }
                },
            )
            proc = run(["check", "--record", str(path)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing surface: grid", proc.stderr)
        self.assertIn("state 'seen' must be checked or na", proc.stdout)

    def test_stdin_record(self) -> None:
        proc = run(["check", "--record", "-"], stdin=EVERY.read_text(encoding="utf-8"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_file_exits_2(self) -> None:
        proc = run(["check", "--record", "no-such-surface-record.json"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Pass --record", proc.stderr)
        self.assertGreaterEqual(len(proc.stderr.strip()), 20)

    def test_bad_json_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text("{", encoding="utf-8")
            proc = run(["check", "--record", str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not JSON", proc.stderr)

    def test_surfaces_must_be_an_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_record(Path(tmp), {"surfaces": ["grid"]})
            proc = run(["check", "--record", str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("surfaces must be a JSON object", proc.stderr)

    def test_template_lists_four_surfaces_and_fails_check(self) -> None:
        proc = run(["template", "--json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(list(payload["surfaces"]), ["grid", "list", "chart", "report"])
        for row in payload["surfaces"].values():
            self.assertIsNone(row["state"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.json"
            path.write_text(proc.stdout, encoding="utf-8")
            checked = run(["check", "--record", str(path)])
        self.assertEqual(checked.returncode, 1)
        self.assertIn("missing surfaces: grid, list, chart, report", checked.stderr)
        self.assertIn("no recorded check", checked.stdout)
        self.assertNotIn("checked with an empty note", checked.stdout)
        self.assertNotIn("na with an empty reason", checked.stdout)

    def test_status_commands_share_the_skill_directory(self) -> None:
        text = (HERE.parents[0] / "workflows" / "status.md").read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:12])
        self.assertIn("cross-cutting/orchestrator/", head)
        self.assertNotIn("python3 cross-cutting/orchestrator/scripts/", text)
        for line in text.splitlines():
            if "python3 " in line and ".py" in line:
                self.assertTrue(
                    "python3 scripts/" in line or "python3 ../cmux/scripts/" in line,
                    line,
                )

    def test_help_names_subcommands_and_json(self) -> None:
        proc = run(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("grid, list, chart and report", proc.stdout)
        self.assertIn("check", proc.stdout)
        self.assertIn("template", proc.stdout)
        self.assertIn("--json", proc.stdout)
        self.assertIn("--record", run(["check", "--help"]).stdout)

    def test_missing_command_exits_2(self) -> None:
        proc = run([])
        self.assertEqual(proc.returncode, 2)
        self.assertGreaterEqual(len(proc.stderr.strip()), 20)


if __name__ == "__main__":
    unittest.main()
