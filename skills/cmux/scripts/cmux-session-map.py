#!/usr/bin/env python3
"""Map Claude Code sessions to cmux surfaces/workspaces.
Maintains /tmp/cmux-session-map.json with active mappings."""

import json
import os
import sys
import fcntl
from datetime import datetime

MAP_FILE = "/tmp/cmux-session-map.json"

def load_map():
    try:
        with open(MAP_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_map(data):
    with open(MAP_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        f.write("\n")
        fcntl.flock(f, fcntl.LOCK_UN)

def handle_start(payload):
    session_id = payload.get("session_id")
    surface_id = os.environ.get("CMUX_SURFACE_ID")
    workspace_id = os.environ.get("CMUX_WORKSPACE_ID")
    if not session_id or not surface_id:
        return
    data = load_map()
    data[surface_id] = {
        "session_id": session_id,
        "workspace_id": workspace_id or "",
        "cwd": payload.get("cwd", ""),
        "started": datetime.now().isoformat(),
    }
    save_map(data)

def handle_end(payload):
    surface_id = os.environ.get("CMUX_SURFACE_ID")
    if not surface_id:
        return
    data = load_map()
    if surface_id in data:
        del data[surface_id]
        save_map(data)

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        event = payload.get("hook_event_name")
        if event == "SessionStart":
            handle_start(payload)
        elif event == "SessionEnd":
            handle_end(payload)
    except Exception:
        pass
