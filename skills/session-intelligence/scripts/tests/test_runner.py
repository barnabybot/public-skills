#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("runner")
F = _load("friction")


class RunnerTests(unittest.TestCase):
    def test_build_command_for_each_harness(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prompt.md"
            p.write_text("hello world", encoding="utf-8")
            cwd = Path(d)

            cmd, stdin = R.build_command("agy", p, cwd, model="flash")
            self.assertIn("--dangerously-skip-permissions", cmd)
            self.assertIn("--model", cmd)
            self.assertIsNone(stdin)

            cmd, stdin = R.build_command("codex", p, cwd, model="gpt-5")
            self.assertEqual(cmd[1], "exec")
            self.assertEqual(cmd[-1], "-")
            self.assertEqual(stdin, "hello world")

            cmd, stdin = R.build_command("claude", p, cwd, model="opus")
            self.assertIn("--permission-mode", cmd)
            self.assertIsNone(stdin)

            cmd, stdin = R.build_command("grok", p, cwd)
            self.assertIn("--prompt-file", cmd)
            self.assertIn("--always-approve", cmd)

            cmd, stdin = R.build_command("muse", p, cwd)
            self.assertEqual(cmd[1], "exec")
            self.assertIn("--prompt-file", cmd)

    def test_detect_cli_harness_respects_env(self):
        with mock.patch.dict(os.environ, {"T3_ACP_MCP_NODE": "/x/node"}, clear=True):
            with mock.patch.object(R, "find_binary", side_effect=lambda h: f"/bin/{h}"):
                self.assertEqual(R.detect_cli_harness("auto"), "agy")
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "t1"}, clear=True):
            with mock.patch.object(R, "find_binary", side_effect=lambda h: f"/bin/{h}"):
                self.assertEqual(R.detect_cli_harness("auto"), "codex")

    def test_parse_json_output_handles_fences_and_wrappers(self):
        self.assertEqual(R.parse_json_output('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(R.parse_json_output('{"result": {"b": 2}}'), {"b": 2})

    def test_multi_harness_friction_detects_cmux_on_antigravity_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            ag = Path(d) / "transcript.jsonl"
            rows = [
                {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-28T00:00:00Z",
                 "content": "<user_request>relay this to workspace:5</user_request>"},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-28T00:00:01Z",
                 "tool_calls": [{"name": "run_command", "args": {
                     "CommandLine": '"cmux send workspace:5 hi && cmux send-key workspace:5 Enter"'}}]},
            ]
            ag.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            ev = F.events(ag)
            hits, _ = F.detect(ev, "cmux")
            self.assertEqual([h["signature"] for h in hits], ["cmux-send-positional"])


if __name__ == "__main__":
    unittest.main()
