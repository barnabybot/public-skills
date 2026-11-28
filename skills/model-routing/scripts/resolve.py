#!/usr/bin/env python3
"""Stdlib shell-eval resolver for cmux spawn-workspace.sh backed by routing-catalog.json."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import routing_catalog as rc

LEGACY_TIERS = {
    "A": "housekeeping",
    "B": "classification",
    "C": "coding",
    "D": "writing",
    "E": "systems",
    "basic": "housekeeping",
}


def _emit(values: dict[str, str]) -> None:
    for key, val in values.items():
        print(f"{key}={shlex.quote(str(val))}")


def _allowed_from_request(request_path: str) -> set[str] | None:
    if not request_path:
        return None
    data = json.loads(Path(request_path).expanduser().read_text(encoding="utf-8"))
    auth = data.get("authorisation") or data.get("authorization") or {}
    providers = auth.get("providers")
    if isinstance(providers, list):
        return {str(p) for p in providers}
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve model routing for shell callers.")
    parser.add_argument("--list-tiers", action="store_true")
    parser.add_argument("--tier", default="")
    parser.add_argument("--of", dest="of_tier", default="")
    parser.add_argument("--builder", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--agent", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--runtime-cwd", default="")
    parser.add_argument("--request", default="")
    parser.add_argument("--bundle-out", default="")
    parser.add_argument("--verify-bundle", default="")
    args = parser.parse_args(argv)

    catalog = rc.load_catalog()
    if args.list_tiers:
        for key, row in catalog["categories"].items():
            print(f"  {key:15s} {row['name']}")
        return 0

    allowed_providers = _allowed_from_request(args.request)
    legacy_note = ""

    if args.model:
        found = rc.find_model(catalog, args.model)
        if found is None:
            provider_key = "provider_a"
            agent = args.agent or "claude"
            model_id = args.model
            display = args.model
            effort = args.effort or "unset"
        else:
            provider_key = found["provider"]
            provider = catalog["providers"][provider_key]
            agent = args.agent or str(provider.get("agent") or "claude")
            model_id = found["id"]
            display = found["display"]
            effort = args.effort or "unset"
        if allowed_providers is not None and provider_key not in allowed_providers:
            _emit({"ROUTE_TIER": args.tier or "explicit", "ROUTE_ASK": f"request does not authorise {provider_key}"})
            return 3
        reason_part = f" ({args.reason})" if args.reason else ""
        route_line = f"route: explicit {display} · {effort} ({provider_key}) · capacity unread{reason_part}"
        _emit(
            {
                "ROUTE_AGENT": agent,
                "ROUTE_MODEL": model_id,
                "ROUTE_MODEL_ID": model_id,
                "ROUTE_EFFORT": effort,
                "ROUTE_TIER": args.tier or "explicit",
                "ROUTE_LINE": route_line,
            }
        )
        return 0

    tier = args.tier
    if tier in LEGACY_TIERS:
        mapped = LEGACY_TIERS[tier]
        legacy_note = f"legacy tier word {tier} resolved to {mapped}"
        tier = mapped

    if tier not in catalog["categories"]:
        print(f"unknown tier: {args.tier}", file=sys.stderr)
        return 2

    if tier == "review":
        if not args.of_tier or args.of_tier not in catalog["categories"] or args.of_tier == "review":
            print("review requires --of naming a non-review category", file=sys.stderr)
            return 2
        chain = catalog["categories"][args.of_tier]["chain"]
        tier_label = f"review of {args.of_tier}"
    else:
        chain = catalog["categories"][tier]["chain"]
        tier_label = tier

    chosen = None
    for slot in chain:
        model = rc.model_entry(catalog, slot["model"], slot["effort"])
        pkey = model["provider"]
        provider = catalog["providers"][pkey]
        if provider.get("enabled") is False:
            continue
        if tier == "review" and args.builder and pkey == args.builder:
            continue
        if allowed_providers is not None and pkey not in allowed_providers:
            continue
        chosen = (pkey, provider, model, slot["effort"])
        break

    if chosen is None:
        _emit({"ROUTE_TIER": tier, "ROUTE_ASK": "request does not authorise any eligible provider"})
        return 3

    pkey, provider, model, effort = chosen
    reason_part = f" · {args.reason}" if args.reason else ""
    route_line = f"route: tier {tier_label} → {model['display']} · {effort} ({pkey}) · capacity unread{reason_part}"
    out = {
        "ROUTE_AGENT": str(provider.get("agent") or "claude"),
        "ROUTE_MODEL": model["id"],
        "ROUTE_MODEL_ID": model["id"],
        "ROUTE_EFFORT": effort,
        "ROUTE_TIER": tier,
        "ROUTE_LINE": route_line,
    }
    if legacy_note:
        out["ROUTE_LEGACY_NOTE"] = legacy_note
    _emit(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
