#!/usr/bin/env python3
"""Refuse a live-page push unless the session note records a Thin-Slice preview.

A push is allowed when Preview is an existing filesystem path, a file URL, or
an http(s) loopback URL with a path, and Change is inject or update. Change
replace or remove also needs a Go quote and Provenance direct. Later labelled
lines replace earlier ones.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

KEEP = {"inject": "inject", "update": "update", "in place": "update", "in-place": "update"}
REPLACE = {"replace": "replace", "remove": "remove"}
PROVENANCE = {"direct", "relay", "build"}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LABEL_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\*\*)?(Preview(?:\s+shown)?|Change|Go|Provenance)(?:\*\*)?\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NoteRecord:
    preview: str | None
    change: str | None
    go: str | None
    provenance: str | None


@dataclass(frozen=True)
class Decision:
    status: str
    reasons: tuple[str, ...]

    def as_dict(self, record: NoteRecord) -> dict:
        return {
            "status": self.status,
            "preview": record.preview,
            "change": record.change,
            "go": record.go,
            "provenance": record.provenance,
            "reasons": list(self.reasons),
        }


def parse_note(text: str) -> NoteRecord:
    """Read the last Preview, Change, Go, and Provenance lines."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = LABEL_RE.match(line)
        if not match:
            continue
        label = match.group(1).casefold()
        key = "preview" if label.startswith("preview") else label
        found[key] = match.group(2).strip()
    return NoteRecord(
        preview=found.get("preview") or None,
        change=found.get("change") or None,
        go=found.get("go") or None,
        provenance=found.get("provenance") or None,
    )


def local_preview(value: str | None) -> bool:
    """Accept an existing path, a file URL, or a loopback URL that names a path."""
    if not value:
        return False
    text = value.strip().strip("`").strip("<>").strip()
    if not text:
        return False
    if "://" in text:
        parsed = urlparse(text)
        if parsed.scheme == "file":
            return bool(parsed.path)
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        return (
            parsed.scheme in {"http", "https"}
            and host in LOOPBACK
            and path not in {"", "/"}
        )
    try:
        return Path(text).expanduser().exists()
    except (OSError, ValueError):
        return False


def go_quote(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if len(text) < 2 or not any(ch.isalpha() for ch in text):
        return False
    return text.casefold() not in PROVENANCE


def classify_change(value: str | None) -> str | None:
    """Return inject, update, replace, remove, invalid, or None when absent."""
    if value is None or not value.strip():
        return None
    key = value.strip().casefold()
    if key in KEEP:
        return KEEP[key]
    if key in REPLACE:
        return REPLACE[key]
    return "invalid"


def classify_provenance(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    key = value.strip().casefold()
    if key in PROVENANCE:
        return key
    return "invalid"


def decide(record: NoteRecord) -> Decision:
    reasons: list[str] = []
    if not local_preview(record.preview):
        if record.preview:
            reasons.append(
                "Preview must be an existing local path, a file URL, or an http(s) "
                "loopback URL with a path (127.0.0.1, localhost, or ::1). "
                "Record that path, then run this gate again."
            )
        else:
            reasons.append(
                "The session note has no Preview line. "
                "Record the local preview path or loopback URL from the Thin-Slice, "
                "then run this gate again."
            )
    change = classify_change(record.change)
    if change is None:
        reasons.append(
            "The session note has no Change line. "
            "Record Change: inject or Change: update to keep the live page. "
            "A replace or a removal records Change: replace or Change: remove, "
            "plus Go: and Provenance: direct."
        )
    elif change == "invalid":
        reasons.append(
            f"Change {record.change!r} is outside inject, update, replace, and remove. "
            "Record one of those four, then run this gate again."
        )
    elif change in REPLACE.values():
        if not go_quote(record.go):
            reasons.append(
                f"Change is {change}. "
                "Record a Go: line with the user's own words, then run this gate again."
            )
        provenance = classify_provenance(record.provenance)
        if provenance is None:
            reasons.append(
                f"Change is {change}. "
                "Record Provenance: direct after the user says yes, then run this gate again."
            )
        elif provenance == "invalid":
            reasons.append(
                f"Provenance {record.provenance!r} is outside direct, relay, and build. "
                f"A {change} needs Provenance: direct."
            )
        elif provenance != "direct":
            reasons.append(
                f"Provenance is {provenance}. "
                f"A {change} needs Provenance: direct and a Go: quote from the user. "
                "Record Change: inject or Change: update to keep the live page, "
                "or wait for a direct yes."
            )
    if reasons:
        return Decision("refuse", tuple(reasons))
    return Decision("allow", ())


def fail_invocation(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refuse a live-page push unless the session note records a Thin-Slice "
            "preview (an existing local path, a file URL, or an http(s) loopback "
            "URL with a path) and, when the change replaces or removes a live "
            "section, a direct yes."
        )
    )
    parser.add_argument(
        "--note",
        required=True,
        help="Path of the session note with Preview, Change, Go, and Provenance lines.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON object on stdout.")
    args = parser.parse_args(argv)
    path = Path(args.note)
    if not str(args.note).strip():
        return fail_invocation(
            "Pass --note with the session note path and run the gate again."
        )
    if not path.is_file():
        return fail_invocation(
            f"The session note at {path} is missing. "
            "Pass --note with the session note path and run the gate again."
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return fail_invocation(
            f"The session note at {path} could not be read ({exc}). "
            "Pass --note with a readable session note and run the gate again."
        )
    record = parse_note(text)
    decision = decide(record)
    payload = decision.as_dict(record)
    if args.json:
        print(json.dumps(payload, indent=2))
    elif decision.status == "allow":
        print("allow")
        print(f"preview: {record.preview}")
        print(f"change: {record.change}")
    else:
        print("refuse")
        for reason in decision.reasons:
            print(f"- {reason}")
    return 0 if decision.status == "allow" else 1


if __name__ == "__main__":
    sys.exit(main())
