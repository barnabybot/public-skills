#!/usr/bin/env python3

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "friction.py"
SPEC = importlib.util.spec_from_file_location("friction", MODULE_PATH)
assert SPEC and SPEC.loader
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def user(t):
    return {"k": "user", "t": t, "ts": ""}


def bash(c):
    return {"k": "tool", "name": "Bash", "input": {"command": c}, "ts": ""}


def write(path, content):
    return {"k": "tool", "name": "Write", "input": {"file_path": path, "content": content}, "ts": ""}


def fired(ev, skill):
    hits, _ = F.detect(ev, skill)
    return sorted({h["signature"] for h in hits})


class CmuxSignatureTests(unittest.TestCase):
    def test_positional_workspace_fires_and_flag_form_does_not(self):
        self.assertEqual(fired([user("relay"), bash('cmux send workspace:5 "hi" && cmux send-key workspace:5 Enter')], "cmux"),
                         ["cmux-send-positional"])
        self.assertEqual(fired([user("relay"), bash('cmux send --workspace workspace:5 "hi" && cmux send-key --workspace workspace:5 Enter')], "cmux"), [])

    def test_send_without_enter_looks_ahead_two_calls(self):
        ev = [user("relay"), bash('cmux send --workspace workspace:5 "hi"'), bash("ls"), bash("cmux send-key --workspace workspace:5 Enter")]
        self.assertEqual(fired(ev, "cmux"), [])
        ev = [user("relay"), bash('cmux send --workspace workspace:5 "hi"'), bash("ls"), bash("ls"), bash("cmux send-key --workspace workspace:5 Enter")]
        self.assertEqual(fired(ev, "cmux"), ["cmux-send-without-enter"])

    def test_multiline_send_fires_only_for_newlines_inside_the_message(self):
        self.assertEqual(fired([user("x"), bash('cmux send --workspace workspace:5 "line one\nline two" && cmux send-key --workspace workspace:5 Enter')], "cmux"),
                         ["cmux-multiline-send"])
        self.assertEqual(fired([user("x"), bash('cmux send --workspace workspace:5 "one line" && cmux send-key --workspace workspace:5 Enter\necho done')], "cmux"), [])
        self.assertEqual(fired([user("x"), bash('MSG=$(cat <<\'EOF\'\na\nb\nEOF\n)\ncmux send --workspace workspace:5 "$MSG" && cmux send-key --workspace workspace:5 Enter')], "cmux"),
                         ["cmux-multiline-send"])

    def test_browser_substituted_ignores_heredoc_bodies(self):
        self.assertEqual(fired([user("show it in the cmux browser"), bash("cat > x.js <<'EOF'\nopen(1)\nEOF\ncmux browser open 'file:///x.html'")], "cmux"), [])

    def test_close_raw_and_helper(self):
        self.assertEqual(fired([user("x"), bash("cmux close-workspace --workspace workspace:5")], "cmux"), ["cmux-close-workspace-raw"])
        self.assertEqual(fired([user("x"), bash("~/.claude/skills/cmux/scripts/close-workspace.sh workspace:5")], "cmux"), [])

    def test_shared_checkout_spawn(self):
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/Repos/home" --prompt-file p.md')], "cmux"), ["spawn-shared-checkout"])
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/Repos/home/skills" --prompt-file p.md')], "cmux"), ["spawn-shared-checkout"])
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/Repos/home" --worktree --prompt-file p.md')], "cmux"), [])
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/my-skills" --prompt-file p.md')], "cmux"), ["spawn-shared-checkout"])
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/my-skills" --worktree --prompt-file p.md')], "cmux"), [])
        self.assertEqual(fired([user("x"), bash('spawn-workspace.sh "w" --cwd "$HOME/my-skills-wt/x" --prompt-file p.md')], "cmux"), [])

    def test_browser_substituted_needs_the_user_to_name_cmux(self):
        self.assertEqual(fired([user("open it in the cmux browser"), bash("open -a 'Google Chrome' /tmp/a.html")], "cmux"), ["cmux-browser-substituted"])
        self.assertEqual(fired([user("open it in the cmux browser"), bash("cmux browser open 'file:///tmp/a.html' --focus true")], "cmux"), [])
        self.assertEqual(fired([user("open it"), bash("open -a 'Google Chrome' /tmp/a.html")], "cmux"), [])

    def test_short_tail(self):
        self.assertEqual(fired([user("x"), bash("cmux read-screen --workspace workspace:5 | tail -25")], "cmux"), ["read-screen-short-tail"])
        self.assertEqual(fired([user("x"), bash("cmux read-screen --workspace workspace:5 | tail -40")], "cmux"), [])


class HandoffSignatureTests(unittest.TestCase):
    def test_clipboard_when_handoff_asked(self):
        self.assertEqual(fired([user("/handoff to a new workspace"), bash("cat <<'EOF' | pbcopy\nx\nEOF")], "handoff"), ["handoff-clipboard-not-spawn"])
        self.assertEqual(fired([user("/handoff park"), bash("cat <<'EOF' | pbcopy\nx\nEOF")], "handoff"), [])

    def test_tmp_file_then_spawn_is_clean(self):
        ev = [user("handoff please"), write("/tmp/handoff.md", "brief"), bash('spawn-workspace.sh "w" --prompt-file /tmp/handoff.md')]
        self.assertEqual(fired(ev, "handoff"), [])
        ev = [user("handoff please"), write("/tmp/handoff.md", "brief"), bash("ls")]
        self.assertEqual(fired(ev, "handoff"), ["handoff-clipboard-not-spawn"])

    def test_role_brief_without_skill_line(self):
        p = "/Users/x/agent-notes/Sessions/Handoffs/2026-08-30 seat.md"
        self.assertEqual(fired([user("write the successor brief"), write(p, "# Seat\n\nYou are the orchestrator. Do things.\n\nSuggested Skills: cmux")], "handoff"),
                         ["role-brief-without-skill-line"])
        self.assertEqual(fired([user("write the successor brief"), write(p, "**You are the orchestrator. Load the `orchestrator` skill before you touch the fleet.**")], "handoff"), [])

    def test_successor_spawn_with_tier(self):
        self.assertEqual(fired([user("spawn my successor"), bash('spawn-workspace.sh "w" --tier complex --prompt-file p.md')], "handoff"), ["successor-spawn-with-tier"])
        self.assertEqual(fired([user("spawn my successor"), bash('spawn-workspace.sh "w" --model claude-fable-5 --prompt-file p.md')], "handoff"), [])

    def test_brief_without_suggested_skills(self):
        p = "/Users/x/agent-notes/Sessions/Handoffs/2026-08-30 brief.md"
        self.assertEqual(fired([user("handoff"), write(p, "## Continue\n\nwork")], "handoff"), ["brief-without-suggested-skills"])
        self.assertEqual(fired([user("handoff"), write(p, "## Continue\n\n### Suggested Skills\n- cmux")], "handoff"), [])


class OrchestratorSignatureTests(unittest.TestCase):
    def _tool(self, name, inp, **extra):
        rec = {"k": "tool", "name": name, "input": inp, "ts": ""}
        rec.update(extra)
        return rec

    def _result(self, text):
        return {"k": "result", "t": text, "ts": ""}

    def test_disabled_model_id_detects_muse_spark_and_disabled_providers(self):
        ev_delegate_muse = [
            user("delegate coding work"),
            self._tool(
                "Agent",
                {"task": "fix bug", "target": {"providerInstanceId": "muse", "model": "muse-spark-1.3"}},
                raw_name="mcp_t3-code_delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_delegate_muse, "orchestrator"), ["orchestrator-disabled-model-id"])

        ev_delegate_claude = [
            user("delegate coding work"),
            self._tool(
                "Agent",
                {"task": "fix bug", "target": {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"}},
                raw_name="delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_delegate_claude, "orchestrator"), ["orchestrator-disabled-model-id"])

        ev_bash_spawn = [
            user("spawn worker"),
            bash('spawn-workspace.sh "w" --model muse-spark-1.3 --prompt-file p.md'),
        ]
        self.assertEqual(fired(ev_bash_spawn, "orchestrator"), ["orchestrator-disabled-model-id"])

        ev_clean_neon = [
            user("delegate coding work"),
            self._tool(
                "Agent",
                {"task": "fix bug", "isolation": "worktree", "target": {"providerInstanceId": "antigravity", "model": "gemini-4-neon"}},
                raw_name="mcp_t3-code_delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_clean_neon, "orchestrator"), [])

        ev_clean_cursor_grok = [
            user("delegate coding work"),
            self._tool(
                "Agent",
                {"task": "fix bug", "isolation": "worktree", "target": {"providerInstanceId": "cursor", "model": "grok-4.7"}},
                raw_name="delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_clean_cursor_grok, "orchestrator"), [])

        ev_clean_grep = [user("check catalog"), bash("rg -n 'muse-spark-1.3' skills/")]
        self.assertEqual(fired(ev_clean_grep, "orchestrator"), [])

        ev_clean_heredoc = [
            user("write note"),
            bash("cat > /tmp/note.md <<'EOF'\nspawn-workspace.sh --model muse-spark-1.3 --agent grok\nEOF"),
        ]
        self.assertEqual(fired(ev_clean_heredoc, "orchestrator"), [])

        ev_clean_issue_body = [
            user("open issue"),
            bash("BODY=$(cat <<'EOF'\nFix preflight.py.\nAlso block muse-spark-1.3.\nEOF\n)\ngh issue create --body \"$BODY\""),
        ]
        self.assertEqual(fired(ev_clean_issue_body, "orchestrator"), [])

    def test_pyyaml_import_error_detects_orchestrator_script_failures_only(self):
        ev_fail = [
            user("run preflight"),
            bash("/usr/bin/python3 skills/cross-cutting/model-routing/scripts/check.py --no-live"),
            self._result("Traceback (most recent call last):\nModuleNotFoundError: No module named 'yaml'"),
        ]
        self.assertEqual(fired(ev_fail, "orchestrator"), ["orchestrator-pyyaml-import-error"])

        ev_fail_b_route = [
            user("route coding"),
            bash("b route preflight --host t3 --category coding --json"),
            self._result("ImportError: No module named 'yaml'"),
        ]
        self.assertEqual(fired(ev_fail_b_route, "orchestrator"), ["orchestrator-pyyaml-import-error"])

        ev_clean = [
            user("run preflight"),
            bash("/usr/bin/python3 -I -S skills/cross-cutting/model-routing/scripts/check.py --no-live --no-log"),
            self._result("ok    structure: 11 categories verified\npython3 scripts/check.py: ok"),
        ]
        self.assertEqual(fired(ev_clean, "orchestrator"), [])

        ev_unrelated_script = [
            user("run random script"),
            bash("/usr/bin/python3 -c 'import yaml'"),
            self._result("ModuleNotFoundError: No module named 'yaml'"),
        ]
        self.assertEqual(fired(ev_unrelated_script, "orchestrator"), [])

        ev_other_repo_check = [
            user("run site check"),
            bash("/usr/bin/python3 ~/Repos/cupofrecord/scripts/check.py"),
            self._result("ModuleNotFoundError: No module named 'yaml'"),
        ]
        self.assertEqual(fired(ev_other_repo_check, "orchestrator"), [])

    def test_linked_env_worktree_detects_worktree_with_environment_id(self):
        ev_bad = [
            user("delegate to mac mini"),
            self._tool(
                "Agent",
                {
                    "task": "check logs",
                    "isolation": "worktree",
                    "target": {"providerInstanceId": "antigravity", "model": "gemini-4-neon", "environmentId": "env-mac-mini"},
                },
                raw_name="mcp_t3-code_delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_bad, "orchestrator"), ["orchestrator-linked-env-worktree"])

        ev_bad_acp = [
            user("delegate via acp"),
            bash(
                "acp-mcp-call delegate_task "
                '\'{"task":"check","isolation":"worktree","target":{"providerInstanceId":"codex","model":"gpt-6.2-sol","environmentId":"env-1"}}\''
            ),
        ]
        self.assertEqual(fired(ev_bad_acp, "orchestrator"), ["orchestrator-linked-env-worktree"])

        ev_good_shared = [
            user("delegate to mac mini"),
            self._tool(
                "Agent",
                {
                    "task": "check logs",
                    "isolation": "shared",
                    "target": {"providerInstanceId": "antigravity", "model": "gemini-4-neon", "environmentId": "env-mac-mini"},
                },
                raw_name="mcp_t3-code_delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_good_shared, "orchestrator"), [])

        ev_good_local_worktree = [
            user("delegate locally"),
            self._tool(
                "Agent",
                {
                    "task": "implement feature",
                    "isolation": "worktree",
                    "target": {"providerInstanceId": "antigravity", "model": "gemini-4-neon"},
                },
                raw_name="mcp_t3-code_delegate_task",
            ),
        ]
        self.assertEqual(fired(ev_good_local_worktree, "orchestrator"), [])

    def test_native_subagent_boundary_detects_antigravity_t3_and_outside_home(self):
        ev_agy_t3 = [
            user("inspect repo"),
            self._tool(
                "Agent",
                {"Prompt": "read skills/README.md", "Role": "Researcher"},
                raw_name="invoke_subagent",
                harness="antigravity",
                host="t3-code",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev_agy_t3, "orchestrator"), ["orchestrator-native-subagent-boundary"])

        ev_agent_outside_home = [
            user("audit website"),
            self._tool(
                "Agent",
                {"prompt": "inspect src/pages/index.astro"},
                raw_name="Agent",
                cwd="/Users/dev/Repos/site-repo",
            ),
        ]
        self.assertEqual(fired(ev_agent_outside_home, "orchestrator"), ["orchestrator-native-subagent-boundary"])

        ev_spawn_outside_home = [
            user("review DAS notes"),
            self._tool(
                "spawn_agent",
                {"message": "audit ~/Vaults/Ops/plan.md"},
                raw_name="spawn_agent",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev_spawn_outside_home, "orchestrator"), ["orchestrator-native-subagent-boundary"])

        ev_clean_delegate_outside = [
            user("audit website"),
            self._tool(
                "Agent",
                {
                    "task": "audit ~/Repos/site-repo",
                    "isolation": "worktree",
                    "target": {"providerInstanceId": "antigravity", "model": "gemini-4-neon"},
                },
                raw_name="mcp_t3-code_delegate_task",
                harness="antigravity",
                host="t3-code",
                cwd="/Users/dev/Repos/site-repo",
            ),
        ]
        self.assertEqual(fired(ev_clean_delegate_outside, "orchestrator"), [])

        ev_clean_claude_inside_home = [
            user("inspect skills"),
            self._tool(
                "Agent",
                {"prompt": "read ~/Repos/home/skills/README.md"},
                raw_name="Agent",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev_clean_claude_inside_home, "orchestrator"), [])

        ev_clean_codex_inside_home = [
            user("run tests"),
            self._tool(
                "spawn_agent",
                {"message": "check skills/scripts/ci_fast_checks.py"},
                raw_name="spawn_agent",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev_clean_codex_inside_home, "orchestrator"), [])

        for bad_cwd in (
            "/tmp/client-repo",
            "~/Documents/client",
            "/Users/dev/my-skills/not-home",
            "/Users/dev/.t3/worktrees/home/t3-abc123",
        ):
            ev_bad_cwd = [
                user("run helper"),
                self._tool("Agent", {"prompt": "inspect files"}, raw_name="Agent", cwd=bad_cwd),
            ]
            self.assertEqual(fired(ev_bad_cwd, "orchestrator"), ["orchestrator-native-subagent-boundary"], bad_cwd)

        ev_non_t3_delegate_mention = [
            user("please do not call delegate_task in this standalone IDE session"),
            self._tool(
                "Agent",
                {"Prompt": "read ~/Repos/home/AGENTS.md", "Role": "Researcher"},
                raw_name="invoke_subagent",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev_non_t3_delegate_mention, "orchestrator"), [])

    def test_agent_prompt_with_cmux_text_does_not_fire_cmux_signatures(self):
        ev = [
            user("ask helper to explain cmux"),
            self._tool(
                "Agent",
                {"prompt": 'Explain why cmux send workspace:5 "hi" fails'},
                raw_name="Agent",
                cwd="/Users/dev/Repos/home",
            ),
        ]
        self.assertEqual(fired(ev, "cmux"), [])

    def test_prefilter_candidate_files_finds_claude_agent_only_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "proj"
            proj.mkdir()
            tpath = proj / "claude-agent-only.jsonl"
            rows = [
                {"type": "user", "timestamp": "2026-11-28T00:00:00Z", "cwd": "/Users/dev/Repos/site-repo", "message": {"role": "user", "content": "audit website"}},
                {"type": "assistant", "timestamp": "2026-11-28T00:00:01Z", "cwd": "/Users/dev/Repos/site-repo", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Agent", "input": {"prompt": "inspect src/pages/index.astro"}}
                ]}},
            ]
            tpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            found = F.candidate_files(proj, "orchestrator", source_list="claude")
            self.assertEqual(found, [tpath])
            self.assertEqual(fired(F.events(tpath), "orchestrator"), ["orchestrator-native-subagent-boundary"])

    def test_end_to_end_antigravity_t3_jsonl_parse_fires_native_invoke_subagent(self):
        with tempfile.TemporaryDirectory() as d:
            log_dir = Path(d) / ".t3/userdata/providers/antigravity/p1/antigravity-acp/brain/s1/.system_generated/logs"
            log_dir.mkdir(parents=True)
            tpath = log_dir / "transcript.jsonl"
            rows = [
                {
                    "step_index": 0,
                    "type": "USER_INPUT",
                    "created_at": "2026-11-28T00:00:00Z",
                    "content": "<USER_REQUEST><t3_code_instructions>rules</t3_code_instructions><user_request>check repo</user_request></USER_REQUEST>",
                },
                {
                    "step_index": 1,
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-28T00:00:02Z",
                    "content": "Delegating.",
                    "tool_calls": [
                        {"name": "invoke_subagent", "args": {"Role": "Researcher", "Prompt": "check ~/Repos/home/AGENTS.md"}},
                    ],
                },
            ]
            tpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            ev = F.events(tpath)
            self.assertEqual(fired(ev, "orchestrator"), ["orchestrator-native-subagent-boundary"])


class EventTests(unittest.TestCase):
    def test_events_parse_raw_and_stream_shapes(self):
        rows = [
            {"type": "user", "timestamp": "2026-08-30T01:00:00Z", "message": {"role": "user", "content": "<command-name>/handoff</command-name><command-args>to a new workspace</command-args>"}},
            {"type": "assistant", "timestamp": "2026-08-30T01:00:01Z", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "On it."}, {"type": "tool_use", "name": "Bash", "input": {"command": "echo hi"}}]}},
            {"type": "user", "timestamp": "2026-08-30T01:00:02Z", "message": {"role": "user", "content": [{"type": "tool_result", "content": "hi"}]}},
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows))
            ev = F.events(p)
        self.assertEqual([e["k"] for e in ev], ["user", "text", "tool", "result"])
        self.assertEqual(ev[0]["t"], "/handoff to a new workspace")

    def test_render_window_keeps_commands(self):
        ev = [user("go"), bash("cmux send --workspace workspace:5 'x'"), {"k": "result", "t": "OK surface:1 workspace:5", "ts": ""}]
        text = F.render_events(ev, 0, 3)
        self.assertIn("TOOL Bash: cmux send --workspace workspace:5", text)
        self.assertIn("RESULT: OK surface:1", text)


class HoldoutAndScoreTests(unittest.TestCase):
    def test_holdout_is_seeded_one_per_session_round_robin(self):
        hits = [{"session_id": f"s{i}", "signature": "a" if i % 2 else "b", "trigger": 0} for i in range(10)]
        hits.append({"session_id": "s1", "signature": "b", "trigger": 0})
        x = F.choose_holdout(hits, 4, 7)
        y = F.choose_holdout(hits, 4, 7)
        self.assertEqual([h["session_id"] for h in x], [h["session_id"] for h in y])
        self.assertEqual(len({h["session_id"] for h in x}), 4)
        self.assertEqual(sorted(h["signature"] for h in x), ["a", "a", "b", "b"])

    def test_score_counts_passes_and_hard_failures(self):
        res = [{"pass": True, "other": [], "attempted": True}, {"pass": False, "other": ["z"], "attempted": True},
               {"pass": False, "other": [], "attempted": False}]
        self.assertEqual(F.print_score(res), (1, 1))


class ReplayTests(unittest.TestCase):
    def test_replay_settings_keep_the_mutating_tools_visible(self):
        st = F.replay_settings()
        for tool in F.REFUSED:
            self.assertNotIn(tool, st["permissions"]["deny"])
            self.assertIn(tool, st["hooks"]["PreToolUse"][0]["matcher"].split("|"))
        self.assertEqual(st["permissions"]["deny"], F.HIDDEN)
        self.assertIn("exit 2", st["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(F.SETTING_SOURCES, "")

    def test_judge_reads_a_refused_call_and_ignores_the_exit_code(self):
        rows = [
            {"type": "system", "subtype": "init", "tools": ["Bash", "Read"]},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": 'cmux send --workspace workspace:5 "hi" && cmux send-key --workspace workspace:5 Enter'}}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True, "content": "PreToolUse:Bash hook error: Refused"}]}},
            {"type": "system", "subtype": "permission_denied", "tool_name": "Bash", "message": "a string, not a dict"},
            {"type": "result", "subtype": "error_max_turns", "num_turns": 12, "permission_denials": [{"tool_name": "Bash"}]},
        ]
        item = {"id": "x-cmux-send-without-enter", "signature": "cmux-send-without-enter", "trigger": "relay it"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.stream.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows))
            r = F.judge_replay(item, p, "cmux", 1)
            self.assertTrue(r["attempted"] and not r["fired"] and r["pass"])
            self.assertEqual((r["result"], r["turns"], r["exit"]), ("error_max_turns", 12, 1))
            self.assertEqual((r["other"], r["advisory"]), ([], []))
            rows.insert(2, {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "cmux read-screen --workspace workspace:5 | tail -20"}}]}})
            p.write_text("\n".join(json.dumps(r) for r in rows))
            r = F.judge_replay(item, p, "cmux", 1)
            self.assertEqual((r["other"], r["advisory"], r["pass"]), ([], ["read-screen-short-tail"], True))
            p.write_text("\n".join(json.dumps(r) for r in rows[:-1]))
            self.assertFalse(F.judge_replay(item, p, "cmux", 1)["pass"])

    def test_judge_seeds_the_trigger_for_detectors_that_read_the_user_message(self):
        rows = [
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "cat <<'EOF' | pbcopy\n## Continue\nEOF"}}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True, "content": "Refused"}]}},
            {"type": "result", "subtype": "success", "num_turns": 2},
        ]
        item = {"id": "x-role-brief-without-skill-line", "signature": "role-brief-without-skill-line", "trigger": "commit then handoff i guess"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.stream.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows))
            r = F.judge_replay(item, p, "handoff", 0)
            self.assertEqual((r["attempted"], r["other"]), (False, ["handoff-clipboard-not-spawn"]))

    def test_multi_harness_replay_hooks_record_and_refuse_and_judge_scores_them(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            for harness in ("agy", "codex", "grok"):
                cmd, workdir, env, stdin_text, calls_log = F.build_replay_invocation(
                    harness, f"item-{harness}", "prompt body", "system skill", out, [str(out)],
                )
                self.assertTrue(len(cmd) >= 3)
                hook_script = workdir / "refuse-hook.py"
                self.assertTrue(hook_script.is_file())
                if harness == "agy":
                    self.assertTrue((workdir / ".agents/hooks.json").is_file())
                    payload = json.dumps({"toolCall": {"name": "run_command", "args": {
                        "CommandLine": 'cmux send --workspace workspace:5 "hi" && cmux send-key --workspace workspace:5 Enter'}}})
                    proc = subprocess.run([str(hook_script)], input=payload, capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(json.loads(proc.stdout)["decision"], "deny")
                    stream = out / f"item-{harness}.stream.jsonl"
                    stream.write_text(json.dumps({"event": "result", "result": {"status": "DONE", "num_turns": 2}}) + "\n")
                else:
                    payload = json.dumps({"tool_name": "Bash", "tool_input": {
                        "command": 'cmux send --workspace workspace:5 "hi" && cmux send-key --workspace workspace:5 Enter'}})
                    proc = subprocess.run([str(hook_script)], input=payload, capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn("Refused:", proc.stderr)
                    stream = out / f"item-{harness}.stream.jsonl"
                    done_rec = {"type": "turn.completed"} if harness == "codex" else {"type": "turn_completed", "num_turns": 2}
                    stream.write_text(json.dumps(done_rec) + "\n")
                item = {"id": f"item-{harness}", "signature": "cmux-send-without-enter", "trigger": "relay it"}
                r = F.judge_replay(item, stream, "cmux", 0, calls_log=calls_log)
                self.assertTrue(r["attempted"] and not r["fired"] and r["pass"], f"{harness}: {r}")

            err_stream = out / "err.stream.jsonl"
            err_stream.write_text(json.dumps({"event": "result", "result": {"status": "ERROR", "error": "auth"}}) + "\n")
            self.assertIsNone(F.result_record(err_stream))


if __name__ == "__main__":
    unittest.main()
