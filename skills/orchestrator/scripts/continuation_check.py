#!/usr/bin/env python3
"""Judge coordinator continuation cases and push-approval consumption.

python3 scripts/continuation_check.py judge CASE.json --json
python3 scripts/continuation_check.py apply CASE.json --approval ID --target TARGET --result rejected --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GATE_KIND = {
    "direct-release": "decision",
    "author-decision": "decision",
    "push-approval": "push",
    "pr-approval": "pr",
    "merge-approval": "merge",
    "contact": "contact",
}


class CaseError(Exception):
    pass


def load_case(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseError(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise CaseError(f"{path}: expected an object with an items list")
    if not isinstance(data.get("approvals", []), list):
        raise CaseError(f"{path}: approvals must be a list")
    return data


def remaining(approval: dict) -> int:
    return int(approval["authorised"]) - int(approval["used"])


def covers(approval: dict, item: dict) -> bool:
    gate = item.get("gate")
    if not gate:
        return False
    kind = GATE_KIND.get(gate)
    if kind is None or approval.get("kind") != kind:
        return False
    if remaining(approval) <= 0:
        return False
    if kind in ("decision", "contact"):
        scope = approval.get("scope") or []
        return item.get("id") in scope
    approved = approval.get("target")
    wanted = item.get("target")
    if approved or wanted:
        return bool(approved) and approved == wanted
    return kind in ("pr", "merge")


def judge(case: dict) -> dict:
    threshold = int(case.get("recycle_percent", 30))
    handoff = int(case.get("context_percent", 0)) >= threshold
    ready: list[dict] = []
    held: list[dict] = []
    in_flight: list[dict] = []
    approvals = case.get("approvals") or []
    for item in case.get("items") or []:
        entry = {"item": item["id"], "owner": item.get("owner", "")}
        if item.get("in_flight"):
            in_flight.append(entry)
            continue
        if item.get("conflict"):
            if item.get("authority") == "clarify":
                ready.append({**entry, "action": item.get("action", "clarify")})
            else:
                held.append({**entry, "gate": "ownership"})
            continue
        gate = item.get("gate")
        if not gate and item.get("authority"):
            ready.append({**entry, "action": item["action"]})
            continue
        if gate and any(covers(approval, item) for approval in approvals):
            ready.append({**entry, "action": item["action"]})
            continue
        held.append({**entry, "gate": gate or "authority"})
    spent = []
    for approval in approvals:
        if approval.get("kind") != "push":
            continue
        used = int(approval["used"])
        authorised = int(approval["authorised"])
        spent.append(
            {
                "id": approval["id"],
                "used": used,
                "authorised": authorised,
                "remaining": authorised - used,
            }
        )
    return {
        "handoff": handoff,
        "next": ready,
        "spent": spent,
        "held": held,
        "in_flight": in_flight,
    }


def approval_view(approval: dict) -> dict:
    used = int(approval["used"])
    authorised = int(approval["authorised"])
    view = {
        "id": approval["id"],
        "used": used,
        "authorised": authorised,
        "remaining": authorised - used,
    }
    if "target" in approval:
        view["target"] = approval["target"]
    return view


def apply_case(case: dict, approval_id: str, target: str, result: str) -> dict:
    if result not in ("rejected", "accepted"):
        raise CaseError("result must be rejected or accepted")
    match = next(
        (item for item in case.get("approvals") or [] if item.get("id") == approval_id),
        None,
    )
    decision_before = judge(case)
    if match is None:
        return {
            "applied": False,
            "reason": "missing",
            "approval": None,
            "decision": decision_before,
        }
    if match.get("target") != target:
        return {
            "applied": False,
            "reason": "target",
            "approval": approval_view(match),
            "decision": decision_before,
        }
    if remaining(match) <= 0:
        return {
            "applied": False,
            "reason": "spent",
            "approval": approval_view(match),
            "decision": decision_before,
        }
    match["used"] = int(match["used"]) + 1
    return {
        "applied": True,
        "reason": None,
        "approval": approval_view(match),
        "decision": judge(case),
    }


def emit(payload: dict, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
        return
    if "decision" in payload:
        print(f"applied: {str(payload['applied']).lower()}")
        print(f"reason: {payload['reason']}")
        payload = payload["decision"]
    print(f"handoff: {str(payload['handoff']).lower()}")
    for row in payload["next"]:
        print(f"next: {row['item']} {row['owner']} {row['action']}")
    for row in payload["spent"]:
        print(
            f"spent: {row['id']} used {row['used']} of {row['authorised']} remaining {row['remaining']}"
        )
    for row in payload["held"]:
        print(f"held: {row['item']} {row['owner']} {row['gate']}")
    for row in payload["in_flight"]:
        print(f"in_flight: {row['item']} {row['owner']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="continuation_check.py",
        description=(
            "Judge a continuation case. Exit 0 when judge reads the case. "
            "apply exits 0 when the named push attempt is spent, and 1 when "
            "the approval is missing, spent, or aimed at another target. "
            "Exit 2 on a bad invocation. apply leaves the fixture file unchanged."
        ),
    )
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--json", action="store_true", help="Print the verdict as JSON.")
    sub = parser.add_subparsers(dest="command", required=True)
    judge_cmd = sub.add_parser("judge", parents=[shared], help="Judge one case file.")
    judge_cmd.add_argument("case", type=Path, help="Path to one continuation case JSON file.")
    apply_cmd = sub.add_parser(
        "apply",
        parents=[shared],
        help="Spend one push attempt in memory and print the resulting verdict.",
    )
    apply_cmd.add_argument("case", type=Path, help="Path to one continuation case JSON file.")
    apply_cmd.add_argument("--approval", required=True, help="Approval id to spend.")
    apply_cmd.add_argument("--target", required=True, help="Push target named by that approval.")
    apply_cmd.add_argument(
        "--result",
        required=True,
        choices=("rejected", "accepted"),
        help="Attempt result. rejected and accepted both spend a matching approval.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        case = load_case(args.case)
        if args.command == "judge":
            emit(judge(case), args.json)
            return 0
        if args.command == "apply":
            payload = apply_case(case, args.approval, args.target, args.result)
            emit(payload, args.json)
            return 0 if payload["applied"] else 1
    except CaseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("Unknown command. Pass judge CASE or apply CASE.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
