#!/usr/bin/env python3
"""Fixture checks for the public surface-stamp reader."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_adapters import read_spawned_surface


class RuntimeAdapterTests(unittest.TestCase):
    def test_stamp_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "spawned-surfaces"
            folder.mkdir()
            payload = {
                "workspaceId": "ws",
                "surfaceId": "surface-1",
                "agent": "codex",
                "model": "REPLACE-WITH-YOUR-PROVIDER-B-LARGE-MODEL-ID",
                "effort": "high",
                "cwd": "/tmp/work",
            }
            (folder / "surface-1.json").write_text(json.dumps(payload), encoding="utf-8")
            got = read_spawned_surface("SURFACE-1", root)
            self.assertEqual(got["agent"], "codex")
            self.assertEqual(got["effort"], "high")

    def test_missing_stamp_names_the_next_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                read_spawned_surface("missing", Path(tmp))
            self.assertIn("stamp_surface.py", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
