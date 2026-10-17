#!/usr/bin/env python3
"""Judge whether a worker seat is stalled.

The silence clock starts at the later of the warm-up (default 12 minutes),
the latest activity, and the latest promise. A session-note write, a
worktree file write, a tool-visible read, compaction, and any other tool
call count as activity and restart that clock. The command exits 1 only for
a verified stall: the input line is idle, the trace contains a promise of
action, and the silence window (default 5 minutes) has elapsed on that clock.

The command reads a JSON trace and prints a verdict. It does not write state.

    python3 scripts/stall_check.py judge TRACE [--json]
    python3 scripts/stall_check.py batch DIR [--json]

Exit 0 when every judged seat is active. Exit 1 when a seat is stalled.
Exit 2 on a bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_WARMUP_MINUTES = 12
DEFAULT_SILENCE_MINUTES = 5
ACTIVITY_KINDS = frozenset(
    {"session_note_write", "worktree_write", "read", "compaction", "tool_call"}
)
EVENT_KINDS = ACTIVITY_KINDS | {"promise"}
INPUTS = frozenset({"idle", "active"})


class TraceError(ValueError):
    """The trace or the flags cannot be judged."""


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TraceError(
            f"{label} is missing. Pass a UTC timestamp such as 2026-10-04T11:49:00Z."
        )
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TraceError(
            f"{label} value {value!r} is not ISO-8601. Pass a UTC timestamp such as 2026-10-04T11:49:00Z."
        ) from exc
    if parsed.tzinfo is None:
        raise TraceError(
            f"{label} value {value!r} has no timezone. Pass a UTC timestamp ending in Z."
        )
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceError(
            f"{label} must be a whole number of minutes. Pass --{label.replace('_', '-')} N."
        )
    if value < 0:
        raise TraceError(
            f"{label.replace('_', ' ')} must be zero or greater. Pass --{label.replace('_', '-')} N."
        )
    return value


def normalise(raw: object, fallback_seat: str) -> dict:
    if not isinstance(raw, dict):
        raise TraceError(
            "The trace must be a JSON object with started_at, now, input, and events. Pass judge PATH."
        )
    started = parse_time(raw.get("started_at"), "started_at")
    now = parse_time(raw.get("now"), "now")
    if now < started:
        raise TraceError(
            "now is earlier than started_at. Pass a now at or after the seat start."
        )
    state = raw.get("input")
    if state not in INPUTS:
        raise TraceError(
            "input must be idle or active. Pass input idle when the input line is waiting."
        )
    events_raw = raw.get("events")
    if not isinstance(events_raw, list):
        raise TraceError(
            "events must be a list. Each item needs at and kind. Pass an empty list when the seat has no events."
        )
    events = []
    for index, item in enumerate(events_raw, start=1):
        if not isinstance(item, dict):
            raise TraceError(
                f"events[{index}] must be an object with at and kind. Fix that item and rerun judge."
            )
        kind = item.get("kind")
        if kind not in EVENT_KINDS:
            names = ", ".join(sorted(EVENT_KINDS))
            raise TraceError(
                f"events[{index}] kind {kind!r} is unknown. Use one of: {names}."
            )
        at = parse_time(item.get("at"), f"events[{index}].at")
        if at < started or at > now:
            raise TraceError(
                f"events[{index}].at {format_time(at)} sits outside started_at..now. Move the event inside that span."
            )
        events.append({"at": at, "kind": kind})
    events.sort(key=lambda item: item["at"])
    seat = raw.get("seat", fallback_seat)
    if not isinstance(seat, str) or not seat.strip():
        raise TraceError(
            "seat must be a non-empty string. Pass seat, or name the trace file."
        )
    return {
        "seat": seat.strip(),
        "started_at": started,
        "now": now,
        "input": state,
        "events": events,
    }


def evaluate(trace: dict, warmup_minutes: int, silence_minutes: int) -> dict:
    """Return a verdict dict. `trace` is the normalised form from `normalise`."""
    warmup_minutes = _minutes(warmup_minutes, "warmup_minutes")
    silence_minutes = _minutes(silence_minutes, "silence_minutes")
    started = trace["started_at"]
    now = trace["now"]
    warmup_end = started + timedelta(minutes=warmup_minutes)
    events = trace["events"]
    activity = [item for item in events if item["kind"] in ACTIVITY_KINDS]
    promises = [item for item in events if item["kind"] == "promise"]
    last_promise = promises[-1] if promises else None
    later = []
    if last_promise is not None:
        later = [item for item in activity if item["at"] > last_promise["at"]]
    clock_points = [warmup_end]
    if activity:
        clock_points.append(activity[-1]["at"])
    if last_promise is not None:
        clock_points.append(last_promise["at"])
    clock_start = max(clock_points)
    if now < warmup_end:
        elapsed = timedelta(0)
        clock_reported = warmup_end
    else:
        elapsed = now - clock_start
        clock_reported = clock_start
    elapsed_seconds = int(elapsed.total_seconds())
    needed_seconds = silence_minutes * 60
    tool_after = bool(later)
    stalled = (
        now >= warmup_end
        and trace["input"] == "idle"
        and last_promise is not None
        and elapsed_seconds >= needed_seconds
    )
    result = {
        "seat": trace["seat"],
        "verdict": "stall" if stalled else "active",
        "input": trace["input"],
        "warmup_minutes": warmup_minutes,
        "silence_minutes": silence_minutes,
        "warmup_ends_at": format_time(warmup_end),
        "silence_clock_starts_at": format_time(clock_reported),
        "silence_elapsed_seconds": elapsed_seconds,
        "last_promise_at": format_time(last_promise["at"]) if last_promise else None,
        "tool_after_promise": tool_after,
        "reason": _reason(
            stalled=stalled,
            now=now,
            warmup_end=warmup_end,
            clock_start=clock_reported,
            elapsed_seconds=elapsed_seconds,
            silence_minutes=silence_minutes,
            state=trace["input"],
            last_promise=last_promise,
            later=later,
        ),
    }
    return result


def _reason(
    stalled: bool,
    now: datetime,
    warmup_end: datetime,
    clock_start: datetime,
    elapsed_seconds: int,
    silence_minutes: int,
    state: str,
    last_promise: dict | None,
    later: list[dict],
) -> str:
    if stalled and last_promise is not None:
        return (
            f"Verified stall: input is idle, the promise at {format_time(last_promise['at'])} "
            f"is on the trace, and silence is {elapsed_seconds // 60} minutes "
            f"after {format_time(clock_start)}. Send one authorised continuation."
        )
    if now < warmup_end:
        return (
            f"Warm-up runs until {format_time(warmup_end)}. The silence clock starts at that time."
        )
    if state != "idle":
        return "Input is active. A stall needs an idle input line. Pass input idle when the line is waiting."
    if last_promise is None:
        return (
            "The trace has no promise of action. A stall needs a promise of action, "
            "an idle input line, and silence past the window."
        )
    if later:
        latest = later[-1]
        return (
            f"{latest['kind']} at {format_time(latest['at'])} is the latest activity. "
            f"Silence is {elapsed_seconds // 60} minutes from {format_time(clock_start)}. "
            f"The stall window is {silence_minutes} minutes."
        )
    return (
        f"Silence is {elapsed_seconds // 60} minutes from {format_time(clock_start)}. "
        f"The stall window is {silence_minutes} minutes after the warm-up."
    )


def load_trace(path: Path) -> dict:
    if not path.is_file():
        raise TraceError(
            f"Trace file {path} is missing. Pass judge PATH to an existing JSON trace."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TraceError(
            f"Trace file {path} is not JSON ({exc.msg} at line {exc.lineno}). "
            "Pass a JSON object with started_at, now, input, and events."
        ) from exc
    except OSError as exc:
        raise TraceError(
            f"Trace file {path} could not be read ({exc}). Check the path and rerun judge."
        ) from exc
    return normalise(raw, path.stem)


def render_text(result: dict) -> str:
    return f"{result['verdict']:<6} {result['seat']}  {result['reason']}"


def _emit(payload: object, as_json: bool, text_lines: list[str]) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    for line in text_lines:
        print(line)


def run_judge(path: Path, warmup: int, silence: int, as_json: bool) -> int:
    result = evaluate(load_trace(path), warmup, silence)
    result["path"] = str(path)
    _emit(result, as_json, [render_text(result)])
    return 1 if result["verdict"] == "stall" else 0


def run_batch(directory: Path, warmup: int, silence: int, as_json: bool) -> int:
    if not directory.is_dir():
        raise TraceError(
            f"Batch directory {directory} is missing. Pass batch DIR containing one JSON trace per seat."
        )
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise TraceError(
            f"Batch directory {directory} has no JSON traces. Add one .json file per seat and rerun batch."
        )
    results = []
    for path in paths:
        item = evaluate(load_trace(path), warmup, silence)
        item["path"] = path.name
        results.append(item)
    verdict = "stall" if any(item["verdict"] == "stall" for item in results) else "active"
    payload = {
        "verdict": verdict,
        "warmup_minutes": warmup,
        "silence_minutes": silence,
        "traces": results,
    }
    _emit(payload, as_json, [render_text(item) for item in results])
    return 1 if verdict == "stall" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stall_check.py",
        description=(
            "Judge whether a worker seat is stalled. The silence clock starts at the "
            "later of the warm-up and the latest activity. Session-note writes, "
            "worktree writes, tool-visible reads, compaction, and other tool calls "
            "count as activity and restart that clock. Exit 0 when the seat is active, "
            "1 on a verified stall (idle input, a promise of action, and silence past "
            "the window since the latest activity), and 2 on a bad invocation. The "
            "command reads traces and prints a verdict."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Trace JSON keys: seat, started_at, now, input (idle or active), events.\n"
            "Event kinds: session_note_write, worktree_write, read, compaction, tool_call, promise.\n"
            "Flags that change the verdict: --warmup-minutes (default 12), --silence-minutes (default 5).\n"
            "A tool call after a promise restarts the silence clock. The seat stalls once that silence passes the window.\n"
            "Example: python3 scripts/stall_check.py judge trace.json --json"
        ),
    )
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--json",
        action="store_true",
        help="Print the verdict as a JSON object on stdout.",
    )
    shared.add_argument(
        "--warmup-minutes",
        type=int,
        default=DEFAULT_WARMUP_MINUTES,
        metavar="N",
        help="Minutes after start before the silence clock starts. Default: 12.",
    )
    shared.add_argument(
        "--silence-minutes",
        type=int,
        default=DEFAULT_SILENCE_MINUTES,
        metavar="N",
        help="Minutes of silence on that clock before a stall. Default: 5. Use with --warmup-minutes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    judge = sub.add_parser(
        "judge",
        parents=[shared],
        help="Judge one JSON trace and print active or stall.",
    )
    judge.add_argument("trace", type=Path, help="Path to one seat trace JSON file.")
    batch = sub.add_parser(
        "batch",
        parents=[shared],
        help="Judge every JSON trace in a directory.",
    )
    batch.add_argument("directory", type=Path, help="Directory of seat trace JSON files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _minutes(args.warmup_minutes, "warmup_minutes")
        _minutes(args.silence_minutes, "silence_minutes")
        if args.command == "judge":
            return run_judge(args.trace, args.warmup_minutes, args.silence_minutes, args.json)
        if args.command == "batch":
            return run_batch(args.directory, args.warmup_minutes, args.silence_minutes, args.json)
    except TraceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        "Unknown command. Pass judge TRACE or batch DIR. Run stall_check.py --help for the flags.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
