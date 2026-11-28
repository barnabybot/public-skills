#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import preflight
import provider_health as ph
import routing_catalog as rc


class ModelRoutingTests(unittest.TestCase):
    def test_catalog_loads_and_matches_skill_table(self):
        catalog = rc.load_catalog(require_skill_table=True)
        self.assertIn("coding", catalog["categories"])
        self.assertIn("review", catalog["categories"])
        self.assertEqual(catalog["categories"]["coding"]["first"]["model"], "a_mid")

    def test_check_cli_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check.py"), "--no-live", "--no-log"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_preflight_shapes_t3_cmux_and_cli_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            caps = Path(tmp) / "caps.json"
            caps.write_text(
                json.dumps(
                    {
                        "providers": [
                            {"providerInstanceId": "provider_a", "models": ["claude-sonnet-5-5", "claude-opus-5-5"]},
                            {"providerInstanceId": "provider_b", "models": ["configure-provider-b-mid"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            t3 = preflight.run_preflight(
                category="coding", host="t3", capabilities_path=caps, health_path=health
            )
            self.assertTrue(t3["ok"])
            self.assertEqual(t3["isolation"], "worktree")
            self.assertEqual(t3["targets"][0]["delegate_target"]["providerInstanceId"], "provider_a")
            self.assertEqual(t3["targets"][0]["delegate_target"]["model"], "claude-sonnet-5-5")
            self.assertEqual(t3["targets"][0]["delegate_target"]["options"], {"effort": "high"})

            linked = preflight.run_preflight(
                category="coding",
                host="t3",
                capabilities_path=caps,
                environment_id="env-remote-1",
                health_path=health,
            )
            self.assertEqual(linked["isolation"], "shared")
            self.assertEqual(linked["targets"][0]["delegate_target"]["environmentId"], "env-remote-1")

            cmux = preflight.run_preflight(category="coding", host="cmux", health_path=health)
            self.assertEqual(cmux["targets"][0]["agent"], "claude")
            self.assertIn("--model", cmux["targets"][0]["cli_flags"])

            cli = preflight.run_preflight(category="coding", host="cli", health_path=health)
            self.assertEqual(cli["targets"][0]["target"], {"provider": "provider_a", "model": "claude-sonnet-5-5", "effort": "high"})

    def test_review_excludes_builder_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            res = preflight.run_preflight(
                category="review", of_category="coding", builder="provider_a", host="t3", no_live=True, health_path=health
            )
            self.assertTrue(res["ok"])
            self.assertEqual([t["provider"] for t in res["targets"]], ["provider_b"])
            self.assertTrue(any(s["reason"] == "excluded_builder_provider" for s in res["skipped"]))

    def test_circuit_breaker_and_two_hop_takeover(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            unclassified = ph.record_failure("provider_a", "AssertionError: unit test failed", path=health)
            self.assertFalse(unclassified["tripped"])

            rc_code, diverted = preflight.run_takeover(
                category="coding",
                failed_provider="provider_a",
                error_text="HTTP 403 geo-block",
                attempt=0,
                host="t3",
                no_live=True,
                health_path=health,
            )
            self.assertEqual(rc_code, 0)
            self.assertEqual(diverted["action"], "divert")
            self.assertEqual(diverted["next_target"]["provider"], "provider_b")

            rc_cap, capped = preflight.run_takeover(
                category="coding",
                failed_provider="provider_b",
                error_text="HTTP 429 rate limit",
                attempt=2,
                host="t3",
                no_live=True,
                health_path=health,
            )
            self.assertEqual(rc_cap, 3)
            self.assertEqual(capped["action"], "escalate")
            self.assertIn("max_takeover_hops_reached", capped["reason"])

            cleared = ph.clear_health("provider_a", path=health)
            self.assertTrue(cleared["removed"])
            self.assertNotIn("provider_a", cleared["active_trips"])

    def test_takeover_preserves_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp) / "wt"
            wt.mkdir()
            subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
            (wt / "notes.txt").write_text("partial work\n", encoding="utf-8")
            health = Path(tmp) / "health.json"
            rc_code, res = preflight.run_takeover(
                category="coding",
                failed_provider="provider_a",
                error_text="HTTP 429 quota exhausted",
                attempt=0,
                worktree=str(wt),
                no_live=True,
                health_path=health,
            )
            self.assertEqual(rc_code, 0)
            self.assertEqual(res["salvage"]["action"], "preserve_worktree")
            self.assertTrue(res["salvage"]["has_changes"])
            self.assertIn(str(wt), res["salvage"]["brief_context"])

    def test_expired_trip_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            ph.record_failure("provider_a", "401 unauthorized", path=health, ttl_seconds=10, now=100.0)
            loaded = ph.load_health(health, now=200.0)
            self.assertEqual(loaded["providers"], {})

    def test_cli_preflight_and_health_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            p1 = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "preflight.py"), "preflight", "--category", "coding", "--host", "cli", "--health-file", str(health), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(p1.returncode, 0, p1.stderr)
            self.assertTrue(json.loads(p1.stdout)["ok"])

            p2 = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "preflight.py"), "preflight", "--category", "unknown-cat", "--health-file", str(health), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(p2.returncode, 2)


if __name__ == "__main__":
    unittest.main()
