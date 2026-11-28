#!/usr/bin/env python3
from __future__ import annotations

import ast
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SKILL_MANAGER_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_MANAGER_DIR / "scripts"
WORKFLOW_PATH = SKILL_MANAGER_DIR / "workflows" / "skill-audit.workflow"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import skill_audit as sa


def _sample_score(name: str, family: str, score_val: int, top_fix: str = "Trim prose.") -> dict:
    row = {"name": name, "family": family, "lines": 42, "top_fix": top_fix}
    for dim in sa.DIMENSIONS:
        row[dim] = {"score": score_val, "note": f"{dim} note for {name}"}
    return row


def _sample_synthesis() -> dict:
    return {
        "headline_fix": {
            "skill": "alpha-skill",
            "what": "Tighten the description triggers.",
            "why": "Routers fire on description text alone.",
        },
        "top_five": [
            {"skill": "alpha-skill", "fix": "Add concrete triggers.", "impact": "high"},
            {"skill": "beta-skill", "fix": "Move tables into references/.", "impact": "medium"},
        ],
        "themes": [
            {"theme": "Vague triggers", "count": 2, "note": "Descriptions lack user phrases."},
        ],
    }


def _make_family_tree(root: Path) -> None:
    (root / "writing" / "writing-edit").mkdir(parents=True)
    (root / "writing" / "SKILL.md").write_text("---\nname: writing\ndescription: Parent.\n---\nLine 1\n", encoding="utf-8")
    (root / "writing" / "writing-edit" / "SKILL.md").write_text(
        "---\nname: writing-edit\ndescription: Edit.\n---\nLine 1\nLine 2\n", encoding="utf-8"
    )
    (root / "ops" / "ops-sync").mkdir(parents=True)
    (root / "ops" / "ops-sync" / "SKILL.md").write_text(
        "---\nname: ops-sync\ndescription: Sync.\n---\nBody\n", encoding="utf-8"
    )
    (root / "research" / "research-brief").mkdir(parents=True)
    (root / "research" / "research-brief" / "SKILL.md").write_text(
        "---\nname: research-brief\ndescription: Brief.\n---\nBody\n", encoding="utf-8"
    )
    (root / "vendor" / "upstream-pack").mkdir(parents=True)
    (root / "vendor" / "upstream-pack" / "SKILL.md").write_text("---\nname: up\ndescription: x\n---\n", encoding="utf-8")
    (root / ".retired" / "old-skill").mkdir(parents=True)
    (root / ".retired" / "old-skill" / "SKILL.md").write_text("---\nname: o\ndescription: x\n---\n", encoding="utf-8")


def _make_flat_tree(root: Path) -> None:
    for slug in ("alpha", "beta"):
        (root / slug).mkdir(parents=True)
        (root / slug / "SKILL.md").write_text(f"---\nname: {slug}\ndescription: {slug}.\n---\nBody\n", encoding="utf-8")


class SkillAuditTests(unittest.TestCase):
    def test_default_skills_root_respects_env_and_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sa.default_skills_root(), Path.home() / "my-skills")
        with mock.patch.dict(os.environ, {"SKILLS_ROOT": "/custom/skills"}, clear=True):
            self.assertEqual(sa.default_skills_root(), Path("/custom/skills"))

    def test_rubric_and_workflow_are_harness_portable(self):
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        for text in (sa.RUBRIC, wf_text):
            self.assertNotIn("haiku", text.lower())
            self.assertNotIn("opus", text.lower())
            self.assertNotIn("~/.claude/skills/", text)
            self.assertNotIn("Claude Code skill", text)

    def test_discover_skills_supports_family_and_flat_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            fam_root = Path(tmp) / "families"
            _make_family_tree(fam_root)
            discovered = sa.discover_skills(fam_root)
            pairs = [(item["family"], item["name"]) for item in discovered]
            self.assertEqual(
                pairs,
                [("ops", "ops-sync"), ("research", "research-brief"), ("writing", "writing-edit")],
            )
            self.assertEqual(next(i for i in discovered if i["name"] == "writing-edit")["lines"], 6)

            with_parents = sa.discover_skills(fam_root, include_parents=True)
            parent_pairs = [(item["family"], item["name"]) for item in with_parents]
            self.assertIn(("writing", "writing"), parent_pairs)
            self.assertIn(("writing", "writing-edit"), parent_pairs)

            filtered = sa.discover_skills(fam_root, families=["ops"])
            self.assertEqual([(item["family"], item["name"]) for item in filtered], [("ops", "ops-sync")])

            flat_root = Path(tmp) / "skills"
            _make_flat_tree(flat_root)
            flat_found = sa.discover_skills(flat_root)
            self.assertEqual([(item["family"], item["name"]) for item in flat_found], [("skills", "alpha"), ("skills", "beta")])

    def test_aggregate_scores_computes_35_point_total_and_ranks_worst_first(self):
        good = _sample_score("good-skill", "ops", 5)
        bad = _sample_score("bad-skill", "writing", 2)
        mid = _sample_score("mid-skill", "research", 3)

        ranked = sa.aggregate_scores([good, None, mid, bad])
        self.assertEqual([r["name"] for r in ranked], ["bad-skill", "mid-skill", "good-skill"])
        self.assertEqual([r["total"] for r in ranked], [14, 21, 35])

        slim = sa.slim_scores(ranked)
        self.assertEqual(slim[0]["total"], 14)
        self.assertEqual(
            slim[0]["scores"],
            {"desc": 2, "budget": 2, "prog": 2, "self": 2, "name": 2, "fresh": 2, "sig": 2},
        )

    def test_render_html_escapes_html_uses_35_max_and_omits_model_pins(self):
        bad = _sample_score("<script>bad</script>", "writing", 2, top_fix='Fix "quotes" & <tags>.')
        good = _sample_score("clean-skill", "ops", 5, top_fix="Keep as is.")
        ranked = sa.aggregate_scores([good, bad])
        html = sa.render_html(ranked, _sample_synthesis(), len(ranked))

        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Total /35", html)
        self.assertNotIn("Total /30", html)
        self.assertNotIn("haiku", html.lower())
        self.assertNotIn("opus", html.lower())
        self.assertNotIn("<script>bad</script>", html)
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", html)
        self.assertIn("Fix &quot;quotes&quot; &amp; &lt;tags&gt;.", html)
        self.assertIn("#cf222e", html)
        self.assertIn("#1a7f37", html)

    def test_workflow_script_runs_end_to_end_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_family_tree(root)
            out_html = root / "out" / "audit.html"
            out_json = root / "out" / "audit.json"
            source = WORKFLOW_PATH.read_text(encoding="utf-8")
            calls: list[dict] = []

            async def mock_agent(prompt: str, *, schema: dict | None = None, role: str | None = None, model: str | None = None):
                calls.append({"role": role, "model": model, "prompt": prompt})
                if role and role.startswith("score:"):
                    skill_name = role.split(":", 1)[1]
                    val = 2 if skill_name == "writing-edit" else 4
                    return _sample_score(skill_name, "writing" if skill_name == "writing-edit" else "ops", val)
                if role == "synthesis":
                    return _sample_synthesis()
                raise AssertionError(f"Unexpected role: {role}")

            async def mock_parallel(items, fn):
                return list(await asyncio.gather(*(fn(item) for item in items)))

            phases: list[str] = []
            env = {
                "__name__": "__main__",
                "__file__": str(WORKFLOW_PATH),
                "args": {
                    "root": str(root),
                    "outHtml": str(out_html),
                    "outJson": str(out_json),
                },
                "agent": mock_agent,
                "parallel": mock_parallel,
                "phase": lambda name: phases.append(name),
                "log": lambda *parts: None,
            }
            code = compile(source, str(WORKFLOW_PATH), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            buf = io.StringIO()

            async def _exec():
                with redirect_stdout(buf):
                    coro = eval(code, env)
                    if coro is not None:
                        await coro

            asyncio.run(_exec())
            self.assertEqual(phases, ["Discover", "Score", "Synthesise"])
            result = json.loads(buf.getvalue().splitlines()[-1])
            self.assertEqual(result["count"], 3)
            self.assertEqual(result["ranked"][0]["name"], "writing-edit")
            self.assertEqual(result["ranked"][0]["total"], 14)
            self.assertTrue(out_html.is_file())
            self.assertTrue(out_json.is_file())
            self.assertIn("Total /35", out_html.read_text(encoding="utf-8"))
            score_models = {c["model"] for c in calls if c["role"] and c["role"].startswith("score:")}
            self.assertEqual(score_models, {"flash"})
            synth_call = next(c for c in calls if c["role"] == "synthesis")
            self.assertEqual(synth_call["model"], "inherit")

    def test_cli_discover_render_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_family_tree(root)
            discover_proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "skill_audit.py"), "discover", "--root", str(root), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(discover_proc.returncode, 0, discover_proc.stderr)
            disc = json.loads(discover_proc.stdout)
            self.assertEqual(disc["count"], 3)

            dry_proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "skill_audit.py"), "run", "--root", str(root), "--dry-run", "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(dry_proc.returncode, 0, dry_proc.stderr)
            dry = json.loads(dry_proc.stdout)
            self.assertTrue(dry["dry_run"])
            self.assertEqual(dry["count"], 3)

            saved_json = root / "raw.json"
            out_html = root / "report.html"
            ranked = sa.aggregate_scores([_sample_score("writing-edit", "writing", 3)])
            saved_json.write_text(
                json.dumps({"count": 1, "ranked": ranked, "synthesis": _sample_synthesis()}),
                encoding="utf-8",
            )
            render_proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "skill_audit.py"),
                    "render",
                    "--input-json",
                    str(saved_json),
                    "--out-html",
                    str(out_html),
                    "--json",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(render_proc.returncode, 0, render_proc.stderr)
            self.assertTrue(out_html.is_file())
            self.assertIn("writing-edit", out_html.read_text(encoding="utf-8"))

    def test_build_command_preserves_sandbox_and_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_file = root / "p.md"
            prompt_file.write_text("score this", encoding="utf-8")
            for harness in ("agy", "codex", "grok", "claude"):
                with mock.patch.object(sa, "find_binary", return_value=f"/bin/{harness}"):
                    cmd, _ = sa.build_command(harness, prompt_file, root)
                joined = " ".join(cmd)
                self.assertNotIn("--dangerously-skip-permissions", joined)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", joined)
                self.assertNotIn("--always-approve", joined)
                self.assertNotIn("bypassPermissions", joined)
                if harness == "codex":
                    self.assertIn("--sandbox", cmd)
                    self.assertIn("read-only", cmd)


if __name__ == "__main__":
    unittest.main()
