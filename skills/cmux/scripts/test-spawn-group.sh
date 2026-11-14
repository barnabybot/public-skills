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
w, g, c, h, child = [str(i)*8+'-'+str(i)*4+'-'+str(i)*4+'-'+str(i)*4+'-'+str(i)*12 for i in range(1,6)]
marker = 'cmux.group-header/v1/'+w+'/'+g
state_path = Path(os.environ['CALLS']+'.state')
state = json.loads(state_path.read_text()) if state_path.exists() else {'created':False,'header':case not in ('agent-anchor','new-window-anchor'),'promoted':case not in ('agent-anchor','new-window-anchor')}
if "--help" in args:
    print("--cwd --command" if case == "legacy" else "--group --group-reference --focus --window")
elif "identify" in args:
    print(json.dumps({"caller": None if case == "no-caller" else {"workspace_id": "mismatch" if case == "caller-mismatch" else c, "window_id": w}, "focused": {"workspace_id": c, "window_id": w}}))
elif "workspace-group" in args:
    if case == "lookup-error":
        sys.exit("socket unavailable")
    if case == "malformed":
        print("{}")
    elif 'set-anchor' in args:
        state['promoted'] = True
        print('OK')
    else:
        members = [c] + ([h] if state['header'] else []) + ([child] if state['created'] else [])
        groups = [] if case in ('ungrouped','new-window') else [{"id": g,"anchor_workspace_id": h if state['promoted'] else c, "member_workspace_ids": members}]
        print(json.dumps({"window_id": args[args.index('--window')+1], "groups": groups}))
elif "current-workspace" in args:
    print("workspace:99")
elif "new-window" in args:
    print("OK 555D2979-D5DE-43A3-B186-671890A1D90E")
elif "list-windows" in args:
    print(json.dumps([{'id':w}]))
elif "list-workspaces" in args:
    if '--json' in args:
        rows = [{'id':c,'ref':'workspace:100','title':'Caller','description':''}]
        if state['header']: rows.append({'id':h,'ref':'workspace:102','title':'Header','description':marker})
        if state['created']: rows.append({'id':child,'ref':'workspace:101','title':'Child','description':''})
        print(json.dumps({'window_id':args[args.index('--window')+1],'workspaces':rows}))
    else: print("workspace:100")
elif "new-workspace" in args:
    if '--description' in args:
        state['header'] = True
        print('OK workspace:102')
    elif case == "creation-error":
        print("workspace:101")
        sys.exit("group no longer exists")
    else:
        subprocess.run(args[args.index("--command") + 1], shell=True, check=True)
        state['created'] = True
        print("OK workspace:101")
elif "read-screen" in args:
    print("trust this folder")
else:
    print("OK")
state_path.write_text(json.dumps(state))
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
    prompt.write_text("Continue the grouped task.\n\n")
    env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", ROUTING_RESOLVER=str(resolver),
               CMUX_WORKSPACE_ID="33333333-3333-3333-3333-333333333333", CMUX_AGENT_LAUNCH_KIND="claude",
               CMUX_GROUP_HEADER_STATE_DIR=str(root / "locks"), CALLS=str(root / "calls"), RUNNER_CALL=str(root / "runner"))
    failures = []
    for case, extra in [("grouped", []), ("agent-anchor", []), ("ungrouped", []),
                        ("handoff", ["--prompt-file", str(prompt)]),
                        ("new-window", ["--new-window"]), ("new-window-anchor", ["--new-window"]), ("lookup-error", []),
                        ("malformed", []), ("caller-mismatch", []), ("no-caller", []), ("creation-error", []), ("legacy", []), ("dry-run", ["--dry-run"])]:
        Path(env["CALLS"]).write_text("")
        Path(env["CALLS"]+".state").unlink(missing_ok=True)
        Path(env["RUNNER_CALL"]).unlink(missing_ok=True)
        result = subprocess.run([os.environ["SPAWN_HELPER"], "fixture", "--tier", "coding",
                                 "--cwd", tmp, "--no-session", *extra],
                                env=dict(env, CASE=case, CMUX_WORKSPACE_ID="" if case == "no-caller" else "33333333-3333-3333-3333-333333333333"), text=True, capture_output=True)
        calls = [json.loads(line) for line in Path(env["CALLS"]).read_text().splitlines()]
        creates = [call for call in calls if call[0] == "new-workspace" and "--help" not in call and "--description" not in call]
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
                if case in ("grouped", "handoff", "agent-anchor"):
                    for flag, value in [("--group", "22222222-2222-2222-2222-222222222222"), ("--group-reference", "33333333-3333-3333-3333-333333333333"),
                                        ("--group-placement", "afterCurrent"), ("--window", "11111111-1111-1111-1111-111111111111")]:
                        assert args[args.index(flag) + 1] == value, args
                else:
                    assert "--group" not in args, args
                if case != "legacy":
                    assert not any(call[0] == "select-workspace" for call in calls), calls
                if case in ("new-window", "new-window-anchor"):
                    assert args[args.index("--window") + 1] == "555D2979-D5DE-43A3-B186-671890A1D90E", args
                    assert not any("set-anchor" in call for call in calls), calls
                if case == "ungrouped":
                    assert args[args.index("--window") + 1] == "11111111-1111-1111-1111-111111111111", args
                launched = json.loads(Path(env["RUNNER_CALL"]).read_text())
                assert launched[:3] == ["--dangerously-skip-permissions", "--model", "test-model"], launched
                if case == "handoff":
                    launch_file = Path(launched[-1].split("Read the file at ", 1)[1].split(" in full.", 1)[0])
                    assert launch_file.read_text() == "Effort: high\n\nContinue the grouped task.\n\n"
                    launch_file.unlink()
            if case == "new-window-anchor":
                assert not any(call[0] == 'close-workspace' for call in calls), calls
                assert 'Retained default workspace' in result.stderr, result.stderr
            if case == "agent-anchor":
                state = json.loads(Path(env["CALLS"]+".state").read_text())
                assert state == {'created':True,'header':True,'promoted':True}, state
                headers = [call for call in calls if '--description' in call]
                assert len(headers) == 1, headers
            print(f"PASS {case}")
        except (AssertionError, ValueError) as exc:
            failures.append(case)
            print(f"FAIL {case}: {exc}")
    assert not failures, failures
PY
