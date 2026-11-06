from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


def parse_bundle_instant(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def request_file_sha256(request_path: str | None) -> str:
    if not request_path:
        return ""
    return hashlib.sha256(Path(request_path).read_bytes()).hexdigest()


def write_route_bundle(bundle_path: Path, args: Any, observed_at: str,
                       pairs: Mapping[str, Any], now: datetime) -> None:
    bundle_path = Path(bundle_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "no_capacity": False,
        "resolved_at": now.isoformat(),
        "observed_at": observed_at,
        "runtime_cwd": str(Path(args.runtime_cwd).resolve()),
        "request_sha256": request_file_sha256(args.request),
        "requested_tier": args.tier or "",
        "requested_of": args.of or "",
        "requested_builder": args.builder or "",
        "requested_model": args.model or "",
        "requested_effort": args.effort or "",
        "pairs": dict(pairs),
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=bundle_path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2)
        temp_name = handle.name
    os.chmod(temp_name, 0o600)
    os.replace(temp_name, bundle_path)


def verify_route_bundle(bundle_path: Path, canon: Mapping[str, Any], args: Any,
                        now: datetime) -> tuple[int, dict[str, Any] | None, str]:
    try:
        raw = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return (2, None, "verified route bundle is missing or unreadable")
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or raw.get("no_capacity") is not False:
        return (2, None, "verified route bundle schema or capacity flag is invalid")
    try:
        expected_sha = request_file_sha256(args.request)
        expected_cwd = str(Path(args.runtime_cwd).resolve())
    except OSError:
        return (2, None, "verified route bundle request or runtime directory is unreadable")
    expected_selectors = {
        "runtime_cwd": expected_cwd,
        "request_sha256": expected_sha,
        "requested_tier": args.tier or "",
        "requested_of": args.of or "",
        "requested_builder": args.builder or "",
        "requested_model": args.model or "",
        "requested_effort": args.effort or "",
    }
    for key, expected in expected_selectors.items():
        if raw.get(key) != expected:
            return (2, None, f"verified route bundle {key} does not match requested route inputs")
    pairs = raw.get("pairs")
    if not isinstance(pairs, dict) or pairs.get("ROUTE_STATUS") not in ("held", "tight", "override", "explicit"):
        return (2, None, "verified route bundle contains invalid route status or pairs")
    max_age = float((canon.get("capacity") or {}).get("max_observation_age_seconds", 300))
    for stamp_key in ("observed_at", "resolved_at"):
        stamp = parse_bundle_instant(raw.get(stamp_key))
        if stamp is None or not 0 <= (now - stamp).total_seconds() <= max_age:
            ask_pairs = {
                "ROUTE_STATUS": "ask",
                "ROUTE_TIER": str(pairs.get("ROUTE_TIER") or args.tier or "explicit"),
                "ROUTE_ASK": f"verified route bundle {stamp_key} is stale; re-run route resolution",
            }
            return (3, ask_pairs, ask_pairs["ROUTE_ASK"])
    return (0, dict(pairs), "")
