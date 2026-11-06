#!/usr/bin/env python3
"""Read the surface stamp that cmux/scripts/stamp_surface.py writes at launch.

A cross-model handoff uses this record to confirm the predecessor's agent,
model, effort and directory before the successor is spawned. It does not
probe provider accounts or read a keychain.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def state_dir() -> Path:
    override = os.environ.get("CMUX_AGENT_HOOK_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cmuxterm"


def read_spawned_surface(surface_id: str, root: Path | None = None) -> dict:
    """Return the stamp for one surface id, or raise ValueError."""
    key = surface_id.strip().lower()
    if not key:
        raise ValueError("surface id is empty; pass the live terminal surface UUID")
    folder = (root or state_dir()) / "spawned-surfaces"
    path = folder / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"spawned surface stamp is missing or unreadable: {path}. "
            "Relaunch through spawn-workspace.sh so stamp_surface.py can write it."
        ) from exc
    if not isinstance(payload, dict) or payload.get("surfaceId", "").lower() != key:
        raise ValueError("spawned surface stamp does not match the requested surface")
    for field in ("agent", "model", "effort", "cwd"):
        if not isinstance(payload.get(field), str):
            raise ValueError(f"spawned surface stamp lacks {field}")
    return payload
