#!/usr/bin/env python3
"""Fixture tests for continuation_check.py.

Run: python3 cross-cutting/orchestrator/scripts/test_continuation_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "continuation_check.py"
CASES = HERE / "fixtures" / "continuation"

READY = {
    "handoff": False,
    "next": [
        {"item": "media-evidence", "owner": "Media evidence", "action": "collect"},
    ],
    "spent": [],
    "held": [
        {"item": "source-integration", "owner": "Selector source", "gate": "direct-release"},
        {"item": "publication", "owner": "Site release", "gate": "push-approval"},
    ],
    "in_flight": [],
}
DEPENDENT = {
    "handoff": False,
    "next": [
        {"item": "media-trial", "owner": "Media trial", "action": "dispatch"},
    ],
    "spent": [],
    "held": [
        {"item": "publication", "owner": "Site release", "gate": "push-approval"},
    ],
    "in_flight": [],
}
ACCOUNT = {
    "handoff": False,
    "next": [
        {"item": "account-read", "owner": "Media evidence", "action": "collect"},
        {"item": "report-check", "owner": "Report check", "action": "dispatch"},
    ],
    "spent": [],
    "held": [
        {"item": "source-integration", "owner": "Selector source", "gate": "direct-release"},
    ],
    "in_flight": [],
}
ALL_GATED = {
    "handoff": False,
    "next": [],
    "spent": [],
    "held": [
        {"item": "source-integration", "owner": "Selector source", "gate": "direct-release"},
        {"item": "publication", "owner": "Site release", "gate": "push-approval"},
        {"item": "pilot-contact", "owner": "Pilot contact", "gate": "contact"},
        {"item": "pilot-scope", "owner": "Pilot scope", "gate": "author-decision"},
    ],
    "in_flight": [],
}
OWNERSHIP = {
    "handoff": False,
    "next": [
        {
            "item": "ownership-clarification",
            "owner": "Selector source, Media trial",
            "action": "clarify",
        },
    ],
    "spent": [],
    "held": [
        {"item": "ranking-write", "owner": "Media trial", "gate": "ownership"},
    ],
    "in_flight": [],
}
HANDOFF = {
    "handoff": True,
    "next": READY["next"],
    "spent": [],
    "held": READY["held"],
    "in_flight": [],
}
PUSH_MAIN = {
    "handoff": False,
    "next": [
        {"item": "local-pr", "owner": "coordinator", "action": "prepare-pr"},
        {"item": "local-test", "owner": "coordinator", "action": "test"},
    ],
    "spent": [
        {"id": "push-main", "used": 1, "authorised": 1, "remaining": 0},
    ],
    "held": [
        {"item": "create-pr", "owner": "coordinator", "gate": "pr-approval"},
        {"item": "merge", "owner": "coordinator", "gate": "merge-approval"},
        {"item": "alt-push", "owner": "coordinator", "gate": "push-approval"},
    ],
    "in_flight": [],
}
PUSH_OPEN = {
    "handoff": False,
    "next": [
        {"item": "worker-push", "owner": "coordinator", "action": "push"},
        {"item": "local-test", "owner": "coordinator", "action": "test"},
    ],
    "spent": [
        {"id": "push-worker", "used": 0, "authorised": 1, "remaining": 1},
    ],
    "held": [
        {"item": "create-pr", "owner": "coordinator", "gate": "pr-approval"},
        {"item": "merge", "owner": "coordinator", "gate": "merge-approval"},
    ],
    "in_flight": [],
}
PUSH_SPENT = {
    "handoff": False,
    "next": [
        {"item": "local-test", "owner": "coordinator", "action": "test"},
    ],
    "spent": [
        {"id": "push-worker", "used": 1, "authorised": 1, "remaining": 0},
    ],
    "held": [
        {"item": "worker-push", "owner": "coordinator", "gate": "push-approval"},
        {"item": "create-pr", "owner": "coordinator", "gate": "pr-approval"},
        {"item": "merge", "owner": "coordinator", "gate": "merge-approval"},
    ],
    "in_flight": [],
}


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


class ContinuationCheckTests(unittest.TestCase):
    def test_help_names_the_commands(self) -> None:
        proc = run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("judge", proc.stdout)
        self.assertIn("apply", proc.stdout)
        judge = run("judge", "--help")
        self.assertEqual(judge.returncode, 0, judge.stderr)
        self.assertIn("--json", judge.stdout)
        apply = run("apply", "--help")
        self.assertEqual(apply.returncode, 0, apply.stderr)
        self.assertIn("--json", apply.stdout)
        self.assertIn("--approval", apply.stdout)
        self.assertIn("--target", apply.stdout)
        self.assertIn("--result", apply.stdout)

    def test_ready_evidence_collects_and_holds_release(self) -> None:
        proc, payload = run_json("judge", str(CASES / "ready-evidence.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, READY)

    def test_dependent_trial_dispatches_and_holds_publication(self) -> None:
        proc, payload = run_json("judge", str(CASES / "dependent-trial.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, DEPENDENT)

    def test_blocked_report_does_not_stop_authorised_reads(self) -> None:
        proc, payload = run_json("judge", str(CASES / "account-and-report.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, ACCOUNT)

    def test_composer_and_keep_going_hold_every_gate(self) -> None:
        proc, payload = run_json("judge", str(CASES / "all-gated.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, ALL_GATED)
        self.assertNotIn("push go", json.dumps(payload))

    def test_conflict_clarifies_and_holds_the_write(self) -> None:
        proc, payload = run_json("judge", str(CASES / "ownership-conflict.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, OWNERSHIP)
        self.assertNotIn("write", [item["action"] for item in payload["next"]])

    def test_context_threshold_hands_off_with_the_evidence_action(self) -> None:
        proc, payload = run_json("judge", str(CASES / "handoff-threshold.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, HANDOFF)

    def test_spent_main_push_leaves_local_work_and_holds_other_targets(self) -> None:
        proc, payload = run_json("judge", str(CASES / "push-main-spent.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, PUSH_MAIN)

    def test_open_worker_push_stays_separate_from_pr_and_merge(self) -> None:
        proc, payload = run_json("judge", str(CASES / "push-worker-open.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, PUSH_OPEN)

    def test_spent_worker_push_holds_the_retry(self) -> None:
        proc, payload = run_json("judge", str(CASES / "push-worker-spent.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload, PUSH_SPENT)

    def test_rejected_push_matches_the_spent_fixture(self) -> None:
        path = CASES / "push-worker-open.json"
        before = path.read_bytes()
        proc, payload = run_json(
            "apply",
            str(path),
            "--approval",
            "push-worker",
            "--target",
            "worker-branch",
            "--result",
            "rejected",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(
            payload,
            {
                "applied": True,
                "reason": None,
                "approval": {
                    "id": "push-worker",
                    "used": 1,
                    "authorised": 1,
                    "remaining": 0,
                    "target": "worker-branch",
                },
                "decision": PUSH_SPENT,
            },
        )

    def test_accepted_push_spends_the_same_approval(self) -> None:
        proc, payload = run_json(
            "apply",
            str(CASES / "push-worker-open.json"),
            "--approval",
            "push-worker",
            "--target",
            "worker-branch",
            "--result",
            "accepted",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["approval"]["used"], 1)
        self.assertEqual(payload["decision"], PUSH_SPENT)

    def test_second_attempt_on_a_spent_approval_is_refused(self) -> None:
        path = CASES / "push-worker-spent.json"
        before = path.read_bytes()
        proc, payload = run_json(
            "apply",
            str(path),
            "--approval",
            "push-worker",
            "--target",
            "worker-branch",
            "--result",
            "rejected",
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["reason"], "spent")
        self.assertEqual(payload["approval"]["used"], 1)
        self.assertEqual(payload["decision"], PUSH_SPENT)

    def test_other_target_does_not_spend_the_approval(self) -> None:
        proc, payload = run_json(
            "apply",
            str(CASES / "push-worker-open.json"),
            "--approval",
            "push-worker",
            "--target",
            "other-branch",
            "--result",
            "accepted",
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["reason"], "target")
        self.assertEqual(payload["approval"]["used"], 0)
        self.assertEqual(payload["approval"]["remaining"], 1)
        self.assertEqual(payload["decision"], PUSH_OPEN)

    def test_missing_approval_leaves_the_decision(self) -> None:
        proc, payload = run_json(
            "apply",
            str(CASES / "push-worker-open.json"),
            "--approval",
            "missing-push",
            "--target",
            "worker-branch",
            "--result",
            "rejected",
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(payload["applied"], False)
        self.assertEqual(payload["reason"], "missing")
        self.assertIsNone(payload["approval"])
        self.assertEqual(payload["decision"], PUSH_OPEN)

    def test_threshold_boundary_and_in_flight_and_decision_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = json.loads((CASES / "ready-evidence.json").read_text(encoding="utf-8"))
            at_threshold = dict(ready, context_percent=30)
            (root / "at.json").write_text(json.dumps(at_threshold), encoding="utf-8")
            proc, payload = run_json("judge", str(root / "at.json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(payload["handoff"])
            self.assertEqual(payload["next"], READY["next"])

            widened = dict(at_threshold, recycle_percent=40)
            (root / "wide.json").write_text(json.dumps(widened), encoding="utf-8")
            proc, payload = run_json("judge", str(root / "wide.json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(payload["handoff"])
            self.assertEqual(payload["next"], READY["next"])

            flying = json.loads(json.dumps(ready))
            flying["items"][0]["in_flight"] = True
            (root / "fly.json").write_text(json.dumps(flying), encoding="utf-8")
            proc, payload = run_json("judge", str(root / "fly.json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(payload["next"], [])
            self.assertEqual(
                payload["in_flight"],
                [{"item": "media-evidence", "owner": "Media evidence"}],
            )
            self.assertEqual(payload["held"], READY["held"])

            scoped = {
                "context_percent": 10,
                "approvals": [
                    {
                        "id": "rule",
                        "kind": "decision",
                        "scope": ["media-rule"],
                        "authorised": 1,
                        "used": 0,
                    }
                ],
                "items": [
                    {
                        "id": "media-rule",
                        "owner": "author",
                        "action": "apply",
                        "gate": "author-decision",
                    },
                    {
                        "id": "source-integration",
                        "owner": "Selector source",
                        "action": "integrate",
                        "gate": "direct-release",
                    },
                ],
            }
            (root / "scope.json").write_text(json.dumps(scoped), encoding="utf-8")
            proc, payload = run_json("judge", str(root / "scope.json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                payload["next"],
                [{"item": "media-rule", "owner": "author", "action": "apply"}],
            )
            self.assertEqual(
                payload["held"],
                [
                    {
                        "item": "source-integration",
                        "owner": "Selector source",
                        "gate": "direct-release",
                    }
                ],
            )

            wide_decision = {
                "context_percent": 10,
                "approvals": [
                    {"id": "wide", "kind": "decision", "authorised": 1, "used": 0}
                ],
                "items": [
                    {
                        "id": "pilot-scope",
                        "owner": "Pilot scope",
                        "action": "select",
                        "gate": "author-decision",
                    }
                ],
            }
            (root / "unscope.json").write_text(json.dumps(wide_decision), encoding="utf-8")
            proc, payload = run_json("judge", str(root / "unscope.json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(payload["next"], [])
            self.assertEqual(
                payload["held"],
                [
                    {
                        "item": "pilot-scope",
                        "owner": "Pilot scope",
                        "gate": "author-decision",
                    }
                ],
            )

    def test_bad_case_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{", encoding="utf-8")
            proc = run("judge", str(path), "--json")
            self.assertEqual(proc.returncode, 2)
            missing = run("judge", str(Path(tmp) / "absent.json"), "--json")
            self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
