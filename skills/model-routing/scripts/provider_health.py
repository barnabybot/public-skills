"""Stdlib-only provider health circuit breaker and deterministic failure classifier."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

DEFAULT_TTL_SECONDS = 20 * 60
DEFAULT_HEALTH_ENV = "MODEL_ROUTING_HEALTH_PATH"

FAILURE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("http_403_geoblock", re.compile(r"(403|forbidden|geo[\s-]?block|region\s+not\s+supported|unsupported\s+country)", re.I)),
    ("auth_expired", re.compile(r"(401|unauthori[sz]ed|token\s+expired|auth\s+expired|not\s+logged\s+in|re-?authenticate|invalid\s+api\s+key)", re.I)),
    ("quota_exhausted", re.compile(r"(429|rate\s+limit|quota\s+exhausted|usage\s+limit|insufficient_quota|capacity\s+exhausted)", re.I)),
    ("model_unavailable", re.compile(r"(model\s+not\s+found|model_not_found|model\s+unavailable|unsupported\s+model|no\s+access\s+to\s+model)", re.I)),
    ("linked_env_worktree_rejected", re.compile(r"(linked\s+environment.*worktree|isolation.*shared|worktree.*not\s+supported\s+on\s+linked)", re.I)),
    ("session_open_failure", re.compile(r"(failed\s+to\s+open\s+session|connection\s+refused|econnrefused|session\s+start\s+failed|transport\s+closed)", re.I)),
)


def default_health_path() -> Path:
    override = os.environ.get(DEFAULT_HEALTH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "model-routing" / "health.json"


def classify_failure(error_text: str) -> str | None:
    text = (error_text or "").strip()
    if not text:
        return None
    for code, pattern in FAILURE_PATTERNS:
        if pattern.search(text):
            return code
    return None


def load_health(path: Path | None = None, *, now: float | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else default_health_path()
    current = time.time() if now is None else now
    if not target.is_file():
        return {"schema_version": 1, "providers": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "providers": {}}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    active: dict[str, Any] = {}
    for key, rec in providers.items():
        if not isinstance(rec, dict):
            continue
        expires_at = float(rec.get("expires_at") or 0)
        if expires_at > current:
            active[key] = rec
    return {"schema_version": 1, "providers": active}


def save_health(data: dict[str, Any], path: Path | None = None) -> Path:
    target = Path(path) if path is not None else default_health_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def record_failure(
    provider: str,
    error_text: str,
    *,
    path: Path | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    current = time.time() if now is None else now
    failure_class = classify_failure(error_text)
    if failure_class is None:
        return {
            "tripped": False,
            "provider": provider,
            "failure_class": None,
            "reason": "unclassified non-provider error; circuit breaker not tripped",
        }
    state = load_health(path, now=current)
    prior = state["providers"].get(provider) or {}
    count = int(prior.get("count") or 0) + 1
    record = {
        "provider": provider,
        "failure_class": failure_class,
        "error": error_text.strip()[:300],
        "tripped_at": current,
        "expires_at": current + ttl_seconds,
        "ttl_seconds": ttl_seconds,
        "count": count,
    }
    state["providers"][provider] = record
    save_health(state, path)
    return {"tripped": True, **record}


def clear_health(provider: str | None = None, *, path: Path | None = None, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    state = load_health(path, now=current)
    if provider:
        removed = state["providers"].pop(provider, None) is not None
    else:
        removed = bool(state["providers"])
        state["providers"] = {}
    save_health(state, path)
    return {"cleared": provider or "all", "removed": removed, "active_trips": sorted(state["providers"].keys())}


def active_trip(provider: str, state: dict[str, Any], *, now: float | None = None) -> dict[str, Any] | None:
    current = time.time() if now is None else now
    rec = (state.get("providers") or {}).get(provider)
    if isinstance(rec, dict) and float(rec.get("expires_at") or 0) > current:
        return rec
    return None
