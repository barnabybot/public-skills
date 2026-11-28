#!/usr/bin/env python3
"""Multi-harness session trace and Agents-vault boundary parsers.

Normalises raw transcripts from Claude Code, Codex, Grok, Muse, and Antigravity
(T3 Code and standalone) plus operational session notes and optional scheduled-job logs from
the Agents vault into a single internal shape for discovery, extraction, and
friction scanning.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _default_agents_vault(home: Path) -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "scripts" / "vault_paths.py",
        Path.home() / "Repos" / "home" / "skills" / "scripts" / "vault_paths.py",
    ]
    vp = next((c for c in candidates if c.is_file()), None)
    if vp is not None:
        cached = sys.modules.get("skills_vault_paths")
        if cached is None:
            spec = importlib.util.spec_from_file_location("skills_vault_paths", vp)
            if spec and spec.loader:
                cached = importlib.util.module_from_spec(spec)
                sys.modules["skills_vault_paths"] = cached
                spec.loader.exec_module(cached)
        if cached is not None and hasattr(cached, "agents_dir"):
            return Path(cached.agents_dir(home))
    env = os.environ.get("AGENT_NOTES", "").strip()
    if env:
        return Path(env).expanduser()
    return home / "agent-notes"

ALL_SOURCES = ("claude", "codex", "grok", "muse", "antigravity", "vault", "cron")
RAW_HARNESSES = ("claude", "codex", "grok", "muse", "antigravity")

CORRECTION = re.compile(
    r"\b(no|not|don'?t|stop|wrong|wait|actually|instead|revert|undo|fix|"
    r"again|nope|isn'?t|doesn'?t|bad|never|but)\b",
    re.I,
)

HARNESS_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-",
    "<system-reminder>",
    "<turn_aborted>",
    "<environment_context>",
    "<user_instructions>",
    "# AGENTS.md instructions",
)

GROK_TAB_NAMER = "You name terminal workspace tabs for a developer running coding agents."
T3_DELEGATED_PREFIX = "[T3 Code: the agent in T3 thread"
USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S)
USER_REQUEST_RE = re.compile(r"<user_request>\s*(.*?)\s*</user_request>", re.S)
CODEX_SID_RE = re.compile(r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(.+)\.jsonl$")
SLASH_CMD_RE = re.compile(r"^/([a-zA-Z0-9][a-zA-Z0-9:_-]{1,50})\b")
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")

TOOL_NAME_MAP = {
    "bash": "Bash",
    "run_command": "Bash",
    "run_terminal_command": "Bash",
    "exec": "Bash",
    "exec_command": "Bash",
    "shell": "Bash",
    "shell_command": "Bash",
    "terminal": "Bash",
    "write": "Write",
    "write_file": "Write",
    "write_to_file": "Write",
    "create_file": "Write",
    "edit": "Edit",
    "edit_file": "Edit",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "MultiEdit",
    "multiedit": "MultiEdit",
    "apply_patch": "Edit",
    "read": "Read",
    "read_file": "Read",
    "view_file": "Read",
    "grep": "Grep",
    "grep_search": "Grep",
    "ripgrep": "Grep",
    "glob": "Glob",
    "find_by_name": "Glob",
    "webfetch": "WebFetch",
    "web_fetch": "WebFetch",
    "websearch": "WebSearch",
    "search_web": "WebSearch",
    "skill": "Skill",
    "agent": "Agent",
    "task": "Task",
    "invoke_subagent": "Agent",
    "delegate_task": "Agent",
    "mcp_t3-code_delegate_task": "Agent",
}


def default_roots(
    claude_projects: str | Path | None = None,
    agents_vault: str | Path | None = None,
) -> dict[str, object]:
    """Resolve default source roots with optional environment or CLI overrides."""
    home = Path.home()
    claude = Path(claude_projects or os.environ.get("CLAUDE_PROJECTS_DIR") or home / ".claude/projects").expanduser()
    codex = Path(os.environ.get("CODEX_SESSIONS_DIR") or home / ".codex/sessions").expanduser()
    grok = Path(os.environ.get("GROK_SESSIONS_DIR") or home / ".grok/sessions").expanduser()
    muse = Path(os.environ.get("MUSE_SESSIONS_DIR") or home / ".local/share/muse/sessions").expanduser()
    ag_env = os.environ.get("ANTIGRAVITY_ROOTS", "").strip()
    if ag_env:
        antigravity = [Path(p).expanduser() for p in ag_env.split(os.pathsep) if p.strip()]
    else:
        antigravity = [
            home / ".t3/userdata/providers/antigravity",
            home / ".gemini/antigravity/brain",
        ]
    vault_override = agents_vault or os.environ.get("AGENTS_VAULT_DIR")
    vault = Path(vault_override).expanduser() if vault_override else _default_agents_vault(home)
    return {
        "claude": claude,
        "codex": codex,
        "grok": grok,
        "muse": muse,
        "antigravity": antigravity,
        "vault": vault,
    }


def iso_from_epoch(value: int | float | None) -> str:
    """Convert Unix seconds, milliseconds, or microseconds into UTC ISO-8601."""
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    if num <= 0:
        return ""
    if num > 1e14:
        num /= 1e6
    elif num > 1e11:
        num /= 1e3
    return datetime.fromtimestamp(num, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise_tool_name(name: str) -> str:
    """Map harness-specific tool names onto canonical tool labels."""
    raw = (name or "").strip()
    if not raw:
        return ""
    mapped = TOOL_NAME_MAP.get(raw.lower())
    return mapped or raw


def normalise_tool_input(tool_name: str, raw_input: object) -> dict:
    """Normalise harness-specific tool argument keys onto canonical keys."""
    if isinstance(raw_input, str):
        stripped = raw_input.strip()
        if stripped.startswith("{"):
            try:
                raw_input = json.loads(stripped)
            except json.JSONDecodeError:
                raw_input = {"command": raw_input}
        else:
            raw_input = {"command": raw_input}
    if not isinstance(raw_input, dict):
        return {}
    out = dict(raw_input)
    for k, v in list(out.items()):
        if isinstance(v, str) and len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    if tool_name == "Bash":
        cmd = out.get("command") or out.get("CommandLine") or out.get("cmd") or out.get("script") or out.get("input")
        if cmd is not None:
            out["command"] = str(cmd)
    elif tool_name in ("Write", "Edit", "MultiEdit", "Read"):
        fp = (
            out.get("file_path")
            or out.get("Path")
            or out.get("AbsolutePath")
            or out.get("TargetFile")
            or out.get("target_file")
            or out.get("path")
        )
        if fp is not None:
            out["file_path"] = str(fp)
        if "Content" in out and "content" not in out:
            out["content"] = str(out["Content"])
        if "Replacement" in out and "new_string" not in out:
            out["new_string"] = str(out["Replacement"])
        if "ReplacementContent" in out and "new_string" not in out:
            out["new_string"] = str(out["ReplacementContent"])
    elif tool_name == "Grep":
        pat = out.get("pattern") or out.get("Query") or out.get("query")
        if pat is not None:
            out["pattern"] = str(pat)
    elif tool_name == "WebFetch":
        url = out.get("url") or out.get("Url")
        if url is not None:
            out["url"] = str(url)
    elif tool_name == "Agent":
        desc = out.get("description") or out.get("Role") or out.get("toolSummary") or out.get("title")
        if desc is not None:
            out["description"] = str(desc)
    return out


def clean_user_text(text: str) -> tuple[str, str | None]:
    """Strip Claude/harness XML wrappers and detect slash-command invocations."""
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<local-command-stdout>.*?</local-command-stdout>", "", text, flags=re.S)
    cmd = None
    m = re.search(r"<command-name>([^<]+)</command-name>", text)
    if m:
        cmd = m.group(1).strip().lstrip("/")
        a = re.search(r"<command-args>(.*?)</command-args>", text, flags=re.S)
        text = f"/{cmd} {(a.group(1).strip() if a else '')}".strip()
    text = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cmd:
        sm = SLASH_CMD_RE.match(cleaned)
        if sm:
            cmd = sm.group(1)
    return cleaned, cmd


def is_harness_text(text: str) -> bool:
    return text.lstrip().startswith(HARNESS_PREFIXES)


def first_line(text: str | None, n: int = 200) -> str:
    s = (text or "").strip()
    return s.splitlines()[0][:n] if s else ""


def tool_brief(name: str, inp: object) -> tuple[str, str | None]:
    """Produce a compact timeline summary and optional detected skill name."""
    cname = normalise_tool_name(name)
    data = normalise_tool_input(cname, inp)
    if cname == "Bash":
        return f"Bash: {str(data.get('command', ''))[:100]}", None
    if cname in ("Edit", "Write", "Read", "MultiEdit", "NotebookEdit"):
        fp = str(data.get("file_path", ""))
        sk = _skill_from_path(fp)
        return f"{cname}: {fp}", sk
    if cname == "Skill":
        sk = data.get("skill") or data.get("command")
        return f"Skill: {sk}", (str(sk) if sk else None)
    if cname in ("Task", "Agent"):
        return f"{cname}: {str(data.get('description', ''))[:80]}", None
    if cname == "Grep":
        return f"Grep: {str(data.get('pattern', ''))[:60]}", None
    if cname == "WebFetch":
        return f"WebFetch: {data.get('url', '')}", None
    return cname or name, None


def _skill_from_path(path_str: str) -> str | None:
    if not path_str.endswith("/SKILL.md"):
        return None
    parts = Path(path_str).parts
    if len(parts) >= 2:
        return parts[-2]
    return None


def classify_domain(project: str = "", cwd: str = "") -> str:
    """Assign a neutral domain bucket without encoding private client names."""
    probe = f"{project} {cwd}".lower()
    if "cron" in probe:
        return "cron"
    if "agent-notes" in probe or "vault" in probe:
        return "vault"
    if "scratch" in probe:
        return "scratch"
    if "repos" in probe or "skills" in probe or "home" in probe:
        return "repos"
    if "course" in probe:
        return "course"
    return "other"


def slug_from_cwd(cwd: str, fallback: str = "unknown") -> str:
    """Derive a clean readable project label from a working directory path."""
    cleaned = (cwd or "").strip().rstrip("/")
    if not cleaned:
        return fallback
    p = Path(cleaned)
    home = str(Path.home())
    if cleaned == home:
        return "home"
    if cleaned.startswith(home + "/"):
        rel = cleaned[len(home) + 1 :]
        parts = rel.split("/")
        if len(parts) >= 2 and parts[0] in ("Repos", "Vaults", "Scratch"):
            return f"{parts[0].lower()}/{parts[1]}"
        return parts[0]
    return p.name or fallback


def decode_claude_slug(slug: str) -> str:
    """Convert Claude Code's dash-encoded project folder name into a short label."""
    s = slug.strip("-")
    for marker, prefix in (
        ("Repos-", "repos/"),
        ("Vaults-", "vaults/"),
        ("Scratch-", "scratch/"),
    ):
        idx = s.find(marker)
        if idx >= 0:
            rest = s[idx + len(marker) :]
            return prefix + rest if rest else prefix.rstrip("/")
    return slug


def _iter_jsonl(path: Path):
    try:
        fh = path.open(encoding="utf-8", errors="ignore")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def detect_harness(path: Path) -> str:
    """Infer transcript harness from JSON record structure first, then path layout."""
    for rec in _iter_jsonl(path):
        if "step_index" in rec and "type" in rec:
            return "antigravity"
        if rec.get("type") in ("session_meta", "response_item", "event_msg"):
            return "codex"
        if rec.get("method") in ("session/update", "_x.ai/session/update"):
            return "grok"
        if "payload_type" in rec or "retained_frame" in rec:
            return "muse"
        if rec.get("type") in ("user", "assistant", "system", "result"):
            return "claude"
        break
    parts = path.parts
    if ".claude" in parts:
        return "claude"
    if ".codex" in parts or CODEX_SID_RE.match(path.name):
        return "codex"
    if ".grok" in parts or path.name == "updates.jsonl":
        return "grok"
    if "muse" in parts and path.name == "session.jsonl":
        return "muse"
    if ".system_generated" in parts and path.name in ("transcript.jsonl", "transcript_full.jsonl"):
        return "antigravity"
    return "claude"


def parse_events_claude(path: Path) -> list[dict]:
    ev: list[dict] = []
    last_cwd = ""
    for o in _iter_jsonl(path):
        if o.get("cwd"):
            last_cwd = str(o["cwd"])
        t = o.get("type")
        ts = o.get("timestamp", "") or ""
        msg = o.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if t == "user":
            kind = "user"
            if o.get("isMeta"):
                kind = "meta"
            elif (o.get("origin") or {}).get("kind") == "task-notification" or o.get("promptSource") == "system":
                kind = "notice"
            if isinstance(content, str):
                txt, _ = clean_user_text(content)
                if txt:
                    ev.append({"k": kind, "t": txt, "ts": ts})
            elif isinstance(content, list):
                texts, results = [], []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        results.append(str(c or ""))
                    elif b.get("type") == "text":
                        texts.append(b.get("text", ""))
                for r in results:
                    ev.append({"k": "result", "t": r[:2000], "ts": ts})
                if texts and not results:
                    txt, _ = clean_user_text(" ".join(texts))
                    if txt:
                        ev.append({"k": kind, "t": txt, "ts": ts})
        elif t == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    ev.append({"k": "text", "t": b["text"], "ts": ts})
                elif b.get("type") == "tool_use":
                    raw_name = str(b.get("name", ""))
                    cname = normalise_tool_name(raw_name)
                    rec = {
                        "k": "tool",
                        "name": cname,
                        "raw_name": raw_name,
                        "input": normalise_tool_input(cname, b.get("input") or {}),
                        "ts": ts,
                    }
                    if last_cwd:
                        rec["cwd"] = last_cwd
                    ev.append(rec)
    return ev


def parse_events_codex(path: Path) -> list[dict]:
    ev: list[dict] = []
    last_cwd = ""
    for o in _iter_jsonl(path):
        ts = o.get("timestamp", "") or ""
        if o.get("type") == "session_meta":
            pl = o.get("payload") or {}
            if pl.get("cwd"):
                last_cwd = str(pl["cwd"])
            continue
        if o.get("type") != "response_item":
            continue
        pl = o.get("payload") or {}
        ptype = pl.get("type")
        role = pl.get("role")
        if role == "user":
            texts = []
            for block in pl.get("content") or []:
                if isinstance(block, dict) and block.get("type") in ("input_text", "text"):
                    txt = block.get("text") or ""
                    if txt and not is_harness_text(txt):
                        texts.append(txt)
            if texts:
                cleaned = " ".join(t.strip() for t in texts if t.strip())
                if cleaned:
                    ev.append({"k": "user", "t": cleaned, "ts": ts})
        elif role == "assistant":
            for block in pl.get("content") or []:
                if isinstance(block, dict) and block.get("type") in ("output_text", "text"):
                    txt = (block.get("text") or "").strip()
                    if txt:
                        ev.append({"k": "text", "t": txt, "ts": ts})
        elif ptype in ("function_call", "custom_tool_call"):
            raw_name = pl.get("name") or ""
            raw_args = pl.get("arguments") if "arguments" in pl else pl.get("input")
            cname = normalise_tool_name(raw_name)
            rec = {
                "k": "tool",
                "name": cname,
                "raw_name": raw_name,
                "input": normalise_tool_input(cname, raw_args),
                "ts": ts,
            }
            if last_cwd:
                rec["cwd"] = last_cwd
            ev.append(rec)
        elif ptype in ("function_call_output", "custom_tool_call_output"):
            out = pl.get("output")
            if isinstance(out, list):
                out = " ".join(str(x.get("text", "")) for x in out if isinstance(x, dict))
            ev.append({"k": "result", "t": str(out or "")[:2000], "ts": ts})
    return ev


def parse_events_grok(path: Path) -> list[dict]:
    ev: list[dict] = []
    decoded_cwd = urllib.parse.unquote(path.parent.parent.name)
    grok_cwd = decoded_cwd if decoded_cwd.startswith("/") else ""
    user_buf: list[str] = []
    user_ts = ""
    ai_buf: list[str] = []
    ai_ts = ""

    def flush_user():
        nonlocal user_buf, user_ts
        if not user_buf:
            return
        raw = "".join(user_buf).strip()
        m = USER_QUERY_RE.search(raw)
        if m:
            raw = m.group(1).strip()
        if raw and not is_harness_text(raw):
            ev.append({"k": "user", "t": raw, "ts": user_ts})
        user_buf, user_ts = [], ""

    def flush_ai():
        nonlocal ai_buf, ai_ts
        if not ai_buf:
            return
        raw = "".join(ai_buf).strip()
        if raw:
            ev.append({"k": "text", "t": raw, "ts": ai_ts})
        ai_buf, ai_ts = [], ""

    for o in _iter_jsonl(path):
        ts = iso_from_epoch(o.get("timestamp")) or (o.get("timestamp") if isinstance(o.get("timestamp"), str) else "")
        u = (o.get("params") or {}).get("update")
        if isinstance(u, dict):
            su = u.get("sessionUpdate")
            if su == "user_message_chunk":
                flush_ai()
                txt = (u.get("content") or {}).get("text") or ""
                if not user_ts:
                    user_ts = ts
                user_buf.append(txt)
            elif su == "agent_message_chunk":
                flush_user()
                txt = (u.get("content") or {}).get("text") or ""
                if not ai_ts:
                    ai_ts = ts
                ai_buf.append(txt)
            elif su == "tool_call":
                flush_user()
                flush_ai()
                meta_tool = ((u.get("_meta") or {}).get("x.ai/tool") or {}).get("name")
                raw_name = meta_tool or u.get("title") or ""
                cname = normalise_tool_name(raw_name)
                rec = {
                    "k": "tool",
                    "name": cname,
                    "raw_name": raw_name,
                    "input": normalise_tool_input(cname, u.get("rawInput") or {}),
                    "ts": ts,
                }
                if grok_cwd:
                    rec["cwd"] = grok_cwd
                ev.append(rec)
            elif su == "tool_call_update":
                raw_out = u.get("rawOutput")
                if raw_out is not None:
                    text_out = json.dumps(raw_out) if not isinstance(raw_out, str) else raw_out
                    ev.append({"k": "result", "t": text_out[:2000], "ts": ts})
            elif su == "turn_completed":
                flush_user()
                flush_ai()
        elif o.get("type") == "user":
            content = o.get("content")
            if isinstance(content, str):
                m = USER_QUERY_RE.search(content)
                txt = (m.group(1) if m else content).strip()
                if txt and not is_harness_text(txt):
                    ev.append({"k": "user", "t": txt, "ts": ts})
    flush_user()
    flush_ai()
    return ev


def parse_events_muse(path: Path) -> list[dict]:
    ev: list[dict] = []
    last_cwd = ""
    for o in _iter_jsonl(path):
        pt = o.get("payload_type")
        pl = o.get("payload") or {}
        ts = iso_from_epoch(o.get("recorded_at"))
        if pt == "runtime.session.metadata":
            rec_meta = pl.get("record") or {}
            if rec_meta.get("workspace_root"):
                last_cwd = str(rec_meta["workspace_root"])
        elif pt == "runtime.user_intent.accepted":
            if pl.get("surface") not in (None, "main"):
                continue
            texts = [
                (b.get("text") or "").strip()
                for b in (pl.get("refill_blocks") or [])
                if isinstance(b, dict) and b.get("kind") == "text" and (b.get("text") or "").strip()
            ]
            if texts:
                ev.append({"k": "user", "t": "\n".join(texts), "ts": ts})
        elif pt == "runtime.session" and pl.get("kind") == "run":
            inner = pl.get("event") or {}
            ik = inner.get("kind")
            if ik == "assistant_message_committed":
                txt = (inner.get("text") or "").strip()
                if txt:
                    ev.append({"k": "text", "t": txt, "ts": ts})
            elif ik == "assistant_tool_calls_committed":
                for tc in inner.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    raw_name = str(tc.get("name") or "")
                    cname = normalise_tool_name(raw_name)
                    args = tc.get("arguments") or tc.get("input") or {}
                    rec = {
                        "k": "tool",
                        "name": cname,
                        "raw_name": raw_name,
                        "input": normalise_tool_input(cname, args),
                        "ts": ts,
                    }
                    if last_cwd:
                        rec["cwd"] = last_cwd
                    ev.append(rec)
            elif ik == "tool_result_batch_committed":
                for res in inner.get("results") or []:
                    if isinstance(res, dict) and res.get("text"):
                        ev.append({"k": "result", "t": str(res["text"])[:2000], "ts": ts})
    return ev


def _extract_antigravity_user_text(content: str) -> str:
    m = USER_REQUEST_RE.search(content)
    if m:
        return m.group(1).strip()
    stripped = re.sub(r"<t3_code_instructions>.*?</t3_code_instructions>", "", content, flags=re.S)
    stripped = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", stripped, flags=re.S)
    stripped = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", stripped, flags=re.S)
    stripped = re.sub(r"<runtime_info>.*?</runtime_info>", "", stripped, flags=re.S)
    return stripped.strip()


def _load_antigravity_full_user_steps(path: Path) -> dict[int, str]:
    if path.name != "transcript.jsonl":
        return {}
    full = path.with_name("transcript_full.jsonl")
    if not full.is_file():
        return {}
    out: dict[int, str] = {}
    for o in _iter_jsonl(full):
        if o.get("type") == "USER_INPUT" and "step_index" in o:
            out[int(o["step_index"])] = str(o.get("content") or "")
    return out


def parse_events_antigravity(path: Path) -> list[dict]:
    full_users = _load_antigravity_full_user_steps(path)
    is_t3 = ".t3" in path.parts
    ev: list[dict] = []
    for o in _iter_jsonl(path):
        t = o.get("type")
        ts = o.get("created_at", "") or ""
        if t == "USER_INPUT":
            idx = o.get("step_index")
            raw = full_users.get(int(idx), str(o.get("content") or "")) if idx is not None else str(o.get("content") or "")
            if "<t3_code_instructions>" in raw:
                is_t3 = True
            txt = _extract_antigravity_user_text(raw)
            if txt:
                ev.append({"k": "user", "t": txt, "ts": ts})
        elif t == "PLANNER_RESPONSE":
            txt = (o.get("content") or o.get("response") or "").strip()
            if txt:
                ev.append({"k": "text", "t": txt, "ts": ts})
            for tc in o.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                raw_name = str(tc.get("name") or "")
                cname = normalise_tool_name(raw_name)
                rec = {
                    "k": "tool",
                    "name": cname,
                    "raw_name": raw_name,
                    "harness": "antigravity",
                    "input": normalise_tool_input(cname, tc.get("args") or {}),
                    "ts": ts,
                }
                if is_t3:
                    rec["host"] = "t3-code"
                ev.append(rec)
        elif t in ("RUN_COMMAND", "GENERIC") and o.get("content"):
            ev.append({"k": "result", "t": str(o["content"])[:2000], "ts": ts})
    inferred_cwd = _antigravity_cwd_from_events(ev)
    if inferred_cwd:
        for e in ev:
            if e.get("k") == "tool" and not e.get("cwd"):
                e["cwd"] = inferred_cwd
    return ev


def parse_events_hook_calls(path: Path) -> list[dict]:
    """Parse tool calls recorded by a replay PreToolUse refusal hook."""
    ev: list[dict] = []
    for o in _iter_jsonl(path):
        ts = str(o.get("ts") or o.get("timestamp") or "")
        tc = o.get("toolCall") if isinstance(o.get("toolCall"), dict) else None
        if tc is not None:
            raw_name = tc.get("name") or ""
            raw_input = tc.get("args") or tc.get("input") or {}
        else:
            raw_name = o.get("tool_name") or o.get("toolName") or o.get("name") or ""
            raw_input = o.get("tool_input") or o.get("toolInput") or o.get("input") or o.get("args") or {}
        cname = normalise_tool_name(str(raw_name))
        if cname:
            ev.append({
                "k": "tool",
                "name": cname,
                "raw_name": str(raw_name),
                "input": normalise_tool_input(cname, raw_input),
                "ts": ts,
            })
    return ev


def parse_events_codex_exec(path: Path) -> list[dict]:
    """Parse NDJSON emitted by `codex exec --json`."""
    ev: list[dict] = []
    for o in _iter_jsonl(path):
        if o.get("type") != "item.completed":
            continue
        item = o.get("item") or {}
        itype = item.get("type")
        if itype == "command_execution":
            cmd = item.get("command") or ""
            if cmd:
                ev.append({"k": "tool", "name": "Bash", "input": {"command": str(cmd)}, "ts": ""})
            out = item.get("aggregated_output") or ""
            if out:
                ev.append({"k": "result", "t": str(out)[:2000], "ts": ""})
        elif itype == "file_change":
            for ch in item.get("changes") or []:
                if isinstance(ch, dict) and ch.get("path"):
                    ev.append({"k": "tool", "name": "Write", "input": {"file_path": str(ch["path"]), "content": ""}, "ts": ""})
        elif itype in ("agent_message", "message"):
            txt = (item.get("text") or "").strip()
            if txt:
                ev.append({"k": "text", "t": txt, "ts": ""})
    return ev


def parse_events(path: str | Path, harness: str | None = None) -> list[dict]:
    """Parse any supported harness transcript or replay stream into ordered events."""
    p = Path(path).expanduser()
    if harness == "hook-calls":
        return parse_events_hook_calls(p)
    if harness == "codex-exec":
        return parse_events_codex_exec(p)
    for rec in _iter_jsonl(p):
        if rec.get("type") in ("thread.started", "turn.started", "item.completed", "turn.completed", "turn.failed"):
            return parse_events_codex_exec(p)
        if "toolCall" in rec or "tool_name" in rec or "toolName" in rec:
            return parse_events_hook_calls(p)
        break
    h = harness or detect_harness(p)
    if h == "codex":
        return parse_events_codex(p)
    if h == "grok":
        return parse_events_grok(p)
    if h == "muse":
        return parse_events_muse(p)
    if h == "antigravity":
        return parse_events_antigravity(p)
    return parse_events_claude(p)


def _claude_meta(path: Path) -> tuple[bool, str]:
    headless = False
    cwd = ""
    for o in _iter_jsonl(path):
        if not cwd and o.get("cwd"):
            cwd = str(o["cwd"])
        ep = o.get("entrypoint")
        if ep and str(ep).startswith("sdk-"):
            headless = True
            break
        if cwd:
            break
    return headless, cwd


def _codex_meta(path: Path) -> tuple[bool, str, str]:
    sid = ""
    cwd = ""
    child = False
    for o in _iter_jsonl(path):
        if o.get("type") == "session_meta":
            pl = o.get("payload") or {}
            sid = str(pl.get("session_id") or pl.get("id") or "")
            cwd = str(pl.get("cwd") or "")
            src = pl.get("source")
            child = pl.get("originator") == "codex_exec" or (isinstance(src, dict) and "subagent" in src)
            break
    if not sid:
        m = CODEX_SID_RE.match(path.name)
        sid = m.group(1) if m else path.stem
    return child, sid, cwd


def _muse_meta(path: Path) -> tuple[bool, str]:
    headless = False
    cwd = ""
    for o in _iter_jsonl(path):
        pt = o.get("payload_type")
        pl = o.get("payload") or {}
        if pt == "runtime.session.route_facts":
            facts = pl.get("record") or {}
            if "local_runtime_command_socket_path" not in facts:
                headless = True
        elif pt == "runtime.session.metadata":
            rec = pl.get("record") or {}
            cwd = str(rec.get("workspace_root") or "")
        if cwd and pt == "runtime.session.route_facts":
            break
    return headless, cwd


def _antigravity_cwd_from_events(ev: list[dict]) -> str:
    path_re = re.compile(r"/Users/[^/\s\"']+/(?:Repos|Vaults|Scratch)/[^/\s\"']+")
    counts: Counter[str] = Counter()
    for e in ev[:40]:
        probe = e.get("t") or ""
        if e.get("k") == "tool":
            probe = json.dumps(e.get("input") or {})
        for m in path_re.findall(probe):
            counts[m] += 1
    return counts.most_common(1)[0][0] if counts else ""


def resume_command(harness: str, session_id: str, source_path: str = "", host: str = "") -> str:
    """Return the native resume command or pointer for a given harness."""
    if harness == "claude-code":
        return f"claude --resume {session_id}"
    if harness == "codex":
        return f"codex resume {session_id}"
    if harness == "grok":
        return f"grok --resume {session_id}"
    if harness == "antigravity":
        if host == "t3-code":
            return f"agy --conversation {session_id}"
        return f"agy --conversation {session_id}"
    if harness == "muse":
        return f"muse --resume {session_id}"
    return source_path


def events_to_session(
    ev: list[dict],
    *,
    session_id: str,
    harness: str,
    host: str = "",
    project: str = "",
    cwd: str = "",
    source_path: str = "",
) -> dict:
    """Summarise ordered events into a unified session dict for digest rendering."""
    timeline: list[tuple[str, str, str]] = []
    skills: set[str] = set()
    human = assistant = tools = correction_hits = human_chars = 0
    first_ts = last_ts = None
    first_msg = ""

    for e in ev:
        ts = e.get("ts") or ""
        hhmm = ts[11:16] if len(ts) >= 16 else "--:--"
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        k = e.get("k")
        if k == "user":
            txt, cmd = clean_user_text(e.get("t") or "")
            if cmd:
                skills.add(cmd)
            if txt:
                human += 1
                human_chars += len(txt)
                if CORRECTION.search(txt):
                    correction_hits += 1
                if not first_msg:
                    first_msg = txt[:200]
                timeline.append((hhmm, "USER", txt[:500]))
        elif k == "text":
            fl = first_line(e.get("t"))
            if fl:
                timeline.append((hhmm, "AI", fl))
                assistant += 1
        elif k == "tool":
            tools += 1
            brief, sk = tool_brief(e.get("name", ""), e.get("input"))
            if sk:
                skills.add(sk)
            timeline.append((hhmm, "TOOL", brief))

    label = project or slug_from_cwd(cwd)
    return {
        "session_id": session_id,
        "harness": harness,
        "host": host,
        "project": label,
        "cwd": cwd,
        "vault_domain": classify_domain(label, cwd),
        "timeline": timeline,
        "skills": sorted(skills),
        "human": human,
        "assistant": assistant,
        "tools": tools,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "first_msg": first_msg,
        "correction_hits": correction_hits,
        "human_chars": human_chars,
        "source_path": source_path,
        "resume_cmd": resume_command(harness, session_id, source_path, host),
    }


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse flat YAML frontmatter key/value pairs and return (meta, body)."""
    if not text.startswith("---\n"):
        return {}, text
    parts = text[4:].split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[0].splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, parts[1]


def _extract_section(body: str, heading: str) -> str:
    m = re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", body, flags=re.S)
    return m.group(1).strip() if m else ""


AGENT_ALIAS_MAP = {
    "claude": "claude-code",
    "claude-code": "claude-code",
    "agy": "antigravity",
    "antigravity": "antigravity",
    "grok": "grok",
    "grok-bot": "grok",
    "codex": "codex",
    "muse": "muse",
    "cursor": "cursor",
    "cron": "cron",
    "cmux": "cmux",
}


def normalise_agent_name(raw: str) -> str:
    val = (raw or "").strip().lower()
    if not val:
        return "unknown"
    return AGENT_ALIAS_MAP.get(val, val)


def _date_in_window(date_str: str, mtime: float, since_ts: float | None) -> bool:
    if since_ts is None:
        return True
    if date_str and len(date_str) >= 10:
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt.timestamp() + 86400 >= since_ts
        except ValueError:
            pass
    return mtime >= since_ts


def scan_cron_daily(cron_dir: Path, since_date: str = "") -> list[dict]:
    daily: dict[tuple[str, str], Counter] = {}
    if not cron_dir.is_dir():
        return []
    for p in sorted(cron_dir.glob("*.md")):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        meta, _ = parse_frontmatter(raw)
        dm = DATE_PREFIX_RE.match(p.name)
        started = meta.get("started_at") or (dm.group(1) if dm else "")
        d = started[:10]
        if not d or (since_date and d < since_date):
            continue
        skill = meta.get("skill") or p.stem
        status = (meta.get("status") or "unknown").lower()
        daily.setdefault((d, skill), Counter())[status] += 1
    return [
        {
            "d": d,
            "skill": sk,
            "completed": cnt.get("completed", 0),
            "failed": cnt.get("failed", 0) + cnt.get("error", 0),
            "silent": cnt.get("silent", 0),
            "total": sum(cnt.values()),
        }
        for (d, sk), cnt in sorted(daily.items())
    ]


def index_agents_vault(vault_dir: Path, since_ts: float | None = None) -> dict:
    """Index session notes and optional scheduled-job health within the window."""
    sessions_dir = vault_dir / "Sessions"
    by_sid: dict[str, dict] = {}
    notes: list[dict] = []
    if sessions_dir.is_dir():
        for p in sorted(sessions_dir.glob("*.md")):
            if p.name in ("Sessions Dashboard.md", "auto-log.md"):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            raw = p.read_text(encoding="utf-8", errors="ignore")
            meta, body = parse_frontmatter(raw)
            dm = DATE_PREFIX_RE.match(p.name)
            date = (meta.get("created") or (dm.group(1) if dm else ""))[:10]
            sid = meta.get("session_id") or ""
            rec = {
                "note_path": str(p),
                "note_name": p.stem,
                "session_id": sid,
                "agent": normalise_agent_name(meta.get("agent") or ""),
                "host": meta.get("host") or "",
                "status": meta.get("status") or "",
                "date": date,
                "description": meta.get("description") or "",
                "goal": _extract_section(body, "Goal"),
                "outcome": _extract_section(body, "Outcome"),
                "body": body.strip(),
                "mtime": mtime,
            }
            if sid:
                by_sid[sid] = rec
            if _date_in_window(date, mtime, since_ts):
                notes.append(rec)

    cron_dir = vault_dir / "Cron" / "sessions"
    cron_counts: dict[str, Counter] = {}
    cron_daily: dict[tuple[str, str], Counter] = {}
    cron_failures: list[dict] = []
    if cron_dir.is_dir():
        for p in sorted(cron_dir.glob("*.md")):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            raw = p.read_text(encoding="utf-8", errors="ignore")
            meta, body = parse_frontmatter(raw)
            dm = DATE_PREFIX_RE.match(p.name)
            started = meta.get("started_at") or (dm.group(1) if dm else "")
            if not _date_in_window(started[:10], mtime, since_ts):
                continue
            skill = meta.get("skill") or p.stem
            status = (meta.get("status") or "unknown").lower()
            c = cron_counts.setdefault(skill, Counter())
            c[status] += 1
            if started[:10]:
                cron_daily.setdefault((started[:10], skill), Counter())[status] += 1
            if status in ("failed", "error", "blocked"):
                cron_failures.append({
                    "note_path": str(p),
                    "session_id": f"cron-{p.stem}",
                    "skill": skill,
                    "status": status,
                    "started_at": started,
                    "outcome": meta.get("outcome") or "",
                    "body": body.strip()[:2000],
                })

    cron_skills = [
        {
            "skill": sk,
            "completed": cnt.get("completed", 0),
            "failed": cnt.get("failed", 0) + cnt.get("error", 0),
            "silent": cnt.get("silent", 0),
            "total": sum(cnt.values()),
        }
        for sk, cnt in sorted(cron_counts.items(), key=lambda kv: (-kv[1].get("failed", 0), -sum(kv[1].values())))
    ]
    daily_rows = [
        {
            "d": d,
            "skill": sk,
            "completed": cnt.get("completed", 0),
            "failed": cnt.get("failed", 0) + cnt.get("error", 0),
            "silent": cnt.get("silent", 0),
            "total": sum(cnt.values()),
        }
        for (d, sk), cnt in sorted(cron_daily.items())
    ]
    return {
        "by_sid": by_sid,
        "notes": notes,
        "cron_health": {
            "total_runs": sum(s["total"] for s in cron_skills),
            "total_failures": len(cron_failures),
            "skills": cron_skills,
            "daily": daily_rows,
            "recent_failures": cron_failures[-25:],
        },
        "cron_failures": cron_failures,
    }


def _vault_note_to_session(note: dict) -> dict | None:
    goal = note["goal"] or note["description"]
    outcome = note["outcome"]
    body_lines = [ln.strip() for ln in note["body"].splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not goal and not outcome and len(body_lines) < 2:
        return None
    sid = note["session_id"] or f"vault-{re.sub(r'[^a-zA-Z0-9_-]+', '-', note['note_name'])[:48]}"
    date = note["date"]
    ts = f"{date}T00:00:00Z" if len(date) == 10 else ""
    timeline: list[tuple[str, str, str]] = []
    if goal:
        timeline.append(("--:--", "USER", f"[Vault Goal] {goal[:500]}"))
    if outcome:
        timeline.append(("--:--", "AI", f"[Vault Outcome ({note['status'] or 'recorded'})] {outcome[:500]}"))
    for ln in body_lines[:40]:
        timeline.append(("--:--", "AI", ln[:300]))
    correction_hits = 1 if note["status"] in ("blocked", "failed") else 0
    return {
        "session_id": sid,
        "harness": note["agent"] if note["agent"] != "unknown" else "vault-note",
        "host": note["host"] or "agents-vault",
        "project": "agents-vault",
        "cwd": "",
        "vault_domain": "vault",
        "timeline": timeline,
        "skills": [],
        "human": 1,
        "assistant": max(1, len(timeline) - 1),
        "tools": 0,
        "first_ts": ts,
        "last_ts": ts,
        "first_msg": (goal or note["note_name"])[:200],
        "correction_hits": correction_hits,
        "human_chars": len(goal),
        "source_path": note["note_path"],
        "resume_cmd": note["note_path"],
        "source_kind": "vault-note",
        "vault_note": note["note_path"],
        "vault_status": note["status"],
        "vault_goal": goal[:300],
        "vault_outcome": outcome[:400],
    }


def _cron_failure_to_session(fail: dict) -> dict:
    ts = fail["started_at"]
    timeline = [
        (ts[11:16] if len(ts) >= 16 else "--:--", "USER", f"[Scheduled job: {fail['skill']}] status={fail['status']}"),
    ]
    if fail["outcome"]:
        timeline.append(("--:--", "AI", fail["outcome"][:400]))
    if fail["body"]:
        timeline.append(("--:--", "AI", fail["body"][:500]))
    return {
        "session_id": fail["session_id"],
        "harness": "cron",
        "host": "scheduler",
        "project": f"cron/{fail['skill']}",
        "cwd": "",
        "vault_domain": "cron",
        "timeline": timeline,
        "skills": [fail["skill"]],
        "human": 1,
        "assistant": 1,
        "tools": 0,
        "first_ts": ts,
        "last_ts": ts,
        "first_msg": f"Scheduled job {fail['skill']} failed: {fail['outcome'][:160]}",
        "correction_hits": 2,
        "human_chars": len(fail["outcome"]),
        "source_path": fail["note_path"],
        "resume_cmd": fail["note_path"],
        "source_kind": "cron-failure",
        "vault_note": fail["note_path"],
        "vault_status": fail["status"],
        "vault_goal": f"Scheduled job {fail['skill']}",
        "vault_outcome": fail["outcome"][:400],
    }


def raw_transcript_files(roots: dict[str, object], enabled: set[str], since_ts: float | None = None) -> list[tuple[str, Path]]:
    """Enumerate candidate raw JSONL transcript files across enabled harnesses."""
    found: list[tuple[str, Path]] = []

    def add_if_fresh(harness: str, p: Path):
        try:
            if since_ts is not None and p.stat().st_mtime < since_ts:
                return
        except OSError:
            return
        found.append((harness, p))

    if "claude" in enabled:
        root = Path(roots["claude"])
        if root.is_dir():
            for p in root.glob("*/*.jsonl"):
                add_if_fresh("claude", p)

    if "codex" in enabled:
        root = Path(roots["codex"])
        if root.is_dir():
            for p in root.rglob("rollout-*.jsonl"):
                add_if_fresh("codex", p)

    if "grok" in enabled:
        root = Path(roots["grok"])
        if root.is_dir():
            for p in root.glob("*/*/updates.jsonl"):
                add_if_fresh("grok", p)

    if "muse" in enabled:
        root = Path(roots["muse"])
        if root.is_dir():
            for p in root.rglob("session.jsonl"):
                if "subagent" in p.parts:
                    continue
                add_if_fresh("muse", p)

    if "antigravity" in enabled:
        for base in roots["antigravity"]:
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            for p in base_path.rglob(".system_generated/logs/transcript.jsonl"):
                add_if_fresh("antigravity", p)

    return found


def discover_sessions(
    *,
    roots: dict[str, object],
    enabled_sources: set[str],
    since_ts: float | None = None,
    min_turns: int = 5,
    project_filter: str = "",
    harness_filter: str = "",
) -> tuple[list[dict], dict]:
    """Discover, parse, deduplicate, and vault-enrich sessions across all enabled sources."""
    vault_dir = Path(roots["vault"])
    vault_idx = index_agents_vault(vault_dir, since_ts=since_ts) if vault_dir.is_dir() else {
        "by_sid": {},
        "notes": [],
        "cron_health": {"total_runs": 0, "total_failures": 0, "skills": [], "recent_failures": []},
        "cron_failures": [],
    }
    by_sid = vault_idx["by_sid"]
    sessions: list[dict] = []
    seen_sids: set[str] = set()

    for harness, path in raw_transcript_files(roots, enabled_sources, since_ts=since_ts):
        host = ""
        project = ""
        cwd = ""
        sid = path.stem
        canonical_harness = "claude-code" if harness == "claude" else harness

        if harness == "claude":
            headless, cwd = _claude_meta(path)
            if headless:
                continue
            project = decode_claude_slug(path.parent.name)
        elif harness == "codex":
            child, sid, cwd = _codex_meta(path)
            if child:
                continue
            project = slug_from_cwd(cwd, fallback="codex")
        elif harness == "grok":
            sid = path.parent.name
            cwd = urllib.parse.unquote(path.parent.parent.name)
            project = slug_from_cwd(cwd, fallback="grok")
        elif harness == "muse":
            headless, cwd = _muse_meta(path)
            if headless:
                continue
            sid = path.parent.name
            project = slug_from_cwd(cwd, fallback="muse")
        elif harness == "antigravity":
            sid = path.parents[2].name
            host = "t3-code" if ".t3" in path.parts else "antigravity"

        if harness_filter and harness_filter.lower() not in canonical_harness.lower():
            continue

        ev = parse_events(path, harness=harness)
        if not ev:
            continue
        if harness == "grok" and any(e["k"] == "user" and GROK_TAB_NAMER in e["t"] for e in ev[:3]):
            continue
        if harness == "antigravity":
            if any(e["k"] == "user" and e["t"].lstrip().startswith(T3_DELEGATED_PREFIX) for e in ev[:2]):
                continue
            cwd = _antigravity_cwd_from_events(ev)
            project = slug_from_cwd(cwd, fallback=host)

        if project_filter and project_filter.lower() not in f"{project} {cwd}".lower():
            continue

        sess = events_to_session(
            ev,
            session_id=sid,
            harness=canonical_harness,
            host=host,
            project=project,
            cwd=cwd,
            source_path=str(path),
        )
        if sess["human"] < min_turns:
            continue

        vnote = by_sid.get(sid)
        if vnote:
            sess["vault_note"] = vnote["note_path"]
            sess["vault_status"] = vnote["status"]
            sess["vault_goal"] = vnote["goal"][:300]
            sess["vault_outcome"] = vnote["outcome"][:400]
            if not sess["host"] and vnote["host"]:
                sess["host"] = vnote["host"]
            if vnote["status"] in ("blocked", "failed"):
                sess["correction_hits"] += 1
        sess["source_kind"] = "transcript"
        seen_sids.add(sid)
        sessions.append(sess)

    if "vault" in enabled_sources:
        for note in vault_idx["notes"]:
            sid = note["session_id"]
            if sid and sid in seen_sids:
                continue
            if harness_filter and harness_filter.lower() not in note["agent"].lower():
                continue
            if project_filter and project_filter.lower() not in f"{note['note_name']} {note['description']}".lower():
                continue
            sess = _vault_note_to_session(note)
            if sess is None:
                continue
            if sess["session_id"] in seen_sids:
                continue
            seen_sids.add(sess["session_id"])
            sessions.append(sess)

    if "cron" in enabled_sources:
        for fail in vault_idx["cron_failures"]:
            if harness_filter and harness_filter.lower() not in "cron":
                continue
            if project_filter and project_filter.lower() not in fail["skill"].lower():
                continue
            sess = _cron_failure_to_session(fail)
            if sess["session_id"] not in seen_sids:
                seen_sids.add(sess["session_id"])
                sessions.append(sess)

    return sessions, vault_idx["cron_health"]
