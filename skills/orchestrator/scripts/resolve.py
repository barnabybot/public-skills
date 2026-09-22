#!/usr/bin/env python3
"""Resolve a spawn route from the SKILL.md table and live CodexBar capacity.

Called by cross-cutting/cmux/scripts/spawn-workspace.sh. Prints shell-safe
KEY=value lines for `eval`. Exit 0 resolved; exit 3 a ruling is needed (every
candidate exhausted or excluded), with ROUTE_ASK naming them; exit 2 bad input.

    resolve.py --tier E [--reason TEXT]
    resolve.py --tier R --of F --builder claude
    resolve.py --model claude-fable-5-1 --effort high [--agent claude]
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

try:
    import yaml
except ImportError:  # PyYAML is not in the standard library.
    sys.exit(
        "resolve.py needs PyYAML to read references/routing-metadata.yaml.\n"
        "Install it with:  pip install PyYAML\n"
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
        if cells[0] == "Tier" or all(set(cell) <= set("-: ") for cell in cells):
            continue
        if len(cells) != 6:
            raise ValueError("routing rows must have six columns")
        tier, name, first, effort, backup, backup_effort = cells
        if tier in seen or tier not in canon["tiers"]:
            raise ValueError(f"duplicate or unknown tier: {tier}")
        seen.add(tier)
        row = canon["tiers"][tier]
        row["metadata_name"] = row["name"]
        row["name"] = name
        if row.get("of") == "required":
            if cells[2:] != ["Inherit reviewed tier", "—", "Exclude builder", "—"]:
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

    def assess(self, provider: str, scoped_window: str | None = None) -> dict:
        """Return {state, detail} with state in held|tight|exhausted|unread."""
        entry = self.read(provider)
        if not entry:
            why = "no CodexBar provider" if not (self.canon["providers"].get(provider) or {}).get("codexbar") else "capacity unread"
            return {"state": "unread", "detail": f"{provider} {why}"}
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
            if worst is None or used > worst[0]:
                worst = (used, detail)
        pace = ((entry.get("pace") or {}).get("secondary") or {})
        if pace.get("willLastToReset") is False:
            return {"state": "tight", "detail": (worst[1] if worst else f"{provider} weekly") + "; tight, pace runs out before reset"}
        if worst is None:
            return {"state": "unread", "detail": f"{provider} capacity unread"}
        return {"state": "held", "detail": worst[1]}


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
            seat = " → the tier of the work it checks, on another provider (--of, --builder)"
        lines.append(f"  {key:<11} {row['name']}: {row['what']}{seat}")
    legacy = ", ".join(f"{k}→{v}" for k, v in (canon.get("legacy_tiers") or {}).items())
    if legacy:
        lines.append(f"  legacy      {legacy} (deprecated words, one release)")
    return "\n".join(lines)


def resolve_tier(canon: dict, args: argparse.Namespace) -> int:
    tiers = canon["tiers"]
    legacy = canon.get("legacy_tiers") or {}
    key = args.tier
    legacy_note = ""
    if key in legacy:
        legacy_note = f"legacy tier word {key} resolved to {legacy[key]}; pass the letter next time"
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
        if pinfo.get("inferred", True) is False:
            tried.append(f"{label_c}: only when named, allowance unreadable")
            continue
        state = cap.assess(provider, model.get("scoped_window"))
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
    cap = Capacity(canon, disabled=args.no_capacity)
    state = cap.assess(model["provider"], model.get("scoped_window"))
    label = args.tier or "explicit"
    base = args.reason or "named in request"
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
    emit(pairs)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier")
    ap.add_argument("--of")
    ap.add_argument("--builder")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--agent")
    ap.add_argument("--reason")
    ap.add_argument("--no-capacity", action="store_true")
    ap.add_argument("--list-tiers", action="store_true")
    ap.add_argument("--skill", default=str(DEFAULT_SKILL))
    args = ap.parse_args(argv)
    try:
        canon = load_canon(Path(args.skill))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        sys.stderr.write(f"invalid routing table: {exc}\n")
        return 2
    if args.list_tiers:
        print(list_tiers(canon))
        return 0
    if args.model:
        return resolve_model(canon, args)
    if args.tier:
        return resolve_tier(canon, args)
    sys.stderr.write("pass --tier <letter>, or --model <id> with --effort <level>\n" + list_tiers(canon) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
