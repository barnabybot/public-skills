#!/usr/bin/env python3

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "patterns.py"
SPEC = importlib.util.spec_from_file_location("patterns", MODULE_PATH)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def items(n_fail, n_pass):
    out = [{"id": f"F{i}", "outcome": "fail", "files": []} for i in range(n_fail)]
    out += [{"id": f"P{i}", "outcome": "pass", "files": []} for i in range(n_pass)]
    return out


class ChooseTests(unittest.TestCase):
    def test_stratified_caps(self):
        chosen = M.choose(items(10, 6), max_total=8, max_fail=5, max_pass=3, seed=1)
        self.assertEqual(len(chosen), 8)
        self.assertEqual(sum(1 for c in chosen if c["outcome"] == "fail"), 5)
        self.assertEqual(sum(1 for c in chosen if c["outcome"] == "pass"), 3)

    def test_priority_wins_over_shuffle(self):
        pool = items(10, 0)
        pool[7]["priority"] = 0
        pool[9]["priority"] = 0
        chosen = M.choose(pool, max_fail=2, max_pass=0, seed=3)
        self.assertEqual(sorted(c["id"] for c in chosen), ["F7", "F9"])

    def test_seed_is_deterministic(self):
        a = [c["id"] for c in M.choose(items(10, 6), seed=42)]
        b = [c["id"] for c in M.choose(items(10, 6), seed=42)]
        self.assertEqual(a, b)

    def test_short_pools_return_what_exists(self):
        self.assertEqual(len(M.choose(items(1, 1))), 2)


class RenderTests(unittest.TestCase):
    def test_cap_truncates_with_marker(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "log.md"
            f.write_text("x" * 500)
            text = M.render_trace({"id": "T", "outcome": "fail", "files": [str(f)]}, cap=120)
            self.assertTrue(text.startswith("TRACE T\noutcome: fail"))
            self.assertTrue(text.endswith("[truncated at 120 characters]"))
            self.assertLessEqual(len(text), 120 + len("\n[truncated at 120 characters]"))

    def test_missing_file_is_named(self):
        text = M.render_trace({"id": "T", "outcome": "pass", "files": ["/nowhere/none.md"]})
        self.assertIn("[missing file", text)


class ManifestFromRunTests(unittest.TestCase):
    def test_verified_friction_marks_failure(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / "data"
            data.mkdir()
            (data / "work-list.jsonl").write_text(
                json.dumps({"session_id": "a", "digest_path": "/x/a.txt"}) + "\n"
                + json.dumps({"session_id": "b", "digest_path": "/x/b.txt"}) + "\n")
            (data / "conversations.jsonl").write_text(
                json.dumps({"session_id": "a", "title": "A", "friction": [{"quote": "q", "evidence_verified": True}]}) + "\n"
                + json.dumps({"session_id": "b", "title": "B", "friction": [{"quote": "q", "evidence_verified": False}]}) + "\n")
            got = {i["id"]: i["outcome"] for i in M.manifest_from_run(d)}
            self.assertEqual(got, {"a": "fail", "b": "pass"})


class VerifyTests(unittest.TestCase):
    def wiki(self, d, index, pages, log="## 2026-08-30\n\nentry\n"):
        w = Path(d)
        (w / "patterns").mkdir()
        (w / "index.md").write_text(index)
        (w / "log.md").write_text(log)
        for name, text in pages.items():
            (w / "patterns" / name).write_text(text)
        return w

    PAGE = "---\ntitle: One\ntype: pattern\nevidence:\n  - T1\n---\n\nbody\n"

    def test_clean_wiki_passes(self):
        with tempfile.TemporaryDirectory() as d:
            w = self.wiki(d, "- [one](patterns/one.md): problem, cause, fix.\n", {"one.md": self.PAGE})
            self.assertEqual(M.verify(w), [])

    def test_dangling_link_and_orphan_page_and_bare_page(self):
        with tempfile.TemporaryDirectory() as d:
            w = self.wiki(d, "- [gone](patterns/gone.md): x.\n",
                          {"one.md": self.PAGE, "bare.md": "no frontmatter\n"})
            problems = M.verify(w)
            self.assertIn("index links a missing page: patterns/gone.md", problems)
            self.assertIn("page not in index: patterns/one.md", problems)
            self.assertIn("page lacks frontmatter with evidence: patterns/bare.md", problems)

    def test_empty_log_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            w = self.wiki(d, "- [one](patterns/one.md): x.\n", {"one.md": self.PAGE}, log="")
            self.assertIn("log.md missing or empty", M.verify(w))


class ProposeTests(unittest.TestCase):
    def test_snapshot_carries_every_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            w = Path(d) / "wiki"
            (w / "patterns").mkdir(parents=True)
            for name in ("index.md", "log.md", "skill-impact.md", "skill-impact-cmux.md"):
                (w / name).write_text(name + "\n")
            traces = Path(d) / "traces"
            traces.mkdir()
            (traces / "MANIFEST.md").write_text("# traces\n")
            skill = Path(d) / "SKILL.md"
            skill.write_text("---\nname: x\nversion: 1.0.0\n---\n")
            a = argparse.Namespace(wiki=str(w), traces=str(traces), skill=str(skill), out=str(Path(d) / "out"),
                                   iteration="x-1", model="opus", note="", dry_run=True)
            self.assertEqual(M.cmd_propose(a), 0)
            snap = Path(d) / "out" / "wiki"
            self.assertTrue((snap / "skill-impact.md").is_file())
            self.assertTrue((snap / "skill-impact-cmux.md").is_file())


if __name__ == "__main__":
    unittest.main()
