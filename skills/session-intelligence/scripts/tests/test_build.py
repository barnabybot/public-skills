#!/usr/bin/env python3
from __future__ import annotations

import ast
import asyncio
import base64
import importlib.util
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("build")


def _extract_embedded_json(html: str) -> dict:
    match = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, flags=re.S)
    assert match, "missing embedded JSON payload script tag"
    return json.loads(match.group(1).replace("<\\/", "</"))


def _exec_workflow(path: Path, args: dict, agent_fn):
    source = path.read_text(encoding="utf-8")
    wrapped = "async def _workflow(args, agent, parallel, phase, log):\n" + "\n".join(
        "    " + line if line else "" for line in source.splitlines()
    )
    ns: dict = {}
    exec(compile(wrapped, str(path), "exec"), ns)

    async def parallel(items, fn):
        return await asyncio.gather(*(fn(item) for item in items))

    logs: list[str] = []
    phases: list[str] = []
    buf = io.StringIO()
    with redirect_stdout(buf):
        asyncio.run(ns["_workflow"](args, agent_fn, parallel, phases.append, logs.append))
    return buf.getvalue(), phases, logs


class FontEmbeddingTests(unittest.TestCase):
    def test_build_font_css_returns_empty_when_directory_absent(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "no-such-fonts"
            self.assertEqual(B.build_font_css(missing), "")

    def test_build_font_css_embeds_present_fonts_and_skips_missing(self):
        with tempfile.TemporaryDirectory() as d:
            fonts_dir = Path(d)
            sample = fonts_dir / "meta-pro" / "meta-pro-regular.woff2"
            sample.parent.mkdir(parents=True, exist_ok=True)
            payload = b"wOF2-test-bytes"
            sample.write_bytes(payload)

            css = B.build_font_css(fonts_dir)
            self.assertIn('@font-face{font-family:"Meta Pro"', css)
            self.assertIn("font-weight:400;font-style:normal;", css)
            self.assertIn(f'data:font/woff2;base64,{base64.b64encode(payload).decode("ascii")}', css)
            self.assertNotIn("ET Book", css)
            self.assertNotIn("JetBrains Mono", css)

    def test_default_fonts_dir_is_optional_and_safe(self):
        self.assertEqual(B.build_font_css(Path("/nonexistent/fonts/dir")), "")

    def test_templates_keep_placeholders_and_contain_no_binary_fonts(self):
        for name in ("app.html", "life.html"):
            text = (SCRIPTS / "templates" / name).read_text(encoding="utf-8")
            self.assertIn("__FONTS__", text)
            self.assertIn("__DATA__", text)
            self.assertNotIn("data:font/", text)
            self.assertNotIn("@font-face", text)


class ComputeRhythmTests(unittest.TestCase):
    def test_compute_rhythm_converts_utc_with_offset_and_ignores_date_only_sentinels(self):
        convs = [
            {"date": "2026-11-20", "started_at": "2026-11-19T22:15:00Z"},
            {"date": "2026-11-21", "started_at": "2026-11-20T22:45:00+00:00"},
            {"date": "2026-11-22", "started_at": "2026-11-22T00:00:00Z"},
            {"date": "2026-11-23", "started_at": "not-a-timestamp"},
            {"date": "2026-11-24", "started_at": ""},
            {"date": "2026-11-25", "started_at": "2026-11-25T10:30:00Z"},
        ]
        with mock.patch.dict("os.environ", {"SESSION_TZ_OFFSET": "8", "SESSION_TZ_LABEL": "UTC+8"}):
            rhythm = B.compute_rhythm(convs)
        self.assertEqual(rhythm["n_sessions"], 6)
        self.assertEqual(rhythm["date_range"], ["2026-11-20", "2026-11-25"])
        self.assertEqual(rhythm["tz_label"], "UTC+8")
        self.assertEqual(rhythm["local_hours"], {"06": 2, "18": 1})

    def test_compute_rhythm_handles_empty_list(self):
        with mock.patch.dict("os.environ", {"SESSION_TZ_OFFSET": "8", "SESSION_TZ_LABEL": "UTC+8"}):
            self.assertEqual(
                B.compute_rhythm([]),
                {"n_sessions": 0, "date_range": [], "tz_label": "UTC+8", "local_hours": {}},
            )


class RenderTests(unittest.TestCase):
    def _write_run(self, root: Path, *, with_convs: bool = True, life_payload: dict | None = None):
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        if with_convs:
            convs = [
                {
                    "session_id": "s-1",
                    "harness": "codex",
                    "date": "2026-11-20",
                    "started_at": "2026-11-19T23:00:00Z",
                    "title": "Fix </script> escaping",
                    "task_type": "coding",
                },
                {
                    "session_id": "s-2",
                    "harness": "antigravity",
                    "date": "2026-11-28",
                    "started_at": "2026-11-28T00:10:00Z",
                    "title": "Build editorial report",
                    "task_type": "content",
                },
            ]
            (data / "conversations.jsonl").write_text(
                "\n".join(json.dumps(c) for c in convs) + "\n",
                encoding="utf-8",
            )
        (data / "observations.jsonl").write_text(
            json.dumps({"session_id": "s-1", "type": "friction", "text": "retry", "evidence": "fix it", "evidence_verified": True})
            + "\n",
            encoding="utf-8",
        )
        (data / "synthesis.json").write_text(
            json.dumps({
                "headline": "Eliminate repeat manual checks",
                "automation_themes": [{"title": "Theme 1", "kind": "improve-skill", "automation_score": 12.0}],
                "profile": {"summary": "Work focuses on skills and builds."},
            }),
            encoding="utf-8",
        )
        if life_payload is not None:
            (data / "life.json").write_text(json.dumps(life_payload), encoding="utf-8")

    def test_render_embeds_tokens_data_and_handles_missing_fonts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_run(root)
            with mock.patch.object(B, "FONTS_DIR", root / "missing-fonts"):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = B.main(["render", "--root", str(root)])
            self.assertEqual(rc, 0)
            out_file = root / "app" / "index.html"
            self.assertTrue(out_file.is_file())
            html = out_file.read_text(encoding="utf-8")
            self.assertNotIn("__FONTS__", html)
            self.assertNotIn("__DATA__", html)
            self.assertIn("--paper:#fffff8;", html)
            self.assertIn("--accent:#c82118;", html)
            self.assertIn("--slate:#3e4e54;", html)
            self.assertIn('[data-theme="dark"]', html)
            self.assertIn('class="masthead"', html)
            self.assertIn('href="life.html"', html)

            payload = _extract_embedded_json(html)
            self.assertEqual(payload["synthesis"]["n_sessions"], 2)
            self.assertEqual(payload["synthesis"]["date_range"], ["2026-11-20", "2026-11-28"])
            self.assertEqual(payload["conversations"][0]["title"], "Fix </script> escaping")
            self.assertIn("(2 conv, 1 obs, 1 themes)", buf.getvalue())

    def test_render_dry_run_skips_writing_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_run(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = B.main(["render", "--root", str(root), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse((root / "app" / "index.html").exists())
            self.assertIn("[dry-run] rendered", buf.getvalue())

    def test_render_life_attaches_computed_rhythm_from_conversations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_run(
                root,
                with_convs=True,
                life_payload={
                    "profile": {
                        "one_liner": "Direct and evidence-first.",
                        "portrait": "You build fast.",
                        "patterns": [{"name": "Dawn sprints", "kind": "rhythm", "description": "Early starts."}],
                        "tensions": [],
                    },
                    "lens_findings": [{"lens": "rhythm", "name": "Dawn"}],
                    "harnesses": ["codex", "antigravity"],
                },
            )
            with mock.patch.object(B, "FONTS_DIR", root / "missing-fonts"), mock.patch.dict(
                "os.environ", {"SESSION_TZ_OFFSET": "8", "SESSION_TZ_LABEL": "UTC+8"}
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = B.main(["render-life", "--root", str(root)])
            self.assertEqual(rc, 0)
            html = (root / "app" / "life.html").read_text(encoding="utf-8")
            self.assertNotIn("__FONTS__", html)
            self.assertNotIn("__DATA__", html)
            self.assertIn("--paper:#fffff8;", html)
            self.assertIn("--accent:#c82118;", html)
            self.assertIn('id="rhythmMount"', html)
            self.assertIn('class="pat-grid"', html)

            payload = _extract_embedded_json(html)
            self.assertEqual(
                payload["rhythm"],
                {"n_sessions": 2, "date_range": ["2026-11-20", "2026-11-28"], "tz_label": "UTC+8", "local_hours": {"07": 1, "08": 1}},
            )
            self.assertEqual(
                payload["sessions"],
                [
                    {"d": "2026-11-20", "hr": "codex", "h": 7, "wd": 4},
                    {"d": "2026-11-28", "hr": "antigravity", "h": 8, "wd": 5},
                ],
            )
            self.assertIn('id="periodBar"', html)
            self.assertIn('id="opStrip"', html)
            self.assertIn('id="beatsWrap"', html)
            self.assertIn("portrait_beats", html)
            self.assertIn("(1 patterns)", buf.getvalue())

    def test_render_backfills_cron_daily_and_supports_out_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "run"
            out_dir = Path(d) / "preview"
            vault = Path(d) / "Agents"
            (vault / "Cron" / "sessions").mkdir(parents=True)
            (vault / "Cron" / "sessions" / "2026-11-25-0700-digest.md").write_text(
                "---\nskill: morning-briefing\nstatus: completed\nstarted_at: 2026-11-25T07:00:00Z\n---\n",
                encoding="utf-8",
            )
            (vault / "Cron" / "sessions" / "2026-11-28-0700-digest.md").write_text(
                "---\nskill: morning-briefing\nstatus: failed\nstarted_at: 2026-11-28T07:00:00Z\n---\n",
                encoding="utf-8",
            )
            self._write_run(root)
            synth_path = root / "data" / "synthesis.json"
            synth = json.loads(synth_path.read_text(encoding="utf-8"))
            synth["profile"]["cron_health"] = {
                "total_runs": 2,
                "total_failures": 1,
                "skills": [{"skill": "morning-briefing", "completed": 1, "failed": 1, "total": 2}],
            }
            synth_path.write_text(json.dumps(synth), encoding="utf-8")

            with mock.patch.object(B, "FONTS_DIR", root / "missing-fonts"):
                rc = B.main([
                    "render",
                    "--root", str(root),
                    "--out-dir", str(out_dir),
                    "--agents-vault", str(vault),
                ])
            self.assertEqual(rc, 0)
            self.assertFalse((root / "app" / "index.html").exists())
            html = (out_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="periodBar"', html)
            self.assertNotIn("(E-01)", html)
            payload = _extract_embedded_json(html)
            daily = payload["synthesis"]["profile"]["cron_health"]["daily"]
            self.assertEqual(len(daily), 2)
            self.assertEqual(daily[0]["d"], "2026-11-25")
            self.assertEqual(daily[1]["failed"], 1)

    def test_render_attaches_cluster_linked_matched_sessions_to_themes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_run(root)
            sd = root / "data" / "synth"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "candidate-clusters.json").write_text(
                json.dumps([
                    {"kind": "improve-skill", "target": "orchestrator", "count": 2, "sessions": ["s-1", "s-2"], "examples": []},
                ]),
                encoding="utf-8",
            )
            synth_path = root / "data" / "synthesis.json"
            synth = json.loads(synth_path.read_text(encoding="utf-8"))
            synth["automation_themes"] = [{
                "title": "Harden orchestrator preflight",
                "kind": "improve-skill",
                "automation_score": 12.0,
                "evidence_sessions": ["s-1"],
                "proposed_action": "Update orchestrator SKILL.md",
            }]
            synth_path.write_text(json.dumps(synth), encoding="utf-8")

            with mock.patch.object(B, "FONTS_DIR", root / "missing-fonts"):
                rc = B.main(["render", "--root", str(root)])
            self.assertEqual(rc, 0)
            payload = _extract_embedded_json((root / "app" / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(payload["synthesis"]["automation_themes"][0]["matched_sessions"], ["s-1", "s-2"])

    def test_render_life_works_when_only_life_json_exists(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            data.mkdir(parents=True, exist_ok=True)
            preset_rhythm = {"n_sessions": 9, "date_range": ["2026-10-01", "2026-10-09"], "local_hours": {"07": 4}}
            (data / "life.json").write_text(
                json.dumps({
                    "profile": {"one_liner": "Standalone portrait.", "portrait": "Only life.json.", "patterns": []},
                    "lens_findings": [],
                    "rhythm": preset_rhythm,
                }),
                encoding="utf-8",
            )
            with mock.patch.object(B, "FONTS_DIR", root / "missing-fonts"), mock.patch.dict(
                "os.environ", {"SESSION_TZ_OFFSET": "8", "SESSION_TZ_LABEL": "UTC+8"}
            ):
                rc = B.main(["render-life", "--root", str(root)])
            self.assertEqual(rc, 0)
            payload = _extract_embedded_json((root / "app" / "life.html").read_text(encoding="utf-8"))
            self.assertEqual(payload["rhythm"], preset_rhythm)


class WorkflowContractTests(unittest.TestCase):
    def test_workflows_parse_cleanly_as_async_python(self):
        for name in ("extract.workflow", "synth.workflow", "life.workflow"):
            src = (SCRIPTS / name).read_text(encoding="utf-8")
            wrapped = "async def _w():\n" + "\n".join("    " + l if l else "" for l in src.splitlines())
            ast.parse(wrapped, filename=name)

    def test_extract_workflow_inlines_batches_and_recovers_from_batch_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            digests = data / "digests"
            digests.mkdir(parents=True, exist_ok=True)
            (digests / "tr-1.txt").write_text("[07:00] USER: fix bug\n", encoding="utf-8")
            (digests / "vn-1.txt").write_text("[08:00] USER: [Vault Goal] note 1\n", encoding="utf-8")
            (digests / "vn-2.txt").write_text("[09:00] USER: [Vault Goal] note 2\n", encoding="utf-8")

            wl = [
                {"session_id": "tr-1", "source_kind": "transcript", "score": 90, "digest_path": str(digests / "tr-1.txt")},
                {"session_id": "vn-1", "source_kind": "vault-note", "score": 20, "digest_path": str(digests / "vn-1.txt")},
                {"session_id": "vn-2", "source_kind": "vault-note", "score": 10, "digest_path": str(digests / "vn-2.txt")},
            ]
            (data / "work-list.jsonl").write_text("\n".join(json.dumps(r) for r in wl) + "\n", encoding="utf-8")
            (data / "missing-full.json").write_text(
                json.dumps([{"session_id": r["session_id"]} for r in wl]),
                encoding="utf-8",
            )

            seen_prompts: list[str] = []

            async def fake_agent(prompt, schema=None, role="", model=""):
                seen_prompts.append(prompt)
                if "tr-1" in prompt:
                    raise RuntimeError("transient model timeout")
                return {
                    "sessions": [
                        {"session_id": "vn-1", "title": "Note 1", "highlights": ["[Vault Goal] note 1"]},
                        {"session_id": "vn-2", "title": "Note 2", "highlights": ["[Vault Goal] note 2"]},
                    ]
                }

            out, _, _ = _exec_workflow(
                SCRIPTS / "extract.workflow",
                {"scriptsDir": str(SCRIPTS), "root": str(root), "concurrency": 2, "model": "flash"},
                fake_agent,
            )
            self.assertEqual(len(seen_prompts), 2)
            self.assertTrue((data / "runs" / "conv-vn-1.json").is_file())
            self.assertTrue((data / "runs" / "conv-vn-2.json").is_file())
            self.assertFalse((data / "runs" / "conv-tr-1.json").exists())
            self.assertIn("'written': 2", out)
            self.assertIn("'failed_batches': 1", out)

    def test_synth_and_life_workflows_run_inline_with_zero_tool_calls(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            sd = data / "synth"
            ld = data / "life"
            sd.mkdir(parents=True, exist_ok=True)
            ld.mkdir(parents=True, exist_ok=True)
            (data / "work-list.jsonl").write_text(
                json.dumps({
                    "session_id": "s-1",
                    "harness": "codex",
                    "source_kind": "transcript",
                    "date": "2026-11-28",
                    "started_at": "2026-11-27T23:00:00Z",
                    "ended_at": "2026-11-27T23:45:00Z",
                    "human_turns": 12,
                    "tool_calls": 30,
                    "correction_hits": 2,
                    "score": 80,
                    "first_message": "ship it",
                }) + "\n",
                encoding="utf-8",
            )
            (data / "conversations.jsonl").write_text(
                json.dumps({
                    "session_id": "s-1",
                    "harness": "codex",
                    "source_kind": "transcript",
                    "date": "2026-11-28",
                    "task_type": "coding",
                    "highlights": ["ship it"],
                    "friction": [{"quote": "too slow", "cost": "medium"}],
                }) + "\n",
                encoding="utf-8",
            )
            (sd / "profile.json").write_text(json.dumps({"n_sessions": 1, "cron_health": {}}), encoding="utf-8")
            (sd / "titles.json").write_text(json.dumps([{"id": "s-1", "title": "Ship it"}]), encoding="utf-8")
            (sd / "candidate-clusters.json").write_text(json.dumps([]), encoding="utf-8")
            (sd / "skill-friction.json").write_text(json.dumps([]), encoding="utf-8")
            (sd / "preferences.json").write_text(json.dumps([]), encoding="utf-8")
            (sd / "toil.json").write_text(json.dumps([]), encoding="utf-8")
            (ld / "quotes.json").write_text(json.dumps([{"kind": "friction", "q": "too slow"}]), encoding="utf-8")

            synth_prompts: list[str] = []

            async def fake_synth_agent(prompt, schema=None, role="", model=""):
                synth_prompts.append(prompt)
                if role == "synth:profile":
                    return {"summary": "Focused.", "recurring_patterns": []}
                if role == "synth:roadmap":
                    return {"headline": "Top win", "automation_themes": [{"title": "T", "kind": "improve-skill", "automation_score": 5.0, "proposed_action": "Edit"}]}
                if role == "synth:skill-backlog":
                    return {"skill_backlog": []}
                if role == "synth:new-work":
                    return {"new_skills": [], "new_crons": []}
                return {"agents_md_rules": []}

            _exec_workflow(SCRIPTS / "synth.workflow", {"scriptsDir": str(SCRIPTS), "root": str(root)}, fake_synth_agent)
            self.assertEqual(len(synth_prompts), 5)
            self.assertTrue(all("Do NOT call any file or shell tools" in p for p in synth_prompts))
            synth_raw = json.loads((data / "synth-raw.json").read_text(encoding="utf-8"))
            self.assertEqual(synth_raw["result"]["roadmap"]["headline"], "Top win")

            life_prompts: list[str] = []

            async def fake_life_agent(prompt, schema=None, role="", model=""):
                life_prompts.append(prompt)
                if role == "Behavioural portrait":
                    return {"one_liner": "Fast.", "portrait": "You ship.", "patterns": [{"name": "P1", "description": "D", "reveals": "R", "kind": "rhythm"}]}
                return {"patterns": [{"name": role, "what": "W", "reveals": "R", "evidence_quotes": ["ship it"]}]}

            _exec_workflow(SCRIPTS / "life.workflow", {"scriptsDir": str(SCRIPTS), "root": str(root)}, fake_life_agent)
            self.assertEqual(len(life_prompts), 8)
            self.assertTrue(all("Do NOT call any file or shell tools" in p for p in life_prompts))
            self.assertIn('"07:00": 1', life_prompts[0])
            life_raw = json.loads((data / "life-raw.json").read_text(encoding="utf-8"))
            self.assertEqual(len(life_raw["result"]["lens_findings"]), 7)
            self.assertEqual(life_raw["result"]["profile"]["one_liner"], "Fast.")


if __name__ == "__main__":
    unittest.main()
