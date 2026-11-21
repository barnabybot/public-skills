#!/usr/bin/env python3
"""Reject a diff that adds an explanatory or workaround code comment.

A comment may stay when it is a licence header, a shebang, a lint or type
directive, or a why-comment that names a constraint the code cannot show.
`vendor/` directories are upstream snapshots, so this
check leaves them alone. Markdown is prose.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".retired"}
HASH_SUFFIXES = {".sh", ".bash", ".zsh", ".rb"}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".scss"}
CSS_SUFFIXES = {".css"}
HTML_SUFFIXES = {".html", ".htm"}

DIRECTIVE_RE = re.compile(
    r"(?i)("
    r"spdx-license-identifier|\bcopyright\b|\blicen[cs]e\b|all rights reserved|"
    r"eslint-disable|eslint-enable|@ts-ignore|@ts-expect-error|@ts-nocheck|@ts-check|"
    r"\bnoqa\b|\btype:\s*\S|\bshellcheck\b|"
    r"phpcs:|phpstan|psalm-|rubocop:|prettier-ignore|biome-ignore|stylelint-disable|"
    r"cspell:|istanbul ignore|v8 ignore|v8-ignore|\bcoverage:\s*(?:off|on)|"
    r"noinspection|frozen_string_literal|\bcoding[:=]|-\*-|"
    r"pylint:|pyright:|ruff:|mypy:|\bnosec\b|\bpragma:|\bfmt:\s*(?:off|on)|"
    r"[\w.-]+:(?:ignore|ignore-file|start|end|begin)\b|"
    r">>>\s*BEGIN|<<<\s*END"
    r")"
)
WHY_RE = re.compile(
    r"(?i)("
    r"\bbecause\b|\botherwise\b|\bmust\b|\bcannot\b|\bcan't\b|\bdo not\b|\bdon't\b|"
    r"\bupstream\b|\bprotocol\b|\bquirk\b|\bregression\b|\bruled\b|\bruling\b|"
        r"\binvariant\b|\bclobber|\bdeadlock\b|\bwent blind\b|\bsilently\b|"
        r"\bftruncate\b|\bidempoten\w*|\bbreak|\bbroken\b|\bfails\b|\bfailed\b|"
        r"\brefus|\brejects\b|\bunless\b|\buntil\b|"
        r"\bCVE-\d|\bGHSA-|\bRFC\s*\d|\b20\d{2}-\d{2}-\d{2}\b|"
    r"\bso\b|\bnever\b|\binstead\b|\bintentionally\b|\bearlier\b|\brather than\b|"
    r"\bignores?\b|\bwithout\b|\busage:|\bonly when\b|\bstill\b|\bwould\b|"
        r"\bbug\b|\bendpoint\b|\bCORS\b|\bauthoris|\bauthoriz|\bwhy\b|"
        r"\bADR-\d|\bcompatib|\bfallback\b|\bno range\b"
        r")"
)
BANNED_RE = re.compile(
    r"(?i)^(?:hack|hacks|workaround|work-around|todo|fixme|xxx|temp|temporary|kludge|fallback|note)\b"
)
URL_RE = re.compile(r"https?://")
TOKEN_KEY_RE = re.compile(r"^[A-Za-z_][\w-]*(?:\.[A-Za-z0-9_-]+)+\s*(?:—|–|-)")
MIRROR_BLOCK_RE = re.compile(
    r"/\*\s*>>>\s*BEGIN\s+.*?\*/.*?/\*\s*<<<\s*END\s+(?:mirrored block|canon mirror)\s*\*/",
    re.I | re.S,
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
HEREDOC_RE = re.compile(r"<<-?\s*(['\"\\]?)(\w+)\1")
STAR_COMMENT_RE = re.compile(r"^\s*\*(?:/|\s+[A-Za-z])")


def normalise_comment(raw: str) -> str:
    text = raw.strip()
    if text.startswith("<!--"):
        text = text[4:]
        if text.endswith("-->"):
            text = text[:-3]
        return text.strip()
    if text.startswith("/*"):
        text = text[2:]
        if text.endswith("*/"):
            text = text[:-2]
        return text.strip()
    if text.startswith("//"):
        return text[2:].strip()
    if text.startswith("#"):
        return text[1:].strip()
    if text.startswith("*"):
        return text[1:].strip()
    return text


def block_allowed(bodies: list[str]) -> bool:
    """True when a comment block is a directive, a licence, or a why-comment."""
    texts = []
    for body in bodies:
        cleaned = normalise_comment(body).strip()
        if cleaned:
            texts.append(cleaned)
    if not texts:
        return False
    blob = "\n".join(texts)
    if DIRECTIVE_RE.search(blob) or URL_RE.search(blob):
        return True
    if any(TOKEN_KEY_RE.match(text) for text in texts):
        return True
    if BANNED_RE.match(texts[0]):
        return False
    return WHY_RE.search(blob) is not None


def in_scope(path: str) -> bool:
    rel = path.replace("\\", "/").lstrip("./")
    if rel.startswith("vendor/") or rel.startswith(".retired/"):
        return False
    if "/fixtures/" in f"/{rel}" or "/golden/" in f"/{rel}":
        return False
    if rel.endswith(".md"):
        return False
    return language_for(rel) is not None


def language_for(path: str, text: str | None = None) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in HASH_SUFFIXES:
        return "hash"
    if suffix in JS_SUFFIXES:
        return "js"
    if suffix in CSS_SUFFIXES:
        return "css"
    if suffix in HTML_SUFFIXES:
        return "html"
    if suffix == ".rb":
        return "ruby"
    if suffix:
        return None
    if text is None:
        candidate = Path(path)
        if not candidate.is_file():
            return None
        try:
            text = candidate.read_text(encoding="utf-8")[:240]
        except (OSError, UnicodeError):
            return None
    first = text.split("\n", 1)[0]
    if not first.startswith("#!"):
        return None
    if "python" in first:
        return "python"
    if "ruby" in first:
        return "ruby"
    if re.search(r"\b(bash|sh|zsh)\b", first):
        return "hash"
    return None


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _abs(starts: list[int], line: int, col: int) -> int:
    return starts[line - 1] + col


def _hash_fallback(text: str) -> list[tuple[int, int, int, str, bool]]:
    """Full-line hash comments when a diff fragment does not tokenise."""
    spans = []
    for line_no, line in enumerate(text.split("\n"), 1):
        stripped = line.lstrip()
        if not stripped.startswith("#") or stripped.startswith("#!"):
            continue
        col = len(line) - len(stripped)
        spans.append((line_no, col, len(line.rstrip("\n")), stripped, True))
    return spans


def python_comment_spans(text: str) -> list[tuple[int, int, int, str, bool]]:
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(text.encode("utf-8")).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError, UnicodeError):
        return _hash_fallback(text)
    lines = text.split("\n")
    spans = []
    for tok in tokens:
        if tok.type != tokenize.COMMENT or tok.string.startswith("#!"):
            continue
        line_no = tok.start[0]
        start_col = tok.start[1]
        end_col = tok.end[1]
        line = lines[line_no - 1] if line_no - 1 < len(lines) else ""
        full = line[:start_col].strip() == ""
        spans.append((line_no, start_col, end_col, tok.string, full))
    return spans


def _close_quote(line: str, quote: str) -> str | None:
    index = 0
    while index < len(line):
        if line[index] == "\\" and quote != "'":
            index += 2
            continue
        if line[index] == quote:
            return None
        index += 1
    return quote


def hash_comment_spans(text: str) -> list[tuple[int, int, int, str, bool]]:
    spans: list[tuple[int, int, int, str, bool]] = []
    heredoc: str | None = None
    quote: str | None = None
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        if heredoc:
            if line.strip() == heredoc:
                heredoc = None
            continue
        if quote:
            quote = _close_quote(line, quote)
            continue
        index = 0
        opened: str | None = None
        found: tuple[int, int, str, bool] | None = None
        while index < len(line):
            char = line[index]
            if char == "\\" and opened != "'":
                index += 2
                continue
            if opened:
                if char == opened:
                    opened = None
                index += 1
                continue
            if char in {"'", '"'}:
                opened = char
                index += 1
                continue
            if char == "`":
                close = line.find("`", index + 1)
                index = len(line) if close < 0 else close + 1
                continue
            if char == "#":
                prev = line[index - 1] if index else ""
                if prev in {"$", "{"}:
                    index += 1
                    continue
                raw = line[index:]
                if raw.startswith("#!") and line[:index].strip() == "":
                    found = None
                else:
                    found = (index, len(line), raw, line[:index].strip() == "")
                break
            if char == "<" and line.startswith("<<", index):
                match = HEREDOC_RE.match(line[index:])
                if match:
                    heredoc = match.group(2)
                    index += match.end()
                    continue
            index += 1
        if opened and found is None:
            quote = opened
        if found and heredoc and found[0] < line.find("<<"):
            heredoc = None
        if found:
            spans.append((line_no, found[0], found[1], found[2], found[3]))
    return spans


def _skip_quoted(text: str, start: int, quote: str, limit: int) -> int:
    index = start + 1
    while index < limit:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        if text[index] == "\n" and quote != "`":
            return index
        index += 1
    return limit


def _skip_template(text: str, start: int, limit: int) -> int:
    index = start + 1
    while index < limit:
        if text[index] == "\\":
            index += 2
            continue
        if text.startswith("${", index):
            index += 2
            depth = 1
            while index < limit and depth:
                if text[index] in {"'", '"', "`"}:
                    index = _skip_quoted(text, index, text[index], limit)
                    continue
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                index += 1
            continue
        if text[index] == "`":
            return index + 1
        index += 1
    return limit


_REGEX_BEFORE = set("([{:;,=!&|?*%^~<>")
_REGEX_WORDS = {
    "return", "throw", "case", "typeof", "in", "of", "delete", "void",
    "yield", "await", "else", "do", "new",
}


def _starts_regex(text: str, index: int) -> bool:
    cursor = index - 1
    while cursor >= 0 and text[cursor] in " \t\r\n":
        cursor -= 1
    if cursor < 0:
        return True
    char = text[cursor]
    if char in _REGEX_BEFORE:
        return True
    if char in "+-":
        return cursor == 0 or text[cursor - 1] != char
    if char.isalnum() or char in {"_", "$"}:
        end = cursor + 1
        while cursor >= 0 and (text[cursor].isalnum() or text[cursor] in {"_", "$"}):
            cursor -= 1
        return text[cursor + 1:end] in _REGEX_WORDS
    return False


def _skip_regex(text: str, start: int, limit: int) -> int:
    index = start + 1
    in_class = False
    while index < limit:
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            return start + 1
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            index += 1
            while index < limit and text[index].isalpha():
                index += 1
            return index
        index += 1
    return start + 1


def slash_comment_spans(text: str, line_comments: bool, start: int = 0, limit: int | None = None):
    """Absolute (start, end, raw) spans. end is exclusive and stops before a newline for //."""
    end_limit = len(text) if limit is None else limit
    spans: list[tuple[int, int, str]] = []
    index = start
    while index < end_limit:
        char = text[index]
        if char in {"'", '"'}:
            index = _skip_quoted(text, index, char, end_limit)
            continue
        if char == "`" and line_comments:
            index = _skip_template(text, index, end_limit)
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2, end_limit)
            if close < 0:
                break
            stop = close + 2
            spans.append((index, stop, text[index:stop]))
            index = stop
            continue
        if line_comments and text.startswith("//", index):
            close = text.find("\n", index, end_limit)
            stop = end_limit if close < 0 else close
            spans.append((index, stop, text[index:stop]))
            index = stop
            continue
        if line_comments and char == "/" and _starts_regex(text, index):
            index = _skip_regex(text, index, end_limit)
            continue
        index += 1
    return spans


def html_comment_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    index = 0
    length = len(text)
    while index < length:
        comment = text.find("<!--", index)
        script = text.find("<script", index)
        style = text.find("<style", index)
        points = [(pos, kind) for pos, kind in ((comment, "comment"), (script, "script"), (style, "style")) if pos >= 0]
        if not points:
            break
        pos, kind = min(points)
        if kind == "comment":
            close = text.find("-->", pos + 4)
            if close < 0:
                break
            stop = close + 3
            spans.append((pos, stop, text[pos:stop]))
            index = stop
            continue
        if kind == "script":
            tag = re.match(r"<script\b[^>]*>", text[pos:], re.IGNORECASE)
            if not tag:
                index = pos + 7
                continue
            body = pos + tag.end()
            close = re.search(r"</script\s*>", text[body:], re.IGNORECASE)
            stop = body + close.start() if close else length
            spans.extend(slash_comment_spans(text, True, body, stop))
            index = body + close.end() if close else length
            continue
        tag = re.match(r"<style\b[^>]*>", text[pos:], re.IGNORECASE)
        if not tag:
            index = pos + 6
            continue
        body = pos + tag.end()
        close = re.search(r"</style\s*>", text[body:], re.IGNORECASE)
        stop = body + close.start() if close else length
        spans.extend(slash_comment_spans(text, False, body, stop))
        index = body + close.end() if close else length
    return spans


def _expand(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start) + 1
    newline = text.find("\n", end)
    suffix_end = len(text) if newline < 0 else newline
    prefix = text[line_start:start]
    suffix = text[end:suffix_end]
    if prefix.strip() == "" and suffix.strip() == "":
        return line_start, (suffix_end + 1 if newline >= 0 else suffix_end)
    while start > line_start and text[start - 1] in " \t":
        start -= 1
    return start, end


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _protect_mirror_blocks(text: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Leave a canon mirror block untouched, markers and token-key comments included."""
    protected = [(match.start(), match.end()) for match in MIRROR_BLOCK_RE.finditer(text)]
    if not protected:
        return ranges
    return [
        (start, end)
        for start, end in ranges
        if not any(start < stop and end > begin for begin, stop in protected)
    ]


def _apply(text: str, ranges: list[tuple[int, int]]) -> str:
    for start, end in reversed(_merge(ranges)):
        text = text[:start] + text[end:]
    return text


def _hash_ranges(text: str, spans: list[tuple[int, int, int, str, bool]]) -> list[tuple[int, int]]:
    starts = _line_starts(text)
    ranges: list[tuple[int, int]] = []
    group: list[tuple[int, int, int, str, bool]] = []

    def flush() -> None:
        if not group:
            return
        if not block_allowed([item[3] for item in group]):
            for line_no, col, end_col, _raw, full in group:
                abs_start = _abs(starts, line_no, col)
                abs_end = _abs(starts, line_no, end_col)
                if full:
                    ranges.append((starts[line_no - 1], starts[line_no] if line_no < len(starts) else len(text)))
                else:
                    ranges.append(_expand(text, abs_start, abs_end))
        group.clear()

    last_line = None
    for span in spans:
        line_no, _col, _end, _raw, full = span
        if full and group and group[-1][4] and last_line is not None and line_no == last_line + 1:
            group.append(span)
        else:
            flush()
            group = [span]
        last_line = line_no
    flush()
    return ranges


def _slash_ranges(text: str, spans: list[tuple[int, int, str]]) -> list[tuple[int, int]]:
    """Group consecutive full-line // comments. Inline and block comments stand alone."""
    ranges: list[tuple[int, int]] = []
    line_at = []
    for start, end, raw in spans:
        line_no = text.count("\n", 0, start) + 1
        line_start = text.rfind("\n", 0, start) + 1
        full = raw.startswith("//") and text[line_start:start].strip() == ""
        line_at.append((line_no, start, end, raw, full))

    group: list[tuple[int, int, int, str, bool]] = []
    last_line = None

    def flush() -> None:
        if not group:
            return
        if not block_allowed([item[3] for item in group]):
            for _line, start, end, _raw, _full in group:
                ranges.append(_expand(text, start, end))
        group.clear()

    for line_no, start, end, raw, full in line_at:
        if (
            full
            and group
            and group[-1][4]
            and last_line is not None
            and line_no == last_line + 1
        ):
            group.append((line_no, start, end, raw, full))
        else:
            flush()
            group = [(line_no, start, end, raw, full)]
        last_line = line_no
    flush()
    return ranges


def strip_text(path: str, text: str) -> str:
    if "\0" in text[:1024]:
        return text
    lang = language_for(path, text)
    if lang == "python":
        spans = python_comment_spans(text)
        if not spans and _looks_unparsed(text):
            return text
        return _apply(text, _hash_ranges(text, spans))
    if lang == "hash":
        return _apply(text, _hash_ranges(text, hash_comment_spans(text)))
    if lang == "ruby":
        spans = [span for span in hash_comment_spans(text) if span[4]]
        return _apply(text, _hash_ranges(text, spans))
    if lang == "js":
        return _apply(text, _slash_ranges(text, slash_comment_spans(text, True)))
    if lang == "css":
        ranges = _slash_ranges(text, slash_comment_spans(text, False))
        return _apply(text, _protect_mirror_blocks(text, ranges))
    if lang == "html":
        return _apply(text, _slash_ranges(text, html_comment_spans(text)))
    return text


def _looks_unparsed(text: str) -> bool:
    return any(line.strip().startswith("#") and not line.strip().startswith("#!") for line in text.split("\n"))


def iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and name != "vendor"]
        else:
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if in_scope(rel) or (Path(rel).suffix == "" and path.is_file()):
                yield rel, path


def _comment_only(line: str, lang: str) -> tuple[list[str], bool]:
    probe = line if line.endswith("\n") else line + "\n"
    if lang == "python":
        spans = python_comment_spans(probe)
    elif lang == "hash":
        spans = hash_comment_spans(probe)
    elif lang == "js":
        raws = slash_comment_spans(probe, True)
        return _slash_line_result(line, raws)
    elif lang == "css":
        raws = slash_comment_spans(probe, False)
        return _slash_line_result(line, raws)
    elif lang == "html":
        raws = html_comment_spans(probe)
        extra = STAR_COMMENT_RE.match(line)
        if not raws and extra:
            return [line.strip()], True
        return _slash_line_result(line, raws)
    else:
        return [], False
    if not spans:
        return [], False
    return [span[3] for span in spans], all(span[4] for span in spans)


def _slash_line_result(line: str, spans: list[tuple[int, int, str]]) -> tuple[list[str], bool]:
    if not spans:
        if STAR_COMMENT_RE.match(line):
            return [line.strip()], True
        return [], False
    bodies = [raw for _start, _end, raw in spans]
    only = line.strip() == "".join(body.strip() for _s, _e, body in [(0, 0, b) for b in bodies]) or (
        len(spans) == 1 and line.strip() == spans[0][2].strip()
    )
    return bodies, only


def violations(diff: str) -> list[str]:
    findings: list[str] = []
    path = ""
    lang = None
    new_line = 0
    pending: list[tuple[str, int, str]] = []

    def flush() -> None:
        if not pending:
            return
        if path and not block_allowed([body for _path, _line, body in pending]):
            for item_path, line_no, body in pending:
                findings.append(f"{item_path}:{line_no}: {normalise_comment(body)[:180]}")
        pending.clear()

    for raw in diff.split("\n"):
        if raw.startswith("diff --git "):
            flush()
            path = raw.split(" b/", 1)[1] if " b/" in raw else ""
            if path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            lang = language_for(path) if path and in_scope(path) else None
            new_line = 0
            continue
        if raw.startswith("@@"):
            flush()
            match = HUNK_RE.match(raw)
            new_line = int(match.group(1)) if match else 0
            continue
        if raw.startswith("+++") or raw.startswith("---") or raw.startswith("\\"):
            continue
        if lang is None or path == "/dev/null":
            if raw.startswith("+"):
                new_line += 1
            elif raw.startswith(" "):
                new_line += 1
            continue
        if raw.startswith("+"):
            text = raw[1:]
            bodies, only = _comment_only(text, lang)
            if bodies and only:
                pending.append((path, new_line, bodies[0] if len(bodies) == 1 else "\n".join(bodies)))
            else:
                flush()
                if bodies and not block_allowed(bodies):
                    findings.append(f"{path}:{new_line}: {normalise_comment(bodies[0])[:180]}")
            new_line += 1
            continue
        flush()
        if raw.startswith(" "):
            new_line += 1
    flush()
    return findings


def resolve_base() -> str | None:
    env = os.environ.get("COMMENT_CHECK_BASE", "").strip()
    if env and set(env) != {"0"}:
        try:
            return subprocess.check_output(
                ["git", "merge-base", "HEAD", env], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            return env
    for ref in ("origin/main", "main"):
        try:
            return subprocess.check_output(
                ["git", "merge-base", "HEAD", ref], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            continue
    return None


def diff_text(base: str) -> str:
    return subprocess.check_output(
        ["git", "diff", "-U0", "--no-ext-diff", base], text=True, errors="replace"
    )



RATCHET_BASELINE_REL = "scripts/code-comments-baseline.json"
RATCHET_EXTS = {".py", ".js", ".mjs", ".ts", ".sh"}
STRICT_ALLOW_PREFIXES = (
    "#!", "# type:", "# noqa", "# pylint:", "# pragma:", "# fmt:", "# ruff:",
    "# -*-", "# coding:", "// @ts-", "// eslint-", "/* eslint-",
)


def is_strict_directive(text: str) -> bool:
    s = text.strip()
    if any(s.startswith(prefix) for prefix in STRICT_ALLOW_PREFIXES):
        return True
    low = s.lower()
    return "spdx-license-identifier" in low or "copyright" in low or "license" in low or "licence" in low


def strict_comment_count(rel: str, src: str) -> int:
    ext = Path(rel).suffix.lower()
    if ext not in RATCHET_EXTS:
        return 0
    if ext == ".py":
        count = 0
        try:
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT and not is_strict_directive(tok.string):
                    count += 1
        except (tokenize.TokenError, IndentationError):
            return 0
        return count
    count = 0
    for line in src.splitlines():
        st = line.strip()
        if ext == ".sh":
            if st.startswith("#") and not is_strict_directive(st):
                count += 1
        else:
            if (st.startswith("//") or st.startswith("/*")) and not is_strict_directive(st):
                count += 1
    return count


def ratchet_tracked_files(root: Path, staged: bool) -> list[str]:
    args = ["git", "-C", str(root), "diff", "--cached", "--relative", "--name-only", "--diff-filter=ACMR", "-z"] if staged else ["git", "-C", str(root), "ls-files", "-z"]
    raw = subprocess.check_output(args)
    results = []
    for rel in raw.decode("utf-8", errors="replace").split("\0"):
        if not rel or rel.startswith("vendor/"):
            continue
        parts = Path(rel).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if Path(rel).suffix.lower() in RATCHET_EXTS:
            results.append(rel)
    return sorted(results)


def scan_ratchet_counts(root: Path, rel_paths: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rel in rel_paths:
        full = root / rel
        if full.is_symlink() or not full.is_file():
            continue
        try:
            src = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cnt = strict_comment_count(rel, src)
        if cnt > 0:
            counts[rel] = cnt
    return counts


def evaluate_ratchet(counts: dict[str, int], baseline: dict[str, int], staged: bool = False) -> list[str]:
    errors = []
    for rel, cnt in sorted(counts.items()):
        cap = baseline.get(rel, 0)
        if cnt > cap:
            errors.append(f"EXCEEDED: {rel} has {cnt} non-directive comment lines (baseline cap {cap})")
    if not staged:
        for rel, cap in sorted(baseline.items()):
            cur = counts.get(rel, 0)
            if cur < cap:
                errors.append(f"TIGHTEN BASELINE: {rel} dropped from {cap} to {cur}; run --write-baseline")
    return errors


def load_ratchet_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in data.get("files", {}).items()}


def write_ratchet_baseline(path: Path, counts: dict[str, int]) -> None:
    payload = {
        "total_comment_lines": sum(counts.values()),
        "files_with_comments": len(counts),
        "files": dict(sorted(counts.items())),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="strip non-essential comments in the tree")
    parser.add_argument("--audit", action="store_true", help="report what --write would delete")
    parser.add_argument("--ratchet", action="store_true", help="enforce the shrinking per-file comment baseline")
    parser.add_argument("--staged", action="store_true", help="check staged files only with --ratchet")
    parser.add_argument("--write-baseline", action="store_true", help="write the per-file comment ratchet baseline")
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.write_baseline or args.ratchet:
        baseline_path = Path(args.baseline) if args.baseline else root / RATCHET_BASELINE_REL
        rel_paths = ratchet_tracked_files(root, staged=args.staged)
        counts = scan_ratchet_counts(root, rel_paths)
        if args.write_baseline:
            write_ratchet_baseline(baseline_path, counts)
            print(f"comment_ratchet: wrote {len(counts)} files ({sum(counts.values())} comment lines)")
            return 0
        baseline = load_ratchet_baseline(baseline_path)
        errors = evaluate_ratchet(counts, baseline, staged=args.staged)
        if errors:
            for err in errors[:100]:
                print(err, file=sys.stderr)
            if len(errors) > 100:
                print(f"... {len(errors) - 100} more", file=sys.stderr)
            return 1
        print(f"comment_ratchet: ok ({sum(counts.values())} baseline lines across {len(counts)} files)")
        return 0
    if args.write or args.audit:
        files = 0
        removed = 0
        samples: list[str] = []
        for rel, path in iter_source_files(root):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if language_for(rel, original) is None:
                continue
            updated = strip_text(rel, original)
            if updated == original:
                continue
            files += 1
            removed += max(0, original.count("\n") - updated.count("\n"))
            if args.audit and len(samples) < 12:
                samples.append(rel)
            if args.write:
                path.write_text(updated, encoding="utf-8")
        mode = "would change" if args.audit else "changed"
        print(f"{mode} {files} files, about {removed} lines")
        for sample in samples:
            print(sample)
        return 0

    base = resolve_base()
    if not base:
        print("check_code_comments: no base commit, skipped", file=sys.stderr)
        return 0
    found = violations(diff_text(base))
    if not found:
        print("check_code_comments: ok")
        return 0
    for line in found[:200]:
        print(line)
    if len(found) > 200:
        print(f"... {len(found) - 200} more")
    print(f"check_code_comments: {len(found)} explanatory or workaround comments added")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
