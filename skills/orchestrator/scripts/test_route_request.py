#!/usr/bin/env python3
"""Structured request gates and route-bundle reuse on the placeholder table."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import resolve

HERE = Path(__file__).resolve().parent
NOW = "2026-09-14T00:32:45Z"


class RouteRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        skill = root / "SKILL.md"
        refs = root / "references"
        refs.mkdir()
        skill.write_text((HERE.parent / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
        meta = (HERE.parent / "references" / "routing-metadata.yaml").read_text(encoding="utf-8")
        meta = meta.replace(
            '    codexbar: null\n    subscription: "(your plan)"',
            '    codexbar: PROVIDER\n    subscription: "(your plan)"',
        )
        meta = meta.replace(
            "  provider_a:\n    agent: claude\n    codexbar: PROVIDER",
            "  provider_a:\n    agent: claude\n    codexbar: provider_a",
        )
        meta = meta.replace(
            "  provider_b:\n    agent: codex\n    codexbar: PROVIDER",
            "  provider_b:\n    agent: codex\n    codexbar: provider_b",
        )
        (refs / "routing-metadata.yaml").write_text(meta, encoding="utf-8")
        self.skill = skill
        self.fixtures = root / "fixtures"
        shutil.copytree(HERE / "fixtures", self.fixtures)
        self.env_now = os.environ.get("ROUTING_NOW")
        os.environ["ROUTING_NOW"] = NOW
        os.environ["ROUTING_FIXTURE_DIR"] = str(self.fixtures)

    def tearDown(self):
        if self.env_now is None:
            os.environ.pop("ROUTING_NOW", None)
        else:
            os.environ["ROUTING_NOW"] = self.env_now
        os.environ.pop("ROUTING_FIXTURE_DIR", None)

    def test_unauthorised_providers_exit_3(self):
        path = Path(self.tmp.name) / "request.json"
        path.write_text(json.dumps({
            "authorisation": {"source": "fixture brief", "providers": ["missing"]},
        }), encoding="utf-8")
        rc = self.run_resolve(["--skill", str(self.skill), "--tier", "systems", "--request", str(path)])
        self.assertEqual(rc, 3)

    def test_required_capacity_holds_when_the_meter_is_readable(self):
        path = Path(self.tmp.name) / "request.json"
        path.write_text(json.dumps({
            "capacity": "required",
            "authorisation": {"source": "fixture brief", "providers": ["provider_a", "provider_b"]},
            "bounded_preference": {"tasks": 1, "task": "one fixture task", "source": "fixture ruling"},
        }), encoding="utf-8")
        rc = self.run_resolve(["--skill", str(self.skill), "--tier", "systems", "--request", str(path)])
        self.assertEqual(rc, 0)

    def test_bundle_reuse_skips_a_second_resolution(self):
        bundle = Path(self.tmp.name) / "bundle.json"
        rc = self.run_resolve([
            "--skill", str(self.skill), "--tier", "systems",
            "--runtime-cwd", self.tmp.name, "--bundle-out", str(bundle),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(bundle.is_file())
        os.environ.pop("ROUTING_FIXTURE_DIR", None)
        rc = self.run_resolve([
            "--skill", str(self.skill), "--tier", "systems",
            "--runtime-cwd", self.tmp.name, "--verify-bundle", str(bundle),
        ])
        self.assertEqual(rc, 0)

    def run_resolve(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return resolve.main(argv)

    def test_pace_without_a_meter_flag_marks_a_fast_burn_tight(self):
        raw = json.loads((self.fixtures / "provider_a.json").read_text(encoding="utf-8"))
        entry = raw[0]
        entry.pop("pace", None)
        entry["usage"]["secondary"]["usedPercent"] = 70
        entry["usage"]["primary"]["usedPercent"] = 5
        (self.fixtures / "provider_a.json").write_text(json.dumps(raw), encoding="utf-8")
        canon = resolve.load_canon(self.skill)
        cap = resolve.Capacity(canon)
        state = cap.assess("provider_a")
        self.assertEqual(state["state"], "tight")
        self.assertIn("pace runs out before reset", state["detail"])


if __name__ == "__main__":
    unittest.main()
