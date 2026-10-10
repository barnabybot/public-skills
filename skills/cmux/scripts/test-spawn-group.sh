#!/bin/bash
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
export SPAWN_HELPER="$HERE/spawn-workspace.sh"
"${SPAWN_PYTHON:-python3}" - <<'PY'
import json
import os
from pathlib import Path
import subprocess
import tempfile

with tempfile.TemporaryDirectory(prefix="spawn-group-") as tmp:
    root = Path(tmp)
    cmux = root / "cmux"
    cmux.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps(args) + "\\n")
case = os.environ["CASE"]
if "--help" in args:
    print("--cwd --command" if case == "legacy" else "--group --group-reference --focus --window")
elif "identify" in args:
    print(json.dumps({"caller": None if case == "no-caller" else {"workspace_id": "mismatch" if case == "caller-mismatch" else "caller", "window_id": "source-window"}, "focused": {"workspace_id": "other", "window_id": "other-window"}}))
elif "workspace-group" in args:
    if case == "lookup-error":
        sys.exit("socket unavailable")
    if case == "malformed":
        print("{}")
    else:
        members = ["caller"] if case != "ungrouped" else ["other"]
        print(json.dumps({"window_id": "source-window", "groups": [{"id": "source-group", "member_workspace_ids": members}]}))
elif "current-workspace" in args:
    print("workspace:99")
elif "new-window" in args:
    print("OK 555D2979-D5DE-43A3-B186-671890A1D90E")
elif "list-workspaces" in args:
    print("workspace:100")
elif "new-workspace" in args:
    if case == "creation-error":
        print("workspace:101")
        sys.exit("group no longer exists")
    subprocess.run(args[args.index("--command") + 1], shell=True, check=True)
    print("OK workspace:101")
elif "read-screen" in args:
    print("trust this folder")
else:
    print("OK")
''')
    cmux.chmod(0o755)
    runner = root / "claude"
    runner.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ["RUNNER_CALL"]).write_text(json.dumps(sys.argv[1:]))
''')
    runner.chmod(0o755)
    (root / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (root / "sleep").chmod(0o755)
    resolver = root / "resolve.py"
    resolver.write_text('print("ROUTE_AGENT=claude\\nROUTE_MODEL=test-model\\nROUTE_EFFORT=high\\nROUTE_MODEL_ID=test-model\\nROUTE_LINE=fixture")\n')
    prompt = root / "handoff.md"
    prompt.write_text("Continue the grouped task.")
    env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", ROUTING_RESOLVER=str(resolver),
               CMUX_WORKSPACE_ID="caller", CMUX_AGENT_LAUNCH_KIND="claude",
               CALLS=str(root / "calls"), RUNNER_CALL=str(root / "runner"))
    failures = []
    for case, extra in [("grouped", []), ("ungrouped", []),
                        ("handoff", ["--prompt-file", str(prompt)]),
                        ("new-window", ["--new-window"]), ("lookup-error", []),
                        ("malformed", []), ("caller-mismatch", []), ("no-caller", []), ("creation-error", []), ("legacy", []), ("dry-run", ["--dry-run"])]:
        Path(env["CALLS"]).write_text("")
        Path(env["RUNNER_CALL"]).unlink(missing_ok=True)
        result = subprocess.run([os.environ["SPAWN_HELPER"], "fixture", "--tier", "coding",
                                 "--cwd", tmp, "--no-session", *extra],
                                env=dict(env, CASE=case, CMUX_WORKSPACE_ID="" if case == "no-caller" else "caller"), text=True, capture_output=True)
        calls = [json.loads(line) for line in Path(env["CALLS"]).read_text().splitlines()]
        creates = [call for call in calls if call[0] == "new-workspace" and "--help" not in call]
        try:
            if case in ("lookup-error", "malformed", "caller-mismatch"):
                assert result.returncode != 0 and not creates, (result.returncode, creates)
            elif case == "creation-error":
                assert result.returncode != 0 and len(creates) == 1, result.stderr
                assert not any(call[0] in ("rename-workspace", "select-workspace") for call in calls), calls
            elif case == "dry-run":
                assert result.returncode == 0 and calls == [], (result.returncode, calls)
            else:
                assert result.returncode == 0 and len(creates) == 1, result.stderr
                args = creates[0]
                if case == "legacy":
                    assert "--focus" not in args and "--group" not in args, args
                    assert "warning:" in result.stderr, result.stderr
                else:
                    assert args[args.index("--focus") + 1] == "false", args
                if case in ("grouped", "handoff"):
                    for flag, value in [("--group", "source-group"), ("--group-reference", "caller"),
                                        ("--group-placement", "afterCurrent"), ("--window", "source-window")]:
                        assert args[args.index(flag) + 1] == value, args
                else:
                    assert "--group" not in args, args
                if case != "legacy":
                    assert not any(call[0] == "select-workspace" for call in calls), calls
                if case == "new-window":
                    assert args[args.index("--window") + 1] == "555D2979-D5DE-43A3-B186-671890A1D90E", args
                    assert not any("workspace-group" in call for call in calls), calls
                if case == "ungrouped":
                    assert args[args.index("--window") + 1] == "source-window", args
                launched = json.loads(Path(env["RUNNER_CALL"]).read_text())
                assert launched[:3] == ["--dangerously-skip-permissions", "--model", "test-model"], launched
                if case == "handoff":
                    launch_file = Path(launched[-1].split("Read the file at ", 1)[1].split(" in full.", 1)[0])
                    assert launch_file.read_text() == "Effort: high\n\nContinue the grouped task."
                    launch_file.unlink()
            print(f"PASS {case}")
        except (AssertionError, ValueError) as exc:
            failures.append(case)
            print(f"FAIL {case}: {exc}")
    assert not failures, failures
PY
