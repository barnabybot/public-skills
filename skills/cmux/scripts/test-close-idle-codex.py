#!/usr/bin/env python3

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("close-workspace.sh")
WORKSPACE = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
WINDOW = "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB"
SURFACE = "CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC"
PANE = "EEEEEEEE-EEEE-EEEE-EEEE-EEEEEEEEEEEE"
OTHER = "DDDDDDDD-DDDD-DDDD-DDDD-DDDDDDDDDDDD"
REF = "workspace:8"
NAME = "Offline fixture - finished Codex"
IDLE = "Final response.\n\n  Worked for 2m 1s • 12:31\n\n›\n\n  GPT-6.1-Sol max · 828K window · Context 4% used · ~\n"
NATIVE_IDLE = (
    " \n"
    "• Ran cmux read-screen --workspace workspace:1000010112 --lines 14\n"
    "  └\n"
    "      GPT-6.1-Sol max · 828K window · Context 12% used · ~\n"
    "      ? for shortcuts                                                                                                                                                                                                                          ⚠ 1 warning · f2 to …\n"
    "    + 12 lines (⌃t to expand)                                                                                                                                                                                                                                       \n"
    " \n"
    "• Ran python3 - <<'PY' …\n"
    "  └ Linked successor boot verified; own ended Outcome and dispatch review saved. Underlying R146/T8 goal remains incomplete and active in Codex23.\n"
    "    + Show details                                                                                                                                                                                                                                                  \n"
    " \n"
    "• Codex23 (workspace:1000010112) has accepted takeover. It will update the graph with completed work, challenges, owners and next actions, then continue acceptance.\n"
    " \n"
    "  Current gaps: matrix last observed at 40/90, unresolved report path and two retained test failures. Cleanup worker111 is fixing idle CLI retirement; Codex19–21 are closed.\n"
    " \n"
    "  This seat exceeded the orchestrator skill’s (Skills/cross-cutting/orchestrator/SKILL.md) “30% of its window” limit. The complete handoff preserves all remaining obligations.\n"
    " \n"
    "  Worked for 35m 49s • 13:04                                                                                                                                                                                                                                        \n"
    "\n"
    " \n"
    "› Ask Codex to do anything\n"
    " \n"
    "  GPT-6.1-Sol max · 828K window · Context 9% used · ~\n"
    "  ? for shortcuts                                                                                                                                                                                                                          ⚠ 1 warning · f2 to view\n"
)

STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

p = Path(os.environ["CMUX_FIXTURE_STATE"])
s = json.loads(p.read_text())
args = sys.argv[1:]
s["calls"].append(args)
as_json = "--json" in args
if as_json:
    args = args[3:]
command = args[0]
rc = 0
out = ""
if command == "list-windows":
    if s.get("list_failure"):
        rc, out = 1, "Offline fixture listing failed"
    else:
        windows = [{"id": s["window"]}]
        if s.get("other_window"):
            windows.insert(0, {"id": s["other"]})
        out = json.dumps(windows)
elif command == "list-workspaces":
    entries = []
    correct_window = "--window" not in args or args[args.index("--window") + 1] == s["window"]
    if s["present"] and correct_window:
        entries.append({"id": s["uuid"], "ref": s["ref"], "title": s["name"]})
    if s.get("duplicate"):
        entries += entries
    if as_json:
        out = json.dumps({"window_id": s["window"], "workspaces": entries})
    else:
        out = "\n".join("  " + e["ref"] + "  " + e["title"] for e in entries)
elif command == "list-panes":
    panes = [{"id": s["pane"], "surface_ids": [s["surface"]]}]
    if s.get("empty_global_dock"):
        panes.append({"id": s["other"], "dock_scope": "global", "surface_count": 0, "surface_ids": []})
    if s.get("extra_pane"):
        panes.append({"id": s["other"], "surface_ids": [s["other"]]})
    out = json.dumps({"workspace_id": s["uuid"], "panes": panes})
elif command == "list-pane-surfaces":
    surfaces = [{"id": s["surface"], "type": s.get("type", "terminal")}]
    if s.get("extra_surface"):
        surfaces.append({"id": s["other"], "type": "terminal"})
    out = json.dumps({"workspace_id": s["uuid"], "pane_id": s["pane"], "surfaces": surfaces})
elif command == "read-screen":
    s["reads"] += 1
    out = s.get("second_screen", s["screen"]) if s["reads"] > 1 else s["screen"]
    if s.get("disappear_on_read"):
        s["present"] = False
        rc, out = 1, "Workspace disappeared before screen read"
    if s.get("rebind_after_read"):
        s["uuid"] = s["other"]
    if s.get("surface_after_read"):
        s["surface"] = s["other"]
    if s.get("rename_after_read"):
        s["name"] = "Offline fixture - resumed work"
    if s.get("note_after_read") and s["reads"] == s.get("change_note_at_read", 1):
        Path(s["note"]).write_text(s["note_after_read"])
elif command == "send-key":
    expected = ["send-key", "--workspace", s["uuid"], "--surface", s["surface"], "ctrl+d"]
    if args != expected:
        rc, out = 1, "Wrong stable key target"
    elif s.get("key_failure"):
        rc, out = 1, "Offline fixture key failed"
    else:
        s["exited"] = True
        if s.get("auto_disappear"):
            s["present"] = False
        out = "OK surface:9 workspace:8"
elif command == "close-workspace":
    s["closes"] += 1
    if s["present"] and (not s["exited"] or s.get("still_running") or s["closes"] <= s.get("close_confirmations", 0)):
        rc, out = 1, "Error: confirmation_required: Workspace has a running process; retry with --force"
    else:
        s["present"] = False
        out = "OK"
else:
    rc, out = 1, "Unsupported offline fixture command"
p.write_text(json.dumps(s))
print(out, file=sys.stderr if rc else sys.stdout)
sys.exit(rc)
'''


class IdleCodexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cmux-idle-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        stub = self.bin / "cmux"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.note = self.root / "finished.md"
        self.handoff = self.root / "handoff.md"
        self.handoff.write_text("# Handoff\nKeep the exact successor instructions.\n")
        self.note.write_text(
            f'---\nagent: codex\nstatus: done\nended: 2026-01-01\n'
            f'workspace_id: "{REF}"\nworkspace_name: "{NAME}"\n---\n'
            f'\n## Outcome\nSuccessor [brief]({self.handoff}).\n'
        )
        self.state = self.root / "state.json"
        self.state.write_text(json.dumps({
            "uuid": WORKSPACE, "window": WINDOW, "surface": SURFACE,
            "other": OTHER, "pane": PANE, "ref": REF, "name": NAME, "present": True,
            "screen": IDLE, "calls": [], "reads": 0, "closes": 0, "exited": False,
            "note": str(self.note),
        }))
        self.write_hook()
        self.result = None

    def configure(self, **changes):
        state = json.loads(self.state.read_text())
        state.update(changes)
        self.state.write_text(json.dumps(state))

    def run_helper(self, uuid=WORKSPACE, note=None, extra=()):
        self.before_note = self.note.read_bytes()
        self.before_handoff = self.handoff.read_bytes()
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   CMUX_FIXTURE_STATE=str(self.state), CMUX_SESSIONS_DIR=str(self.root),
                   CMUX_AGENT_HOOK_STATE_DIR=str(self.root / "hooks"))
        self.result = subprocess.run(
            ["bash", str(SCRIPT), REF, "--exit-idle-codex", uuid,
             str(note or self.note), *extra],
            env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(self.handoff.read_bytes(), self.before_handoff)
        self.assertTrue(self.handoff.exists())
        return json.loads(self.state.read_text())

    def retained(self, **changes):
        self.configure(**changes)
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertEqual(self.mutations(state), [])
        self.assertIn("Retained", self.result.stdout + self.result.stderr)

    @staticmethod
    def mutations(state):
        return [call for call in state["calls"] if call[0] in ("send-key", "close-workspace")]

    def tearDown(self):
        if self.result is not None and os.environ.get("CMUX_FIXTURE_EVIDENCE"):
            with Path(os.environ["CMUX_FIXTURE_EVIDENCE"]).open("a") as f:
                f.write(json.dumps({
                    "test": self.id(), "offline_fixture": True,
                    "returncode": self.result.returncode,
                    "stdout": self.result.stdout, "stderr": self.result.stderr,
                    "state": json.loads(self.state.read_text()),
                    "note_before": self.before_note.decode(),
                    "note_after": self.note.read_text(),
                    "handoff_preserved": self.handoff.read_bytes() == self.before_handoff,
                }) + "\n")

    def test_verified_idle_codex_retires_and_preserves_records(self):
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertEqual(self.mutations(state), [
            ["send-key", "--workspace", WORKSPACE, "--surface", SURFACE, "ctrl+d"],
            ["close-workspace", "--workspace", WORKSPACE],
        ])
        self.assertIn("absent from all windows", self.result.stdout)

    def test_normal_exit_can_remove_workspace_automatically(self):
        self.configure(auto_disappear=True)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertEqual(len(self.mutations(state)), 1)
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_original_actual_screen_retires_and_preserves_records(self):
        self.configure(screen=NATIVE_IDLE)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_native_working_screen_is_retained(self):
        self.retained(screen=NATIVE_IDLE.replace("Worked for 35m 49s • 13:04", "Working (esc to interrupt)"))

    def test_old_worked_line_above_active_turn_is_retained(self):
        self.retained(screen=NATIVE_IDLE.replace("\n› Ask Codex", "\n• Working (esc to interrupt)\n› Ask Codex"))

    def test_native_draft_composer_is_retained(self):
        self.retained(screen=NATIVE_IDLE.replace("› Ask Codex to do anything", "› Resume the unfinished write"))

    def test_shutdown_screen_is_retained(self):
        self.retained(screen=NATIVE_IDLE.replace("› Ask Codex to do anything", "› Shutting down..."))

    def test_unknown_status_row_does_not_block_an_idle_lifecycle(self):
        self.configure(screen=NATIVE_IDLE + "\nUnrecognised live status\n")
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_active_status_on_worked_row_is_retained(self):
        self.retained(screen=NATIVE_IDLE.replace("Worked for 35m 49s • 13:04", "Worked for 35m 49s • 13:04 • Working"))

    def test_renamed_model_line_still_retires_on_idle_lifecycle(self):
        self.configure(screen=NATIVE_IDLE.replace(
            "GPT-6.1-Sol max · 828K window · Context 9% used · ~",
            "Codex-Sol Working with Context unknown",
        ))
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_repeated_call_after_automatic_absence_preserves_records(self):
        self.configure(screen=NATIVE_IDLE, auto_disappear=True)
        first = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(first["present"])
        self.assertEqual(len(self.mutations(first)), 1)
        second = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(second["present"])
        self.assertEqual(self.mutations(second), self.mutations(first))
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertIn("Already absent", self.result.stdout)

    def test_active_work_is_retained(self):
        self.retained(screen=IDLE.replace("›\n", "• Running a tool (esc to interrupt)\n›\n"))

    def test_draft_composer_is_retained(self):
        self.retained(screen=IDLE.replace("›\n", "› Continue the work\n"))

    def test_completion_claim_without_hook_signal_is_retained(self):
        hook = self.root / "hooks" / "codex-hook-sessions.json"
        hook.unlink()
        self.configure(screen="Final response says done.\n›\n")
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertIn("no-signal", self.result.stderr)
        self.assertEqual(self.mutations(state), [])

    def test_activity_after_first_read_is_retained(self):
        self.retained(second_screen=IDLE.replace("›\n", "› New queued instruction\n"))

    def test_uuid_mismatch_is_retained(self):
        self.retained(uuid=OTHER)

    def test_reused_reference_after_read_is_retained(self):
        self.retained(rebind_after_read=True)

    def test_renamed_workspace_after_read_is_retained(self):
        self.retained(rename_after_read=True)

    def test_surface_replacement_is_retained(self):
        self.retained(surface_after_read=True)

    def test_duplicate_identity_is_retained(self):
        self.retained(duplicate=True)

    def test_multiple_surfaces_are_retained(self):
        self.retained(extra_surface=True)

    def test_hidden_split_pane_is_retained(self):
        self.retained(extra_pane=True)

    def test_empty_global_dock_pane_does_not_block_retirement(self):
        self.configure(empty_global_dock=True)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_browser_surface_is_retained(self):
        self.retained(type="browser")

    def test_failed_inventory_does_not_prove_absence(self):
        self.retained(list_failure=True)

    def test_wrong_note_name_is_retained(self):
        self.note.write_text(self.note.read_text().replace(NAME, "Previous seat"))
        self.retained()

    def test_wrong_note_ref_is_retained(self):
        self.note.write_text(self.note.read_text().replace(REF, "workspace:7"))
        self.retained()

    def test_open_note_is_retained(self):
        self.note.write_text(self.note.read_text().replace("status: done", "status: in-progress")
                             .replace("ended: 2026-01-01\n", ""))
        self.retained()

    def test_completion_metadata_in_body_is_insufficient(self):
        self.note.write_text(self.note.read_text().replace("status: done", "status: review")
                             .replace("ended: 2026-01-01\n", "") + "\nended: 2026-01-01\n")
        self.retained()

    def test_other_agent_note_is_retained(self):
        self.note.write_text(self.note.read_text().replace("agent: codex", "agent: claude-code"))
        self.retained()

    def test_failed_note_is_preserved(self):
        self.note.write_text(self.note.read_text().replace("status: done", "status: failed")
                             .replace("ended: 2026-01-01\n", ""))
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_ended_review_note_is_preserved(self):
        self.note.write_text(self.note.read_text().replace("status: done", "status: review"))
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_changed_note_after_final_read_is_retained(self):
        changed_note = self.note.read_text() + "\nResumed by its owner.\n"
        self.configure(note_after_read=changed_note, change_note_at_read=2)
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertEqual(self.mutations(state), [])
        self.assertEqual(self.note.read_text(), changed_note)

    def test_duplicate_note_identity_is_retained(self):
        self.note.write_text(self.note.read_text().replace("---\n\n##", f'workspace_id: "{REF}"\n---\n\n##'))
        self.retained()

    def test_other_window_is_checked_and_retired(self):
        self.configure(other_window=True)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        windows = {call[-1] for call in state["calls"] if "list-workspaces" in call}
        self.assertEqual(windows, {WINDOW, OTHER})

    def test_normal_close_waits_for_shutdown(self):
        self.configure(close_confirmations=2)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_uuid_still_live_after_exit_is_pending(self):
        self.configure(still_running=True, screen=NATIVE_IDLE)
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertIn("UUID remains live", self.result.stderr)
        self.assertTrue(all("--force" not in call for call in state["calls"]))

    def test_key_failure_preserves_pending_workspace(self):
        self.configure(key_failure=True)
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertEqual(self.mutations(state), [
            ["send-key", "--workspace", WORKSPACE, "--surface", SURFACE, "ctrl+d"],
        ])

    def test_already_absent_workspace_is_idempotent(self):
        self.configure(present=False)
        for _ in range(2):
            state = self.run_helper()
            self.assertEqual(self.result.returncode, 0, self.result.stderr)
            self.assertFalse(state["present"])
            self.assertEqual(self.mutations(state), [])
            self.assertEqual(self.note.read_bytes(), self.before_note)
            self.assertIn("Already absent", self.result.stdout)

    def test_disappearance_during_screen_read_has_no_stale_action(self):
        self.configure(disappear_on_read=True)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertFalse(state["present"])
        self.assertEqual(self.mutations(state), [])
        self.assertEqual(self.note.read_bytes(), self.before_note)
        self.assertIn("disappeared", self.result.stdout + self.result.stderr)

    def test_invalid_uuid_is_refused_before_action(self):
        state = self.run_helper(uuid="workspace:8")
        self.assertNotEqual(self.result.returncode, 0)
        self.assertEqual(self.mutations(state), [])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_force_flag_is_refused(self):
        state = self.run_helper(extra=("--force",))
        self.assertNotEqual(self.result.returncode, 0)
        self.assertEqual(self.mutations(state), [])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def write_hook(self, lifecycle="idle", surface=SURFACE, **extra):
        folder = self.root / "hooks"
        folder.mkdir(exist_ok=True)
        row = {
            "sessionId": "codex-session",
            "workspaceId": WORKSPACE,
            "surfaceId": surface,
            "agentLifecycle": lifecycle,
            "runtimeStatus": "idle" if lifecycle == "idle" else "running",
            "activePromptDepth": 0,
            "hadPendingBackgroundWorkAtStop": False,
            "updatedAt": 1,
        }
        row.update(extra)
        (folder / "codex-hook-sessions.json").write_text(json.dumps({
            "version": 1,
            "sessions": {row["sessionId"]: row},
        }))

    def test_reordered_footer_retires_when_lifecycle_is_idle(self):
        self.write_hook()
        reordered = (
            "Final response.\n\n"
            "  GPT-6.1-Sol max · 828K window · Context 4% used · ~\n\n"
            "  Worked for 2m 1s • 12:31\n\n"
            "›\n"
        )
        self.configure(screen=reordered)
        state = self.run_helper()
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertFalse(state["present"])
        self.assertTrue(state["exited"])
        self.assertEqual(self.note.read_bytes(), self.before_note)

    def test_idle_screen_without_hook_signal_is_retained(self):
        hook = self.root / "hooks" / "codex-hook-sessions.json"
        if hook.exists():
            hook.unlink()
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertIn("no-signal", self.result.stderr)
        self.assertEqual(self.mutations(state), [])

    def test_running_lifecycle_retains_idle_screen(self):
        self.write_hook(lifecycle="running")
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertIn("active", self.result.stderr)
        self.assertEqual(self.mutations(state), [])

    def test_missing_composer_is_grammar_break(self):
        self.write_hook()
        screen = (
            "Final response.\n\n"
            "  Worked for 2m 1s • 12:31\n\n"
            "  GPT-6.1-Sol max · 828K window · Context 4% used · ~\n\n"
            "  renamed status row\n\n"
            "  another status row\n\n"
            "  third status row\n\n"
            "  fourth status row\n\n"
            "  fifth status row\n\n"
            "  sixth status row\n"
        )
        self.configure(screen=screen)
        state = self.run_helper()
        self.assertNotEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertTrue(state["present"])
        self.assertFalse(state["exited"])
        self.assertIn("grammar-break", self.result.stderr)
        self.assertEqual(self.mutations(state), [])

    def test_shell_does_not_embed_footer_chrome(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("Ask Codex", text)
        self.assertNotIn("Worked for", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
