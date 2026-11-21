#!/usr/bin/env python3
"""Unit tests for brun-hygiene ci_audit.py."""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_audit


class CiAuditTests(unittest.TestCase):
    def test_split_job_buckets_separates_wait_setup_and_run(self) -> None:
        job = {
            "name": "validate-fast",
            "created_at": "2026-11-21T10:00:00Z",
            "started_at": "2026-11-21T10:00:03Z",
            "completed_at": "2026-11-21T10:00:38Z",
            "steps": [
                {
                    "name": "Set up job",
                    "started_at": "2026-11-21T10:00:03Z",
                    "completed_at": "2026-11-21T10:00:06Z",
                },
                {
                    "name": "Checkout",
                    "started_at": "2026-11-21T10:00:06Z",
                    "completed_at": "2026-11-21T10:00:12Z",
                },
                {
                    "name": "Run validators",
                    "started_at": "2026-11-21T10:00:12Z",
                    "completed_at": "2026-11-21T10:00:36Z",
                },
                {
                    "name": "Post Checkout",
                    "started_at": "2026-11-21T10:00:36Z",
                    "completed_at": "2026-11-21T10:00:38Z",
                },
            ],
        }
        buckets = ci_audit.split_job_buckets(job)
        self.assertEqual(buckets["wait_s"], 3.0)
        self.assertEqual(buckets["setup_s"], 9.0)
        self.assertEqual(buckets["run_s"], 24.0)
        self.assertEqual(buckets["total_s"], 35.0)
        self.assertEqual(buckets["billable_min"], 1.0)

    def test_summarise_runs_counts_overlaps_and_percentiles(self) -> None:
        runs = [
            {
                "id": 1,
                "event": "pull_request",
                "head_branch": "feat/a",
                "created_at": "2026-11-01T10:00:00Z",
                "updated_at": "2026-11-01T10:02:00Z",
            },
            {
                "id": 2,
                "event": "pull_request",
                "head_branch": "feat/a",
                "created_at": "2026-11-01T10:01:00Z",
                "updated_at": "2026-11-01T10:03:00Z",
            },
            {
                "id": 3,
                "event": "push",
                "head_branch": "main",
                "created_at": "2026-11-11T10:00:00Z",
                "updated_at": "2026-11-11T10:01:00Z",
            },
        ]
        jobs = {
            1: [{"name": "build", "created_at": "2026-11-01T10:00:00Z", "started_at": "2026-11-01T10:00:02Z", "completed_at": "2026-11-01T10:01:05Z", "steps": []}],
            2: [{"name": "build", "created_at": "2026-11-01T10:01:00Z", "started_at": "2026-11-01T10:01:02Z", "completed_at": "2026-11-01T10:02:05Z", "steps": []}],
            3: [{"name": "build", "created_at": "2026-11-11T10:00:00Z", "started_at": "2026-11-11T10:00:02Z", "completed_at": "2026-11-11T10:00:50Z", "steps": []}],
        }
        summary = ci_audit.summarise_runs(runs, jobs)
        self.assertEqual(summary["run_count"], 3)
        self.assertEqual(summary["pr_run_count"], 2)
        self.assertEqual(summary["pr_overlap_count"], 1)
        self.assertEqual(summary["wall_p50_s"], 120.0)
        self.assertEqual(summary["jobs"][0]["name"], "build")
        self.assertEqual(summary["jobs"][0]["n"], 3)

    def test_dry_run_json_requires_no_network(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ci_audit.main(["--repo", "example/repo", "--limit", "50", "--dry-run", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["repo"], "example/repo")
        self.assertEqual(payload["limit"], 50)


if __name__ == "__main__":
    unittest.main()
