#!/usr/bin/env python3
"""Classify the latest direct author line before orchestrator succession.

python3 scripts/author_build_intent.py classify --text "LINE" --json
python3 scripts/author_build_intent.py classify CASE.json --json

Build or stop-spawning language dispatches or continues a writer.
Explicit handoff-to-orchestrator language still allows succession.
classify only reads and prints. It does not write, so --dry-run does not apply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BUILD_PHRASES = (
    ("stop-spawning-orchestrator", "stop spawning additional orchestrator"),
    ("get-building", "get building"),
    ("immediately-build", "immediately build"),
    ("build-out", "build out"),
)
ACTUALLY_BUILT = "actually being built"
KEEP_SEAT = ("keep-this-seat", "keep this seat")
SUCCESSION_PHRASES = (
    ("want-handoff-orchestrator", "want handoff to a new orchestrator"),
    ("handoff-to-new-orchestrator", "handoff to a new orchestrator"),
)
ALLOWED = {"author_line", "active_writer", "context_percent"}
REFUSE = {"dispatch_writer", "continue_writer", "keep_seat"}
USAGE = "Pass classify --text TEXT --json, or classify CASE.json --json."


class CaseError(ValueError):
    """The case or the invocation cannot be classified."""


class GuidedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, f"{self.prog}: {message}. {USAGE}\n")


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def phrase_help() -> str:
    build_lines = "\n".join(f"  {phrase} ({ident})" for ident, phrase in BUILD_PHRASES)
    succession_lines = "\n".join(
        f"  {phrase} ({ident})" for ident, phrase in SUCCESSION_PHRASES
    )
    return (
        "Match is a case-insensitive substring. The first matching group wins, "
        "then the first phrase in that group. Build language beats keep-seat "
        "and explicit succession on the same line.\n"
        "build language -> dispatch_writer, or continue_writer when active_writer is true:\n"
        f"{build_lines}\n"
        f"  {ACTUALLY_BUILT}, plus a later build follow-up (the word build) "
        "(actually-being-built)\n"
        "keep-seat -> keep_seat:\n"
        f"  {KEEP_SEAT[1]} ({KEEP_SEAT[0]})\n"
        "explicit succession -> succession_ok:\n"
        f"{succession_lines}\n"
        "else -> unclear. refuse_orchestrator_spawn is false, and matched is none. "
        "The caller may ask or follow other rules.\n"
        "--text classifies that line with active_writer false. Put active_writer "
        "or context_percent in a case file. context_percent must be a JSON integer "
        "when present and does not change the action. --json prints action, "
        "refuse_orchestrator_spawn, and matched. Exit 0 on every valid classify. "
        "Exit 2 on bad JSON or bad arguments. There is no --dry-run."
    )


def match_build(line: str) -> str | None:
    for ident, phrase in BUILD_PHRASES:
        if phrase in line:
            return ident
    index = line.find(ACTUALLY_BUILT)
    if index >= 0 and re.search(r"\bbuild\b", line[index + len(ACTUALLY_BUILT) :]):
        return "actually-being-built"
    return None


def match_succession(line: str) -> str | None:
    for ident, phrase in SUCCESSION_PHRASES:
        if phrase in line:
            return ident
    return None


def classify_case(case: dict) -> dict:
    line = case["author_line"].casefold()
    matched = match_build(line)
    if matched:
        action = "continue_writer" if case["active_writer"] else "dispatch_writer"
    elif KEEP_SEAT[1] in line:
        matched = KEEP_SEAT[0]
        action = "keep_seat"
    else:
        matched = match_succession(line)
        if matched:
            action = "succession_ok"
        else:
            matched = "none"
            action = "unclear"
    return {
        "action": action,
        "refuse_orchestrator_spawn": action in REFUSE,
        "matched": matched,
    }


def validate_case(data: dict, label: str) -> dict:
    if not isinstance(data, dict):
        raise CaseError(
            f"{label} must be a JSON object with author_line. "
            "Pass classify --text when you have only the line."
        )
    unknown = sorted(set(data) - ALLOWED)
    if unknown:
        names = ", ".join(unknown)
        raise CaseError(
            f"{label} has unknown field {names}. Keep author_line, and optionally "
            "active_writer (bool) and context_percent (int)."
        )
    if "author_line" not in data:
        raise CaseError(
            f"{label} is missing author_line. Set author_line to the latest direct author line."
        )
    line = data["author_line"]
    if not isinstance(line, str) or not line.strip():
        raise CaseError(
            f"{label} author_line must be a non-empty string. Pass the latest direct author line."
        )
    active = False
    if "active_writer" in data:
        active = data["active_writer"]
        if not isinstance(active, bool):
            raise CaseError(
                f"{label} active_writer must be a JSON boolean. Use true when a writer "
                "is already active, otherwise omit it."
            )
    if "context_percent" in data:
        percent = data["context_percent"]
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise CaseError(
                f"{label} context_percent must be a JSON integer. Omit it when the meter "
                "was not read. It does not change the action."
            )
    return {"author_line": line.strip(), "active_writer": active}


def load_case(path: Path) -> dict:
    if not path.is_file():
        raise CaseError(
            f"{path} is not a file. Pass the path to a classify case JSON object with author_line."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseError(
            f"{path} could not be read ({exc}). Pass a readable JSON case file."
        ) from exc
    except json.JSONDecodeError as exc:
        raise CaseError(
            f"{path} is not valid JSON ({exc}). Pass an object with author_line, "
            "or classify --text for a bare line."
        ) from exc
    return validate_case(data, str(path))


def emit(payload: dict, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
        return
    print(f"action: {payload['action']}")
    flag = str(payload["refuse_orchestrator_spawn"]).lower()
    print(f"refuse_orchestrator_spawn: {flag}")
    print(f"matched: {payload['matched']}")


def build_parser() -> argparse.ArgumentParser:
    parser = GuidedParser(
        prog="author_build_intent.py",
        description=(
            "Classify the latest direct author line before an orchestrator succession. "
            "Build or stop-spawning language dispatches or continues a writer. "
            "Explicit handoff-to-orchestrator language still allows succession. "
            "classify only reads and prints, so --dry-run does not apply. "
            "Exit 0 on every valid classify. Exit 2 on bad JSON or bad arguments."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=phrase_help(),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    classify_cmd = sub.add_parser(
        "classify",
        help="Classify one author line or one case file.",
        description=(
            "Classify one latest direct author line. "
            "Exit 0 on a valid classify. Exit 2 on bad JSON or bad arguments.\n\n"
            + phrase_help()
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    classify_cmd.add_argument(
        "case",
        nargs="?",
        type=Path,
        help="Path to a case JSON object with author_line.",
    )
    classify_cmd.add_argument(
        "--text",
        help="Author line to classify. Omits active_writer. Do not combine with a case file.",
    )
    classify_cmd.add_argument(
        "--json",
        action="store_true",
        help="Print action, refuse_orchestrator_spawn, and matched as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.text is not None and args.case is not None:
        return fail(
            "Pass either --text or a case file, not both. Use --text for one author line, "
            "or CASE.json when active_writer or context_percent is set."
        )
    try:
        if args.text is not None:
            case = validate_case({"author_line": args.text}, "--text")
        elif args.case is not None:
            case = load_case(args.case)
        else:
            return fail(f"Nothing to classify. {USAGE}")
        emit(classify_case(case), args.json)
    except CaseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
