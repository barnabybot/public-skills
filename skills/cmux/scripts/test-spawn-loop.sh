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

with tempfile.TemporaryDirectory(prefix="spawn-loop-") as tmp:
    root = Path(tmp)
    stubs = root / "bin"
    stubs.mkdir()
    scripts = {
        "cmux": '''#!/usr/bin/env python3
import json, subprocess, sys
args = sys.argv[1:]
if "--help" in args:
    print("--group-reference --focus --window")
elif "identify" in args:
    print(json.dumps({"caller": None}))
elif "new-workspace" in args:
    subprocess.run(args[args.index("--command") + 1], shell=True, check=True)
    print("OK workspace:101")
elif "read-screen" in args:
    print("trust this folder")
else:
    print("OK")
''',
        "claude": '''#!/usr/bin/env python3
import os
from pathlib import Path
Path(os.environ["RUNNER_RECEIPT"]).write_text("launched")
''',
        "sleep": "#!/bin/sh\nexit 0\n",
    }
    for name, content in scripts.items():
        path = stubs / name
        path.write_text(content)
        path.chmod(0o755)
    resolver = root / "resolve.py"
    resolver.write_text('print("ROUTE_AGENT=claude\\nROUTE_MODEL=test-model\\nROUTE_EFFORT=high\\nROUTE_MODEL_ID=test-model\\nROUTE_LINE=fixture")\n')
    failures = []
    for label, flags, expected in [("default", ["--loop"], 30),
                                    ("custom", ["--loop", "45"], 45),
                                    ("omitted", [], None)]:
        case_home = root / label
        case_home.mkdir()
        receipt = case_home / "runner"
        env = dict(os.environ, HOME=str(case_home), PATH=f"{stubs}:{os.environ['PATH']}",
                   ROUTING_RESOLVER=str(resolver), CMUX_WORKSPACE_ID="",
                   CMUX_AGENT_LAUNCH_KIND="claude", RUNNER_RECEIPT=str(receipt))
        result = subprocess.run([os.environ["SPAWN_HELPER"], "loop-fixture", "--tier", "coding",
                                 "--cwd", str(root), "--no-session", *flags],
                                env=env, text=True, capture_output=True)
        try:
            assert result.returncode == 0, result.stderr
            assert receipt.read_text() == "launched"
            loop_file = case_home / ".claude/loops/ws-workspace:101.json"
            if expected is None:
                assert not loop_file.exists()
            else:
                assert json.loads(loop_file.read_text()) == {"threshold": expected}, loop_file.read_text()
            print(f"PASS {label}")
        except AssertionError as exc:
            failures.append(label)
            print(f"FAIL {label}: {exc}")
    assert not failures, failures
PY
