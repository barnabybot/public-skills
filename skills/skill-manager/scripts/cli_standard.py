"""Advisory lint for references/cli-standard.md.

Finds Python argparse or click entrypoints that a skill, workflow, or
reference tells an agent to run, then reports gaps in --help, --json,
--dry-run on writers, and terse errors. The caller prints the gaps.
This module does not exit the process.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

MIN_TEXT = 20
EXCLUDE_TOP = {
    ".cursor",
    ".git",
    ".github",
    ".plan",
    ".retired",
    "agents",
    "docs",
    "hooks",
    "output",
    "pstack",
    "publish",
    "scripts",
    "vendor",
}
SKIP_PARTS = {"tests", "test", "__pycache__", "node_modules"}
GUIDANCE_RE = re.compile(r"\b(try|use|pass)\b", re.I)
BARE_ERROR_RE = re.compile(r"error[.!]?", re.I)
IDENT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
WRITER_RE = re.compile(
    r"\.(?:write_text|write_bytes)\s*\("
    r"|\.unlink\s*\("
    r"|\bos\.(?:remove|unlink|replace|rename)\s*\("
    r"|\bshutil\.(?:move|copy2?|copytree|rmtree)\s*\("
)
OPEN_WRITE_RE = re.compile(r"""['\"][^'\"]*(?:[wax]|\+)[^'\"]*['\"]""")
EXIT2_RE = re.compile(r"\breturn\s+2\b|\bsys\.exit\(\s*2\s*\)")
FSTRING_FIELD_RE = re.compile(r"\{[^{}]*\}")


def audit(root: Path) -> tuple[int, list[tuple[str, str]]]:
    """Return the number of agent-facing CLIs and their gap messages."""
    root = root.resolve()
    entrypoints = discover(root)
    docs = skill_docs(root)
    ambiguous = ambiguous_names(entrypoints)
    chosen = [path for path in entrypoints if mentioned(docs, path, root, ambiguous)]
    gaps: list[tuple[str, str]] = []
    for path in chosen:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for message in gaps_for(text):
            gaps.append((rel, message))
    return len(chosen), gaps


def discover(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in EXCLUDE_TOP and not name.startswith(".")
            ]
        else:
            dirnames[:] = [
                name
                for name in dirnames
                if name not in SKIP_PARTS
                and not name.startswith(".")
                and not name.startswith("_archive")
            ]
        if not skill_tree(root, Path(dirpath)):
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
                continue
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if is_entrypoint(text):
                found.append(path)
    found.sort()
    return found


def skill_tree(root: Path, directory: Path) -> bool:
    rel = directory.relative_to(root)
    if rel.parts and (rel.parts[0] in EXCLUDE_TOP or rel.parts[0].startswith(".")):
        return False
    if any(part in SKIP_PARTS or part.startswith("_archive") for part in rel.parts):
        return False
    current = directory
    while True:
        if (current / "SKILL.md").is_file():
            return True
        if current == root:
            return False
        current = current.parent


def skill_docs(root: Path) -> str:
    chunks: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in EXCLUDE_TOP and not name.startswith(".")
            ]
        else:
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".") and not name.startswith("_archive") and name != ".retired"
            ]
            if ".retired" in rel_dir.parts or "vendor" in rel_dir.parts or "pstack" in rel_dir.parts:
                dirnames[:] = []
                continue
        for name in filenames:
            if not name.endswith(".md"):
                continue
            rel = (rel_dir / name)
            if not is_skill_doc(rel):
                continue
            path = Path(dirpath) / name
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(chunks)


def is_skill_doc(rel: Path) -> bool:
    if rel.name == "SKILL.md":
        return True
    return "workflows" in rel.parts or "references" in rel.parts


def is_entrypoint(text: str) -> bool:
    if not re.search(r"__name__\s*==\s*['\"]__main__['\"]", text):
        return False
    scan = Scan(text)
    if scan.calls("ArgumentParser"):
        return True
    if scan.calls("click.command") or scan.calls("click.group"):
        return True
    return "@click.command" in text or "@click.group" in text


def ambiguous_names(paths: list[Path]) -> set[str]:
    counts: dict[str, int] = {}
    for path in paths:
        counts[path.name] = counts.get(path.name, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def mentioned(docs: str, path: Path, root: Path, ambiguous: set[str]) -> bool:
    name = path.name
    if not re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", docs):
        return False
    if name not in ambiguous:
        return True
    rel = path.relative_to(root).as_posix()
    key = "/".join(rel.split("/")[-3:])
    return key in docs or rel in docs


def gaps_for(text: str) -> list[str]:
    messages: list[str] = []
    help_gap = help_message(text)
    if help_gap:
        messages.append(help_gap)
    if not has_json(text):
        messages.append("missing machine-readable output (--json or equivalent)")
    if writes(text) and not has_dry_run(text):
        messages.append("writer has no --dry-run")
    messages.extend(terse_messages(text))
    if bare_exit(text):
        messages.append("exit 2 with no stderr guidance")
    return messages


def help_message(text: str) -> str | None:
    scan = Scan(text)
    parsers = scan.calls("ArgumentParser")
    click_calls = scan.calls("click.command") + scan.calls("click.group")
    docs = click_docstrings(text)
    enabled = [body for body in parsers if not keyword_is_false(body, "add_help")]
    has_click = bool(click_calls or docs or "@click.command" in text or "@click.group" in text)
    manual_help = False
    for body in scan.calls("add_argument") + scan.calls("click.option"):
        if any(value in {"--help", "-h"} for value, _flag in literal_strings(body)):
            manual_help = True
    if not enabled and not has_click and not manual_help:
        return "missing --help"
    descriptions: list[str] = []
    for body in enabled:
        desc = keyword_string(body, "description")
        if desc:
            descriptions.append(desc)
    for body in click_calls:
        hint = keyword_string(body, "help")
        if hint:
            descriptions.append(hint)
    descriptions.extend(docs)
    if any(len(" ".join(item.split())) >= MIN_TEXT for item in descriptions):
        return None
    return "thin --help: parser description is missing or shorter than 20 characters"


def has_json(text: str) -> bool:
    scan = Scan(text)
    for body in scan.calls("add_argument") + scan.calls("click.option"):
        literals = [value for value, _fstring in literal_strings(body)]
        if "--json" in literals:
            return True
        if "--format" in literals and "json" in literals:
            return True
    return False


def has_dry_run(text: str) -> bool:
    scan = Scan(text)
    for body in scan.calls("add_argument") + scan.calls("click.option"):
        if any(value == "--dry-run" for value, _fstring in literal_strings(body)):
            return True
    return False


def writes(text: str) -> bool:
    scan = Scan(text)
    if WRITER_RE.search(scan.code_text()):
        return True
    for body in scan.calls("open"):
        if OPEN_WRITE_RE.search(body):
            return True
    return False


def terse_messages(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    scan = Scan(text)
    bodies: list[str] = []
    bodies.extend(body for body in scan.calls("print") if "sys.stderr" in body)
    bodies.extend(scan.calls("parser.error"))
    bodies.extend(scan.calls("sys.stderr.write"))
    bodies.extend(scan.calls("SystemExit"))
    for name in stderr_helpers(text):
        bodies.extend(scan.calls(name))
    for body in bodies:
        literals = literal_strings(body)
        if not literals:
            continue
        value, fstring = literals[0]
        static = static_text(value, fstring)
        if not static or static in seen or not terse(static):
            continue
        seen.add(static)
        shown = static if len(static) <= 60 else static[:57] + "..."
        found.append(f"terse error: {shown}")
    found.sort()
    return found


def terse(static: str) -> bool:
    if BARE_ERROR_RE.fullmatch(static):
        return True
    if len(static) >= MIN_TEXT:
        return False
    return GUIDANCE_RE.search(static) is None


def bare_exit(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not EXIT2_RE.search(line):
            continue
        window = "\n".join(lines[max(0, index - 12) : index + 1])
        if "SystemExit" in window:
            continue
        if "sys.stderr" in window or "parser.error" in window:
            continue
        if re.search(r"\bfail\s*\(", window):
            continue
        return True
    return False


def stderr_helpers(text: str) -> set[str]:
    names: set[str] = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"def ([A-Za-z_]\w*)\s*\(", line)
        if not match:
            continue
        window = "\n".join(lines[index : index + 25])
        if "sys.stderr" in window and EXIT2_RE.search(window):
            names.add(match.group(1))
    return names


def static_text(value: str, fstring: bool) -> str:
    text = value
    if fstring:
        text = FSTRING_FIELD_RE.sub("", text)
    return " ".join(text.split())


def click_docstrings(text: str) -> list[str]:
    docs: list[str] = []
    for match in re.finditer(r"@click\.(?:command|group)\b", text):
        tail = text[match.end() : match.end() + 1200]
        found = re.search(
            r"def\s+\w+\s*\(.*?\)\s*:\s*(?:\"\"\"(.*?)\"\"\"|'''(.*?)''')",
            tail,
            re.S,
        )
        if found:
            docs.append(found.group(1) if found.group(1) is not None else found.group(2) or "")
    return docs


def keyword_is_false(body: str, keyword: str) -> bool:
    scan = Scan(body)
    index = 0
    while True:
        found = scan.find_code(keyword, index)
        if found is None:
            return False
        cursor = scan.skip_space(found + len(keyword))
        if cursor < len(body) and body[cursor] == "=":
            cursor = scan.skip_space(cursor + 1)
            if body.startswith("False", cursor):
                return True
        index = found + len(keyword)
    return False


def keyword_string(body: str, keyword: str) -> str | None:
    scan = Scan(body)
    index = 0
    while True:
        found = scan.find_code(keyword, index)
        if found is None:
            return None
        cursor = scan.skip_space(found + len(keyword))
        if cursor >= len(body) or body[cursor] != "=":
            index = found + len(keyword)
            continue
        cursor = scan.skip_space(cursor + 1)
        if cursor < len(body) and body[cursor] == "(":
            cursor = scan.skip_space(cursor + 1)
        parts: list[str] = []
        while True:
            literal = read_literal(body, cursor)
            if literal is None:
                break
            value, _fstring, end = literal
            parts.append(value)
            cursor = scan.skip_space(end)
        if not parts:
            index = found + len(keyword)
            continue
        return "".join(parts)
    return None


def literal_strings(body: str) -> list[tuple[str, bool]]:
    values: list[tuple[str, bool]] = []
    index = 0
    while index < len(body):
        literal = read_literal(body, index)
        if literal is None:
            index += 1
            continue
        value, fstring, end = literal
        if end > index:
            values.append((value, fstring))
            index = end
            continue
        index += 1
    return values


def read_literal(src: str, index: int) -> tuple[str, bool, int] | None:
    if index >= len(src):
        return None
    flags, cursor = string_flags(src, index)
    if cursor >= len(src) or src[cursor] not in "'\"":
        return None
    quote = src[cursor]
    triple = src.startswith(quote * 3, cursor)
    if triple:
        end = src.find(quote * 3, cursor + 3)
        if end < 0:
            return None
        return src[cursor + 3 : end], "f" in flags, end + 3
    end = cursor + 1
    while end < len(src):
        if src[end] == "\\":
            end += 2
            continue
        if src[end] == quote:
            return src[cursor + 1 : end], "f" in flags, end + 1
        end += 1
    return None


def string_flags(src: str, index: int) -> tuple[str, int]:
    cursor = index
    flags = ""
    while cursor < len(src) and src[cursor] in "rRuUfFbB" and len(flags) < 2:
        nxt = cursor + 1
        if nxt < len(src) and (src[nxt] in "'\"" or src[nxt] in "rRuUfFbB"):
            flags += src[cursor].lower()
            cursor += 1
            continue
        break
    return flags, cursor


class Scan:
    def __init__(self, src: str) -> None:
        self.src = src
        self.mask = code_mask(src)

    def calls(self, callee: str) -> list[str]:
        bodies: list[str] = []
        start = 0
        while True:
            found = self.find_code(callee, start)
            if found is None:
                break
            if found > 0 and self.src[found - 1] in IDENT:
                start = found + len(callee)
                continue
            cursor = self.skip_space(found + len(callee))
            if cursor >= len(self.src) or self.src[cursor] != "(" or not self.mask[cursor]:
                start = found + len(callee)
                continue
            end = matching_paren(self.src, self.mask, cursor)
            if end is None:
                break
            bodies.append(self.src[cursor + 1 : end])
            start = end + 1
        return bodies

    def find_code(self, needle: str, start: int) -> int | None:
        while True:
            found = self.src.find(needle, start)
            if found < 0:
                return None
            if all(self.mask[found + offset] for offset in range(len(needle))):
                return found
            start = found + 1

    def skip_space(self, index: int) -> int:
        while index < len(self.src) and self.src[index] in " \t\r\n" and self.mask[index]:
            index += 1
        return index

    def code_text(self) -> str:
        return "".join(ch if self.mask[index] else " " for index, ch in enumerate(self.src))


def code_mask(src: str) -> list[bool]:
    mask = [True] * len(src)
    index = 0
    while index < len(src):
        if src[index] == "#":
            end = src.find("\n", index)
            end = len(src) if end < 0 else end
            for cursor in range(index, end):
                mask[cursor] = False
            index = end
            continue
        flags, cursor = string_flags(src, index)
        if cursor < len(src) and src[cursor] in "'\"" and (flags or cursor == index):
            start = index if flags else cursor
            literal = read_literal(src, start)
            if literal is not None:
                _value, _fstring, end = literal
                for pos in range(start, end):
                    mask[pos] = False
                index = end
                continue
        index += 1
    return mask


def matching_paren(src: str, mask: list[bool], open_at: int) -> int | None:
    depth = 0
    index = open_at
    while index < len(src):
        if not mask[index]:
            index += 1
            continue
        char = src[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None
