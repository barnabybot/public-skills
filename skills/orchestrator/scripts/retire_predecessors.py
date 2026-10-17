#!/usr/bin/env python3
"""Retire recorded orchestrator predecessors.

python3 scripts/retire_predecessors.py retire CASE.json --dry-run --json

Match a predecessor only when the stable UUID, the live name, and the exact
session note agree. A reused ref or a similar title leaves that seat alone.
--dry-run prints planned closes and does not call cmux.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HELPER_TAILS = (
    Path("cross-cutting") / "cmux" / "scripts" / "close-workspace.sh",
    Path("skills") / "cmux" / "scripts" / "close-workspace.sh",
)
HELPER_TAIL = HELPER_TAILS[0]
OPEN_STATUSES = frozenset({"in-progress", "review", "blocked"})
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|$)", re.S)
_cmux_calls = 0


class CaseError(ValueError):
    """The case, the helper, or the live list cannot be retired."""


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def norm(value: str) -> str:
    return value.strip().casefold()


def required_str(item: dict, key: str, label: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CaseError(
            f"{label} is missing. Pass a non-empty string for {label}."
        )
    return value.strip()


def parse_note(body: str) -> dict:
    fields = {
        "status": None,
        "ended": None,
        "workspace_id": None,
        "workspace_name": None,
    }
    match = FRONTMATTER.match(body)
    if not match:
        return fields
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep or key not in fields:
            continue
        if fields[key] is not None:
            raise CaseError(
                f"Session note field {key} is repeated. Keep one {key} line in the frontmatter."
            )
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        fields[key] = value
    return fields


def add_outcome_links(body: str, successor_note: str, successor_handoff: str) -> str:
    lines = [
        f"Successor: {successor_note}",
        f"Handoff: {successor_handoff}",
    ]
    missing = [line for line in lines if line not in body]
    if not missing:
        return body
    block = "\n".join(missing) + "\n"
    heading = re.search(r"(?m)^## Outcome\s*$", body)
    if heading is None:
        suffix = "" if body.endswith("\n") else "\n"
        return f"{body}{suffix}\n## Outcome\n\n{block}"
    rest = body[heading.end() :]
    nxt = re.search(r"(?m)^## ", rest)
    if nxt is None:
        suffix = "" if body.endswith("\n") else "\n"
        return f"{body}{suffix}{block}"
    insert_at = heading.end() + nxt.start()
    prefix = body[:insert_at]
    if not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + block + body[insert_at:]


def mark_done(body: str, today: str) -> str:
    meta = parse_note(body)
    if meta.get("ended"):
        return body
    status = meta.get("status")
    if status not in OPEN_STATUSES:
        return body
    body, count = re.subn(
        rf"(?m)^status: {re.escape(status)}\s*$",
        "status: done",
        body,
        count=1,
    )
    if count != 1:
        raise CaseError(
            "Session note status line could not be updated. Keep one status line in the frontmatter."
        )
    if re.search(r"(?m)^ended:", body):
        return body
    body, count = re.subn(
        r"(?m)^status: done\s*$",
        f"status: done\nended: {today}",
        body,
        count=1,
    )
    if count != 1:
        raise CaseError(
            "Session note ended line could not be added. Keep one status line in the frontmatter."
        )
    return body


def plan_note(body: str, kind: str, successor: dict, today: str) -> tuple[str | None, str | None]:
    if kind == "close":
        return "link", add_outcome_links(body, successor["session_note"], successor["handoff"])
    if kind != "already-absent":
        return None, None
    meta = parse_note(body)
    if meta.get("ended") or meta.get("status") not in OPEN_STATUSES:
        return "preserve", None
    updated = add_outcome_links(body, successor["session_note"], successor["handoff"])
    return "reconcile", mark_done(updated, today)


def commit_note(path: str, body: str) -> str | None:
    file = Path(path)
    if file.is_file():
        file.write_text(body, encoding="utf-8")
        return None
    return body


def resolve_helper(
    skills_root: Path | None = None,
    script_file: Path | None = None,
) -> tuple[Path, Path]:
    if skills_root is not None:
        root = Path(skills_root).expanduser()
        for tail in HELPER_TAILS:
            helper = root / tail
            if helper.is_file():
                return helper, root
        helper = root / HELPER_TAIL
        raise CaseError(
            "close-workspace.sh is absent from the cmux skill directory at "
            f"{helper}. Pass --skills-root PATH to the Skills checkout that contains "
            "cmux/scripts/close-workspace.sh, or set BRUN_SKILLS_ROOT."
        )
    script = (script_file or Path(__file__)).resolve()
    roots: list[Path] = []
    if len(script.parents) >= 4:
        roots.append(script.parents[3])
    env_root = os.environ.get("BRUN_SKILLS_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser())
    looked: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for tail in HELPER_TAILS:
            helper = root / tail
            looked.append(str(helper))
            if helper.is_file():
                return helper, root
    searched = ", ".join(looked) if looked else "no Skills checkout"
    raise CaseError(
        "close-workspace.sh is absent from the cmux skill directory and from BRUN_SKILLS_ROOT. "
        "Pass --skills-root PATH to the Skills checkout, or set BRUN_SKILLS_ROOT to that checkout. "
        f"Looked at {searched}."
    )


def helper_label(helper: Path, root: Path) -> str:
    helper = helper.resolve()
    root = root.resolve()
    try:
        return helper.relative_to(root).as_posix()
    except ValueError:
        parts = helper.parts
        for prefix in ("cross-cutting", "skills"):
            if prefix in parts:
                index = parts.index(prefix)
                return "/".join(parts[index:])
        return helper.as_posix()


def _cmux_json(args: list[str]) -> object:
    global _cmux_calls
    _cmux_calls += 1
    command = " ".join(args)
    try:
        result = subprocess.run(
            ["cmux", "--json", "--id-format", "both", *args],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CMUX_QUIET": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise CaseError(
            f"cmux {command} timed out. Pass a case with workspaces, or retry when cmux answers."
        ) from exc
    except OSError as exc:
        raise CaseError(
            f"cmux {command} could not be started ({exc}). Pass a case with workspaces, or install cmux and retry."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CaseError(
            f"cmux {command} exited {result.returncode}: {detail}. "
            "Pass a case with workspaces, or retry when the window UUID is live."
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CaseError(
            f"cmux {command} did not return JSON ({exc}). Pass a case with workspaces, or retry the refresh."
        ) from exc


def parse_workspace(item: object, label: str, index: int, require_window: bool) -> dict:
    if not isinstance(item, dict):
        raise CaseError(
            f"{label}[{index}] must be an object with id, ref, and title. Pass that workspace object."
        )
    row = {
        "id": required_str(item, "id", f"{label}[{index}].id"),
        "ref": required_str(item, "ref", f"{label}[{index}].ref"),
        "title": required_str(item, "title", f"{label}[{index}].title"),
    }
    if require_window:
        row["window_uuid"] = required_str(item, "window_uuid", f"{label}[{index}].window_uuid")
    return row


def parse_workspaces(raw: object, label: str) -> list[dict]:
    if not isinstance(raw, list):
        raise CaseError(
            f"{label} must be a list of live workspaces. Pass {label} from cmux list-workspaces."
        )
    return [
        parse_workspace(item, label, index, require_window=True)
        for index, item in enumerate(raw, start=1)
    ]


def refresh(recorded_window: str) -> list[dict]:
    listed = _cmux_json(["list-windows"])
    if not isinstance(listed, list):
        raise CaseError(
            "cmux list-windows did not return a JSON list. Pass a case with workspaces, "
            "or rerun when cmux --json list-windows returns a list of windows."
        )
    windows: list[str] = []
    for index, item in enumerate(listed, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise CaseError(
                f"cmux list-windows entry {index} has no id. Pass a case with workspaces, "
                "or rerun when each window has an id."
            )
        windows.append(item["id"].strip())
    if not any(norm(item) == norm(recorded_window) for item in windows):
        windows.insert(0, recorded_window)
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for window in windows:
        payload = _cmux_json(["list-workspaces", "--window", window])
        if not isinstance(payload, dict) or not isinstance(payload.get("workspaces"), list):
            raise CaseError(
                f"cmux list-workspaces --window {window} did not return a workspaces list. "
                "Pass a case with workspaces, or rerun when cmux --json returns that object."
            )
        for index, item in enumerate(payload["workspaces"], start=1):
            row = parse_workspace(item, "workspaces", index, require_window=False)
            row["window_uuid"] = window
            key = (norm(window), norm(row["id"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def parse_screens(raw: object) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise CaseError(
            "screens must be an object keyed by workspace UUID. Pass screens after reading each live screen."
        )
    parsed = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise CaseError(
                "screens keys must be workspace UUIDs. Pass the stable UUID returned by the refresh."
            )
        if not isinstance(value, dict):
            raise CaseError(
                f"screens.{key} must be an object. Pass stopped, handoff, and in_flight for that workspace."
            )
        inflight = value.get("in_flight")
        if inflight is not None and not isinstance(inflight, str):
            raise CaseError(
                f"screens.{key}.in_flight must be a string such as tool_call or unfinished_write. Pass that string, or omit in_flight."
            )
        if "stopped" in value and not isinstance(value["stopped"], bool):
            raise CaseError(
                f"screens.{key}.stopped must be true or false. Pass true when the workspace has stopped at the handoff."
            )
        handoff = value.get("handoff")
        if handoff is not None and not isinstance(handoff, str):
            raise CaseError(
                f"screens.{key}.handoff must be the outgoing handoff path. Pass that path."
            )
        parsed[norm(key)] = value
    return parsed


def parse_predecessor(item: object, index: int) -> dict:
    label = f"predecessors[{index}]"
    if not isinstance(item, dict):
        raise CaseError(
            f"{label} must be an object. Pass name, uuid, window_uuid, ref, session_note, and handoff."
        )
    if "uuid" not in item:
        raise CaseError(
            f"{label} has no uuid. Pass the stable UUID, or null for a legacy handoff."
        )
    uuid = item["uuid"]
    if uuid is not None and (not isinstance(uuid, str) or not uuid.strip()):
        raise CaseError(
            f"{label}.uuid must be a UUID string or null. Pass null when the handoff recorded no UUID."
        )
    return {
        "name": required_str(item, "name", f"{label}.name"),
        "uuid": None if uuid is None else uuid.strip(),
        "window_uuid": required_str(item, "window_uuid", f"{label}.window_uuid"),
        "ref": required_str(item, "ref", f"{label}.ref"),
        "session_note": required_str(item, "session_note", f"{label}.session_note"),
        "handoff": required_str(item, "handoff", f"{label}.handoff"),
    }


def load_case(path: Path) -> dict:
    if not path.is_file():
        raise CaseError(f"Case file {path} is missing. Pass retire CASE.json.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseError(
            f"Case file {path} is not valid JSON ({exc}). Pass a JSON object with predecessors, workspaces, notes, and screens."
        ) from exc
    if not isinstance(data, dict):
        raise CaseError(
            f"Case file {path} must be a JSON object. Pass predecessors, workspaces, notes, and screens."
        )
    return data


def snapshot(case: dict, retry: bool) -> dict:
    if not retry:
        return case
    extra = case.get("retry")
    if not isinstance(extra, dict):
        raise CaseError(
            "This case has no retry snapshot. Record the next observation under retry, or omit --retry."
        )
    merged = {key: value for key, value in case.items() if key != "retry"}
    merged.update(extra)
    return merged


def parse_today(value: object) -> str:
    if value is None:
        return date.today().isoformat()
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise CaseError(
            "today must be YYYY-MM-DD. Pass today in the case, or omit it to use the local date."
        )
    return value


def parse_successor(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise CaseError(
            "successor must be an object with session_note and handoff. Pass the successor paths."
        )
    return {
        "session_note": required_str(raw, "session_note", "successor.session_note"),
        "handoff": required_str(raw, "handoff", "successor.handoff"),
    }


def embedded_notes(raw: object) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise CaseError(
            "notes must be an object of session-note path to note text. Pass notes, or omit notes when the files exist."
        )
    notes = {}
    for path, body in raw.items():
        if not isinstance(path, str) or not path.strip():
            raise CaseError(
                "notes keys must be session note paths. Pass the exact session note path from the succession table."
            )
        if not isinstance(body, str):
            raise CaseError(
                f"notes[{path}] must be the note text. Pass a string for that session note."
            )
        notes[path] = body
    return notes


def read_note(path: str, embedded: dict) -> str:
    file = Path(path)
    if file.is_file():
        return file.read_text(encoding="utf-8")
    if path in embedded:
        return embedded[path]
    raise CaseError(
        f"Session note {path} is missing. Pass notes for that path, or a readable session note file."
    )


def row_for(predecessor: dict, record: str, reason: str, ref: str | None, recovered: str | None) -> dict:
    return {
        "action": "close" if record == "closed" else record,
        "name": predecessor["name"],
        "uuid": predecessor.get("uuid"),
        "ref": ref,
        "record": record,
        "planned": False,
        "reason": reason,
        "recovered_uuid": recovered,
        "session_note": predecessor["session_note"],
        "note_action": None,
        "note_body": None,
    }


def retain(predecessor: dict, reason: str, recovered: str | None = None) -> dict:
    return row_for(predecessor, "retained", reason, None, recovered)


def screen_for(screens: dict, uuid: str) -> dict | None:
    return screens.get(norm(uuid))


def flight_reason(screen: dict) -> str | None:
    inflight = screen.get("in_flight")
    if inflight == "tool_call":
        return "Pending cleanup: a tool call remains in flight. Retry on the next status tick."
    if inflight == "unfinished_write":
        return "Pending cleanup: an unfinished write remains in flight. Retry on the next status tick."
    if inflight:
        return (
            f"Pending cleanup: {inflight} remains in flight. Retry on the next status tick."
        )
    if not screen.get("stopped"):
        return (
            "Pending cleanup: the workspace has not stopped at the handoff. "
            "Retry on the next status tick."
        )
    return None


def ready_to_close(predecessor: dict, live: dict, note: str, screens: dict) -> dict:
    meta = parse_note(note)
    if meta.get("workspace_name") != live["title"]:
        shown = meta.get("workspace_name")
        return retain(
            predecessor,
            f"Session note workspace_name {shown!r} differs from the live name {live['title']!r}.",
        )
    screen = screen_for(screens, live["id"])
    recovered = live["id"] if predecessor.get("recovered") else None
    if screen is None:
        return retain(
            predecessor,
            "Live screen is missing. Read the workspace screen and pass screens for that UUID before closure.",
            recovered,
        )
    pending = flight_reason(screen)
    if pending:
        return retain(predecessor, pending, recovered)
    if screen.get("handoff") != predecessor["handoff"]:
        return retain(
            predecessor,
            "Live screen does not show the recorded outgoing handoff. Record pending cleanup and retry after the handoff is on screen.",
            recovered,
        )
    if predecessor.get("recovered"):
        reason = "Recovered the workspace UUID from the linked note and the live screen."
    else:
        reason = "Matched the stable UUID, the live name, and the exact session note."
    return row_for(predecessor, "closed", reason, live["ref"], recovered)


def judge_predecessor(predecessor: dict, fleet: list[dict], note: str, screens: dict) -> dict:
    meta = parse_note(note)
    uuid = predecessor["uuid"]
    if uuid:
        matches = [item for item in fleet if norm(item["id"]) == norm(uuid)]
        if len(matches) > 1:
            return retain(
                predecessor,
                f"Stable UUID {uuid} is listed more than once. Record pending cleanup and retry after the live list has one row.",
            )
        if not matches:
            if meta.get("workspace_name") != predecessor["name"]:
                return retain(
                    predecessor,
                    f"Recorded UUID {uuid} is absent from every live window, and the session note name differs from the recorded name.",
                )
            reused = [item for item in fleet if item["ref"] == predecessor["ref"]]
            reason = f"Recorded UUID {uuid} is absent from every live window."
            if reused:
                reason += (
                    f" Ref {predecessor['ref']} is live on {reused[0]['title']} and was not closed."
                )
            row = row_for(predecessor, "already-absent", reason, None, None)
            row["note_text"] = note
            return row
        live = matches[0]
        if live["title"] != predecessor["name"]:
            return retain(
                predecessor,
                f"Live title {live['title']!r} differs from the recorded name {predecessor['name']!r}.",
            )
        return ready_to_close(predecessor, live, note, screens)
    if meta.get("workspace_name") != predecessor["name"]:
        return retain(
            predecessor,
            "Legacy handoff has no workspace UUID. The linked note name differs from the recorded name.",
        )
    if meta.get("workspace_id") != predecessor["ref"]:
        return retain(
            predecessor,
            "Legacy handoff has no workspace UUID. The linked note ref differs from the recorded ref.",
        )
    candidates = [
        item
        for item in fleet
        if item["title"] == predecessor["name"] and item["ref"] == predecessor["ref"]
    ]
    if len(candidates) != 1:
        return retain(
            predecessor,
            "Legacy handoff has no workspace UUID. The linked note, live name, and ref do not identify one workspace.",
        )
    live = candidates[0]
    screen = screen_for(screens, live["id"])
    if screen is None or screen.get("handoff") != predecessor["handoff"]:
        return retain(
            predecessor,
            "Legacy handoff has no workspace UUID. The live screen does not confirm the exact outgoing handoff.",
        )
    recovered = dict(predecessor)
    recovered["uuid"] = live["id"]
    recovered["recovered"] = True
    return ready_to_close(recovered, live, note, screens)


def same_identity(fleet: list[dict], uuid: str, title: str, ref: str) -> bool:
    rows = [item for item in fleet if norm(item["id"]) == norm(uuid)]
    return len(rows) == 1 and rows[0]["title"] == title and rows[0]["ref"] == ref


def uuid_absent(fleet: list[dict], uuid: str) -> bool:
    return not any(norm(item["id"]) == norm(uuid) for item in fleet)


def public_row(row: dict) -> dict:
    return {
        "name": row["name"],
        "uuid": row.get("uuid"),
        "ref": row.get("ref"),
        "record": row["record"],
        "planned": row["planned"],
        "reason": row["reason"],
        "recovered_uuid": row.get("recovered_uuid"),
        "note_action": row.get("note_action"),
        "note_body": row.get("note_body"),
    }


def render_line(row: dict, helper: str | None) -> str:
    if row["record"] == "closed" and row["planned"]:
        return f"planned close {row['name']} {row['ref']} {helper}"
    if row["record"] == "closed":
        return f"closed {row['name']} {row['ref']} {helper}"
    return f"{row['record']} {row['name']}  {row['reason']}"


def attach_note_plan(row: dict, body: str, successor: dict, today: str, dry_run: bool) -> None:
    kind = "close" if row["action"] == "close" else row["action"]
    action, planned = plan_note(body, kind, successor, today)
    row["note_action"] = action
    if dry_run:
        row["note_body"] = planned
        return
    if planned is None:
        row["note_body"] = None
        return
    echoed = commit_note(row["session_note"], planned)
    row["note_body"] = echoed
    row["note_text"] = planned


def retire_case(
    case: dict,
    dry_run: bool,
    skills_root: Path | None = None,
    script_file: Path | None = None,
) -> dict:
    global _cmux_calls
    _cmux_calls = 0
    window = required_str(case, "window_uuid", "window_uuid")
    if "workspaces" in case:
        fleet = parse_workspaces(case["workspaces"], "workspaces")
        cmux_mode = False
    elif dry_run:
        raise CaseError(
            "Dry-run needs workspaces in the case. Pass a case that includes the refreshed "
            "workspace list, or omit --dry-run to refresh the window with cmux."
        )
    else:
        fleet = refresh(window)
        cmux_mode = True
    if "recheck_workspaces" in case:
        recheck: list[dict] | None = parse_workspaces(case["recheck_workspaces"], "recheck_workspaces")
    elif cmux_mode:
        recheck = None
    else:
        recheck = fleet
    embedded = embedded_notes(case.get("notes"))
    screens = parse_screens(case.get("screens"))
    successor = parse_successor(case.get("successor"))
    today = parse_today(case.get("today"))
    predecessors = case.get("predecessors")
    if not isinstance(predecessors, list):
        raise CaseError(
            "Case needs a predecessors list. Pass the succession table as predecessors."
        )
    decisions = []
    for index, item in enumerate(predecessors, start=1):
        predecessor = parse_predecessor(item, index)
        note = read_note(predecessor["session_note"], embedded)
        row = judge_predecessor(predecessor, fleet, note, screens)
        row["note_text"] = note
        if row["action"] == "close":
            current = recheck if recheck is not None else refresh(window)
            if not same_identity(current, row["uuid"], predecessor["name"], row["ref"]):
                row = retain(
                    predecessor,
                    "Identity changed before closure. Record pending cleanup and retry on the next status tick.",
                )
                row["note_text"] = note
        decisions.append(row)
    needs_close = any(item["action"] == "close" for item in decisions)
    label = None
    helper_path: Path | None = None
    if needs_close:
        helper_path, root = resolve_helper(skills_root, script_file)
        label = helper_label(helper_path, root)
    if needs_close and not dry_run:
        if "after_workspaces" in case:
            after: list[dict] | None = parse_workspaces(case["after_workspaces"], "after_workspaces")
        elif cmux_mode:
            after = None
        else:
            raise CaseError(
                "Apply needs after_workspaces so the closed UUID can be confirmed absent. "
                "Pass after_workspaces, or omit workspaces to refresh the window with cmux."
            )
    else:
        after = None
    for row in decisions:
        body = row["note_text"]
        if row["action"] == "close" and dry_run:
            row["planned"] = True
        attach_note_plan(row, body, successor, today, dry_run)
        if dry_run or row["action"] != "close":
            continue
        if helper_path is None:
            raise CaseError(
                "close-workspace.sh was not resolved before closure. "
                "Pass --skills-root PATH to the Skills checkout, or set BRUN_SKILLS_ROOT."
            )
        proc = subprocess.run(
            [str(helper_path), row["ref"]],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            row.update(
                retain(
                    {
                        "name": row["name"],
                        "uuid": row["uuid"],
                        "session_note": row["session_note"],
                    },
                    f"close-workspace.sh exited {proc.returncode}: {detail}. "
                    "Record pending cleanup and retry on the next status tick.",
                    row.get("recovered_uuid"),
                )
            )
            continue
        confirmed = read_note(row["session_note"], embedded)
        meta = parse_note(confirmed)
        if meta.get("status") != "done" or not meta.get("ended"):
            row.update(
                retain(
                    {
                        "name": row["name"],
                        "uuid": row["uuid"],
                        "session_note": row["session_note"],
                    },
                    f"Session note {row['session_note']} is still open after close-workspace.sh. "
                    "Record pending cleanup and retry on the next status tick.",
                    row.get("recovered_uuid"),
                )
            )
            continue
        fleet_after = after if after is not None else refresh(window)
        if not uuid_absent(fleet_after, row["uuid"]):
            row.update(
                retain(
                    {
                        "name": row["name"],
                        "uuid": row["uuid"],
                        "session_note": row["session_note"],
                    },
                    f"Workspace UUID {row['uuid']} remains live after close-workspace.sh. "
                    "Record pending cleanup and retry on the next status tick.",
                    row.get("recovered_uuid"),
                )
            )
            continue
        row["planned"] = False
        row["record"] = "closed"
    return {
        "helper": label,
        "dry_run": dry_run,
        "cmux_calls": _cmux_calls,
        "results": [public_row(item) for item in decisions],
    }


def emit(payload: dict, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    for row in payload["results"]:
        print(render_line(row, payload["helper"]))


def outcome(payload: dict) -> int:
    if any(row["record"] == "retained" for row in payload["results"]):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retire_predecessors.py",
        description=(
            "Retire recorded orchestrator predecessors. Refresh the live workspace "
            "list for the recorded window UUID, match each predecessor by stable UUID, "
            "live name, and exact session note, then call close-workspace.sh. A reused "
            "ref or a similar title leaves the seat retained or already absent. "
            "--dry-run prints planned closes and does not call cmux. --json prints the "
            "record. Exit 0 when every predecessor is closed or already absent, 1 when "
            "any predecessor is retained, and 2 on a bad invocation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example: python3 scripts/retire_predecessors.py retire CASE.json --dry-run --json\n"
            "The helper is cross-cutting/cmux/scripts/close-workspace.sh from the cmux skill\n"
            "directory or BRUN_SKILLS_ROOT.\n"
            "Flags: --json prints the record, --dry-run prints planned closes, --retry uses\n"
            "the case retry snapshot, --skills-root PATH selects the Skills checkout."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    retire = sub.add_parser(
        "retire",
        help="Retire the predecessor chain in one case file.",
    )
    retire.add_argument("case", type=Path, help="Succession case JSON.")
    retire.add_argument("--json", action="store_true", help="Print the record as JSON.")
    retire.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned closes. Do not call cmux or write notes.",
    )
    retire.add_argument(
        "--retry",
        action="store_true",
        help="Use the retry snapshot recorded in the case.",
    )
    retire.add_argument(
        "--skills-root",
        type=Path,
        help="Skills checkout that contains the cmux close-workspace.sh helper.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "retire":
        return fail(
            "Unknown command. Pass retire CASE.json. Run retire_predecessors.py --help for the flags."
        )
    try:
        case = snapshot(load_case(args.case), args.retry)
        payload = retire_case(case, args.dry_run, args.skills_root)
    except CaseError as exc:
        return fail(str(exc))
    emit(payload, args.json)
    return outcome(payload)


if __name__ == "__main__":
    sys.exit(main())
