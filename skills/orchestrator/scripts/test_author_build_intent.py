#!/usr/bin/env python3
"""Fixture tests for author_build_intent.py.

Run: python3 skills/orchestrator/scripts/test_author_build_intent.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "author_build_intent.py"
FIXTURES = HERE / "fixtures" / "author-build"

CASES = (
    ("project-get-building.json", "dispatch_writer", True, "get-building"),
    (
        "project-stop-spawning-build.json",
        "dispatch_writer",
        True,
        "stop-spawning-orchestrator",
    ),
    ("project-build-out-active-writer.json", "continue_writer", True, "build-out"),
    ("project-keep-seat.json", "keep_seat", True, "keep-this-seat"),
    (
        "project-want-handoff-orchestrator.json",
        "succession_ok",
        False,
        "want-handoff-orchestrator",
    ),
    ("unrelated-status.json", "unclear", False, "none"),
    ("build-output.json", "unclear", False, "none"),
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def run_json(*args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    proc = run(*args, "--json")
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc, payload


class AuthorBuildIntentTests(unittest.TestCase):
    def test_fixtures(self):
        for name, action, refuse, matched in CASES:
            with self.subTest(name=name):
                proc, payload = run_json("classify", str(FIXTURES / name))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(
                    payload,
                    {
                        "action": action,
                        "refuse_orchestrator_spawn": refuse,
                        "matched": matched,
                    },
                )

    def test_text_matches_get_building_fixture(self):
        body = json.loads((FIXTURES / "project-get-building.json").read_text(encoding="utf-8"))
        proc, payload = run_json("classify", "--text", body["author_line"].upper())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["action"], "dispatch_writer")
        self.assertTrue(payload["refuse_orchestrator_spawn"])
        self.assertEqual(payload["matched"], "get-building")

    def test_text_without_active_writer_dispatches(self):
        body = json.loads(
            (FIXTURES / "project-build-out-active-writer.json").read_text(encoding="utf-8")
        )
        proc, payload = run_json("classify", "--text", body["author_line"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["action"], "dispatch_writer")
        self.assertTrue(payload["refuse_orchestrator_spawn"])

    def test_build_out_requires_word_boundaries(self):
        for line in ("build output", "please build output now", "rebuild out"):
            with self.subTest(line=line):
                proc, payload = run_json("classify", "--text", line)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(
                    payload,
                    {"action": "unclear", "refuse_orchestrator_spawn": False, "matched": "none"},
                )
        for line in ("ok, i have steered the worker - can you build out", "BUILD OUT!"):
            with self.subTest(line=line):
                proc, payload = run_json("classify", "--text", line)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(
                    payload,
                    {"action": "dispatch_writer", "refuse_orchestrator_spawn": True, "matched": "build-out"},
                )

    def test_context_percent_does_not_override_build_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(
                json.dumps(
                    {
                        "author_line": "get building",
                        "active_writer": False,
                        "context_percent": 30,
                    }
                ),
                encoding="utf-8",
            )
            proc, payload = run_json("classify", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["action"], "dispatch_writer")
        self.assertTrue(payload["refuse_orchestrator_spawn"])

    def test_plain_handoff_phrase_allows_succession(self):
        proc, payload = run_json(
            "classify",
            "--text",
            "handoff to a new orchestrator",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["action"], "succession_ok")
        self.assertFalse(payload["refuse_orchestrator_spawn"])
        self.assertEqual(payload["matched"], "handoff-to-new-orchestrator")

    def test_actually_being_built_needs_a_build_follow_up(self):
        alone, alone_payload = run_json("classify", "--text", "actually being built")
        self.assertEqual(alone.returncode, 0, alone.stderr)
        self.assertEqual(alone_payload["action"], "unclear")
        self.assertFalse(alone_payload["refuse_orchestrator_spawn"])
        follow, follow_payload = run_json(
            "classify",
            "--text",
            "actually being built, so build the draft",
        )
        self.assertEqual(follow.returncode, 0, follow.stderr)
        self.assertEqual(follow_payload["action"], "dispatch_writer")
        self.assertTrue(follow_payload["refuse_orchestrator_spawn"])
        self.assertEqual(follow_payload["matched"], "actually-being-built")
        earlier, earlier_payload = run_json(
            "classify",
            "--text",
            "build a question: actually being built?",
        )
        self.assertEqual(earlier.returncode, 0, earlier.stderr)
        self.assertEqual(earlier_payload["action"], "unclear")
        self.assertFalse(earlier_payload["refuse_orchestrator_spawn"])

    def test_build_language_beats_keep_seat_and_succession(self):
        proc, payload = run_json(
            "classify",
            "--text",
            "get building, keep this seat, want handoff to a new orchestrator",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["action"], "dispatch_writer")
        self.assertEqual(payload["matched"], "get-building")
        self.assertTrue(payload["refuse_orchestrator_spawn"])

    def test_help_lists_phrases(self):
        proc = run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        help_text = proc.stdout.casefold()
        self.assertIn("word boundaries", help_text)
        for phrase in (
            "get building",
            "build out",
            "stop spawning additional orchestrator",
            "immediately build",
            "actually being built",
            "keep this seat",
            "handoff to a new orchestrator",
            "want handoff to a new orchestrator",
            "--dry-run",
            "--json",
        ):
            self.assertIn(phrase, help_text)

    def test_dry_run_is_rejected(self):
        proc = run("classify", "--text", "get building", "--dry-run")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("classify", proc.stderr.casefold())
        self.assertEqual(proc.stdout, "")

    def test_both_inputs_exit_2(self):
        proc = run(
            "classify",
            "--text",
            "get building",
            str(FIXTURES / "project-get-building.json"),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not both", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_missing_input_exit_2(self):
        proc = run("classify", "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Nothing to classify", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_bad_json_and_shape_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bad = folder / "bad.json"
            bad.write_text("{", encoding="utf-8")
            missing_line = folder / "missing.json"
            missing_line.write_text("{}", encoding="utf-8")
            unknown = folder / "unknown.json"
            unknown.write_text(
                json.dumps({"author_line": "get building", "quote": "no"}),
                encoding="utf-8",
            )
            bad_flag = folder / "flag.json"
            bad_flag.write_text(
                json.dumps({"author_line": "get building", "active_writer": "yes"}),
                encoding="utf-8",
            )
            bad_percent = folder / "percent.json"
            bad_percent.write_text(
                json.dumps({"author_line": "get building", "context_percent": "30"}),
                encoding="utf-8",
            )
            absent = folder / "absent.json"
            for path, fragment in (
                (bad, "not valid JSON"),
                (missing_line, "author_line"),
                (unknown, "unknown field"),
                (bad_flag, "active_writer"),
                (bad_percent, "context_percent"),
                (absent, "is not a file"),
            ):
                with self.subTest(path=path.name):
                    proc = run("classify", str(path), "--json")
                    self.assertEqual(proc.returncode, 2, proc.stderr)
                    self.assertIn(fragment, proc.stderr)
                    self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
