#!/usr/bin/env python3
"""Stdlib-only model routing preflight, host adapters, circuit breaker and 2-hop takeover."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provider_health as ph
import routing_catalog as rc

HOST_CHOICES = ("t3", "cmux", "cli")
MAX_TAKEOVER_HOPS = 2


def _parse_capabilities(path: Path | None) -> dict[str, dict[str, Any]] | None:
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    providers_out: dict[str, dict[str, Any]] = {}
    items = raw.get("providers") if isinstance(raw, dict) else raw
    if isinstance(items, dict):
        for key, val in items.items():
            if isinstance(val, dict):
                providers_out[key] = val
    elif isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("providerInstanceId") or item.get("id") or item.get("driverKind") or "").strip()
            if pid:
                providers_out[pid] = item
    return providers_out


def _capability_model_ids(cap_entry: dict[str, Any]) -> set[str]:
    models = cap_entry.get("models")
    if not isinstance(models, list):
        return set()
    ids: set[str] = set()
    for item in models:
        if isinstance(item, str) and item.strip():
            ids.add(item.strip())
        elif isinstance(item, dict):
            mid = str(item.get("id") or item.get("model") or "").strip()
            if mid:
                ids.add(mid)
    return ids


def _cmux_flags(agent: str, model_id: str, effort: str) -> list[str]:
    flags = ["--model", model_id]
    if not effort:
        return flags
    if agent == "codex":
        flags += ["-c", f"model_reasoning_effort={effort}"]
    elif agent == "grok":
        flags += ["--reasoning-effort", effort]
    else:
        flags += ["--effort", effort]
    return flags


def _shape_target(
    host: str,
    provider_key: str,
    provider: dict[str, Any],
    model: dict[str, Any],
    effort: str,
    environment_id: str = "",
) -> dict[str, Any]:
    effort_opt = str(model.get("effort_option") or provider.get("effort_option") or "effort")
    if host == "cmux":
        agent = str(provider.get("agent") or provider_key)
        flags = _cmux_flags(agent, model["id"], effort)
        return {
            "provider": provider_key,
            "agent": agent,
            "model": model["id"],
            "display": model["display"],
            "effort": effort,
            "cli_flags": flags,
            "cli_flags_str": " ".join(shlex.quote(tok) for tok in flags),
        }
    if host == "cli":
        return {
            "provider": provider_key,
            "display": model["display"],
            "target": {"provider": provider_key, "model": model["id"], "effort": effort},
        }
    delegate_target: dict[str, Any] = {
        "providerInstanceId": str(provider.get("provider_instance_id") or provider_key),
        "driverKind": str(provider.get("driver_kind") or provider.get("agent") or provider_key),
        "model": model["id"],
        "options": {effort_opt: effort} if effort else {},
    }
    if environment_id:
        delegate_target["environmentId"] = environment_id
    return {
        "provider": provider_key,
        "display": model["display"],
        "effort": effort,
        "delegate_target": delegate_target,
    }


def _chain_for_request(
    catalog: dict[str, Any],
    *,
    category: str,
    of_category: str = "",
    explicit_model: str = "",
    explicit_effort: str = "",
) -> tuple[str, list[dict[str, str]]]:
    if explicit_model:
        found = rc.find_model(catalog, explicit_model)
        if found is None:
            raise ValueError(f"unknown model: {explicit_model}")
        allowed = found.get("efforts") or catalog["providers"][found["provider"]]["efforts"]
        effort = explicit_effort or (allowed[-1] if allowed else "")
        if effort and effort not in allowed:
            raise ValueError(f"invalid effort {effort!r} for model {found['id']!r}")
        return category or "explicit", [{"model": found["key"], "effort": effort}]

    if category not in catalog["categories"]:
        raise ValueError(f"unknown category: {category}")
    row = catalog["categories"][category]
    if row.get("of") == "required":
        if not of_category or of_category not in catalog["categories"] or of_category == category:
            raise ValueError("review requires --of naming a non-review category")
        return f"review:{of_category}", list(catalog["categories"][of_category]["chain"])
    return category, list(row["chain"])


def run_preflight(
    *,
    category: str,
    host: str = "t3",
    of_category: str = "",
    builder: str = "",
    explicit_model: str = "",
    explicit_effort: str = "",
    capabilities_path: Path | None = None,
    environment_id: str = "",
    no_live: bool = False,
    health_path: Path | None = None,
    skill_path: Path | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    catalog = rc.load_catalog(skill_path, catalog_path)
    effective_category, chain = _chain_for_request(
        catalog,
        category=category,
        of_category=of_category,
        explicit_model=explicit_model,
        explicit_effort=explicit_effort,
    )
    if category == "review" and not builder:
        raise ValueError("review requires --builder naming the builder provider to exclude")

    health_state = ph.load_health(health_path)
    caps = None if no_live else _parse_capabilities(capabilities_path)
    isolation = "shared" if environment_id else "worktree"

    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    drift_warnings: list[str] = []

    for slot in chain:
        mkey = slot["model"]
        effort = slot["effort"]
        model = rc.model_entry(catalog, mkey, effort)
        pkey = model["provider"]
        provider = catalog["providers"][pkey]

        if category == "review" and pkey == builder:
            skipped.append({"provider": pkey, "model": model["id"], "reason": "excluded_builder_provider"})
            continue
        if provider.get("enabled") is False:
            skipped.append({"provider": pkey, "model": model["id"], "reason": "provider_disabled"})
            continue
        if not explicit_model and provider.get("explicit_only") is True:
            skipped.append({"provider": pkey, "model": model["id"], "reason": "explicit_only_provider"})
            continue
        trip = ph.active_trip(pkey, health_state)
        if trip is not None:
            skipped.append(
                {
                    "provider": pkey,
                    "model": model["id"],
                    "reason": f"circuit_breaker_tripped:{trip['failure_class']}",
                    "expires_at": trip["expires_at"],
                }
            )
            continue
        if host == "t3" and caps is not None:
            pid = str(provider.get("provider_instance_id") or pkey)
            cap_entry = caps.get(pid) or caps.get(pkey)
            if cap_entry is None:
                skipped.append({"provider": pkey, "model": model["id"], "reason": "provider_absent_from_capabilities"})
                continue
            cap_models = _capability_model_ids(cap_entry)
            if cap_models and model["id"] not in cap_models:
                drift_warnings.append(f"{pid}: catalog model {model['id']} not listed in live capabilities")
                skipped.append({"provider": pkey, "model": model["id"], "reason": "model_absent_from_capabilities"})
                continue

        targets.append(_shape_target(host, pkey, provider, model, effort, environment_id=environment_id))

    result: dict[str, Any] = {
        "ok": bool(targets),
        "host": host,
        "category": effective_category,
        "targets": targets,
        "skipped": skipped,
        "drift_warnings": drift_warnings,
    }
    if host == "t3":
        result["isolation"] = isolation
    if no_live:
        result["unread_checks"] = ["live_capabilities"]
    return result


def _inspect_worktree(worktree: str) -> dict[str, Any]:
    if not worktree:
        return {"action": "task_cancel", "has_changes": False, "brief_context": ""}
    wt = Path(worktree).expanduser()
    if not wt.is_dir():
        return {"action": "task_cancel", "has_changes": False, "brief_context": ""}
    proc = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"], capture_output=True, text=True)
    dirty = bool((proc.stdout or "").strip()) if proc.returncode == 0 else False
    if not dirty:
        return {"action": "task_cancel", "has_changes": False, "brief_context": ""}
    return {
        "action": "preserve_worktree",
        "has_changes": True,
        "worktree": str(wt),
        "brief_context": f"Resume from existing uncommitted edits in {wt}; inspect git status and git diff before changing files.",
    }


def run_takeover(
    *,
    category: str,
    failed_provider: str,
    error_text: str,
    attempt: int = 0,
    host: str = "t3",
    failed_model: str = "",
    of_category: str = "",
    builder: str = "",
    worktree: str = "",
    capabilities_path: Path | None = None,
    environment_id: str = "",
    no_live: bool = False,
    health_path: Path | None = None,
    skill_path: Path | None = None,
    catalog_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    salvage = _inspect_worktree(worktree)
    failure_class = ph.classify_failure(error_text)
    if failure_class is None:
        return 3, {
            "ok": False,
            "action": "escalate",
            "reason": "unclassified_error",
            "failed_provider": failed_provider,
            "failed_model": failed_model,
            "salvage": salvage,
        }
    trip = ph.record_failure(failed_provider, error_text, path=health_path)
    if attempt >= MAX_TAKEOVER_HOPS:
        return 3, {
            "ok": False,
            "action": "escalate",
            "reason": f"max_takeover_hops_reached:{MAX_TAKEOVER_HOPS}",
            "failure_class": failure_class,
            "trip": trip,
            "salvage": salvage,
        }
    plan = run_preflight(
        category=category,
        host=host,
        of_category=of_category,
        builder=builder,
        capabilities_path=capabilities_path,
        environment_id=environment_id,
        no_live=no_live,
        health_path=health_path,
        skill_path=skill_path,
        catalog_path=catalog_path,
    )
    if not plan["targets"]:
        return 3, {
            "ok": False,
            "action": "escalate",
            "reason": "no_eligible_fallback_provider",
            "failure_class": failure_class,
            "trip": trip,
            "skipped": plan["skipped"],
            "salvage": salvage,
        }
    return 0, {
        "ok": True,
        "action": "divert",
        "attempt": attempt + 1,
        "max_hops": MAX_TAKEOVER_HOPS,
        "failure_class": failure_class,
        "trip": trip,
        "host": host,
        "isolation": plan.get("isolation"),
        "next_target": plan["targets"][0],
        "targets": plan["targets"],
        "skipped": plan["skipped"],
        "salvage": salvage,
    }


def _add_common_flags(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--host", default="t3", choices=HOST_CHOICES, help="target host adapter")
    sub.add_argument("--capabilities", default="", help="path to JSON capabilities snapshot (for --host t3)")
    sub.add_argument("--environment-id", default="", help="linked environment ID (forces isolation: shared)")
    sub.add_argument("--no-live", action="store_true", help="skip live capability filtering")
    sub.add_argument("--health-file", default="", help="override provider health JSON path")
    sub.add_argument("--json", action="store_true", help="emit JSON output")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stdlib model routing preflight, host adapters, circuit breaker and 2-hop takeover."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pre = sub.add_parser("preflight", help="resolve ordered eligible targets for a category or explicit model")
    p_pre.add_argument("--category", default="", help="routing category")
    p_pre.add_argument("--of", dest="of_category", default="", help="reviewed category (required with --category review)")
    p_pre.add_argument("--builder", default="", help="builder provider to exclude on review")
    p_pre.add_argument("--model", default="", help="explicit model ID or alias")
    p_pre.add_argument("--effort", default="", help="explicit effort override")
    _add_common_flags(p_pre)

    p_take = sub.add_parser("takeover", help="record a provider failure and compute a 2-hop fallback target")
    p_take.add_argument("--category", required=True, help="routing category")
    p_take.add_argument("--of", dest="of_category", default="", help="reviewed category")
    p_take.add_argument("--builder", default="", help="builder provider to exclude on review")
    p_take.add_argument("--failed-provider", required=True, help="provider that failed")
    p_take.add_argument("--failed-model", default="", help="model that failed")
    p_take.add_argument("--error", required=True, help="failure message to classify")
    p_take.add_argument("--attempt", type=int, default=0, help="prior takeover hop count (0-indexed)")
    p_take.add_argument("--worktree", default="", help="optional worker worktree path to inspect for salvage")
    _add_common_flags(p_take)

    p_health = sub.add_parser("health", help="show active circuit breaker trips")
    p_health.add_argument("--health-file", default="", help="override provider health JSON path")
    p_health.add_argument("--json", action="store_true", help="emit JSON output")

    p_rec = sub.add_parser("record-failure", help="classify and record a provider circuit breaker trip")
    p_rec.add_argument("--provider", required=True, help="provider key")
    p_rec.add_argument("--error", required=True, help="error message")
    p_rec.add_argument("--ttl", type=int, default=ph.DEFAULT_TTL_SECONDS, help="trip TTL in seconds")
    p_rec.add_argument("--health-file", default="", help="override provider health JSON path")
    p_rec.add_argument("--json", action="store_true", help="emit JSON output")

    p_clr = sub.add_parser("clear-health", help="clear one provider trip or all active trips")
    p_clr.add_argument("--provider", default="", help="optional single provider key to clear")
    p_clr.add_argument("--health-file", default="", help="override provider health JSON path")
    p_clr.add_argument("--json", action="store_true", help="emit JSON output")

    args = parser.parse_args(argv)
    health_path = Path(args.health_file).expanduser() if getattr(args, "health_file", "") else None

    try:
        if args.cmd == "health":
            payload = ph.load_health(health_path)
            print(json.dumps(payload, indent=2) if args.json else f"active trips: {sorted(payload['providers'].keys())}")
            return 0
        if args.cmd == "record-failure":
            payload = ph.record_failure(args.provider, args.error, path=health_path, ttl_seconds=args.ttl)
            print(json.dumps(payload, indent=2) if args.json else f"{args.provider}: tripped={payload['tripped']} class={payload['failure_class']}")
            return 0
        if args.cmd == "clear-health":
            payload = ph.clear_health(args.provider or None, path=health_path)
            print(json.dumps(payload, indent=2) if args.json else f"cleared={payload['cleared']} active={payload['active_trips']}")
            return 0
        cap_path = Path(args.capabilities).expanduser() if args.capabilities else None
        if args.cmd == "preflight":
            if not args.category and not args.model:
                parser.error("pass --category or --model")
            payload = run_preflight(
                category=args.category,
                host=args.host,
                of_category=args.of_category,
                builder=args.builder,
                explicit_model=args.model,
                explicit_effort=args.effort,
                capabilities_path=cap_path,
                environment_id=args.environment_id,
                no_live=args.no_live,
                health_path=health_path,
            )
            print(json.dumps(payload, indent=2) if args.json else f"ok={payload['ok']} host={payload['host']} targets={len(payload['targets'])}")
            return 0 if payload["ok"] else 3
        rc_code, payload = run_takeover(
            category=args.category,
            failed_provider=args.failed_provider,
            error_text=args.error,
            attempt=args.attempt,
            host=args.host,
            failed_model=args.failed_model,
            of_category=args.of_category,
            builder=args.builder,
            worktree=args.worktree,
            capabilities_path=cap_path,
            environment_id=args.environment_id,
            no_live=args.no_live,
            health_path=health_path,
        )
        print(json.dumps(payload, indent=2) if args.json else f"action={payload['action']} reason={payload.get('reason', '')}")
        return rc_code
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
