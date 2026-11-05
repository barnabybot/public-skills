from __future__ import annotations

import calendar
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def stamp_spawned_surface(argv: list[str]) -> int:
    surface_id = os.environ.get("CMUX_SURFACE_ID", "").strip().lower()
    if not surface_id:
        return 0
    workspace_id = os.environ.get("CMUX_WORKSPACE_ID", "").strip().lower()
    agent = argv[0] if len(argv) > 0 else "gemini"
    model = argv[1] if len(argv) > 1 else ""
    effort = argv[2] if len(argv) > 2 else "unset"
    cwd = argv[3] if len(argv) > 3 else os.getcwd()
    binary_name = argv[4] if len(argv) > 4 else agent
    ppid = os.getppid()
    started = 0
    try:
        proc = subprocess.run(
            ["ps", "-p", str(ppid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
        )
        if proc.returncode == 0 and proc.stdout.strip():
            started = int(calendar.timegm(time.strptime(proc.stdout.strip(), "%a %b %d %H:%M:%S %Y")))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        started = 0
    exe = shutil.which(binary_name) or ""
    for candidate in (f"~/.local/bin/{binary_name}", f"/opt/homebrew/bin/{binary_name}"):
        if exe:
            break
        expanded = str(Path(candidate).expanduser())
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            exe = expanded
    state_root = Path(os.environ.get("CMUX_AGENT_HOOK_STATE_DIR", str(Path.home() / ".cmuxterm")))
    out_dir = state_root / "spawned-surfaces"
    try:
        out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {
            "workspaceId": workspace_id,
            "surfaceId": surface_id,
            "agent": agent,
            "model": model,
            "effort": effort,
            "cwd": str(Path(cwd).resolve()),
            "pid": ppid,
            "pidStartSeconds": started,
            "executablePath": str(Path(exe).absolute()) if exe else "",
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=out_dir, delete=False) as handle:
            json.dump(payload, handle, indent=2)
            temp_name = handle.name
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, out_dir / f"{surface_id}.json")
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(stamp_spawned_surface(sys.argv[1:]))
