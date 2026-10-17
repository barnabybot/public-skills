#!/usr/bin/env python3
"""Fixture tests for retire_predecessors.py.

Run: python3 cross-cutting/orchestrator/scripts/test_retire_predecessors.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import retire_predecessors

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "retire_predecessors.py"
CASES = HERE / "fixtures" / "succession"
REPO = HERE.parents[2]
HELPER_LABEL = f"{HERE.parents[1].name}/cmux/scripts/close-workspace.sh"
NOTE = "sessions/2026-10-16-fleet-coordinator.md"
SEAT = "22222222-2222-4222-8222-222222222222"
LIVE = "33333333-3333-4333-8333-333333333333"
WINDOW = "11111111-1111-4111-8111-111111111111"


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def load(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def legacy_ref_or_similar_title(case: dict) -> dict | None:
    """The match these fixtures retire: a reused ref, or a similar title."""
    predecessor = case["predecessors"][0]
    for row in case["workspaces"]:
        if row.get("ref") == predecessor.get("ref"):
            return row
    recorded = predecessor["name"].casefold()
    for row in case["workspaces"]:
        title = row["title"].casefold()
        if recorded != title and (recorded in title or title in recorded):
            return row
    return None


def write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class RetirePredecessorTests(unittest.TestCase):
    def test_help_names_the_command_and_the_flags(self):
        proc = run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("retire", proc.stdout)
        self.assertIn("--json", proc.stdout)
        self.assertIn("--dry-run", proc.stdout)
        self.assertIn("close-workspace.sh", proc.stdout)
        self.assertIn("UUID", proc.stdout)

    def test_reused_ref_fixture_would_close_under_the_old_match(self):
        case = load("reused-ref.json")
        hit = legacy_ref_or_similar_title(case)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["ref"], "workspace:4")
        self.assertEqual(hit["title"], "intake-worker")
        self.assertNotEqual(hit["id"], case["predecessors"][0]["uuid"])

    def test_reused_ref_is_already_absent_and_leaves_the_new_seat(self):
        path = CASES / "reused-ref.json"
        before = path.read_text(encoding="utf-8")
        proc = run("retire", str(path), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["cmux_calls"], 0)
        self.assertIsNone(payload["helper"])
        row = payload["results"][0]
        self.assertEqual(row["record"], "already-absent")
        self.assertIsNone(row["ref"])
        self.assertIn("absent from every live window", row["reason"])
        self.assertIn("workspace:4", row["reason"])
        self.assertIn("was not closed", row["reason"])
        self.assertNotIn("planned close", proc.stdout)
        self.assertNotIn("close-workspace.sh", proc.stdout)
        self.assertEqual(row["note_action"], "reconcile")
        self.assertIn("status: done", row["note_body"])
        self.assertIn("ended: 2026-10-16", row["note_body"])
        self.assertIn("Stopped at the outgoing handoff.", row["note_body"])
        self.assertIn("Successor: sessions/2026-10-16-successor.md", row["note_body"])

    def test_similar_title_fixture_would_close_under_the_old_match(self):
        case = load("similar-title-only.json")
        hit = legacy_ref_or_similar_title(case)
        self.assertEqual(hit["title"], "fleet-coordinator north")
        self.assertEqual(hit["id"], case["predecessors"][0]["uuid"])

    def test_similar_title_alone_is_retained(self):
        proc = run("retire", str(CASES / "similar-title-only.json"), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        row = json.loads(proc.stdout)["results"][0]
        self.assertEqual(row["record"], "retained")
        self.assertIsNone(row["ref"])
        self.assertIn("fleet-coordinator north", row["reason"])
        self.assertIn("fleet-coordinator", row["reason"])
        self.assertIsNone(row["note_action"])
        self.assertNotIn("close-workspace.sh", proc.stdout)

    def test_missing_uuid_legacy_fixture_would_close_on_the_ref(self):
        case = load("missing-uuid-legacy.json")
        self.assertIsNone(case["predecessors"][0]["uuid"])
        hit = legacy_ref_or_similar_title(case)
        self.assertEqual(hit["ref"], "workspace:4")
        self.assertEqual(hit["title"], "fleet-coordinator")

    def test_missing_uuid_without_the_outgoing_screen_is_retained(self):
        proc = run("retire", str(CASES / "missing-uuid-legacy.json"), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        row = json.loads(proc.stdout)["results"][0]
        self.assertEqual(row["record"], "retained")
        self.assertIsNone(row["uuid"])
        self.assertIsNone(row["ref"])
        self.assertIsNone(row["recovered_uuid"])
        self.assertIn("no workspace UUID", row["reason"])
        self.assertIn("outgoing handoff", row["reason"])

    def test_legacy_handoff_recovers_the_uuid_when_note_and_screen_agree(self):
        case = load("missing-uuid-legacy.json")
        case["screens"][LIVE]["handoff"] = case["predecessors"][0]["handoff"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(json.dumps(case), encoding="utf-8")
            proc = run("retire", str(path), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        row = payload["results"][0]
        self.assertTrue(row["planned"])
        self.assertEqual(row["record"], "closed")
        self.assertEqual(row["recovered_uuid"], LIVE)
        self.assertEqual(row["ref"], "workspace:4")
        self.assertEqual(payload["helper"], HELPER_LABEL)
        self.assertIn(HELPER_LABEL, proc.stdout)
        self.assertIn("workspace:4", proc.stdout)

    def test_loader_path_absent_does_not_call_a_claude_skills_copy(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn(".claude/skills", source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "decoy-called"
            decoy = root / "home" / ".claude" / "skills" / "cmux" / "scripts" / "close-workspace.sh"
            write_executable(
                decoy,
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    echo called > "{sentinel}"
                    exit 0
                    """
                ),
            )
            empty = root / "empty-skills"
            empty.mkdir()
            env = os.environ.copy()
            env.pop("BRUN_SKILLS_ROOT", None)
            env["HOME"] = str(root / "home")
            proc = run(
                "retire",
                str(CASES / "loader-path-absent.json"),
                "--skills-root",
                str(empty),
                "--dry-run",
                "--json",
                env=env,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertFalse(sentinel.exists())
            self.assertIn("BRUN_SKILLS_ROOT", proc.stderr)
            self.assertIn("cmux skill", proc.stderr)
            self.assertNotIn(".claude", proc.stdout + proc.stderr)
            self.assertGreaterEqual(len(proc.stderr.strip()), 20)

    def test_resolver_uses_brun_skills_root_and_reports_a_relative_path(self):
        previous = os.environ.pop("BRUN_SKILLS_ROOT", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                script = base / "cross-cutting" / "orchestrator" / "scripts" / "retire_predecessors.py"
                script.parent.mkdir(parents=True)
                script.write_text("", encoding="utf-8")
                root = base / "skills-checkout"
                helper = root / HELPER_LABEL
                write_executable(helper, "#!/bin/sh\nexit 0\n")
                os.environ["BRUN_SKILLS_ROOT"] = str(root)
                found, used = retire_predecessors.resolve_helper(script_file=script)
                self.assertEqual(found.resolve(), helper.resolve())
                self.assertEqual(retire_predecessors.helper_label(found, used), HELPER_LABEL)
        finally:
            if previous is None:
                os.environ.pop("BRUN_SKILLS_ROOT", None)
            else:
                os.environ["BRUN_SKILLS_ROOT"] = previous

    def test_pending_cleanup_stays_retained_until_the_retry(self):
        path = CASES / "pending-cleanup-retry.json"
        before = path.read_text(encoding="utf-8")
        held = run("retire", str(path), "--json", "--dry-run")
        self.assertEqual(held.returncode, 1, held.stderr)
        row = json.loads(held.stdout)["results"][0]
        self.assertEqual(row["record"], "retained")
        self.assertIn("Pending cleanup", row["reason"])
        self.assertIn("tool call", row["reason"])
        self.assertIsNone(row["note_action"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

        retried = run("retire", str(path), "--retry", "--dry-run")
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertIn(f"planned close fleet-coordinator workspace:4 {HELPER_LABEL}", retried.stdout)
        self.assertNotIn(".claude", retried.stdout + retried.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_unfinished_write_is_pending_cleanup(self):
        case = load("pending-cleanup-retry.json")
        case["screens"][SEAT]["in_flight"] = "unfinished_write"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "write.json"
            path.write_text(json.dumps(case), encoding="utf-8")
            proc = run("retire", str(path), "--json", "--dry-run")
        row = json.loads(proc.stdout)["results"][0]
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(row["record"], "retained")
        self.assertIn("unfinished write", row["reason"])

    def test_dry_run_plans_the_skills_relative_helper_without_calling_cmux(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "cmux-called"
            bindir = root / "bin"
            write_executable(
                bindir / "cmux",
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    echo called > "{sentinel}"
                    exit 9
                    """
                ),
            )
            env = os.environ.copy()
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            proc = run(
                "retire",
                str(CASES / "pending-cleanup-retry.json"),
                "--retry",
                "--dry-run",
                "--json",
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(sentinel.exists())
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["cmux_calls"], 0)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["helper"], HELPER_LABEL)
            self.assertNotIn(".claude", proc.stdout)

    def test_apply_calls_the_helper_with_the_ref_and_confirms_the_note(self):
        case = load("pending-cleanup-retry.json")
        case["screens"] = case["retry"]["screens"]
        case["after_workspaces"] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "sessions" / "2026-10-16-fleet-coordinator.md"
            note.parent.mkdir()
            note.write_text(case["notes"][NOTE], encoding="utf-8")
            case["notes"] = {str(note): case["notes"][NOTE]}
            case["predecessors"][0]["session_note"] = str(note)
            calls = root / "calls"
            helper = root / "skills" / HELPER_LABEL
            write_executable(
                helper,
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    printf '%s\\n' "$@" >> "{calls}"
                    python3 - "{note}" "2026-10-16" <<'PY'
                    import pathlib, sys
                    path, today = sys.argv[1:]
                    file = pathlib.Path(path)
                    text = file.read_text()
                    text = text.replace("status: in-progress", "status: done", 1)
                    if "ended:" not in text:
                        text = text.replace("status: done\\n", "status: done\\nended: " + today + "\\n", 1)
                    file.write_text(text)
                    PY
                    """
                ),
            )
            trap = root / "cmux-called"
            write_executable(
                root / "bin" / "cmux",
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    echo called > "{trap}"
                    exit 9
                    """
                ),
            )
            path = root / "case.json"
            path.write_text(json.dumps(case), encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
            env.pop("BRUN_SKILLS_ROOT", None)
            proc = run(
                "retire",
                str(path),
                "--json",
                "--skills-root",
                str(root / "skills"),
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse(trap.exists())
            self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["workspace:4"])
            payload = json.loads(proc.stdout)
            row = payload["results"][0]
            self.assertEqual(row["record"], "closed")
            self.assertFalse(row["planned"])
            self.assertEqual(payload["helper"], HELPER_LABEL)
            body = note.read_text(encoding="utf-8")
            self.assertIn("status: done", body)
            self.assertIn("ended: 2026-10-16", body)
            self.assertIn("Stopped at the outgoing handoff.", body)
            self.assertIn("Successor: sessions/2026-10-16-successor.md", body)
            self.assertIn("Handoff: handoffs/2026-10-16-successor.md", body)

    def test_failed_and_ended_notes_stay_unchanged_when_the_seat_is_absent(self):
        for status, ended in (("failed", False), ("done", True)):
            with self.subTest(status=status, ended=ended):
                case = load("reused-ref.json")
                lines = ["---", f"status: {status}"]
                if ended:
                    lines.append("ended: 2026-10-01")
                lines.extend(
                    [
                        'workspace_id: "workspace:4"',
                        'workspace_name: "fleet-coordinator"',
                        "---",
                        "",
                        "## Outcome",
                        "",
                        "Kept as written.",
                        "",
                    ]
                )
                body = "\n".join(lines)
                case["notes"][NOTE] = body
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "case.json"
                    path.write_text(json.dumps(case), encoding="utf-8")
                    proc = run("retire", str(path), "--json", "--dry-run")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                row = json.loads(proc.stdout)["results"][0]
                self.assertEqual(row["record"], "already-absent")
                self.assertEqual(row["note_action"], "preserve")
                self.assertIsNone(row["note_body"])

    def test_identity_change_before_closure_stays_pending(self):
        case = load("pending-cleanup-retry.json")
        case["screens"] = case["retry"]["screens"]
        case["recheck_workspaces"] = [
            {
                "window_uuid": WINDOW,
                "id": SEAT,
                "ref": "workspace:4",
                "title": "fleet-coordinator resumed",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps(case), encoding="utf-8")
            proc = run("retire", str(path), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        row = json.loads(proc.stdout)["results"][0]
        self.assertEqual(row["record"], "retained")
        self.assertIn("pending cleanup", row["reason"].casefold())
        self.assertIsNone(row["ref"])

    def test_refresh_uses_the_window_uuid_and_dry_run_does_not(self):
        case = load("reused-ref.json")
        del case["workspaces"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_path = root / "case.json"
            case_path.write_text(json.dumps(case), encoding="utf-8")
            log = root / "cmux-log"
            bindir = root / "bin"
            write_executable(
                bindir / "cmux",
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import os, sys
                    from pathlib import Path
                    log = Path({str(log)!r})
                    with log.open("a", encoding="utf-8") as handle:
                        handle.write(" ".join(sys.argv) + "\\n")
                    args = sys.argv[1:]
                    if args[:3] != ["--json", "--id-format", "both"]:
                        sys.stderr.write("cmux flags were not --json --id-format both\\n")
                        raise SystemExit(2)
                    command = args[3]
                    if command == "close-workspace":
                        sys.stderr.write("cmux close-workspace is not the successor helper\\n")
                        raise SystemExit(2)
                    if command == "list-windows":
                        print('[{{"id": "{WINDOW}"}}]')
                    elif command == "list-workspaces":
                        print('{{"window_id": "{WINDOW}", "workspaces": []}}')
                    else:
                        sys.stderr.write("unexpected cmux command\\n")
                        raise SystemExit(2)
                    """
                ),
            )
            env = os.environ.copy()
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            dry = run("retire", str(case_path), "--dry-run", "--json", env=env)
            self.assertEqual(dry.returncode, 2, dry.stdout + dry.stderr)
            self.assertFalse(log.exists())
            self.assertIn("workspaces", dry.stderr)
            live = run("retire", str(case_path), "--json", env=env)
            self.assertEqual(live.returncode, 0, live.stdout + live.stderr)
            text = log.read_text(encoding="utf-8")
            self.assertIn(f"list-workspaces --window {WINDOW}", text)
            self.assertIn("--json --id-format both", text)
            self.assertNotIn("close-workspace", text)
            row = json.loads(live.stdout)["results"][0]
            self.assertEqual(row["record"], "already-absent")
            self.assertGreater(json.loads(live.stdout)["cmux_calls"], 0)

    def test_bad_invocation_tells_the_agent_what_to_pass(self):
        missing = run("retire", "missing-succession-case.json")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Pass", missing.stderr)
        self.assertGreaterEqual(len(missing.stderr.strip()), 20)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text("{", encoding="utf-8")
            broken = run("retire", str(path))
        self.assertEqual(broken.returncode, 2)
        self.assertIn("JSON", broken.stderr)
        self.assertIn("Pass", broken.stderr)

    def test_handoff_points_steps_at_the_script(self):
        text = (HERE.parent / "workflows" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("retire_predecessors.py", text)
        self.assertNotIn("~/.claude/skills/cmux/scripts/close-workspace.sh", text)
        self.assertNotIn("The follow-up is a script", text)
        workflow_path = REPO / ".github" / "workflows" / "validate.yml"
        if workflow_path.is_file():
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertIn(
                "python3 cross-cutting/orchestrator/scripts/test_retire_predecessors.py",
                workflow,
            )


if __name__ == "__main__":
    unittest.main()
