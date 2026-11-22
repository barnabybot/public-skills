#!/usr/bin/env python3
"""Reject a diff that adds an explanatory or workaround code comment.

A comment may stay when it is a licence header, a shebang, a lint or type
directive, or a why-comment that names a constraint the code cannot show.
`vendor/` and generated `pstack/` skills are upstream snapshots, so this
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
HASH_SUFFIXES = {".sh", ".bash", ".zsh"}
RUBY_SUFFIXES = {".rb"}
TOML_SUFFIXES = {".toml"}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".scss"}
SWIFT_SUFFIXES = {".swift"}
CSS_SUFFIXES = {".css"}
HTML_SUFFIXES = {".html", ".htm"}
ASTRO_SUFFIXES = {".astro"}

DIRECTIVE_RE = re.compile(
    r"(?i)("
    r"spdx-license-identifier|\bcopyright\b|\blicen[cs]e\b|all rights reserved|"
    r"eslint-disable|eslint-enable|@ts-ignore|@ts-expect-error|@ts-nocheck|@ts-check|"
    r"\bnoqa\b|\btype:\s*\S|\bshellcheck\b|"
    r"phpcs:|phpstan|psalm-|rubocop:|prettier-ignore|biome-ignore|stylelint-disable|"
    r"cspell:|istanbul ignore|v8 ignore|v8-ignore|\bcoverage:\s*(?:off|on)|"
    r"noinspection|frozen_string_literal|\bcoding[:=]|-\*-|"
    r"pylint:|pyright:|ruff:|mypy:|\bnosec\b|\bpragma:|\bfmt:\s*(?:off|on)|"
    r"personal-data:|[\w.-]+:(?:ignore|ignore-file|start|end|begin)\b|"
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
        r"\bADR-\d|\bcompatib|\bfallback\b|\bno range\b|\btailscale\b"
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
RUBY_HEREDOC_RE = re.compile(r"<<[-~]?(['\"]?)([A-Za-z_]\w*)\1")
ASTRO_FRONTMATTER_RE = re.compile(r"\A\ufeff?[ \t]*---[ \t]*\r?\n(.*?)\r?\n[ \t]*---[ \t]*(?:\r?\n|\Z)", re.S)
STAR_COMMENT_RE = re.compile(r"^\s*\*(?:/|\s+[A-Za-z])")


def normalise_comment(raw: str) -> str:
    text = raw.strip()
    if text.startswith("{/*"):
        text = text[3:]
        if text.endswith("*/}"):
            text = text[:-3]
        return text.strip()
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
    if rel.startswith("pstack/") and not rel.startswith("pstack/_port/"):
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
    if suffix in RUBY_SUFFIXES:
        return "ruby"
    if suffix in TOML_SUFFIXES:
        return "toml"
    if suffix in JS_SUFFIXES:
        return "js"
    if suffix in SWIFT_SUFFIXES:
        return "swift"
    if suffix in CSS_SUFFIXES:
        return "css"
    if suffix in HTML_SUFFIXES:
        return "html"
    if suffix in ASTRO_SUFFIXES:
        return "astro"
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


_SHELL_COMMENT_BEFORE = set(" \t;|&()")


def hash_comment_spans(text: str) -> list[tuple[int, int, int, str, bool]]:
    spans: list[tuple[int, int, int, str, bool]] = []
    heredocs: list[str] = []
    stack: list[str] = []
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        if heredocs:
            if line.strip() == heredocs[0]:
                heredocs.pop(0)
            continue
        index = 0
        found: tuple[int, int, str, bool] | None = None
        new_heredocs: list[str] = []
        while index < len(line):
            char = line[index]
            state = stack[-1] if stack else ""
            if state == "'":
                if char == "'":
                    stack.pop()
                index += 1
                continue
            if state == '"':
                if char == "\\":
                    index += 2
                    continue
                if char == "$":
                    if line.startswith("$(", index) and not line.startswith("$((", index):
                        stack.append("$(")
                        index += 2
                        continue
                if char == '"':
                    stack.pop()
                index += 1
                continue
            if char == "\\":
                index += 2
                continue
            if char in {"'", '"'}:
                stack.append(char)
                index += 1
                continue
            if char == "$" and line.startswith("$(", index) and not line.startswith("$((", index):
                stack.append("$(")
                index += 2
                continue
            if char == "(" and state in {"$(", "("}:
                stack.append("(")
                index += 1
                continue
            if char == ")" and state in {"$(", "("}:
                stack.pop()
                index += 1
                continue
            if char == "`":
                close = line.find("`", index + 1)
                index = len(line) if close < 0 else close + 1
                continue
            if char == "#":
                prev = line[index - 1] if index else ""
                if index == 0 or prev in _SHELL_COMMENT_BEFORE:
                    raw = line[index:]
                    if raw.startswith("#!") and line[:index].strip() == "":
                        found = None
                    else:
                        found = (index, len(line), raw, line[:index].strip() == "")
                    break
                index += 1
                continue
            if char == "<" and line.startswith("<<", index) and not line.startswith("<<<", index):
                match = HEREDOC_RE.match(line[index:])
                if match:
                    new_heredocs.append(match.group(2))
                    index += match.end()
                    continue
            index += 1
        if new_heredocs:
            heredocs.extend(new_heredocs)
        if found:
            spans.append((line_no, found[0], found[1], found[2], found[3]))
    return spans


def ruby_comment_spans(text: str) -> list[tuple[int, int, int, str, bool]]:
    """Full-line Ruby comments and =begin/=end blocks, skipping Ruby heredocs."""
    spans: list[tuple[int, int, int, str, bool]] = []
    heredocs: list[str] = []
    in_block_doc = False
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        if heredocs:
            if line.strip() == heredocs[0]:
                heredocs.pop(0)
            continue
        if in_block_doc:
            spans.append((line_no, 0, len(line), line, True))
            if line == "=end" or line.startswith(("=end ", "=end\t")):
                in_block_doc = False
            continue
        if line == "=begin" or line.startswith(("=begin ", "=begin\t")):
            in_block_doc = True
            spans.append((line_no, 0, len(line), line, True))
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            if not stripped.startswith("#!"):
                col = len(line) - len(stripped)
                spans.append((line_no, col, len(line), stripped, True))
            continue
        index = 0
        opened: str | None = None
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
            if char == "<" and line.startswith("<<", index):
                match = RUBY_HEREDOC_RE.match(line[index:])
                if match:
                    heredocs.append(match.group(2))
                    index += match.end()
                    continue
            index += 1
    return spans


def toml_comment_spans(text: str) -> list[tuple[int, int, int, str, bool]]:
    """TOML # comments (full-line and inline), skipping basic/literal/multiline strings."""
    spans: list[tuple[int, int, int, str, bool]] = []
    multiline: str | None = None
    for line_no, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        index = 0
        length = len(line)
        while index < length:
            if multiline:
                if multiline == '"""' and line[index] == "\\":
                    index += 2
                    continue
                if line.startswith(multiline, index):
                    index += 3
                    multiline = None
                    continue
                index += 1
                continue
            if line.startswith('"""', index):
                multiline = '"""'
                index += 3
                continue
            if line.startswith("'''", index):
                multiline = "'''"
                index += 3
                continue
            char = line[index]
            if char == '"':
                index += 1
                while index < length:
                    if line[index] == "\\":
                        index += 2
                        continue
                    if line[index] == '"':
                        index += 1
                        break
                    index += 1
                continue
            if char == "'":
                close = line.find("'", index + 1)
                index = length if close < 0 else close + 1
                continue
            if char == "#":
                raw = line[index:]
                full = line[:index].strip() == ""
                if not (full and raw.startswith("#!")):
                    spans.append((line_no, index, length, raw, full))
                break
            index += 1
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


def _skip_triple_double_quote(text: str, start: int, limit: int) -> int:
    index = start + 3
    while index < limit:
        if text[index] == "\\":
            index += 2
            continue
        if text.startswith('"""', index):
            return index + 3
        index += 1
    return limit


def _find_nested_block_comment_end(text: str, start: int, limit: int) -> int:
    depth = 1
    index = start + 2
    while index < limit and depth > 0:
        if text.startswith("/*", index):
            depth += 1
            index += 2
            continue
        if text.startswith("*/", index):
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        index += 1
    return -1


def slash_comment_spans(
    text: str,
    line_comments: bool,
    start: int = 0,
    limit: int | None = None,
    allow_regex: bool = True,
):
    """Absolute (start, end, raw) spans. end is exclusive and stops before a newline for //."""
    end_limit = len(text) if limit is None else limit
    spans: list[tuple[int, int, str]] = []
    index = start
    while index < end_limit:
        char = text[index]
        if not allow_regex and char == '"' and text.startswith('"""', index):
            index = _skip_triple_double_quote(text, index, end_limit)
            continue
        if char in {"'", '"'}:
            index = _skip_quoted(text, index, char, end_limit)
            continue
        if char == "`" and line_comments and allow_regex:
            index = _skip_template(text, index, end_limit)
            continue
        if text.startswith("/*", index):
            if not allow_regex:
                stop = _find_nested_block_comment_end(text, index, end_limit)
                if stop < 0:
                    break
            else:
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
        if line_comments and allow_regex and char == "/" and _starts_regex(text, index):
            index = _skip_regex(text, index, end_limit)
            continue
        index += 1
    return spans


def html_comment_spans(
    text: str,
    start: int = 0,
    jsx_comments: bool = False,
) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    index = start
    length = len(text)
    while index < length:
        candidates = [
            (text.find("<!--", index), "comment"),
            (text.find("<script", index), "script"),
            (text.find("<style", index), "style"),
        ]
        if jsx_comments:
            candidates.append((text.find("{/*", index), "jsx"))
        points = [(pos, kind) for pos, kind in candidates if pos >= 0]
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
        if kind == "jsx":
            close = text.find("*/", pos + 3)
            if close < 0:
                break
            after = close + 2
            while after < length and text[after] in " \t\r\n":
                after += 1
            stop = after + 1 if after < length and text[after] == "}" else close + 2
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


def astro_comment_spans(text: str) -> list[tuple[int, int, str]]:
    """Comments in .astro frontmatter (TS/JS), template (HTML/JSX), <script>, and <style>."""
    spans: list[tuple[int, int, str]] = []
    match = ASTRO_FRONTMATTER_RE.match(text)
    body_start = 0
    if match:
        spans.extend(slash_comment_spans(text, True, match.start(1), match.end(1)))
        body_start = match.end()
    spans.extend(html_comment_spans(text, start=body_start, jsx_comments=True))
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


def _protected_mirror_ranges(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in MIRROR_BLOCK_RE.finditer(text)]


def _protect_mirror_blocks(text: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Leave a canon mirror block untouched, markers and token-key comments included."""
    protected = _protected_mirror_ranges(text)
    if not protected:
        return ranges
    return [
        (start, end)
        for start, end in ranges
        if not any(start < stop and end > begin for begin, stop in protected)
    ]


def _protect_mirror_spans(
    text: str, spans: list[tuple[int, int, str]]
) -> list[tuple[int, int, str]]:
    protected = _protected_mirror_ranges(text)
    if not protected:
        return spans
    return [
        (start, end, raw)
        for start, end, raw in spans
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
        return _apply(text, _hash_ranges(text, ruby_comment_spans(text)))
    if lang == "toml":
        return _apply(text, _hash_ranges(text, toml_comment_spans(text)))
    if lang == "js":
        return _apply(text, _slash_ranges(text, slash_comment_spans(text, True)))
    if lang == "swift":
        return _apply(text, _slash_ranges(text, slash_comment_spans(text, True, allow_regex=False)))
    if lang == "css":
        ranges = _slash_ranges(text, slash_comment_spans(text, False))
        return _apply(text, _protect_mirror_blocks(text, ranges))
    if lang == "html":
        ranges = _slash_ranges(text, html_comment_spans(text))
        return _apply(text, _protect_mirror_blocks(text, ranges))
    if lang == "astro":
        ranges = _slash_ranges(text, astro_comment_spans(text))
        return _apply(text, _protect_mirror_blocks(text, ranges))
    return text


def _looks_unparsed(text: str) -> bool:
    return any(line.strip().startswith("#") and not line.strip().startswith("#!") for line in text.split("\n"))


def iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and name != "vendor"]
        elif rel_dir == "pstack":
            dirnames[:] = [name for name in dirnames if name == "_port"]
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
    elif lang == "ruby":
        spans = ruby_comment_spans(probe)
    elif lang == "toml":
        spans = toml_comment_spans(probe)
    elif lang == "js":
        raws = slash_comment_spans(probe, True)
        return _slash_line_result(line, raws)
    elif lang == "swift":
        raws = slash_comment_spans(probe, True, allow_regex=False)
        return _slash_line_result(line, raws)
    elif lang == "css":
        raws = slash_comment_spans(probe, False)
        return _slash_line_result(line, raws)
    elif lang in {"html", "astro"}:
        raws = html_comment_spans(probe, jsx_comments=(lang == "astro"))
        if not raws and lang == "astro":
            raws = slash_comment_spans(probe, True)
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


def violations(diff: str, root: Path | None = None) -> list[str]:
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
            lang = None
            if path:
                if in_scope(path):
                    lang = language_for(path)
                elif root is not None and Path(path).suffix == "":
                    candidate = root / path
                    if not candidate.is_file() and path.startswith("skills/"):
                        candidate = root / path[len("skills/"):]
                    head = _read_shebang_head(candidate)
                    if head is not None:
                        lang = language_for(path, head)
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
RATCHET_EXTS = (
    {".py"}
    | HASH_SUFFIXES
    | RUBY_SUFFIXES
    | TOML_SUFFIXES
    | JS_SUFFIXES
    | SWIFT_SUFFIXES
    | CSS_SUFFIXES
    | HTML_SUFFIXES
    | ASTRO_SUFFIXES
)
STRICT_ALLOW_PREFIXES = (
    "#!",
    "# type:",
    "# noqa",
    "# pylint:",
    "# pyright:",
    "# mypy:",
    "# pragma:",
    "# fmt:",
    "# ruff:",
    "# nosec",
    "# shellcheck",
    "# frozen_string_literal:",
    "# rubocop:",
    "# personal-data:",
    "# -*-",
    "# coding:",
    "# coding=",
    "// @ts-",
    "// eslint-",
    "// biome-ignore",
    "// prettier-ignore",
    "// swiftlint:",
    "/* eslint-",
    "/* stylelint-",
    "/* prettier-ignore",
    "/* biome-ignore",
    "/* istanbul ignore",
    "/* v8 ignore",
    "/* c8 ignore",
)
STRICT_DIRECTIVE_RE = re.compile(
    r"(?i)(?:"
    r"spdx-license-identifier|"
    r"^\s*copyright\b|"
    r"^\s*all rights reserved\b|"
    r"(?:copyright|©).{0,80}all rights reserved|"
    r"^\s*licen[cs]ed?\s+(?:under|to)\b|"
    r"^\s*(?:mit|apache|bsd|isc|gpl|lgpl|mpl)\s+licen[cs]e\b|"
    r"^\s*(?:noqa|nosec|shellcheck|frozen_string_literal:|coding[:=]|-\*-|"
    r"type:\s*(?:ignore|check)\b|pylint:|pyright:|ruff:|mypy:|pragma:|"
    r"fmt:\s*(?:off|on)\b|coverage:\s*(?:off|on)\b|rubocop:|"
    r"eslint-(?:disable|enable)|@ts-(?:ignore|expect-error|nocheck|check)|"
    r"prettier-ignore|biome-ignore|stylelint-(?:disable|enable)|"
    r"istanbul ignore|v8[- ]ignore|c8 ignore|swiftlint:|cspell:|"
    r"noinspection|phpcs:|phpstan|psalm-|personal-data:)|"
    r"^\s*[\w.-]+:(?:ignore|ignore-file|start|end|begin)\b|"
    r">>>\s*BEGIN|<<<\s*END"
    r")"
)


def is_strict_directive(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if any(s.startswith(prefix) for prefix in STRICT_ALLOW_PREFIXES):
        return True
    body = normalise_comment(s)
    return STRICT_DIRECTIVE_RE.search(body) is not None


def _count_slash_spans(spans: list[tuple[int, int, str]]) -> int:
    count = 0
    for _start, _end, raw in spans:
        if not is_strict_directive(raw):
            count += raw.count("\n") + 1
    return count


def strict_comment_count(rel: str, src: str) -> int:
    lang = language_for(rel, src)
    if lang is None:
        return 0
    if lang == "python":
        return sum(1 for _ln, _c, _e, raw, _f in python_comment_spans(src) if not is_strict_directive(raw))
    if lang == "hash":
        return sum(1 for _ln, _c, _e, raw, _f in hash_comment_spans(src) if not is_strict_directive(raw))
    if lang == "ruby":
        return sum(1 for _ln, _c, _e, raw, _f in ruby_comment_spans(src) if not is_strict_directive(raw))
    if lang == "toml":
        return sum(1 for _ln, _c, _e, raw, _f in toml_comment_spans(src) if not is_strict_directive(raw))
    if lang == "js":
        return _count_slash_spans(slash_comment_spans(src, True))
    if lang == "swift":
        return _count_slash_spans(slash_comment_spans(src, True, allow_regex=False))
    if lang == "css":
        spans = _protect_mirror_spans(src, slash_comment_spans(src, False))
        return _count_slash_spans(spans)
    if lang == "html":
        spans = _protect_mirror_spans(src, html_comment_spans(src))
        return _count_slash_spans(spans)
    if lang == "astro":
        spans = _protect_mirror_spans(src, astro_comment_spans(src))
        return _count_slash_spans(spans)
    return 0


def _read_shebang_head(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            chunk = fh.read(240)
    except OSError:
        return None
    if b"\0" in chunk:
        return None
    return chunk.decode("utf-8", errors="replace")


def ratchet_tracked_files(root: Path, staged: bool) -> list[str]:
    args = (
        ["git", "-C", str(root), "diff", "--cached", "--relative", "--name-only", "--diff-filter=ACMR", "-z"]
        if staged
        else ["git", "-C", str(root), "ls-files", "-z"]
    )
    raw = subprocess.check_output(args)
    results = []
    for rel in raw.decode("utf-8", errors="replace").split("\0"):
        if not rel or rel.startswith("vendor/") or rel.startswith(".retired/"):
            continue
        parts = Path(rel).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if parts and parts[0] == "pstack" and (len(parts) < 2 or parts[1] != "_port"):
            continue
        if "/fixtures/" in f"/{rel}" or "/golden/" in f"/{rel}":
            continue
        suffix = Path(rel).suffix.lower()
        if suffix in RATCHET_EXTS:
            results.append(rel)
            continue
        if suffix == "":
            head = _read_shebang_head(root / rel)
            if head is not None and language_for(rel, head) in {"python", "hash", "ruby"}:
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
    found = violations(diff_text(base), root=root)
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
