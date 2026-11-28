#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load("sources")
D = _load("discover")
B = _load("build")


class MultiHarnessParserTests(unittest.TestCase):
    def test_claude_parser_and_headless_filter(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / ".claude/projects/-Users-test-Repos-home"
            root.mkdir(parents=True)
            normal = root / "sess-claude-1.jsonl"
            rows = [
                {"type": "user", "timestamp": "2026-11-25T01:00:00Z", "cwd": "/Users/test/Repos/home",
                 "message": {"content": "<command-name>/recall</command-name><command-args>yesterday</command-args>"}},
                {"type": "assistant", "timestamp": "2026-11-25T01:00:05Z", "message": {"content": [
                    {"type": "text", "text": "Checking sessions."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
                {"type": "user", "timestamp": "2026-11-25T01:01:00Z", "message": {"content": "no wait fix that"}},
            ]
            normal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            headless = root / "sess-claude-sdk.jsonl"
            headless.write_text(json.dumps({"entrypoint": "sdk-cli", "type": "user", "message": {"content": "auto"}}) + "\n", encoding="utf-8")

            roots = {"claude": Path(d) / ".claude/projects", "codex": Path(d) / "no", "grok": Path(d) / "no",
                     "muse": Path(d) / "no", "antigravity": [], "vault": Path(d) / "no"}
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"claude"}, min_turns=2)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["session_id"], "sess-claude-1")
            self.assertEqual(sessions[0]["harness"], "claude-code")
            self.assertEqual(sessions[0]["skills"], ["recall"])
            self.assertEqual(sessions[0]["correction_hits"], 1)
            self.assertEqual(sessions[0]["resume_cmd"], "claude --resume sess-claude-1")

    def test_codex_parser_skips_exec_and_harness_preambles(self):
        with tempfile.TemporaryDirectory() as d:
            cdir = Path(d) / ".codex/sessions/2026/11/25"
            cdir.mkdir(parents=True)
            f = cdir / "rollout-2026-11-25T07-00-00-codex-sid-1.jsonl"
            rows = [
                {"timestamp": "2026-11-25T07:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "codex-sid-1", "cwd": "/Users/test/Repos/home", "originator": "codex_cli_rs"}},
                {"timestamp": "2026-11-25T07:00:01Z", "type": "response_item",
                 "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /tmp"}]}},
                {"timestamp": "2026-11-25T07:00:02Z", "type": "response_item",
                 "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "fix the parser tests"}]}},
                {"timestamp": "2026-11-25T07:00:03Z", "type": "response_item",
                 "payload": {"type": "custom_tool_call", "name": "exec", "input": "pytest"}},
                {"timestamp": "2026-11-25T07:00:04Z", "type": "response_item",
                 "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}},
            ]
            f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            child = cdir / "rollout-2026-11-25T07-05-00-codex-child.jsonl"
            child.write_text(json.dumps({"type": "session_meta", "payload": {"id": "codex-child", "originator": "codex_exec"}}) + "\n", encoding="utf-8")

            roots = {"claude": Path(d) / "no", "codex": Path(d) / ".codex/sessions", "grok": Path(d) / "no",
                     "muse": Path(d) / "no", "antigravity": [], "vault": Path(d) / "no"}
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"codex"}, min_turns=1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["session_id"], "codex-sid-1")
            self.assertEqual(sessions[0]["harness"], "codex")
            self.assertEqual(sessions[0]["tools"], 1)
            self.assertEqual(sessions[0]["resume_cmd"], "codex resume codex-sid-1")

    def test_grok_parser_handles_updates_and_filters_tab_namer(self):
        with tempfile.TemporaryDirectory() as d:
            enc = quote("/Users/test/Repos/home", safe="")
            gdir = Path(d) / ".grok/sessions" / enc / "grok-sid-1"
            gdir.mkdir(parents=True)
            rows = [
                {"timestamp": 1795000000, "method": "session/update", "params": {"update": {
                    "sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "run last30days "}}}},
                {"timestamp": 1795000001, "method": "session/update", "params": {"update": {
                    "sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "on ai agents"}}}},
                {"timestamp": 1795000002, "method": "session/update", "params": {"update": {
                    "sessionUpdate": "tool_call", "title": "read_file", "rawInput": {"target_file": "/x/skills/last30days/SKILL.md"}}}},
                {"timestamp": 1795000003, "method": "session/update", "params": {"update": {
                    "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Running now."}}}},
            ]
            (gdir / "updates.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

            tab = Path(d) / ".grok/sessions" / enc / "grok-tab"
            tab.mkdir(parents=True)
            (tab / "updates.jsonl").write_text(json.dumps({
                "timestamp": 1795000010, "method": "session/update",
                "params": {"update": {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": S.GROK_TAB_NAMER}}},
            }) + "\n", encoding="utf-8")

            roots = {"claude": Path(d) / "no", "codex": Path(d) / "no", "grok": Path(d) / ".grok/sessions",
                     "muse": Path(d) / "no", "antigravity": [], "vault": Path(d) / "no"}
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"grok"}, min_turns=1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["session_id"], "grok-sid-1")
            self.assertEqual(sessions[0]["skills"], ["last30days"])
            self.assertEqual(sessions[0]["first_msg"], "run last30days on ai agents")

    def test_muse_parser_and_headless_filter(self):
        with tempfile.TemporaryDirectory() as d:
            mdir = Path(d) / "muse/2026/11/25/muse-sid-1"
            mdir.mkdir(parents=True)
            rows = [
                {"recorded_at": 1795000000000000, "payload_type": "runtime.session.metadata",
                 "payload": {"record": {"workspace_root": "/Users/test/Repos/home"}}},
                {"recorded_at": 1795000001000000, "payload_type": "runtime.session.route_facts",
                 "payload": {"record": {"local_runtime_command_socket_path": "/tmp/sock"}}},
                {"recorded_at": 1795000002000000, "payload_type": "runtime.user_intent.accepted",
                 "payload": {"surface": "main", "refill_blocks": [{"kind": "text", "text": "check the deploy"}]}},
                {"recorded_at": 1795000003000000, "payload_type": "runtime.session",
                 "payload": {"kind": "run", "event": {"kind": "assistant_message_committed", "text": "Checking now."}}},
                {"recorded_at": 1795000004000000, "payload_type": "runtime.session",
                 "payload": {"kind": "run", "event": {"kind": "assistant_tool_calls_committed",
                                                      "tool_calls": [{"name": "shell", "arguments": {"cmd": "git status"}}]}}},
            ]
            (mdir / "session.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

            roots = {"claude": Path(d) / "no", "codex": Path(d) / "no", "grok": Path(d) / "no",
                     "muse": Path(d) / "muse", "antigravity": [], "vault": Path(d) / "no"}
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"muse"}, min_turns=1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["harness"], "muse")
            self.assertEqual(sessions[0]["tools"], 1)

    def test_antigravity_uses_transcript_full_and_skips_delegated(self):
        with tempfile.TemporaryDirectory() as d:
            ag = Path(d) / ".t3/userdata/providers/antigravity/p1/antigravity-acp/brain/ag-sid-1/.system_generated/logs"
            ag.mkdir(parents=True)
            (ag / "transcript.jsonl").write_text("\n".join([
                json.dumps({"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-28T00:00:00Z",
                            "content": "<USER_REQUEST><t3_code_instructions>long...", "truncated_fields": ["content"]}),
                json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-28T00:00:05Z",
                            "content": "Checking your skill.", "tool_calls": [
                                {"name": "run_command", "args": {"CommandLine": "\"git status\""}}]}),
            ]), encoding="utf-8")
            (ag / "transcript_full.jsonl").write_text(json.dumps({
                "step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-28T00:00:00Z",
                "content": "<USER_REQUEST><t3_code_instructions>x</t3_code_instructions><user_request>upgrade session intelligence</user_request></USER_REQUEST>",
            }) + "\n", encoding="utf-8")

            child = Path(d) / ".t3/userdata/providers/antigravity/p1/antigravity-acp/brain/ag-child/.system_generated/logs"
            child.mkdir(parents=True)
            (child / "transcript.jsonl").write_text(json.dumps({
                "step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-28T00:01:00Z",
                "content": f"<user_request>{S.T3_DELEGATED_PREFIX} \"abc\" sent this message, not the user.]\ndo review</user_request>",
            }) + "\n", encoding="utf-8")

            roots = {"claude": Path(d) / "no", "codex": Path(d) / "no", "grok": Path(d) / "no",
                     "muse": Path(d) / "no", "antigravity": [Path(d) / ".t3/userdata/providers/antigravity"],
                     "vault": Path(d) / "no"}
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"antigravity"}, min_turns=1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["session_id"], "ag-sid-1")
            self.assertEqual(sessions[0]["host"], "t3-code")
            self.assertEqual(sessions[0]["first_msg"], "upgrade session intelligence")
            self.assertEqual(sessions[0]["tools"], 1)

    def test_agents_vault_enrichment_vault_only_and_cron_health(self):
        with tempfile.TemporaryDirectory() as d:
            cdir = Path(d) / ".claude/projects/-Users-test-Repos-home"
            cdir.mkdir(parents=True)
            (cdir / "matched-1.jsonl").write_text(json.dumps({
                "type": "user", "timestamp": "2026-11-27T01:00:00Z", "message": {"content": "ship the fix"},
            }) + "\n", encoding="utf-8")

            vault = Path(d) / "Agents"
            (vault / "Sessions").mkdir(parents=True)
            (vault / "Sessions/2026-11-27 matched note.md").write_text(
                "---\nagent: claude-code\nhost: cmux\nstatus: blocked\nsession_id: matched-1\ncreated: 2026-11-27\n---\n\n"
                "## Goal\nShip the release.\n\n## Outcome\nBlocked on CI token.\n",
                encoding="utf-8",
            )
            (vault / "Sessions/2026-11-27 cursor only.md").write_text(
                "---\nagent: cursor\nstatus: done\ncreated: 2026-11-27\ndescription: \"Refactored UI layout\"\n---\n\n"
                "## Goal\nTighten card spacing.\n\n## Outcome\nMerged cleanly.\n",
                encoding="utf-8",
            )
            (vault / "Cron/sessions").mkdir(parents=True)
            (vault / "Cron/sessions/2026-11-27-0800-digest.md").write_text(
                "---\nskill: newsletter-digest\nstatus: completed\nstarted_at: 2026-11-27T08:00:00Z\noutcome: ok\n---\n",
                encoding="utf-8",
            )
            (vault / "Cron/sessions/2026-11-27-0900-market.md").write_text(
                "---\nskill: market-brief\nstatus: failed\nstarted_at: 2026-11-27T09:00:00Z\noutcome: timeout\n---\nTimed out.\n",
                encoding="utf-8",
            )

            roots = {"claude": Path(d) / ".claude/projects", "codex": Path(d) / "no", "grok": Path(d) / "no",
                     "muse": Path(d) / "no", "antigravity": [], "vault": vault}
            sessions, hh = S.discover_sessions(roots=roots, enabled_sources={"claude", "vault", "cron"}, min_turns=1)
            by_id = {s["session_id"]: s for s in sessions}
            self.assertIn("matched-1", by_id)
            self.assertEqual(by_id["matched-1"]["vault_status"], "blocked")
            self.assertEqual(by_id["matched-1"]["host"], "cmux")
            self.assertTrue(any(s["harness"] == "cursor" and s["source_kind"] == "vault-note" for s in sessions))
            self.assertTrue(any(s["harness"] == "cron" and s["source_kind"] == "cron-failure" for s in sessions))
            self.assertEqual(hh["total_runs"], 2)
            self.assertEqual(hh["total_failures"], 1)
            self.assertEqual(len(hh["daily"]), 2)
            self.assertEqual(
                {(r["d"], r["skill"], r["completed"], r["failed"]) for r in hh["daily"]},
                {("2026-11-27", "newsletter-digest", 1, 0), ("2026-11-27", "market-brief", 0, 1)},
            )
            self.assertEqual(S.scan_cron_daily(vault / "Cron/sessions", since_date="2026-11-28"), [])

    def test_vault_date_window_ignores_stale_created_date_even_with_fresh_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d) / "Agents"
            (vault / "Sessions").mkdir(parents=True)
            (vault / "Sessions/2026-05-01 old synced note.md").write_text(
                "---\nagent: grok-bot\nstatus: done\ncreated: 2026-05-01\n---\n\n## Goal\nOld work.\n",
                encoding="utf-8",
            )
            (vault / "Sessions/2026-11-27 recent note.md").write_text(
                "---\nagent: agy\nstatus: done\ncreated: 2026-11-27\n---\n\n## Goal\nNew work.\n",
                encoding="utf-8",
            )
            roots = {"claude": Path(d) / "no", "codex": Path(d) / "no", "grok": Path(d) / "no",
                     "muse": Path(d) / "no", "antigravity": [], "vault": vault}
            cutoff = S.datetime(2026, 11, 1, tzinfo=S.timezone.utc).timestamp()
            sessions, _ = S.discover_sessions(roots=roots, enabled_sources={"vault"}, since_ts=cutoff, min_turns=1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["harness"], "antigravity")


class BuildPipelineTests(unittest.TestCase):
    def test_merge_and_render_multi_harness_and_agents_md_rules(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data/digests").mkdir(parents=True)
            (root / "data/runs").mkdir(parents=True)
            dp = root / "data/digests/s1.txt"
            dp.write_text("SESSION s1\n[10:00] USER: please keep rules in AGENTS.md\n", encoding="utf-8")
            (root / "data/work-list.jsonl").write_text(json.dumps({
                "session_id": "s1", "harness": "antigravity", "host": "t3-code", "project": "repos/home",
                "vault_domain": "repos", "date": "2026-11-28", "human_turns": 6, "digest_path": str(dp),
                "resume_cmd": "agy --conversation s1", "vault_note": "/Agents/Sessions/2026-11-28 x.md", "vault_status": "done",
            }) + "\n", encoding="utf-8")
            (root / "data/cron-health.json").write_text(json.dumps({
                "total_runs": 10, "total_failures": 1, "skills": [{"skill": "market-brief", "completed": 9, "failed": 1, "total": 10}],
            }), encoding="utf-8")
            (root / "data/runs/conv-s1.json").write_text(json.dumps({
                "session_id": "s1", "title": "Multi-harness upgrade", "intent": "Port skill", "task_type": "coding",
                "skills_invoked": ["session-intelligence"], "skills_missing": [],
                "highlights": ["please keep rules in AGENTS.md"],
                "friction": [], "toil": [],
                "preferences": [{"quote": "please keep rules in AGENTS.md", "rule": "Write portable AGENTS.md rules"}],
                "outcome": {"status": "completed", "artifacts": [], "committed": True, "summary": "Done"},
                "automation_candidates": [],
            }), encoding="utf-8")
            synth_raw = root / "data/synth-raw.json"
            synth_raw.write_text(json.dumps({"result": {
                "profile_summary": {"summary": "Time across antigravity.", "recurring_patterns": []},
                "roadmap": {"headline": "Automate checks", "automation_themes": []},
                "backlog": {"skill_backlog": []},
                "newwork": {"new_skills": [], "new_crons": []},
                "rules": {"agents_md_rules": [{"rule": "Write portable AGENTS.md rules", "evidence_quotes": ["please keep rules in AGENTS.md"], "sessions": ["s1"]}]},
            }}), encoding="utf-8")

            self.assertEqual(B.main(["assemble", "--root", str(root)]), 0)
            self.assertEqual(B.main(["merge", "--root", str(root), "--synth-out", str(synth_raw)]), 0)
            self.assertEqual(B.main(["render", "--root", str(root)]), 0)

            synth = json.loads((root / "data/synthesis.json").read_text(encoding="utf-8"))
            self.assertEqual(synth["agents_md_rules"][0]["rule"], "Write portable AGENTS.md rules")
            self.assertEqual(synth["profile"]["harness_distribution"], [{"harness": "antigravity", "count": 1}])
            html = (root / "app/index.html").read_text(encoding="utf-8")
            self.assertIn("AGENTS.md rule candidates", html)
            self.assertIn("agy --conversation s1", html)
            self.assertNotIn("CLAUDE.md rule candidates", html)


if __name__ == "__main__":
    unittest.main()
