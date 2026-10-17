#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

GRAMMAR = Path(__file__).with_name("fixtures") / "idle-footer.json"
STORE_NAME = "codex-hook-sessions.json"


def hook_store_path() -> Path:
    override = os.environ.get("CMUX_AGENT_HOOK_STATE_DIR")
    base = Path(override).expanduser() if override else Path.home() / ".cmuxterm"
    return base / STORE_NAME


def load_grammar() -> dict:
    return json.loads(GRAMMAR.read_text(encoding="utf-8"))


def load_store(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Codex hook store is not an object")
    return data


def session_rows(store: object) -> list[dict]:
    if not isinstance(store, dict):
        return []
    sessions = store.get("sessions")
    if not isinstance(sessions, dict):
        return []
    return [row for row in sessions.values() if isinstance(row, dict)]


def match_session(store: object, workspace_id: str, surface_id: str) -> dict | None:
    wanted_workspace = workspace_id.upper()
    wanted_surface = surface_id.upper()
    matches = []
    for row in session_rows(store):
        if str(row.get("workspaceId", "")).upper() != wanted_workspace:
            continue
        if str(row.get("surfaceId", "")).upper() != wanted_surface:
            continue
        matches.append(row)
    if len(matches) != 1:
        return None
    return matches[0]


def lifecycle_verdict(row: dict) -> str:
    life = row.get("agentLifecycle")
    if life != "idle":
        if life in {"running", "needsInput", "unknown"}:
            return "active"
        return "no-signal"
    runtime = row.get("runtimeStatus")
    if runtime not in (None, "idle"):
        return "active"
    depth = row.get("activePromptDepth")
    max_idle_depth = 1 if row.get("hookEventName") == "Stop" else 0
    if isinstance(depth, int) and not isinstance(depth, bool) and depth > max_idle_depth:
        return "active"
    if row.get("hadPendingBackgroundWorkAtStop") is True:
        return "active"
    return "idle"


def tail_lines(screen: str, grammar: dict) -> list[str]:
    lines = [line.strip() for line in screen.splitlines() if line.strip()]
    pattern = grammar["shortcuts"]
    if lines and re.fullmatch(pattern, lines[-1]):
        lines.pop()
    return lines


def composer_state(lines: list[str], grammar: dict) -> str:
    mark = grammar["composer_mark"]
    placeholders = set(grammar["placeholders"])
    prefix = mark + " "
    for line in reversed(lines):
        if line == mark:
            return "empty"
        if line.startswith(prefix):
            if line[len(prefix):] in placeholders:
                return "empty"
            return "grammar-break"
    return "missing"


def prove(screen: str, store: object, workspace_id: str, surface_id: str, grammar: dict) -> str:
    row = match_session(store, workspace_id, surface_id)
    if row is None:
        return "no-signal"
    life = lifecycle_verdict(row)
    if life != "idle":
        return life
    window = tail_lines(screen, grammar)[-int(grammar["tail_lines"]):]
    for marker in grammar["active_markers"]:
        if any(marker in line for line in window):
            return "active"
    state = composer_state(window, grammar)
    if state == "empty":
        return "idle"
    return "grammar-break"


def prove_file(screen: str, workspace_id: str, surface_id: str) -> str:
    return prove(screen, load_store(hook_store_path()), workspace_id, surface_id, load_grammar())
