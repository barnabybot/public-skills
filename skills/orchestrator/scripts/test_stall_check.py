#!/usr/bin/env python3
"""Fixture tests for stall_check.py.

Run: python3 cross-cutting/orchestrator/scripts/test_stall_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import stall_check

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "stall_check.py"
STALL = HERE / "fixtures" / "stall"
FALSE_POSITIVES = (
    "2026-10-04-note-write.json",
    "2026-10-04-warmup-silence.json",
    "2026-10-04-compaction.json",
    "2026-10-05-read-relay.json",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def load_raw(name: str) -> dict:
    return json.loads((STALL / name).read_text(encoding="utf-8"))


def judged(raw: dict, **kwargs: int) -> dict:
    warmup = kwargs.get("warmup_minutes", stall_check.DEFAULT_WARMUP_MINUTES)
    silence = kwargs.get("silence_minutes", stall_check.DEFAULT_SILENCE_MINUTES)
    return stall_check.evaluate(stall_check.normalise(raw, "seat"), warmup, silence)


def legacy_no_worktree_write(raw: dict, minutes: int = 5) -> bool:
    """The watcher these fixtures correct: stall when no worktree write falls in the window.

    It ignored session-note writes, reads, compaction, and the warm-up.
    """
    now = stall_check.parse_time(raw["now"], "now")
    span = timedelta(minutes=minutes)
    for event in raw["events"]:
        if event["kind"] != "worktree_write":
            continue
        at = stall_check.parse_time(event["at"], "at")
        if now - at <= span:
            return False
    return True


def without_kind(raw: dict, kind: str) -> dict:
    clone = json.loads(json.dumps(raw))
    clone["events"] = [event for event in clone["events"] if event["kind"] != kind]
    return clone


class StallCheckTests(unittest.TestCase):
    def test_help_names_subcommands_and_flags(self):
        proc = run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("judge", proc.stdout)
        self.assertIn("batch", proc.stdout)
        self.assertIn("--json", proc.stdout)
        self.assertIn("--warmup-minutes", proc.stdout)
        self.assertIn("--silence-minutes", proc.stdout)
        self.assertIn("warm-up", proc.stdout)
        self.assertIn("latest activity", proc.stdout)

    def test_false_positives_stay_active_where_the_old_watcher_stalled(self):
        for name in FALSE_POSITIVES:
            raw = load_raw(name)
            with self.subTest(name=name):
                self.assertTrue(legacy_no_worktree_write(raw), raw["record"])
                self.assertNotIn("worktree_write", {event["kind"] for event in raw["events"]})
                result = judged(raw)
                self.assertEqual(result["verdict"], "active", result["reason"])
                proc = run("judge", str(STALL / name), "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["verdict"], "active")

    def test_note_write_is_the_activity_the_old_watcher_missed(self):
        raw = load_raw("2026-10-04-note-write.json")
        self.assertEqual(judged(without_kind(raw, "session_note_write"))["verdict"], "stall")

    def test_silence_during_warm_up_is_the_activity_clock_the_old_watcher_missed(self):
        raw = load_raw("2026-10-04-warmup-silence.json")
        self.assertEqual(judged(raw, warmup_minutes=0)["verdict"], "stall")
        self.assertEqual(judged(raw)["silence_elapsed_seconds"], 0)

    def test_compaction_is_the_activity_the_old_watcher_missed(self):
        raw = load_raw("2026-10-04-compaction.json")
        self.assertEqual(judged(without_kind(raw, "compaction"))["verdict"], "stall")

    def test_read_is_the_activity_the_old_watcher_missed(self):
        raw = load_raw("2026-10-05-read-relay.json")
        missed = judged(without_kind(raw, "read"))
        self.assertEqual(missed["verdict"], "stall", missed["reason"])
        self.assertGreaterEqual(missed["silence_elapsed_seconds"], 21 * 60 - 12 * 60)

    def test_verified_stall_exits_1(self):
        raw = load_raw("verified-stall.json")
        self.assertTrue(legacy_no_worktree_write(raw))
        self.assertEqual(judged(raw)["verdict"], "stall")
        proc = run("judge", str(STALL / "verified-stall.json"), "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["verdict"], "stall")
        self.assertEqual(payload["input"], "idle")
        self.assertFalse(payload["tool_after_promise"])
        self.assertIn("authorised continuation", payload["reason"])

    def test_active_input_and_a_quiet_turn_without_a_promise_stay_active(self):
        raw = load_raw("verified-stall.json")
        active = json.loads(json.dumps(raw))
        active["input"] = "active"
        self.assertEqual(judged(active)["verdict"], "active")
        quiet = json.loads(json.dumps(raw))
        quiet["events"] = [event for event in quiet["events"] if event["kind"] != "promise"]
        self.assertEqual(judged(quiet)["verdict"], "active")

    def test_silence_window_boundary(self):
        raw = {
            "seat": "seat-boundary",
            "started_at": "2026-10-05T08:00:00Z",
            "now": "2026-10-05T08:20:59Z",
            "input": "idle",
            "events": [
                {"at": "2026-10-05T08:16:00Z", "kind": "promise"},
            ],
        }
        early = judged(raw)
        self.assertEqual(early["verdict"], "active", early["reason"])
        self.assertEqual(early["silence_elapsed_seconds"], 4 * 60 + 59)
        raw["now"] = "2026-10-05T08:21:00Z"
        stalled = judged(raw)
        self.assertEqual(stalled["silence_elapsed_seconds"], 5 * 60)
        self.assertEqual(stalled["verdict"], "stall")

    def test_worktree_write_and_tool_call_count_as_activity(self):
        raw = load_raw("verified-stall.json")
        for kind in ("worktree_write", "tool_call"):
            clone = json.loads(json.dumps(raw))
            clone["events"].append({"at": "2026-10-05T08:28:00Z", "kind": kind})
            result = judged(clone)
            self.assertEqual(result["verdict"], "active", result["reason"])
            self.assertIn(kind, result["reason"])
            self.assertLess(result["silence_elapsed_seconds"], 5 * 60)

    def test_promise_then_one_read_then_silence_stalls(self):
        name = "2026-10-11-read-then-hang.json"
        raw = load_raw(name)
        kinds = [event["kind"] for event in raw["events"]]
        self.assertEqual(kinds, ["promise", "read"])
        result = judged(raw)
        self.assertEqual(result["verdict"], "stall", result["reason"])
        self.assertTrue(result["tool_after_promise"])
        self.assertEqual(result["silence_clock_starts_at"], "2026-10-11T08:20:00Z")
        self.assertGreaterEqual(result["silence_elapsed_seconds"], 5 * 60)
        proc = run("judge", str(STALL / name), "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["verdict"], "stall")
        self.assertTrue(payload["tool_after_promise"])
        self.assertIn("authorised continuation", payload["reason"])

    def test_batch_reports_the_verified_stall(self):
        proc = run("batch", str(STALL), "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["verdict"], "stall")
        by_seat = {item["seat"]: item["verdict"] for item in payload["traces"]}
        self.assertEqual(by_seat["seat-verified-stall"], "stall")
        self.assertEqual(by_seat["seat-read-then-hang"], "stall")
        for seat in ("seat-note-write", "seat-warmup", "seat-compaction", "seat-read-relay"):
            self.assertEqual(by_seat[seat], "active")

    def test_batch_of_false_positives_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in FALSE_POSITIVES:
                (folder / name).write_text((STALL / name).read_text(encoding="utf-8"), encoding="utf-8")
            proc = run("batch", str(folder))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), len(FALSE_POSITIVES))
        self.assertTrue(all(line.startswith("active ") for line in lines))

    def test_bad_invocation_explains_the_next_argument(self):
        missing = run("judge", str(STALL / "missing.json"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Pass judge PATH", missing.stderr)
        self.assertGreaterEqual(len(missing.stderr.strip()), 20)

        broken = run("judge", str(STALL / "README.md"))
        self.assertEqual(broken.returncode, 2)
        self.assertIn("not JSON", broken.stderr)

        negative = run("judge", str(STALL / "verified-stall.json"), "--warmup-minutes", "-1")
        self.assertEqual(negative.returncode, 2)
        self.assertIn("warmup minutes", negative.stderr)
        self.assertIn("--warmup-minutes", negative.stderr)

        empty = run("batch", str(HERE))
        self.assertEqual(empty.returncode, 2)
        self.assertIn("no JSON traces", empty.stderr)

    def test_unknown_kind_names_the_allowed_kinds(self):
        raw = load_raw("verified-stall.json")
        raw["events"].append({"at": "2026-10-05T08:12:00Z", "kind": "sleep"})
        with self.assertRaises(stall_check.TraceError) as caught:
            stall_check.normalise(raw, "seat")
        self.assertIn("session_note_write", str(caught.exception))
        self.assertIn("compaction", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
