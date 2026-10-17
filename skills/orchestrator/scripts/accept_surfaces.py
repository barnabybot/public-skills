#!/usr/bin/env python3
"""Check HTML page acceptance across every surface.

A headline probe does not accept a page. ``check`` reads a JSON record and
requires grid, list, chart, and report. Each surface is ``checked`` with a
note of what was seen, or ``na`` with a reason. Exit 1 names every surface
that is still open. ``template`` prints a blank record and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SURFACES = ("grid", "list", "chart", "report")


def usage(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def blank_record() -> dict:
    """Return a template whose surface states are still unset."""
    return {
        "surfaces": {
            name: {"state": None, "note": "", "reason": ""}
            for name in SURFACES
        }
    }


def load_record(path: str) -> tuple[dict | None, str | None]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, (
            f"accept_surfaces: cannot read the record ({exc}). "
            "Pass --record with a JSON file that exists, or pass - to read stdin."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, (
            "accept_surfaces: the record is not JSON "
            f"({exc.msg} at line {exc.lineno}). "
            "Pass --record with a JSON object whose surfaces cover grid, list, chart and report."
        )
    if not isinstance(data, dict):
        return None, (
            "accept_surfaces: the record must be a JSON object. "
            "Pass --record with an object that contains a surfaces object."
        )
    return data, None


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def judge(raw: object) -> tuple[bool, str]:
    if raw is None:
        return False, "no recorded check and no N/A reason"
    if not isinstance(raw, dict):
        return False, "entry must be an object with state checked or na"
    state = raw.get("state")
    if state == "checked":
        if _text(raw.get("note")):
            return True, "checked"
        return False, "checked with an empty note"
    if state == "na":
        if _text(raw.get("reason")):
            return True, "na"
        return False, "na with an empty reason"
    if state is None:
        return False, "no recorded check and no N/A reason"
    return False, f"state {state!r} must be checked or na"


def assess(record: dict) -> tuple[dict | None, str | None]:
    raw = record.get("surfaces", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None, (
            "accept_surfaces: surfaces must be a JSON object. "
            "Set surfaces to an object with grid, list, chart and report, then run check again."
        )
    rows = []
    missing = []
    for name in SURFACES:
        ok, detail = judge(raw.get(name))
        rows.append({"surface": name, "ok": ok, "detail": detail})
        if not ok:
            missing.append(name)
    return {"ok": not missing, "missing": missing, "surfaces": rows}, None


def print_human(result: dict) -> None:
    for row in result["surfaces"]:
        mark = "ok" if row["ok"] else "fail"
        print(f"{mark:<5} {row['surface']}: {row['detail']}")


def report_failure(missing: list[str]) -> None:
    label = "surface" if len(missing) == 1 else "surfaces"
    named = ", ".join(missing)
    print(
        f"accept_surfaces: missing {label}: {named}. "
        "Record a check note for each missing surface, or set state to na with a reason, "
        "then run check again.",
        file=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON object on stdout.",
    )
    parser = argparse.ArgumentParser(
        prog="accept_surfaces.py",
        parents=[common],
        description=(
            "Check that an HTML page acceptance recorded grid, list, chart and report, "
            "or an explicit N/A reason for each surface, before the page is accepted."
        ),
        epilog=(
            "Subcommands: check reads a surface record; template prints a blank record. "
            "check takes --record PATH, or - to read stdin. --json prints a machine-readable object. "
            "Exit 0 means every surface is covered. Exit 1 names each missing surface. "
            "Exit 2 means the invocation or the record shape was wrong."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    check = sub.add_parser(
        "check",
        parents=[common],
        help="Require a recorded check or an N/A reason for grid, list, chart and report.",
        description=(
            "Read a surface record and exit 1 when grid, list, chart or report "
            "has no recorded check and no N/A reason. The error names each missing surface."
        ),
    )
    check.add_argument(
        "--record",
        required=True,
        help="JSON record path. Pass - to read the record from stdin.",
    )
    sub.add_parser(
        "template",
        parents=[common],
        help="Print a blank surface record on stdout.",
        description=(
            "Print a blank surface record for grid, list, chart and report. "
            "Each state is null until a check note or an N/A reason is recorded. "
            "This command writes nothing."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "template":
        print(json.dumps(blank_record(), indent=2))
        return 0
    record, error = load_record(args.record)
    if error:
        return usage(error)
    result, error = assess(record)
    if error:
        return usage(error)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_human(result)
    if not result["ok"]:
        report_failure(result["missing"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
