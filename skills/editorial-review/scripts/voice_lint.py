#!/usr/bin/env python3
"""Lexical backstop for Lens E.

    python3 skills/editorial-review/scripts/voice_lint.py PATH
        [--surface analytical|professional|note|essay]
        [--json]

Checks banned vocabulary and banned phrases from
references/ai-voice-detection.md, unspaced em dashes, the comma form,
the two-sentence is-not twin, announcing-pair subheads, and a short
British-spelling list (organise, analyse, behaviour). Prints the file,
the line, the rule id, and the line.

On analytical, professional, and note, a file over 300 words with no
level-two heading is rule unsectioned. Essay skips that rule. With no
--surface, the sectioning rule is skipped.

Exit 0 when the check is clean. Exit 1 when it finds problems.
Exit 2 on a bad invocation.

The semicolon twin, phantom contrast, twin parallel verbs, and rhythm
stay with the reviewer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SURFACES = ("analytical", "professional", "note", "essay")
SECTION_SURFACES = frozenset({"analytical", "professional", "note"})
SECTION_WORD_LIMIT = 300
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}

BANNED_WORDS = """
delve delves delved delving
landscape landscapes
leverage leverages leveraged leveraging
tapestry tapestries
weave weaves weaving woven
navigate navigates navigated navigating
robust
comprehensive
multifaceted
underscore underscores underscored underscoring
nuanced
pivotal
paramount
foster fosters fostered fostering
realm realms
harness harnesses harnessed harnessing
seamlessly
crucial
furthermore
moreover
additionally
fundamental
significant
showcase showcases showcased showcasing
intricate
vibrant
interplay
""".split()

BANNED_PHRASES = (
    "here's the kicker",
    "here's the thing",
    "plot twist",
    "let me break this down",
    "the bottom line",
    "make no mistake",
    "can't stress this enough",
    "in today's fast-paced world",
    "in the realm of",
    "it is important to note",
    "it could be argued",
)

BANNED_VOCAB = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(BANNED_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
BANNED_PHRASE = re.compile(
    "|".join(re.escape(p) for p in sorted(BANNED_PHRASES, key=len, reverse=True)),
    re.IGNORECASE,
)
EM_DASH = re.compile("\\S\u2014|\u2014\\S")
COMMA_NOT = re.compile(r"[A-Za-z], not [A-Za-z]")
IS_NOT_TWIN = re.compile(
    r"is not [^\n]{1,40}\.\s+(?:It|That|They) (?:is|are)",
    re.IGNORECASE,
)
ANNOUNCING = re.compile(r"^\*\*[^*]+\.\s+(?:Then|Or|So|But|And)\s")
US_SPELLING = re.compile(
    r"\b(?:organiz(?:e|es|ed|ing|er|ation|ations|ational)|"
    r"analyz(?:e|es|ed|ing|er)|"
    r"behaviors?|behavioral|behaviorally)\b",
    re.IGNORECASE,
)
WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
LEVEL_TWO = re.compile(r"^##\s+\S")


@dataclass(frozen=True, order=True)
class Finding:
    file: str
    line: int
    rule: str
    text: str

    def as_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "rule": self.rule, "text": self.text}


def normalise_quotes(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def read_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def iter_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(name for name in dirnames if name != ".git" and not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if Path(name).suffix.lower() in TEXT_SUFFIXES:
                found.append(Path(dirpath) / name)
    return found


def label_for(path: Path, root: Path) -> str:
    if root.is_file():
        return root.as_posix()
    return f"{root.as_posix()}/{path.relative_to(root).as_posix()}"


def lint_text(label: str, text: str, surface: str | None) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.split("\n")
    for idx, line in enumerate(lines, start=1):
        if BANNED_VOCAB.search(line):
            findings.append(Finding(label, idx, "banned-vocab", line))
        if BANNED_PHRASE.search(normalise_quotes(line)):
            findings.append(Finding(label, idx, "banned-phrase", line))
        if EM_DASH.search(line):
            findings.append(Finding(label, idx, "em-dash", line))
        if COMMA_NOT.search(line):
            findings.append(Finding(label, idx, "comma-not", line))
        if US_SPELLING.search(line):
            findings.append(Finding(label, idx, "us-spelling", line))
        if ANNOUNCING.search(line):
            findings.append(Finding(label, idx, "announcing-pair", line))
    for match in IS_NOT_TWIN.finditer(text):
        line_no = text.count("\n", 0, match.start()) + 1
        findings.append(Finding(label, line_no, "is-not-twin", lines[line_no - 1]))
    if surface in SECTION_SURFACES and len(WORD.findall(text)) > SECTION_WORD_LIMIT:
        if not any(LEVEL_TWO.match(line) for line in lines):
            for idx, line in enumerate(lines, start=1):
                if line.strip():
                    findings.append(Finding(label, idx, "unsectioned", line))
                    break
    findings.sort()
    return findings


def emit(findings: list[Finding], as_json: bool) -> None:
    if as_json:
        payload = {"problems": len(findings), "findings": [item.as_dict() for item in findings]}
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    for item in findings:
        print(f"{item.file}:{item.line}:{item.rule}: {item.text}")
    print(f"problems: {len(findings)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="voice_lint.py",
        description=(
            "Lexical backstop for Lens E. "
            "Exit 0 when clean, 1 when problems are found, 2 on a bad invocation."
        ),
    )
    parser.add_argument("path", type=Path, help="file or directory to check")
    parser.add_argument(
        "--surface",
        choices=SURFACES,
        help=(
            "analytical, professional, and note flag a file over 300 words "
            "with no level-two heading; essay skips that rule"
        ),
    )
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 2

    if not args.path.exists():
        print(f"path does not exist: {args.path}", file=sys.stderr)
        return 2
    if not args.path.is_file() and not args.path.is_dir():
        print(f"path is not a file or directory: {args.path}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    try:
        for path in iter_inputs(args.path):
            findings.extend(
                lint_text(label_for(path, args.path), read_text(path), args.surface)
            )
    except OSError as exc:
        print(
            f"cannot read {args.path}: {exc}. Pass a file or directory this process can read.",
            file=sys.stderr,
        )
        return 2
    findings.sort()
    emit(findings, args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
