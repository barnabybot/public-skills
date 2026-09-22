#!/usr/bin/env python3
"""python3 scripts/check.py — validate the orchestrator model table.

Structural checks always run. Live checks (pinned ids against the installed
CLIs and their caches, CodexBar allowance per provider) run unless --no-live.
Exit 1 on any structural failure; unread live checks are warnings.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
from routing_log import append_evidence
from resolve import DEFAULT_SKILL, load_canon

BASES = {"measured", "practice", "ruling"}
CLAUDE_ID = re.compile(r"^claude-(fable|opus|sonnet|haiku)-\d+(-\d+)?(\[1m\])?$")


def run(cmd: list[str], timeout: float) -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def structural(canon: dict) -> list[tuple[str, str, str]]:
    """Check metadata after load_canon validates table seats and efforts."""
    out = []
    providers = canon.get("providers") or {}
    models = canon.get("models") or {}
    tiers = canon.get("tiers") or {}
    for key, m in models.items():
        if m.get("provider") not in providers:
            out.append(("fail", "model provider", f"{key} names provider {m.get('provider')!r}, unknown"))
    for key, row in tiers.items():
        if row["name"] != row["metadata_name"]:
            out.append(("warn", "tier name", f"tier {key}: table {row['name']!r} differs from metadata {row['metadata_name']!r}; review its basis and evidence"))
        if row.get("basis") not in BASES:
            out.append(("fail", "basis", f"tier {key} basis {row.get('basis')!r} is outside {sorted(BASES)}"))
    for word, target in (canon.get("legacy_tiers") or {}).items():
        if target not in tiers:
            out.append(("fail", "legacy tiers", f"{word} points at {target!r}, unknown"))
    if not out:
        out.append(("ok", "structure", f"{len(tiers)} tiers, {len(models)} models, {len(providers)} providers; every backup on another provider"))
    return out


def live_ids(canon: dict) -> list[tuple[str, str, str]]:
    out = []
    grok_models = run(["grok", "models"], 20)
    codex_cache = ""
    for path in Path.home().joinpath(".codex").glob("*.json"):
        try:
            codex_cache += path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
    muse_model = None
    muse_settings = Path.home() / ".config" / "muse" / "settings.json"
    if muse_settings.exists():
        try:
            muse_model = json.loads(muse_settings.read_text(encoding="utf-8")).get("model")
        except (OSError, json.JSONDecodeError):
            muse_model = None
    for key, m in (canon.get("models") or {}).items():
        mid, provider = m.get("id"), m.get("provider")
        if provider == "grok":
            if grok_models is None:
                out.append(("warn", "id grok", f"{mid}: grok models unread"))
            elif mid in grok_models:
                out.append(("ok", "id grok", f"{mid} listed by grok models"))
            else:
                out.append(("fail", "id grok", f"{mid} absent from grok models"))
        elif provider == "codex":
            if not codex_cache:
                out.append(("warn", "id codex", f"{mid}: no local model cache"))
            elif mid in codex_cache:
                out.append(("ok", "id codex", f"{mid} in the local model cache"))
            else:
                out.append(("fail", "id codex", f"{mid} absent from the local model cache"))
        elif provider == "muse":
            if muse_model is None:
                out.append(("warn", "id muse", f"{mid}: settings file unread"))
            elif muse_model == mid:
                out.append(("ok", "id muse", f"{mid} matches the settings file"))
            else:
                out.append(("warn", "id muse", f"{mid} differs from settings ({muse_model})"))
        elif provider == "claude":
            if CLAUDE_ID.match(mid or ""):
                out.append(("ok", "id claude", f"{mid} well-formed; shape only, a spawn confirms it"))
            else:
                out.append(("fail", "id claude", f"{mid} is not a pinned Claude id"))
    return out


def live_capacity(canon: dict) -> list[tuple[str, str, str]]:
    out = []
    timeout = float((canon.get("capacity") or {}).get("read_timeout_seconds", 20))
    for key, p in (canon.get("providers") or {}).items():
        name = p.get("codexbar")
        if not name:
            out.append(("warn", "capacity", f"{key}: no CodexBar provider, always unread"))
            continue
        raw = run(["codexbar", "usage", "--provider", name, "--format", "json", "--no-color"], timeout)
        entry = None
        if raw:
            try:
                data = json.loads(raw)
                entry = next((e for e in data if e.get("provider") == name), None) if isinstance(data, list) else data
            except json.JSONDecodeError:
                entry = None
        if not entry:
            out.append(("warn", "capacity", f"{key}: CodexBar unread"))
            continue
        usage = entry.get("usage") or {}
        weekly = usage.get("secondary") or usage.get("primary") or {}
        out.append(("ok", "capacity", f"{key}: {weekly.get('usedPercent', '?')}% used, resets {weekly.get('resetDescription') or weekly.get('resetsAt') or '?'}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--skill", default=str(DEFAULT_SKILL))
    ap.add_argument("--no-log", action="store_true", help="skip the routing evidence row")
    args = ap.parse_args()
    try:
        canon = load_canon(Path(args.skill))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f"fail  canon: {exc}")
        return 1
    rows = structural(canon)
    if not args.no_live:
        rows += live_ids(canon) + live_capacity(canon)
    status = "fail" if any(r[0] == "fail" for r in rows) else ("warn" if any(r[0] == "warn" for r in rows) else "ok")
    if args.json:
        print(json.dumps({"status": status, "rows": [dict(zip(("status", "check", "detail"), r)) for r in rows]}, indent=2))
    else:
        for st, check, detail in rows:
            print(f"{st:<5} {check}: {detail}")
        print(f"\npython3 scripts/check.py: {status}")
    if not args.no_log:
        fails = sum(1 for r in rows if r[0] == "fail")
        warns = sum(1 for r in rows if r[0] == "warn")
        append_evidence("check", status, f"{len(rows)} checks, {fails} fail, {warns} warn{' (no-live)' if args.no_live else ''}")
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
