#!/usr/bin/env python3
"""Resolve a spawn route from the SKILL.md table and live CodexBar capacity.

Called by cross-cutting/cmux/scripts/spawn-workspace.sh. Prints shell-safe
KEY=value lines for `eval`. Exit 0 resolved; exit 3 a ruling is needed (every
candidate exhausted or excluded), with ROUTE_ASK naming them; exit 2 bad input.

    resolve.py --tier systems [--reason TEXT]
    resolve.py --tier review --of writing --builder provider_a
    resolve.py --model claude-opus-5-5 --effort high [--agent claude]
    resolve.py --list-tiers

Test hooks: ROUTING_FIXTURE_DIR (read <dir>/<provider>.json instead of
CodexBar; a missing file is unread), ROUTING_NOW (ISO instant used for
hours-to-reset), --no-capacity (every provider unread), --skill PATH.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_capacity import assess_native, pace_vs_reset
from route_bundle import verify_route_bundle, write_route_bundle

try:
    import yaml
except ImportError:  # PyYAML is not in the standard library.
    sys.exit(
        "resolve.py needs PyYAML to read references/routing-metadata.yaml.\n"
        "Install it with:  python3 -m pip install --user PyYAML\n"
    )

HERE = Path(__file__).resolve().parent
DEFAULT_SKILL = HERE.parent / "SKILL.md"


def load_canon(path: Path) -> dict:
    """Read preferences from the visible table and join provider metadata."""
    metadata = path.parent / "references" / "routing-metadata.yaml"
    canon = yaml.safe_load(metadata.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- routing-table:start -->", "<!-- routing-table:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("SKILL.md needs one marked routing table")
    table = text.split(start, 1)[1].split(end, 1)[0]
    models = {m["display"]: key for key, m in canon["models"].items()}
    seen = set()
    for line in table.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "Category" or all(set(cell) <= set("-: ") for cell in cells):
            continue
        if len(cells) != 7:
            raise ValueError("routing rows must have seven columns")
        tier, name, _use_when, first, effort, backup, backup_effort = cells
        if tier in seen or tier not in canon["tiers"]:
            raise ValueError(f"duplicate or unknown tier: {tier}")
        seen.add(tier)
        row = canon["tiers"][tier]
        row["metadata_name"] = row["name"]
        row["name"] = name
        if row.get("of") == "required":
            if cells[3:] != ["Inherit reviewed category", "—", "Exclude builder", "—"]:
                raise ValueError("review must inherit its tier and exclude the builder")
            continue
        for slot, model, level in (("first", first, effort), ("backup", backup, backup_effort)):
            if model not in models:
                raise ValueError(f"unknown model in tier {tier}: {model}")
            key = models[model]
            provider = canon["models"][key]["provider"]
            if level not in canon["providers"][provider]["efforts"]:
                raise ValueError(f"invalid effort for {model}: {level}")
            row[slot] = {"model": key, "effort": level}
        if canon["models"][row["first"]["model"]]["provider"] == canon["models"][row["backup"]["model"]]["provider"]:
            raise ValueError(f"tier {tier} requires a backup on another provider")
    missing = set(canon["tiers"]) - seen
    if missing:
        raise ValueError(f"routing table missing tiers: {', '.join(sorted(missing))}")
    return canon


def now_utc() -> datetime:
    override = os.environ.get("ROUTING_NOW")
    if override:
        return datetime.fromisoformat(override.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def parse_instant(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_request(path: str | None) -> dict | None:
    """Read a structured dispatch request. None means the caller passed no file."""
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"routing request is missing or unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("routing request must be a JSON object")
    tools = data.get("required_tools", [])
    if not isinstance(tools, list) or any(not isinstance(item, str) or not item for item in tools):
        raise ValueError("required_tools must be a list of tool names")
    authority = data.get("authorisation", {})
    if authority:
        if not isinstance(authority, dict):
            raise ValueError("authorisation must be an object")
        providers = authority.get("providers", [])
        if not isinstance(providers, list) or any(not isinstance(item, str) or not item for item in providers):
            raise ValueError("authorisation.providers must be a list of provider names")
        source = authority.get("source", "")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("authorisation.source needs nonblank text. Name the brief that authorises the providers.")
    bound = data.get("bounded_preference", {})
    if bound:
        if not isinstance(bound, dict):
            raise ValueError("bounded_preference must be an object")
        if bound.get("tasks") != 1 or not isinstance(bound.get("task"), str) or not bound["task"].strip():
            raise ValueError("bounded_preference admits one named task. Set tasks to 1 and name the task.")
        if not isinstance(bound.get("source"), str) or not bound["source"].strip():
            raise ValueError("bounded_preference.source needs nonblank text")
    if "capacity" in data and data["capacity"] not in ("required", "optional"):
        raise ValueError("capacity must be required or optional")
    return data


def local_stamp(instant: datetime, tzname: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        local = instant.astimezone(ZoneInfo(tzname))
        label = "HKT" if tzname == "Asia/Hong_Kong" else local.tzname() or tzname
    except Exception:  # zoneinfo missing or unknown zone: fixed +8 for HKT
        local = instant.astimezone(timezone(timedelta(hours=8)))
        label = "HKT"
    return local.strftime(f"%a %d %b %H:%M {label}")


class Capacity:
    """One scoped CodexBar read per provider, cached, with fixture support."""

    def __init__(self, canon: dict, disabled: bool = False):
        self.canon = canon
        self.cfg = canon.get("capacity", {})
        self.disabled = disabled
        self.fixture_dir = os.environ.get("ROUTING_FIXTURE_DIR")
        self.cache: dict[str, dict | None] = {}

    def read(self, provider: str) -> dict | None:
        if provider in self.cache:
            return self.cache[provider]
        entry = None
        codexbar_name = (self.canon["providers"].get(provider) or {}).get("codexbar")
        if self.disabled or not codexbar_name:
            self.cache[provider] = None
            return None
        if self.fixture_dir:
            path = Path(self.fixture_dir) / f"{provider}.json"
            if path.exists():
                try:
                    entry = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    entry = None
        else:
            cmd = ["codexbar", "usage", "--provider", codexbar_name, "--format", "json", "--no-color"]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=float(self.cfg.get("read_timeout_seconds", 20)),
                )
                if proc.returncode == 0:
                    entry = json.loads(proc.stdout)
            except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
                entry = None
        if isinstance(entry, list):
            entry = next((e for e in entry if e.get("provider") == codexbar_name), None)
        self.cache[provider] = entry if isinstance(entry, dict) else None
        return self.cache[provider]

    def assess(self, provider: str, scoped_window: str | None = None, model_id: str | None = None,
               effort: str | None = None, request: dict | None = None) -> dict:
        """Return {state, detail} with state in held|tight|exhausted|unread."""
        entry = self.read(provider)
        if not entry:
            why = "no CodexBar provider" if not (self.canon["providers"].get(provider) or {}).get("codexbar") else "capacity unread"
            return {"state": "unread", "detail": f"{provider} {why}"}
        native = entry.get("native")
        if isinstance(native, dict) and native.get("kind") == "codex" and model_id and request is not None:
            return self._assess_native(provider, native, model_id, effort or "", request)
        usage = entry.get("usage") or {}
        windows = [("weekly", usage.get("secondary")), ("5-hour", usage.get("primary"))]
        if scoped_window:
            for extra in usage.get("extraRateWindows") or []:
                if extra.get("id") == scoped_window:
                    windows.append((extra.get("title") or scoped_window, extra.get("window")))
        threshold = int(self.cfg.get("exhausted_used_percent", 95))
        min_hours = float(self.cfg.get("exhausted_min_hours_to_reset", 1))
        tz = self.cfg.get("timezone", "Asia/Hong_Kong")
        now = now_utc()
        worst = None
        pace_block = (entry.get("pace") or {}).get("secondary") or {}
        pace_known = isinstance(pace_block.get("willLastToReset"), bool)
        computed_tight = False
        for name, win in windows:
            if not isinstance(win, dict) or win.get("usedPercent") is None:
                continue
            used = int(win["usedPercent"])
            resets = parse_instant(win.get("resetsAt") or "")
            hours = (resets - now).total_seconds() / 3600 if resets else None
            stamp = local_stamp(resets, tz) if resets else "reset unknown"
            detail = f"{provider} {name} {used}% used, resets {stamp}"
            if used >= threshold and (hours is None or hours > min_hours):
                return {"state": "exhausted", "detail": detail}
            minutes = win.get("windowMinutes")
            if (not pace_known and isinstance(minutes, (int, float)) and not isinstance(minutes, bool)
                    and minutes > 0 and resets is not None):
                seconds_left = (resets - now).total_seconds()
                if seconds_left > 0 and pace_vs_reset(used, float(minutes), seconds_left) == "ahead":
                    computed_tight = True
                    detail = detail + "; ahead of schedule, pace runs out before reset"
            if worst is None or used > worst[0]:
                worst = (used, detail)
        pace = ((entry.get("pace") or {}).get("secondary") or {})
        if pace.get("willLastToReset") is False or computed_tight:
            return {"state": "tight", "detail": (worst[1] if worst else f"{provider} weekly") + "; tight, pace runs out before reset"}
        if worst is None:
            return {"state": "unread", "detail": f"{provider} capacity unread"}
        return {"state": "held", "detail": worst[1]}

    def _assess_native(self, provider: str, observation: dict, model_id: str, effort: str, request: dict) -> dict:
        cfg = dict(self.cfg)
        cfg.setdefault("max_observation_age_seconds", 300)
        cfg.setdefault("exhausted_used_percent", 95)
        required = set(request.get("required_tools") or [])
        evidence = {
            "fit": request.get("fit") or "practice",
            "debit_reason": "bounded native observation",
        }
        result = assess_native(observation, model_id, effort, required, evidence, request, cfg, now_utc())
        detail = "; ".join(result.get("reasons") or []) or f"{provider} native observation"
        state = result.get("state")
        if state == "eligible":
            return {"state": "tight" if result.get("tight") else "held", "detail": detail}
        if state == "excluded":
            return {"state": "exhausted", "detail": detail}
        return {"state": "unread", "detail": detail}


def emit(pairs: dict, stream=sys.stdout) -> None:
    for key, value in pairs.items():
        stream.write(f"{key}={shlex.quote('' if value is None else str(value))}\n")


def model_entry(canon: dict, key: str) -> dict:
    m = dict(canon["models"][key])
    m["key"] = key
    return m


def find_model_by_id(canon: dict, model_id: str) -> dict | None:
    for key, m in canon["models"].items():
        if m.get("id") == model_id:
            return model_entry(canon, key)
    return None


def route_pairs(canon: dict, tier_key: str, tier_name: str, model: dict, effort: str,
                default: dict, default_effort: str, status: str, reason: str) -> dict:
    provider = model["provider"]
    agent = canon["providers"][provider]["agent"]
    dispatched_display = f"{model['display']} · {effort}"
    default_display = f"{default['display']} · {default_effort}"
    line = f"route: tier {tier_key} → {dispatched_display} ({provider}) | default {default_display} | {reason}"
    return {
        "ROUTE_STATUS": status,
        "ROUTE_TIER": tier_key,
        "ROUTE_TIER_NAME": tier_name,
        "ROUTE_AGENT": agent,
        "ROUTE_PROVIDER": provider,
        "ROUTE_MODEL": model["id"] if model.get("pass_model", True) else "",
        "ROUTE_MODEL_ID": model["id"],
        "ROUTE_DISPLAY": model["display"],
        "ROUTE_EFFORT": effort,
        "ROUTE_DEFAULT": f"tier {tier_key} → {default['id']} · {default_effort}",
        "ROUTE_DEFAULT_DISPLAY": default_display,
        "ROUTE_DISPATCHED": f"{model['id']} · {effort}",
        "ROUTE_DISPATCHED_DISPLAY": dispatched_display,
        "ROUTE_REASON": reason,
        "ROUTE_LINE": line,
    }


def list_tiers(canon: dict) -> str:
    lines = []
    for key, row in canon["tiers"].items():
        first = row.get("first")
        seat = ""
        if first:
            m = canon["models"][first["model"]]
            seat = f" → {m['display']} · {first['effort']}"
        elif row.get("of") == "required":
            seat = " → the category of the work it checks, on another provider (--of, --builder)"
        lines.append(f"  {key:<15} {row['name']}: {row['what']}{seat}")
    legacy = ", ".join(f"{k}→{v}" for k, v in (canon.get("legacy_tiers") or {}).items())
    if legacy:
        lines.append(f"  legacy          {legacy} (deprecated words, one release)")
    return "\n".join(lines)


def resolve_tier(canon: dict, args: argparse.Namespace) -> int:
    tiers = canon["tiers"]
    legacy = canon.get("legacy_tiers") or {}
    key = args.tier
    legacy_note = ""
    if key in legacy:
        legacy_note = f"legacy tier word {key} resolved to {legacy[key]}; pass the category next time"
        key = legacy[key]
    if key not in tiers:
        sys.stderr.write(f"unknown tier: {args.tier}\n{list_tiers(canon)}\n")
        return 2
    row = tiers[key]
    builder = None
    label = key
    if row.get("of") == "required":
        if not args.of or not args.builder:
            sys.stderr.write(f"tier {key} needs --of <tier of the work> and --builder <provider>\n")
            return 2
        args.of = legacy.get(args.of, args.of)
        if args.of not in tiers or tiers[args.of].get("of") == "required":
            sys.stderr.write(f"--of must name a tier with a seat, got {args.of}\n")
            return 2
        builder = args.builder
        label = f"{key} of {args.of}"
        row = tiers[args.of]
    first = row["first"]
    candidates = [("first", first), ("backup", row["backup"])]
    default_model = model_entry(canon, first["model"])
    cap = Capacity(canon, disabled=args.no_capacity)
    request = getattr(args, "loaded_request", None)
    allowed = []
    if isinstance(request, dict):
        allowed = list((request.get("authorisation") or {}).get("providers") or [])
    tried: list[str] = []        # human lines for the exit-3 message
    exhausted: list[str] = []    # capacity details behind an override
    for slot, cand in candidates:
        model = model_entry(canon, cand["model"])
        provider = model["provider"]
        pinfo = canon["providers"][provider]
        label_c = f"{slot} {model['display']} · {cand['effort']}"
        if builder and provider == builder:
            tried.append(f"{label_c}: excluded, builder's provider")
            continue
        if allowed and provider not in allowed:
            tried.append(f"{label_c}: excluded, request does not authorise {provider}")
            continue
        if pinfo.get("inferred", True) is False:
            tried.append(f"{label_c}: only when named, allowance unreadable")
            continue
        state = cap.assess(
            provider, model.get("scoped_window"), model.get("id"), cand["effort"],
            request if isinstance(request, dict) else None,
        )
        if isinstance(request, dict) and request.get("capacity") == "required" and state["state"] == "unread":
            tried.append(f"{label_c}: capacity required and unread, {state['detail']}")
            continue
        if state["state"] == "exhausted":
            tried.append(f"{label_c}: exhausted, {state['detail']}")
            exhausted.append(state["detail"])
            continue
        if slot == "first":
            status = "held" if state["state"] == "held" else state["state"]
            reason = {"held": "held", "tight": "held (tight)", "unread": "held (capacity unread)"}[state["state"]]
            reason = f"{reason}: {state['detail']}"
        else:
            status = "override"
            reason = "override: " + ("; ".join(exhausted) if exhausted else "first preference excluded")
            if state["state"] == "tight":
                reason += "; backup tight"
            elif state["state"] == "unread":
                reason += "; backup capacity unread"
        if args.reason:
            reason = f"{reason}. {args.reason}"
        if legacy_note:
            reason = f"{reason}. {legacy_note}"
        pairs = route_pairs(canon, label, row["name"], model, cand["effort"],
                            default_model, first["effort"], status, reason)
        pairs["ROUTE_LEGACY_NOTE"] = legacy_note
        maybe_write_bundle(args, pairs)
        emit(pairs)
        return 0
    ask = "; ".join(tried)
    emit({"ROUTE_STATUS": "ask", "ROUTE_TIER": label, "ROUTE_TIER_NAME": row["name"], "ROUTE_ASK": ask,
          "ROUTE_DEFAULT": f"tier {label} → {default_model['id']} · {first['effort']}"})
    sys.stderr.write(f"a ruling is needed for tier {label}: {ask}\n")
    return 3


def resolve_model(canon: dict, args: argparse.Namespace) -> int:
    model = find_model_by_id(canon, args.model)
    if model is None:
        provider = args.agent or ""
        if provider not in canon["providers"]:
            sys.stderr.write(f"model {args.model} is not in the model inventory; pass --agent so its provider is known\n")
            return 2
        model = {"key": None, "id": args.model, "provider": provider, "display": args.model}
    effort = args.effort or ""
    label = args.tier or "explicit"
    base = args.reason or "named in request"
    cap = Capacity(canon, disabled=args.no_capacity)
    request = getattr(args, "loaded_request", None)
    if isinstance(request, dict):
        allowed = list((request.get("authorisation") or {}).get("providers") or [])
        if allowed and model["provider"] not in allowed:
            ask = f"{model['display']} · {effort or 'effort unset'}: excluded, request does not authorise {model['provider']}"
            emit({"ROUTE_STATUS": "ask", "ROUTE_TIER": label, "ROUTE_TIER_NAME": "explicit model",
                  "ROUTE_ASK": ask, "ROUTE_DEFAULT": f"{model['id']} · {effort or 'effort unset'}"})
            sys.stderr.write(f"{base}: {ask}\n")
            return 3
    state = cap.assess(
        model["provider"], model.get("scoped_window"), model.get("id"), effort,
        request if isinstance(request, dict) else None,
    )
    if isinstance(request, dict) and request.get("capacity") == "required" and state["state"] == "unread":
        ask = f"{model['display']} · {effort or 'effort unset'}: capacity required and unread, {state['detail']}"
        emit({"ROUTE_STATUS": "ask", "ROUTE_TIER": label, "ROUTE_TIER_NAME": "explicit model",
              "ROUTE_ASK": ask, "ROUTE_DEFAULT": f"{model['id']} · {effort or 'effort unset'}"})
        sys.stderr.write(f"{base}: {ask}\n")
        return 3
    if state["state"] == "exhausted":
        emit({"ROUTE_STATUS": "ask", "ROUTE_TIER": label, "ROUTE_TIER_NAME": "explicit model",
              "ROUTE_ASK": f"{model['display']} · {effort or 'effort unset'}: exhausted, {state['detail']}",
              "ROUTE_DEFAULT": f"{model['id']} · {effort or 'effort unset'}"})
        sys.stderr.write(f"{base}: {model['display']} is exhausted ({state['detail']})\n")
        return 3
    suffix = {"held": "", "tight": "; tight", "unread": "; capacity unread"}[state["state"]]
    reason = f"{base}: {state['detail']}{suffix}"
    if not effort:
        reason += "; effort unset, CLI default"
    pairs = route_pairs(canon, label, "explicit model", model, effort or "unset",
                        model, effort or "unset", "explicit", reason)
    pairs["ROUTE_LEGACY_NOTE"] = ""
    maybe_write_bundle(args, pairs)
    emit(pairs)
    return 0


def maybe_write_bundle(args: argparse.Namespace, pairs: dict) -> None:
    if not getattr(args, "bundle_out", None):
        return
    if not getattr(args, "runtime_cwd", ""):
        args.runtime_cwd = str(Path.cwd())
    write_route_bundle(Path(args.bundle_out), args, now_utc().isoformat(), pairs, now_utc())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier")
    ap.add_argument("--of")
    ap.add_argument("--builder")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--agent")
    ap.add_argument("--reason")
    ap.add_argument("--runtime-cwd", default="", help="Directory the spawned seat will use")
    ap.add_argument("--request", help="JSON task authority, tools and bounded preference")
    ap.add_argument("--bundle-out", help="Write a verified route bundle for a fast second launch")
    ap.add_argument("--verify-bundle", help="Reuse a fresh route bundle instead of resolving again")
    ap.add_argument("--no-capacity", action="store_true")
    ap.add_argument("--list-tiers", action="store_true")
    ap.add_argument("--skill", default=str(DEFAULT_SKILL))
    args = ap.parse_args(argv)
    if not args.runtime_cwd:
        args.runtime_cwd = str(Path.cwd())
    try:
        canon = load_canon(Path(args.skill))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        sys.stderr.write(f"invalid routing table: {exc}\n")
        return 2
    if args.bundle_out and (args.no_capacity or args.verify_bundle):
        sys.stderr.write("--bundle-out cannot be combined with --no-capacity or --verify-bundle\n")
        return 2
    if args.verify_bundle and args.no_capacity:
        sys.stderr.write("--verify-bundle cannot be combined with --no-capacity\n")
        return 2
    try:
        args.loaded_request = load_request(args.request)
    except ValueError as exc:
        sys.stderr.write(f"invalid routing request: {exc}\n")
        return 2
    if args.verify_bundle:
        rc, pairs, err = verify_route_bundle(Path(args.verify_bundle), canon, args, now_utc())
        if pairs:
            emit(pairs)
        if rc != 0:
            sys.stderr.write(f"route bundle verification failed: {err}\n")
        return rc
    if args.list_tiers:
        print(list_tiers(canon))
        return 0
    if args.model:
        return resolve_model(canon, args)
    if args.tier:
        return resolve_tier(canon, args)
    sys.stderr.write("pass --tier <category>, or --model <id> with --effort <level>\n" + list_tiers(canon) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
