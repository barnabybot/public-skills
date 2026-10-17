#!/usr/bin/env python3
"""CLI tests for live_push_gate.py. Run: python3 cross-cutting/orchestrator/scripts/test_live_push_gate.py"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "live_push_gate.py"
FIXTURES = HERE / "fixtures" / "live-push"

# filename, exit code, status, fragments that must appear in reasons
CASES = (
    ("allow-inject.md", 0, "allow", ()),
    ("allow-update.md", 0, "allow", ()),
    ("allow-replace-direct.md", 0, "allow", ()),
    ("allow-remove-direct.md", 0, "allow", ()),
    ("allow-loopback-update.md", 0, "allow", ()),
    ("allow-file-inject.md", 0, "allow", ()),
    ("allow-corrected.md", 0, "allow", ()),
    ("allow-in-place.md", 0, "allow", ()),
    ("refuse-missing-preview.md", 1, "refuse", ("Preview",)),
    ("refuse-public-preview.md", 1, "refuse", ("local path",)),
    ("refuse-na-preview.md", 1, "refuse", ("local path",)),
    ("refuse-domain-slash.md", 1, "refuse", ("local path",)),
    ("refuse-loopback-no-path.md", 1, "refuse", ("local path",)),
    ("refuse-missing-change.md", 1, "refuse", ("Change",)),
    ("refuse-bad-change.md", 1, "refuse", ("inject, update, replace, and remove",)),
    ("refuse-replace-relay.md", 1, "refuse", ("Provenance is relay", "direct")),
    ("refuse-replace-build.md", 1, "refuse", ("Provenance is build", "direct")),
    ("refuse-replace-no-go.md", 1, "refuse", ("Go:",)),
    ("refuse-remove-no-provenance.md", 1, "refuse", ("Provenance: direct",)),
)


REPO = HERE.parents[2]


def setUpModule() -> None:
    """Materialise the relative preview paths the allow fixtures name."""
    folder = REPO / "output" / "slice"
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "page.html", "old-section.html"):
        target = folder / name
        target.write_text("<!doctype html><title>slice</title>\n", encoding="utf-8")


def run_gate(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO,
    )


class LivePushGateTests(unittest.TestCase):
    def test_fixtures(self):
        for name, code, status, fragments in CASES:
            with self.subTest(name=name):
                proc = run_gate("--json", "--note", str(FIXTURES / name))
                self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
                self.assertEqual(proc.stderr, "")
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], status)
                joined = " ".join(payload["reasons"])
                for fragment in fragments:
                    self.assertIn(fragment, joined)
                if status == "allow":
                    self.assertEqual(payload["reasons"], [])

    def test_corrected_note_keeps_the_later_inject(self):
        proc = run_gate("--json", "--note", str(FIXTURES / "allow-corrected.md"))
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload["change"], "inject")
        self.assertEqual(payload["preview"], "output/slice/index.html")

    def test_update_with_relay_still_allows(self):
        proc = run_gate("--json", "--note", str(FIXTURES / "allow-update.md"))
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload["change"], "update")
        self.assertEqual(payload["provenance"], "relay")

    def test_replace_direct_keeps_the_go_quote(self):
        proc = run_gate("--json", "--note", str(FIXTURES / "allow-replace-direct.md"))
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload["change"], "replace")
        self.assertEqual(payload["provenance"], "direct")
        self.assertIn("replace the live section", payload["go"])

    def test_missing_note_exits_2(self):
        missing = FIXTURES / "no-such-note.md"
        proc = run_gate("--note", str(missing))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Pass --note", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_omitted_note_exits_2(self):
        proc = run_gate()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--note", proc.stderr)

    def test_help_names_the_gate(self):
        proc = run_gate("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Thin-Slice", proc.stdout)
        self.assertIn("--json", proc.stdout)

    def test_human_refuse_lists_the_reason(self):
        proc = run_gate("--note", str(FIXTURES / "refuse-replace-relay.md"))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stdout.startswith("refuse\n"))
        self.assertIn("Provenance is relay", proc.stdout)

    def test_localhost_preview_allows_an_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text(
                "Preview: http://localhost:8765/index.html\nChange: update\n",
                encoding="utf-8",
            )
            proc = run_gate("--json", "--note", str(note))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "allow")

    def test_existing_relative_path_allows_inject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "slice" / "index.html"
            page.parent.mkdir()
            page.write_text("<!doctype html><title>slice</title>\n", encoding="utf-8")
            note = root / "note.md"
            note.write_text("Preview: slice/index.html\nChange: inject\n", encoding="utf-8")
            proc = run_gate("--json", "--note", str(note), cwd=root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "allow")

    def test_loopback_origin_without_a_path_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("Preview: https://localhost/\nChange: update\n", encoding="utf-8")
            proc = run_gate("--json", "--note", str(note))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "refuse")
        self.assertIn("local path", " ".join(json.loads(proc.stdout)["reasons"]))


if __name__ == "__main__":
    unittest.main()
