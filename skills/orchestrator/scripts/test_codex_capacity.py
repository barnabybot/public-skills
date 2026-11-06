#!/usr/bin/env python3
"""Pace-versus-reset checks for a Codex-shaped native observation.

The model id is a placeholder. The checks cover the account windows, not a
named seat.
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from codex_capacity import assess_native

MODEL = "provider-b-large"


class NativeCapacityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.observation = {
            "source": "codex app-server",
            "read_at": self.now.isoformat(),
            "account_type": "chatgpt",
            "plan": "example",
            "ordinaryUsageAllowed": True,
            "models": [{"model": MODEL, "efforts": ["high", "max"]}],
            "probe": {
                "model": MODEL,
                "effort": "max",
                "runnable": True,
                "account_unchanged": True,
                "shell_verified": True,
            },
            "buckets": [{
                "id": "codex",
                "planType": "example",
                "spendControlReached": False,
                "rateLimitReachedType": None,
                "windows": [{
                    "slot": "primary",
                    "usedPercent": 22,
                    "windowDurationMins": 10080,
                    "resetsAt": 1793382323,
                }],
            }],
        }
        self.request = {
            "bounded_preference": {
                "tasks": 1,
                "task": "one successor",
                "source": "standing lineage rule",
            }
        }
        self.evidence = {"fit": "ruling", "debit_reason": "uncalibrated"}

    def assess(self):
        return assess_native(
            self.observation, MODEL, "max", {"shell"}, self.evidence, self.request,
            {"max_observation_age_seconds": 300, "exhausted_used_percent": 95}, self.now,
        )

    def test_bounded_observation_keeps_future_consumption_unknown(self):
        result = self.assess()
        self.assertEqual(result["state"], "eligible")
        self.assertEqual(result["windows"][0]["remaining"], 78)
        self.assertEqual(result["future_debit"], "unknown")
        self.assertIn("weekly 22% used", result["reasons"][0])

    def test_exhausted_window_is_excluded_before_pace(self):
        week = 10080 * 60
        self.observation["buckets"][0]["windows"][0].update(
            usedPercent=95, resetsAt=self.now.timestamp() + week,
        )
        result = self.assess()
        self.assertEqual(result["state"], "excluded")
        self.assertIn("exhausted", result["reasons"][-1])
        self.assertNotIn("pace", result["reasons"][-1])

    def test_pace_grades_linear_burn_toward_reset(self):
        week = 10080 * 60
        ahead = "ahead of schedule, pace runs out before reset"
        cases = [
            ("halfway, used matches elapsed", 50, week / 2, "on", False, "on pace"),
            ("halfway, clearly ahead", 63, week / 2, "ahead", True, ahead),
            ("halfway, clearly behind", 20, week / 2, "behind", False, "behind schedule"),
        ]
        original = copy.deepcopy(self.observation)
        for name, used, seconds_left, pace, tight, phrase in cases:
            with self.subTest(name=name):
                self.observation = copy.deepcopy(original)
                self.observation["buckets"][0]["windows"][0].update(
                    usedPercent=used, resetsAt=self.now.timestamp() + seconds_left,
                )
                result = self.assess()
                self.assertEqual(result["state"], "eligible")
                self.assertIs(result["tight"], tight)
                self.assertEqual(result["windows"][0]["pace"], pace)
                self.assertIn(phrase, result["reasons"][0])

    def test_one_ahead_window_marks_the_account_tight(self):
        week = 10080 * 60
        short = 300 * 60
        self.observation["buckets"][0]["windows"] = [
            {
                "slot": "primary", "usedPercent": 9, "windowDurationMins": 10080,
                "resetsAt": self.now.timestamp() + week,
            },
            {
                "slot": "secondary", "usedPercent": 50, "windowDurationMins": 300,
                "resetsAt": self.now.timestamp() + (short - 3600),
            },
        ]
        result = self.assess()
        self.assertEqual(result["state"], "eligible")
        self.assertIs(result["tight"], True)
        self.assertEqual([row["pace"] for row in result["windows"]], ["on", "ahead"])


if __name__ == "__main__":
    unittest.main()
