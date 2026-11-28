#!/usr/bin/env python3
"""Countable validation signal for a tooling skill under the skill-patterns loop.

A friction signature is a deterministic detector over agent transcripts across
Claude Code, Codex, Grok, Muse, and Antigravity: it fires on a tool call the
skill forbids or a routing the skill rules out. Validation replays held-out
past sessions at the turn that preceded the friction, with the candidate skill
text injected, and counts the held-out items on which the signature no longer
fires while the expected action is still attempted.

  friction.py scan     --skill cmux --out DIR [--sources all] [--projects DIR] [--since YYYY-MM-DD]
  friction.py holdout  --hits DIR/hits.jsonl --n 8 --seed N --out holdout.json
  friction.py traces   --skill cmux --scan DIR --out DIR2 [--exclude holdout.json] [--run RUN] [--seed N]
  friction.py replay   --holdout holdout.json --skill-file SKILL.md --out DIR [--model opus] [--dry-run]
  friction.py score    --results DIR/results.json [--holdout holdout.json]

Signatures live in SIGNATURES below, keyed by skill. Each carries `expects` (the action a replay
must attempt for the item to count) and `fires` (the defect). `scan` writes hits.jsonl, clean.jsonl
and counts.md; `traces` writes windowed trace files plus a manifest for `patterns.py sample`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import runner
import sources

PROJECTS = Path.home() / ".claude/projects"
CLAUDE = os.environ.get("CLAUDE_BIN") or (str(Path.home() / ".local/bin/claude") if (Path.home() / ".local/bin/claude").exists()
                                          else shutil.which("claude"))
REPLAY_HARNESSES = ("auto", "agy", "codex", "grok", "claude")
HIDDEN = ["Skill", "Agent", "WebFetch", "WebSearch", "Artifact", "SendMessage", "Workflow", "Monitor"]
REFUSED = ["Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"]
AGY_REFUSED = ["run_command", "write_file", "edit_file", "replace_file_content", "multi_replace_file_content"]
CODEX_REFUSED = ["Bash", "exec", "exec_command", "shell", "shell_command", "write_file", "apply_patch"]
GROK_REFUSED = ["run_terminal_command", "bash", "shell", "edit_file", "write_file", "create_file", "apply_patch", "Bash", "Write", "Edit"]
REFUSAL = "Refused: this replay records the call and does not run it. Continue with the next call you would have made."
SETTING_SOURCES = ""


def replay_settings():
    hook = {"type": "command", "command": f"echo {json.dumps(REFUSAL)} >&2; exit 2", "timeout": 5}
    return {"permissions": {"deny": HIDDEN},
            "hooks": {"PreToolUse": [{"matcher": "|".join(REFUSED), "hooks": [hook]}]}}


def write_refusal_hook_script(script_path: Path, calls_log: Path, mode: str) -> Path:
    """Write an executable PreToolUse hook that logs the tool call and refuses execution."""
    if mode == "agy":
        body = (
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"raw = sys.stdin.read().strip()\n"
            f"if raw:\n"
            f"    with open({str(calls_log)!r}, 'a', encoding='utf-8') as fh:\n"
            f"        fh.write(raw + '\\n')\n"
            f"print(json.dumps({{'decision': 'deny', 'reason': {REFUSAL!r}}}))\n"
        )
    else:
        body = (
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "raw = sys.stdin.read().strip()\n"
            "if raw:\n"
            f"    with open({str(calls_log)!r}, 'a', encoding='utf-8') as fh:\n"
            "        fh.write(raw + '\\n')\n"
            f"os.write(2, ({REFUSAL!r} + '\\n').encode('utf-8'))\n"
            "block_status = 2\n"
            "sys.exit(block_status)\n"
        )
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(body, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def replay_hooks_config(harness: str, hook_script: Path, system_text: str = "") -> dict:
    """Build the PreToolUse refusal hook configuration for a non-Claude replay harness."""
    if harness == "agy":
        cfg = {
            "replay-refusal": {
                "PreToolUse": [{
                    "matcher": "|".join(AGY_REFUSED),
                    "hooks": [{"type": "command", "command": str(hook_script), "timeout": 5}],
                }],
            }
        }
        if system_text:
            payload_json = json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": system_text}}]})
            cfg["replay-refusal"]["SessionStart"] = [{
                "type": "command",
                "command": "python3 -c " + json.dumps("print(" + repr(payload_json) + ")"),
                "timeout": 5,
            }]
        return cfg
    if harness == "codex":
        return {
            "hooks": {
                "PreToolUse": [{
                    "matcher": "|".join(CODEX_REFUSED),
                    "hooks": [{"type": "command", "command": str(hook_script), "timeout": 5}],
                }]
            }
        }
    return {
        "hooks": {
            "PreToolUse": [{
                "matcher": "|".join(GROK_REFUSED),
                "hooks": [{"type": "command", "command": str(hook_script), "timeout": 5, "failClosed": True}],
            }]
        }
    }


def resolve_replay_harness(preferred: str = "auto") -> str:
    """Resolve the replay harness, preferring agy, codex, grok, then claude."""
    if preferred and preferred != "auto":
        return preferred
    detected = runner.detect_cli_harness("auto")
    if detected in ("agy", "codex", "grok", "claude"):
        return detected
    for cand in ("agy", "codex", "grok", "claude"):
        if runner.find_binary(cand):
            return cand
    return "agy"


HANDOFF_WORDS = re.compile(r"\b(hand-?\s?off|hand-?\s?over|pickup prompt|successor|recycle)\b", re.I)



TRIGGER_MARK = "=== latest user message ===\n"


def clean_user(text):
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<local-command-stdout>.*?</local-command-stdout>", "", text, flags=re.S)
    m = re.search(r"<command-name>([^<]+)</command-name>", text)
    if m:
        cmd = m.group(1).strip()
        a = re.search(r"<command-args>(.*?)</command-args>", text, flags=re.S)
        text = f"{cmd if cmd.startswith('/') else '/' + cmd} {(a.group(1).strip() if a else '')}"
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def events(path):
    """Flatten any supported harness transcript (or replay stream-json) into ordered events."""
    return sources.parse_events(path)


DELEGATION_TOOL_NAMES = frozenset({
    "agent",
    "task",
    "delegate_task",
    "mcp_t3-code_delegate_task",
    "mcp_t3-code_tool_call",
    "invoke_subagent",
    "spawn_agent",
    "spawn_subagent",
    "subagent_spawn",
})


def cmd_of(e):
    """The countable text of a shell or file-edit tool event: Bash or Write/Edit."""
    if e.get("k") != "tool":
        return ""
    inp = e.get("input") or {}
    if not isinstance(inp, dict):
        return ""
    if e["name"] == "Bash":
        return str(inp.get("command", ""))
    if e["name"] in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return f"{inp.get('file_path', '')}\n{inp.get('content', inp.get('new_string', ''))}"
    return ""


def delegation_cmd_of(e):
    """The countable text of a delegation or native subagent tool call (orchestrator scans only)."""
    if e.get("k") != "tool":
        return ""
    inp = e.get("input") or {}
    if not isinstance(inp, dict):
        return ""
    raw_name = str(e.get("raw_name") or "")
    label = raw_name or str(e.get("name") or "")
    if label.lower() in DELEGATION_TOOL_NAMES or str(e.get("name") or "").lower() in DELEGATION_TOOL_NAMES:
        return f"{label} {json.dumps(inp, sort_keys=True)}"
    return ""


def last_user(i, ev):
    """The message the model was answering: the last human message or harness notice before event i."""
    for j in range(i - 1, -1, -1):
        if ev[j]["k"] in ("user", "notice"):
            return j, ev[j]["t"]
    return -1, ""


def next_cmds(i, ev, n=2):
    out = []
    for j in range(i + 1, len(ev)):
        c = cmd_of(ev[j])
        if c:
            out.append(c)
            if len(out) >= n:
                break
    return out



SEND = re.compile(r"\bcmux\s+send\s")
SPAWN = re.compile(r"spawn-workspace\.sh")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*$", re.S | re.M)
QUOTED = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'([^']*)'", re.S)


def strip_heredocs(c):
    return HEREDOC.sub("<<HEREDOC>>", c)


def quoted_args(c):
    return [a if a is not None else b for a, b in QUOTED.findall(c)]


def _positional(i, ev):
    c = cmd_of(ev[i])
    m = re.search(r"\bcmux\s+(send|send-key|read-screen)\s+['\"]?workspace:\d+", c)
    return m.group(0) if m else None


def _no_enter(i, ev):
    c = cmd_of(ev[i])
    if not SEND.search(c) or "send-key" in c:
        return None
    if any("send-key" in n for n in next_cmds(i, ev, 2)):
        return None
    return c.strip().splitlines()[0][:160]


def _multiline(i, ev):
    """Multi-line text handed to cmux send or spawn --prompt: a quoted argument with a newline
    inside it, or a message assembled from a heredoc in the same call."""
    c = cmd_of(ev[i])
    if ev[i].get("name") != "Bash":
        return None
    for m in re.finditer(r"\bcmux\s+send\s+(?:--workspace\s+\S+\s+|--surface\s+\S+\s+|--\s+)*", c):
        rest = c[m.end():]
        q = QUOTED.match(rest)
        if q and "\n" in (q.group(1) or q.group(2) or ""):
            return c[m.start():m.start() + 160].splitlines()[0]
    if SEND.search(c) and HEREDOC.search(c):
        return "cmux send with a heredoc-built message: " + c.strip().splitlines()[0][:120]
    m = re.search(r"spawn-workspace\.sh[^\n]*?--prompt\s+", c)
    if m:
        q = QUOTED.match(c[m.end():])
        if q and "\n" in (q.group(1) or q.group(2) or ""):
            return "spawn --prompt with a multi-line argument: " + c[m.start():m.start() + 120].splitlines()[0]
    return None


def _close_raw(i, ev):
    c = cmd_of(ev[i])
    m = re.search(r"\bcmux\s+close-workspace\b", c)
    return m.group(0) if m else None


def _shared_checkout(i, ev):
    c = cmd_of(ev[i])
    if not SPAWN.search(c) or "--worktree" in c:
        return None
    m = re.search(r"--cwd\s+[\"']?(?:\$HOME|~|/Users/[^/\s]+)/(?:my-skills|Repos/home(?:/skills)?)[\"']?(?=\s|$)", c)
    return m.group(0) if m else None


def _browser_substituted(i, ev):
    c = cmd_of(ev[i])
    if ev[i].get("name") != "Bash" or "cmux browser" in c:
        return None
    _, u = last_user(i, ev)
    if not re.search(r"\bcmux\b.{0,40}\bbrowser\b|\bbrowser\b.{0,40}\bcmux\b", u, re.I | re.S):
        return None
    s = strip_heredocs(c)
    m = re.search(r"(^|&&|;|\|)\s*open\s+(-a\s+|['\"/~$])|\bfullshot\.mjs|\bwebshot\b|Google Chrome|\bsafari\b", s, re.M | re.I)
    return s.strip().splitlines()[0][:160] if m else None


def _short_tail(i, ev):
    c = cmd_of(ev[i])
    m = re.search(r"read-screen[^\n|]*\|\s*tail\s+-n?\s*(\d+)", c)
    return m.group(0) if m and int(m.group(1)) < 40 else None


def _clipboard_not_spawn(i, ev):
    c = cmd_of(ev[i])
    _, u = last_user(i, ev)
    if not HANDOFF_WORDS.search(u) or re.search(r"\bpark\b|\bclipboard\b|\bcopy\b|\bpaste\b", u, re.I):
        return None
    if SPAWN.search(c) or "Handoffs/" in c:
        return None
    if "/tmp/spawn-prompt" in c:
        return None
    looks = re.search(r"\bpbcopy\b", c) or (ev[i].get("name") in ("Write", "Bash") and re.search(
        r"(^|>\s*)[\"']?(/tmp/|/private/tmp/|~/Desktop/|/Users/[^/\s]+/Desktop/)[^\n\"']*(hand-?off|pickup|prompt|brief)", c, re.I | re.M))
    if not looks:
        return None
    if any(SPAWN.search(n) for n in next_cmds(i, ev, 8)):
        return None
    return c.strip().splitlines()[0][:160]


def _role_brief_without_skill_line(i, ev):
    e = ev[i]
    c = cmd_of(e)
    if e.get("name") not in ("Write", "Bash"):
        return None
    body = c
    if e["name"] == "Bash":
        if not re.search(r"Handoffs/", c) or not re.search(r"<<\s*['\"]?EOF", c):
            return None
        body = c.split("EOF", 1)[-1]
    elif "Handoffs/" not in c.split("\n", 1)[0]:
        return None
    if not re.search(r"\bYou are the orchestrator\b|\borchestrator (seat|succession|successor)\b", body, re.I):
        return None
    if re.search(r"[Ll]oad the [`'\"]?orchestrator[`'\"]? skill", body):
        return None
    return body.strip().splitlines()[0][:160] if body.strip() else "role brief"


def _successor_spawn_with_tier(i, ev):
    c = cmd_of(ev[i])
    if not SPAWN.search(c) or "--tier" not in c or "--model" in c:
        return None
    _, u = last_user(i, ev)
    if not re.search(r"\b(successor|recycle|recycled|same seat|continue (this|my) (seat|session))\b", u, re.I):
        return None
    m = re.search(r"--tier\s+\S+", c)
    return m.group(0) if m else None


def _brief_without_suggested_skills(i, ev):
    e = ev[i]
    c = cmd_of(e)
    if e.get("name") != "Write" or "Handoffs/" not in c.split("\n", 1)[0]:
        return None
    body = c.split("\n", 1)[1] if "\n" in c else ""
    if re.search(r"Suggested Skills|[Ll]oad the [`'\"]?\w[\w-]*[`'\"]? skill", body):
        return None
    return "brief lacks a Suggested Skills block and a load-the-skill line"


DISABLED_MODEL_RE = re.compile(r"\bmuse-spark(?:-[\w.-]+)?\b", re.I)
DISABLED_PROVIDERS = frozenset({"muse", "claudeAgent", "grok"})
ORCH_LAUNCH_CMD_RE = re.compile(
    r"(?:spawn-workspace\.sh|\bb\s+(?:route|orchestrator)\b|"
    r"(?:preflight|resolve|takeover|check)\.py\b|acp-mcp-call\s+delegate_task|"
    r"\b(?:muse|grok|claude|codex|agy)\b[^\n]*--model\b)"
)
ORCH_SCRIPT_CMD_RE = re.compile(
    r"(?:(?:orchestrator|model-routing)/scripts/[\w-]+\.py|\bb\s+(?:route|orchestrator)\b|"
    r"\b(?:preflight|takeover|routing_catalog|provider_health|aa_refresh|arena_refresh|routelog)\.py\b)"
)
ORCH_GENERIC_SCRIPT_RE = re.compile(r"\b(?:check|resolve)\.py\b")
ORCH_DIR_HINT_RE = re.compile(r"(?:orchestrator|model-routing)", re.I)
PYYAML_ERROR_RE = re.compile(r"(?:ModuleNotFoundError:\s*)?No module named ['\"]?yaml['\"]?")
WORKSPACE_PATH_RE = re.compile(
    r"(?:(?:~|\$HOME|/Users/[^/\s\"'`),:]+)/(?:Repos|Vaults|Scratch|Projects|Documents|Desktop|\.t3/worktrees|my-skills)|/(?:tmp|private/tmp))(?:/[^\s\"'`),:]+)?"
)
HOME_REPO_PATH_RE = re.compile(
    r"^(?:~|\$HOME|/Users/[^/\s\"'`),:]+)/Repos/home(?:/|$)"
)
T3_CONTEXT_RE = re.compile(r"<t3_code_instructions>|t3-code|mcp_t3-code_|/\.t3/userdata/", re.I)
NATIVE_SUBAGENT_TOOLS = frozenset({"invoke_subagent", "agent", "spawn_agent"})
DELEGATE_TASK_TOOLS = frozenset({"delegate_task", "mcp_t3-code_delegate_task"})


def _extract_delegate_task_args(e):
    inp = e.get("input") or {}
    if not isinstance(inp, dict):
        return None
    raw_lower = str(e.get("raw_name") or "").lower()
    name_lower = str(e.get("name") or "").lower()
    if raw_lower in DELEGATE_TASK_TOOLS or name_lower in DELEGATE_TASK_TOOLS:
        return inp
    if (raw_lower == "mcp_t3-code_tool_call" or name_lower == "mcp_t3-code_tool_call") and inp.get("name") == "delegate_task":
        args = inp.get("arguments")
        return args if isinstance(args, dict) else {}
    if not raw_lower and name_lower == "agent" and "task" in inp and any(k in inp for k in ("target", "isolation", "toolSummary")):
        return inp
    if e.get("name") == "Bash":
        c = str(inp.get("command") or "")
        m = re.search(r"acp-mcp-call\s+delegate_task\s+'(\{.*?\})'", c, re.S)
        if not m:
            m = re.search(r'acp-mcp-call\s+delegate_task\s+"(\{.*?\})"', c, re.S)
        if m:
            try:
                parsed = json.loads(m.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None
    return None


def _disabled_model_id(i, ev):
    e = ev[i]
    dargs = _extract_delegate_task_args(e)
    if dargs is not None:
        target = dargs.get("target") if isinstance(dargs.get("target"), dict) else {}
        model = str(target.get("model") or dargs.get("model") or "")
        provider = str(target.get("providerInstanceId") or target.get("driverKind") or "")
        if DISABLED_MODEL_RE.search(model):
            return f"delegate_task disabled model {model}"
        if provider in DISABLED_PROVIDERS:
            return f"delegate_task disabled provider {provider}"
        return None
    if e.get("name") != "Bash":
        return None
    s = strip_heredocs(cmd_of(e))
    for line in re.split(r"\r?\n|\\n", s):
        if not ORCH_LAUNCH_CMD_RE.search(line):
            continue
        m = DISABLED_MODEL_RE.search(line)
        if m:
            return f"disabled model {m.group(0)} in {line.strip()[:120]}"
        pm = re.search(r"(?:--agent|--provider)\s+['\"]?(muse|claudeAgent|grok)['\"]?(?:\s|$)", line)
        if pm:
            return f"disabled provider {pm.group(1)} in {line.strip()[:120]}"
    return None


def _pyyaml_import_error(i, ev):
    e = ev[i]
    if e.get("name") != "Bash":
        return None
    c = cmd_of(e)
    cwd = str(e.get("cwd") or "")
    is_orch_script = bool(ORCH_SCRIPT_CMD_RE.search(c)) or (
        bool(ORCH_GENERIC_SCRIPT_RE.search(c)) and bool(ORCH_DIR_HINT_RE.search(f"{c} {cwd}"))
    )
    if not is_orch_script:
        return None
    for j in range(i + 1, len(ev)):
        nxt = ev[j]
        if nxt.get("k") in ("tool", "user"):
            break
        if nxt.get("k") == "result":
            text = str(nxt.get("t") or "")
            m = PYYAML_ERROR_RE.search(text)
            if m:
                return f"{m.group(0)} after {c.strip().splitlines()[0][:100]}"
    return None


def _linked_env_worktree(i, ev):
    e = ev[i]
    dargs = _extract_delegate_task_args(e)
    if dargs is not None:
        target = dargs.get("target") if isinstance(dargs.get("target"), dict) else {}
        env_id = str(target.get("environmentId") or dargs.get("environmentId") or "").strip()
        isolation = str(dargs.get("isolation") or "").strip().lower()
        if env_id and isolation == "worktree":
            return f"delegate_task isolation=worktree on linked environment {env_id}"
        return None
    if e.get("name") != "Bash":
        return None
    c = cmd_of(e)
    if re.search(r"(?:--environment-id|--environmentId)\s+\S+", c) and re.search(r"--isolation(?:=|\s+)['\"]?worktree['\"]?", c):
        return c.strip().splitlines()[0][:160]
    return None


def _is_external_cwd(path):
    p = (path or "").strip().rstrip(".,;:")
    if not p:
        return None
    if not (p.startswith("/") or p.startswith("~/") or p == "~" or p.startswith("$HOME/") or p == "$HOME"):
        return None
    return None if HOME_REPO_PATH_RE.match(p) else p


def _external_workspace_path(text):
    for m in WORKSPACE_PATH_RE.finditer(text or ""):
        p = m.group(0).rstrip(".,;:")
        if not HOME_REPO_PATH_RE.match(p):
            return p
    return None


def _session_is_t3(ev):
    for item in ev:
        if item.get("host") == "t3-code":
            return True
        if item.get("k") == "tool":
            raw = str(item.get("raw_name") or item.get("name") or "")
            if raw.lower() in DELEGATE_TASK_TOOLS or raw.lower() == "mcp_t3-code_orchestrator_capabilities":
                return True
        text = str(item.get("t") or "")
        if text and T3_CONTEXT_RE.search(text):
            return True
    return False


def _native_subagent_boundary(i, ev):
    e = ev[i]
    if e.get("k") != "tool":
        return None
    if _extract_delegate_task_args(e) is not None:
        return None
    raw_lower = str(e.get("raw_name") or "").lower()
    name_lower = str(e.get("name") or "").lower()
    if raw_lower:
        if raw_lower not in NATIVE_SUBAGENT_TOOLS:
            return None
        tool_label = str(e.get("raw_name"))
    else:
        if name_lower not in NATIVE_SUBAGENT_TOOLS:
            return None
        tool_label = str(e.get("name"))

    is_antigravity = (
        str(e.get("harness") or "").lower() == "antigravity"
        or tool_label.lower() == "invoke_subagent"
    )
    if is_antigravity and (e.get("host") == "t3-code" or _session_is_t3(ev)):
        return f"native {tool_label} under Antigravity in T3 Code"

    inp = e.get("input") or {}
    cwd = str(e.get("cwd") or inp.get("cwd") or inp.get("workdir") or "")
    if cwd:
        ext = _is_external_cwd(cwd)
        if ext:
            return f"native {tool_label} outside the home repo ({ext})"
        if HOME_REPO_PATH_RE.match(cwd):
            args_blob = " ".join(str(inp.get(k) or "") for k in ("Prompt", "prompt", "message", "description", "path"))
            ext_arg = _external_workspace_path(args_blob)
            if ext_arg:
                return f"native {tool_label} outside the home repo ({ext_arg})"
            return None

    args_blob = " ".join(str(inp.get(k) or "") for k in ("Prompt", "prompt", "message", "description", "path"))
    ext_arg = _external_workspace_path(args_blob)
    if ext_arg:
        return f"native {tool_label} outside the home repo ({ext_arg})"

    for j in range(i - 1, -1, -1):
        prev_cwd = str(ev[j].get("cwd") or "")
        if prev_cwd:
            ext_prev = _is_external_cwd(prev_cwd)
            return f"native {tool_label} outside the home repo ({ext_prev})" if ext_prev else None
    return None


SIGNATURES = {
    "cmux": [
        {"id": "cmux-send-positional", "expects": r"\bcmux\s+(send|send-key|read-screen)\b", "fires": _positional,
         "note": "positional workspace argument; the flag form is the rule (pitfalls.md)"},
        {"id": "cmux-send-without-enter", "expects": r"\bcmux\s+send\s", "fires": _no_enter,
         "note": "send with no send-key Enter in the same call or the next two calls"},
        {"id": "cmux-multiline-send", "expects": r"\bcmux\s+send\s|spawn-workspace\.sh", "fires": _multiline,
         "note": "multi-line text through cmux send or --prompt; the TUI treats newlines as edit input"},
        {"id": "cmux-close-workspace-raw", "expects": r"close-workspace", "fires": _close_raw,
         "note": "raw cmux close-workspace leaves the session note in-progress; close-workspace.sh is the rule"},
        {"id": "spawn-shared-checkout", "expects": r"spawn-workspace\.sh", "fires": _shared_checkout,
         "note": "spawn with --cwd pointing to the shared home repo and no --worktree; the shared checkout is single-writer"},
        {"id": "cmux-browser-substituted", "expects": r"cmux browser|^\s*open\s|fullshot|webshot", "fires": _browser_substituted,
         "note": "user named the cmux browser and the agent opened Chrome, Safari or webshot instead"},
        {"id": "read-screen-short-tail", "expects": r"read-screen", "fires": _short_tail, "advisory": True,
         "note": "read-screen piped to tail under 40 lines misreads the composer as activity (pitfalls.md); advisory, no user complaint behind it"},
    ],
    "handoff": [
        {"id": "handoff-clipboard-not-spawn", "expects": r"spawn-workspace\.sh|\bpbcopy\b|Handoffs/|/tmp/|Desktop/",
         "fires": _clipboard_not_spawn,
         "note": "handoff asked for, agent reached for pbcopy or a /tmp file and no spawn followed"},
        {"id": "role-brief-without-skill-line", "expects": r"Handoffs/", "fires": _role_brief_without_skill_line,
         "note": "an orchestrator brief without the load-the-skill instruction (SKILL.md Key Rules)"},
        {"id": "successor-spawn-with-tier", "expects": r"spawn-workspace\.sh", "fires": _successor_spawn_with_tier,
         "note": "a successor spawned with --tier instead of an explicit --model (auto-spawn.md recycle exception)"},
        {"id": "brief-without-suggested-skills", "expects": r"Handoffs/", "fires": _brief_without_suggested_skills, "advisory": True,
         "note": "a brief written to Handoffs/ with no Suggested Skills block and no load-the-skill line; advisory, the house format ignores the rule"},
    ],
    "orchestrator": [
        {"id": "orchestrator-disabled-model-id", "expects": r"delegate_task|spawn-workspace\.sh|\bb\s+(?:route|orchestrator)\b|(?:preflight|resolve|takeover)\.py",
         "fires": _disabled_model_id,
         "note": "disabled model id (such as muse-spark-1.3) or disabled provider routed in launch/delegation"},
        {"id": "orchestrator-pyyaml-import-error", "expects": r"(?:orchestrator|model-routing)/scripts/|\bb\s+(?:route|orchestrator)\b|\b(?:preflight|takeover|routing_catalog|provider_health|aa_refresh|arena_refresh|routelog)\.py\b",
         "fires": _pyyaml_import_error,
         "note": "bare python3 PyYAML ImportError on orchestrator or model-routing scripts"},
        {"id": "orchestrator-linked-env-worktree", "expects": r"delegate_task|preflight\.py|\bb\s+route\b",
         "fires": _linked_env_worktree,
         "note": "isolation: worktree passed with target.environmentId on a linked environment"},
        {"id": "orchestrator-native-subagent-boundary", "expects": r"delegate_task|invoke_subagent|spawn_agent|\bAgent\b",
         "fires": _native_subagent_boundary,
         "note": "native subagent tool (invoke_subagent/Agent/spawn_agent) used outside the home repo or under Antigravity in T3 Code"},
    ],
}

PREFILTER = {
    "cmux": r"cmux|spawn-workspace",
    "handoff": r"hand-?off|handover|Handoffs/|spawn-workspace",
    "orchestrator": r'muse-spark|No module named [\'"]?yaml|delegate_task|invoke_subagent|spawn_agent|"name"\s*:\s*"Agent"|environmentId|orchestrator/scripts|model-routing/scripts|\bb route\b|\bb orchestrator\b',
}


def detect(ev, skill):
    """Run every signature of a skill over an event list. Returns hits and the index of the
    first event whose command matched any `expects` (or -1)."""
    sigs = SIGNATURES[skill]
    hits, first_expected = [], -1
    for i, e in enumerate(ev):
        c = cmd_of(e)
        if not c and skill == "orchestrator":
            c = delegation_cmd_of(e)
        if not c:
            continue
        for s in sigs:
            if first_expected < 0 and re.search(s["expects"], c, re.M):
                first_expected = i
            found = s["fires"](i, ev)
            if found:
                ti, _ = last_user(i, ev)
                hits.append({"signature": s["id"], "index": i, "trigger": ti, "excerpt": found})
    return hits, first_expected



def render_events(ev, lo, hi, user_cap=2000, text_cap=300, cmd_cap=500, result_cap=250):
    lines = []
    for j in range(max(lo, 0), min(hi, len(ev))):
        e = ev[j]
        ts = (e.get("ts") or "")[11:16]
        if e["k"] == "user":
            lines.append(f"[{ts}] USER: {e['t'][:user_cap]}")
        elif e["k"] == "notice":
            lines.append(f"[{ts}] NOTICE: {e['t'][:400]}")
        elif e["k"] == "meta":
            lines.append(f"[{ts}] META: {e['t'][:120]}")
        elif e["k"] == "text":
            lines.append(f"[{ts}] AI: {' '.join(e['t'].split())[:text_cap]}")
        elif e["k"] == "tool":
            c = cmd_of(e) or delegation_cmd_of(e)
            if c:
                lines.append(f"[{ts}] TOOL {e['name']}: {c[:cmd_cap]}")
            else:
                brief = json.dumps(e.get("input") or {})[:120]
                lines.append(f"[{ts}] TOOL {e['name']}: {brief}")
        elif e["k"] == "result":
            lines.append(f"[{ts}] RESULT: {' '.join(e['t'].split())[:result_cap]}")
    return "\n".join(lines)



def candidate_files(projects, skill, since=None, source_list="all"):
    pat = PREFILTER[skill]
    rg = shutil.which("rg") or next((p for p in ("/opt/homebrew/bin/rg", "/usr/local/bin/rg") if Path(p).is_file()), None)
    roots = sources.default_roots(claude_projects=projects)
    enabled = set(sources.RAW_HARNESSES) if source_list in ("all", "transcripts") else {
        s.strip() for s in source_list.split(",") if s.strip() in sources.RAW_HARNESSES
    }
    search_dirs: list[Path] = []
    for name in ("claude", "codex", "grok", "muse"):
        if name in enabled:
            p = Path(roots[name])
            if p.is_dir():
                search_dirs.append(p)
    if "antigravity" in enabled:
        for base in roots["antigravity"]:
            p = Path(base)
            if p.is_dir():
                search_dirs.append(p)
    if not search_dirs:
        return []
    files: list[Path] = []
    for d in search_dirs:
        cmd = [rg, "--hidden", "-l", "-g", "*.jsonl", pat, str(d)] if rg else ["grep", "-rlE", "--include=*.jsonl", pat, str(d)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        for line in proc.stdout.split("\n"):
            if not line.strip():
                continue
            fp = Path(line)
            if fp.name in ("prompt_history.jsonl", "transcript_full.jsonl") or "subagent" in fp.parts or "chunks" in fp.parts:
                continue
            files.append(fp)
    files = sorted(set(files))
    if since:
        cut = datetime.strptime(since, "%Y-%m-%d").timestamp()
        files = [f for f in files if f.stat().st_mtime >= cut]
    return files


def _session_id_for_path(f: Path) -> str:
    if f.name in ("updates.jsonl", "session.jsonl"):
        return f.parent.name
    if f.name == "transcript.jsonl" and len(f.parents) >= 3:
        return f.parents[2].name
    m = sources.CODEX_SID_RE.match(f.name)
    if m:
        return m.group(1)
    return f.stem


def cmd_scan(a):
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    src = getattr(a, "sources", "all")
    files = candidate_files(Path(a.projects).expanduser(), a.skill, a.since, source_list=src)
    hits_fh = (out / "hits.jsonl").open("w")
    clean_fh = (out / "clean.jsonl").open("w")
    per_sig, sess_sig, recent_sig, n_clean, n_expected = Counter(), defaultdict(set), defaultdict(set), 0, 0
    for f in files:
        ev = events(f)
        hits, first = detect(ev, a.skill)
        sid = _session_id_for_path(f)
        date = next((e.get("ts", "")[:10] for e in ev if e.get("ts")), "")
        if first >= 0:
            n_expected += 1
        for h in hits:
            per_sig[h["signature"]] += 1
            sess_sig[h["signature"]].add(sid)
            if date >= a.recent:
                recent_sig[h["signature"]].add(sid)
            hits_fh.write(json.dumps({"session_id": sid, "harness": sources.detect_harness(f), "path": str(f), "date": date, **h}) + "\n")
        if first >= 0 and not hits:
            n_clean += 1
            clean_fh.write(json.dumps({"session_id": sid, "harness": sources.detect_harness(f), "path": str(f), "date": date, "index": first}) + "\n")
    hits_fh.close()
    clean_fh.close()
    rows = [f"| signature | hits | sessions | sessions since {a.recent} | scored |", "|---|---:|---:|---:|---|"]
    for s in SIGNATURES[a.skill]:
        rows.append(f"| {s['id']} | {per_sig[s['id']]} | {len(sess_sig[s['id']])} | {len(recent_sig[s['id']])} | "
                    f"{'advisory' if s.get('advisory') else 'yes'} |")
    all_sess = set().union(*sess_sig.values()) if sess_sig else set()
    head = (f"# Friction scan: {a.skill}\n\n{datetime.now():%Y-%m-%d %H:%M}. {len(files)} candidate transcripts"
            f"{' since ' + a.since if a.since else ''}; {n_expected} attempted a {a.skill} action; "
            f"{len(all_sess)} carry at least one signature; {n_clean} attempted and stayed clean.\n\n")
    (out / "counts.md").write_text(head + "\n".join(rows) + "\n")
    print(head + "\n".join(rows))
    return 0



def choose_holdout(hits, n, seed, per_signature=None):
    """One item per session, round-robin across signatures, seeded. Deterministic."""
    rng = random.Random(seed)
    by_sig = defaultdict(list)
    for h in hits:
        by_sig[h["signature"]].append(h)
    for v in by_sig.values():
        rng.shuffle(v)
    order = sorted(by_sig)
    rng.shuffle(order)
    chosen, used, taken = [], set(), Counter()
    while len(chosen) < n and any(by_sig[s] for s in order):
        for s in order:
            if len(chosen) >= n:
                break
            while by_sig[s]:
                h = by_sig[s].pop()
                if h["session_id"] in used or (per_signature and taken[s] >= per_signature):
                    continue
                chosen.append(h)
                used.add(h["session_id"])
                taken[s] += 1
                break
    return chosen


def cmd_holdout(a):
    hits = [json.loads(l) for l in Path(a.hits).expanduser().read_text().splitlines() if l.strip()]
    advisory = {s["id"] for v in SIGNATURES.values() for s in v if s.get("advisory")}
    hits = [h for h in hits if h["trigger"] >= 0 and h["signature"] not in advisory and h.get("date", "") >= a.min_date
            and not h["session_id"].startswith("agent-")]
    chosen = choose_holdout(hits, a.n + a.spare, a.seed, a.per_signature)
    items = []
    for h in chosen:
        if len(items) >= a.n:
            break
        ev = events(h["path"])
        ti, _ = last_user(h["index"], ev)
        if ti < 0:
            continue
        ctx = render_events(ev, ti - a.window, ti)
        if len(ctx) > a.context_cap:
            ctx = "[earlier context omitted]\n" + ctx[-a.context_cap:]
        if "USER: " not in ctx and ev[ti]["k"] != "user":
            continue
        if "/tmp/spawn-prompt" in ev[ti]["t"]:
            continue
        items.append({"id": f"{h['session_id'][:8]}-{h['signature']}", "session_id": h["session_id"], "path": h["path"],
                      "date": h.get("date", ""), "signature": h["signature"], "trigger_index": ti,
                      "context": ctx, "trigger": ev[ti]["t"], "original_excerpt": h["excerpt"]})
    Path(a.out).expanduser().write_text(json.dumps({"seed": a.seed, "n": a.n, "items": items}, indent=1))
    print(f"holdout: {len(items)} items, seed {a.seed}, signatures {Counter(i['signature'] for i in items)} -> {a.out}")
    return 0



def load_run_friction(run, skill):
    """Verified friction text per session from a session-intelligence run, filtered to the skill."""
    notes = defaultdict(list)
    conv = Path(run).expanduser() / "data" / "conversations.jsonl"
    if not conv.is_file():
        return notes
    pat = re.compile(PREFILTER[skill], re.I)
    for line in conv.read_text().splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        for f in c.get("friction") or []:
            if f.get("evidence_verified") and pat.search(f.get("what_went_wrong", "") + " " + f.get("quote", "")):
                notes[c["session_id"]].append(f.get("what_went_wrong", ""))
    return notes


def cmd_traces(a):
    scan = Path(a.scan).expanduser()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    exclude = set()
    if a.exclude:
        exclude = {i["session_id"] for i in json.loads(Path(a.exclude).expanduser().read_text())["items"]}
    notes = load_run_friction(a.run, a.skill) if a.run else {}
    hits = [json.loads(l) for l in (scan / "hits.jsonl").read_text().splitlines() if l.strip()]
    clean = [json.loads(l) for l in (scan / "clean.jsonl").read_text().splitlines() if l.strip()]
    by_sess = defaultdict(list)
    for h in hits:
        if h["session_id"] not in exclude:
            by_sess[h["session_id"]].append(h)
    advisory = {s["id"] for s in SIGNATURES[a.skill] if s.get("advisory")}
    manifest = []
    for sid, hs in sorted(by_sess.items()):
        ev = events(hs[0]["path"])
        scored = [h for h in hs if h["signature"] not in advisory]
        pick = sorted(scored, key=lambda x: x["index"])[: a.windows]
        pick += sorted((h for h in hs if h["signature"] in advisory), key=lambda x: x["index"])[: max(0, a.windows - len(pick))]
        blocks = []
        for h in sorted(pick, key=lambda x: x["index"]):
            lo, hi = max(h["trigger"], h["index"] - a.before), h["index"] + a.after
            blocks.append(f"--- signature {h['signature']} fired at event {h['index']} ---\n" + render_events(ev, lo - a.before, hi))
        text = f"session {sid} date {hs[0].get('date', '')}\n" + "\n\n".join(blocks) + "\n"
        (out / f"{sid}.md").write_text(text)
        note = "; ".join(sorted({h["signature"] for h in hs}))
        if notes.get(sid):
            note += " | verified friction: " + " / ".join(n[:200] for n in notes[sid][:2])
        priority = 0 if (scored and notes.get(sid)) else 1 if scored else 2
        manifest.append({"id": sid[:8], "outcome": "fail", "files": [str(out / f"{sid}.md")], "note": note, "priority": priority})
    rng = random.Random(a.seed)
    rng.shuffle(clean)
    clean = [c for c in clean if c["session_id"] not in exclude and not c["session_id"].startswith("agent-")]
    for c in clean[: a.max_pass]:
        ev = events(c["path"])
        text = f"session {c['session_id']} date {c.get('date', '')}\n--- first {a.skill} action at event {c['index']}, no signature fired ---\n" + \
            render_events(ev, c["index"] - a.before, c["index"] + a.after) + "\n"
        (out / f"{c['session_id']}.md").write_text(text)
        manifest.append({"id": c["session_id"][:8], "outcome": "pass", "files": [str(out / f"{c['session_id']}.md")],
                         "note": "clean " + a.skill + " session" + (" | verified friction elsewhere: " + notes[c["session_id"]][0][:160] if notes.get(c["session_id"]) else "")})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    fails = sum(1 for m in manifest if m["outcome"] == "fail")
    print(f"traces: {fails} failing, {len(manifest) - fails} passing -> {out}/manifest.json")
    return 0



REPLAY_PREAMBLE = ("You are resuming an agent session on this Mac. Below is an excerpt of the conversation so far, "
                   "oldest first, then the latest user message. Act on the latest user message now, exactly as you would "
                   "in the live session: use your tools to do the work. Do not describe what you would do; do it. "
                   "Calls that change state are refused in this replay; the refusal is expected and is the record of what "
                   "you intended. When a call is refused, issue the next call you would have made had it succeeded, until "
                   "every call the task needs has been issued, then stop.\n\n")

SYSTEM_PREAMBLE = ("The following skill is active in this session. It replaces any copy of the same skill on disk; "
                   "follow it.\n\n")


def build_replay_invocation(
    harness: str,
    item_id: str,
    prompt: str,
    system_text: str,
    out: Path,
    readable: list[str],
    model: str = "",
    max_turns: int = 16,
) -> tuple[list[str], Path, dict[str, str], str | None, Path]:
    """Prepare isolated hook config and subprocess invocation for one replay item."""
    calls_log = out / f"{item_id}.hook-calls.jsonl"
    env = dict(os.environ)

    if harness == "claude":
        settings = json.dumps(replay_settings())
        cmd = [
            CLAUDE or "claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--disable-slash-commands", "--settings", settings,
            "--permission-mode", "default", "--setting-sources", SETTING_SOURCES,
            "--append-system-prompt-file", str(out / "system.md"), "--max-turns", str(max_turns),
            "--add-dir", *readable,
        ]
        if model:
            cmd += ["--model", model]
        return cmd, out, env, None, calls_log

    workdir = out / ".replay-work" / item_id
    workdir.mkdir(parents=True, exist_ok=True)
    hook_script = write_refusal_hook_script(workdir / "refuse-hook.py", calls_log, mode=harness)

    if harness == "agy":
        agents_dir = workdir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "hooks.json").write_text(
            json.dumps(replay_hooks_config("agy", hook_script), indent=2),
            encoding="utf-8",
        )
        full_prompt = system_text + "\n\n" + prompt
        binary = runner.find_binary("agy") or "agy"
        cmd = [
            binary, "-p", full_prompt, "--output-format", "stream-json",
            "--disable-slash-commands", "--dangerously-skip-permissions",
        ]
        for d in readable:
            cmd += ["--add-dir", d]
        if model:
            cmd += ["--model", model]
        return cmd, workdir, env, None, calls_log

    if harness == "codex":
        codex_home = workdir / "codex-home"
        codex_home.mkdir(parents=True, exist_ok=True)
        user_codex = Path.home() / ".codex"
        for fname in ("auth.json", "config.toml"):
            src = user_codex / fname
            dst = codex_home / fname
            if src.is_file() and not dst.exists():
                dst.symlink_to(src)
        (codex_home / "hooks.json").write_text(
            json.dumps(replay_hooks_config("codex", hook_script), indent=2),
            encoding="utf-8",
        )
        env["CODEX_HOME"] = str(codex_home)
        full_prompt = system_text + "\n\n" + prompt
        binary = runner.find_binary("codex") or "codex"
        cmd = [
            binary, "exec", "--json", "--dangerously-bypass-hook-trust",
            "--skip-git-repo-check", "-C", str(workdir),
        ]
        if model:
            cmd += ["--model", model]
        cmd.append("-")
        return cmd, workdir, env, full_prompt, calls_log

    hooks_dir = workdir / ".grok" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "replay-refusal.json").write_text(
        json.dumps(replay_hooks_config("grok", hook_script), indent=2),
        encoding="utf-8",
    )
    prompt_file = workdir / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    env["GROK_FOLDER_TRUST"] = "0"
    binary = runner.find_binary("grok") or "grok"
    cmd = [
        binary, "--always-approve", "--cwd", str(workdir),
        "--output-format", "streaming-json", "--rules", system_text,
        "--prompt-file", str(prompt_file),
    ]
    for d in readable:
        cmd += ["--add-dir", d]
    if model:
        cmd += ["--model", model]
    return cmd, workdir, env, None, calls_log


def cmd_replay(a):
    hold = json.loads(Path(a.holdout).expanduser().read_text())
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    skill_text = Path(a.skill_file).expanduser().read_text()
    system_text = SYSTEM_PREAMBLE + skill_text
    (out / "system.md").write_text(system_text)
    skill_dir = str(Path(a.skill_dir or Path(a.skill_file).expanduser().resolve().parent))
    readable = [skill_dir, str(Path.home())]
    harness = resolve_replay_harness(getattr(a, "harness", "auto"))
    results = []
    for it in hold["items"]:
        prompt = REPLAY_PREAMBLE + "=== conversation so far ===\n" + it["context"] + "\n\n" + TRIGGER_MARK + it["trigger"]
        (out / f"{it['id']}.prompt.md").write_text(prompt)
        log = out / f"{it['id']}.stream.jsonl"
        calls_log = out / f"{it['id']}.hook-calls.jsonl"
        if log.is_file() and result_record(log) is not None:
            results.append(judge_replay(it, log, a.skill, 0, calls_log=calls_log))
            r = results[-1]
            print(f"{it['id']}: (from disk) attempted={r['attempted']} fired={r['fired']} other={r['other']} pass={r['pass']}")
            continue
        cmd, cwd, env, stdin_text, calls_log = build_replay_invocation(
            harness, it["id"], prompt, system_text, out, readable, model=a.model, max_turns=a.max_turns,
        )
        if a.dry_run:
            shown = [arg if len(arg) < 80 else "<prompt>" for arg in cmd]
            print(f"dry run ({harness}):", " ".join(shown))
            continue
        if calls_log.exists():
            calls_log.unlink()
        with log.open("w") as fh:
            proc = subprocess.run(
                cmd, cwd=cwd, env=env,
                input=stdin_text,
                stdin=None if stdin_text is not None else subprocess.DEVNULL,
                stdout=fh, stderr=subprocess.STDOUT, timeout=a.timeout,
                text=stdin_text is not None,
            )
        results.append(judge_replay(it, log, a.skill, proc.returncode, calls_log=calls_log))
        r = results[-1]
        print(f"{it['id']}: ({harness}) attempted={r['attempted']} fired={r['fired']} other={r['other']} pass={r['pass']} exit={proc.returncode}")
    if not a.dry_run:
        (out / "results.json").write_text(json.dumps({
            "skill": a.skill, "skill_file": str(a.skill_file), "harness": harness, "model": a.model,
            "skill_dir": skill_dir, "readable": readable, "hidden": HIDDEN,
            "refused": REFUSED, "permission_mode": "default", "setting_sources": SETTING_SOURCES,
            "max_turns": a.max_turns, "holdout": str(a.holdout), "items": results,
        }, indent=1))
        print_score(results)
    return 0


def result_record(log):
    """The stream's closing completion record across Claude, agy, codex, or grok, or None."""
    for line in Path(log).read_text(errors="ignore").splitlines()[::-1]:
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if o.get("type") == "result":
            return o
        if o.get("event") == "result" and isinstance(o.get("result"), dict):
            res = o["result"]
            if str(res.get("status", "")).upper() == "ERROR" or res.get("error"):
                return None
            return {"subtype": str(res.get("finished_reason") or res.get("status") or "success").lower(),
                    "num_turns": res.get("num_turns")}
        if o.get("type") == "turn.completed":
            return {"subtype": "success", "num_turns": 1}
        if o.get("type") == "turn.failed":
            return None
        if o.get("type") in ("turn_completed", "done"):
            return {"subtype": "success", "num_turns": o.get("num_turns")}
        if o.get("type") == "error":
            return None
    return None


def judge_replay(item, log, skill, rc, calls_log=None):
    stream_ev = events(log)
    hook_path = Path(calls_log) if calls_log else Path(log).with_name(f"{item['id']}.hook-calls.jsonl")
    hook_ev = sources.parse_events_hook_calls(hook_path) if hook_path.is_file() else []
    stream_cmds = {cmd_of(e) for e in stream_ev if cmd_of(e)}
    extra_hook_ev = [e for e in hook_ev if cmd_of(e) and cmd_of(e) not in stream_cmds]
    ev = [{"k": "user", "t": item["trigger"], "ts": ""}] + stream_ev + extra_hook_ev
    sig = next(s for s in SIGNATURES[skill] if s["id"] == item["signature"])
    cmds = [cmd_of(e) for e in ev if cmd_of(e)]
    attempted = any(re.search(sig["expects"], c, re.M) for c in cmds)
    hits, _ = detect(ev, skill)
    advisory_ids = {s["id"] for s in SIGNATURES[skill] if s.get("advisory")}
    fired = any(h["signature"] == item["signature"] for h in hits)
    other = sorted({h["signature"] for h in hits if h["signature"] != item["signature"] and h["signature"] not in advisory_ids})
    advisory = sorted({h["signature"] for h in hits if h["signature"] in advisory_ids})
    res = result_record(log)
    return {"id": item["id"], "signature": item["signature"], "exit": rc, "result": (res or {}).get("subtype"),
            "turns": (res or {}).get("num_turns"), "attempted": attempted, "fired": fired, "other": other,
            "advisory": advisory, "pass": bool(attempted and not fired and res is not None),
            "commands": [c[:300] for c in cmds[:6]]}


def print_score(results):
    passes = sum(1 for r in results if r["pass"])
    hard = sum(1 for r in results if r["other"])
    no_action = sum(1 for r in results if not r["attempted"])
    print(f"score {passes}/{len(results)} passes; hard failures (another signature fired) {hard}; no expected action {no_action}")
    return passes, hard


def cmd_score(a):
    res = json.loads(Path(a.results).expanduser().read_text())
    passes, hard = print_score(res["items"])
    print(f"brun-skills gate --score {passes} --hard-failures {hard} --max-score {len(res['items'])} ...")
    return 0



def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan")
    s.add_argument("--skill", required=True, choices=sorted(SIGNATURES))
    s.add_argument("--sources", default="all", help="comma-separated harnesses (claude,codex,grok,muse,antigravity) or 'all'")
    s.add_argument("--projects", default=str(PROJECTS), help="Claude Code projects directory override")
    s.add_argument("--since")
    s.add_argument("--recent", default="2026-08-01", help="date from which the recurrence column counts")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_scan)

    h = sub.add_parser("holdout")
    h.add_argument("--hits", required=True)
    h.add_argument("--n", type=int, default=8)
    h.add_argument("--spare", type=int, default=6, help="extra candidates drawn so unreplayable items can be skipped")
    h.add_argument("--seed", type=int, default=0)
    h.add_argument("--per-signature", type=int)
    h.add_argument("--min-date", default="2026-06-01", help="only hits on or after this date enter the held-out set")
    h.add_argument("--window", type=int, default=60)
    h.add_argument("--context-cap", type=int, default=12000)
    h.add_argument("--out", required=True)
    h.set_defaults(fn=cmd_holdout)

    t = sub.add_parser("traces")
    t.add_argument("--skill", required=True, choices=sorted(SIGNATURES))
    t.add_argument("--scan", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--exclude")
    t.add_argument("--run")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--before", type=int, default=25)
    t.add_argument("--after", type=int, default=15)
    t.add_argument("--max-pass", type=int, default=6)
    t.add_argument("--windows", type=int, default=3, help="windows rendered per session, scored signatures first")
    t.set_defaults(fn=cmd_traces)

    r = sub.add_parser("replay")
    r.add_argument("--holdout", required=True)
    r.add_argument("--skill", required=True, choices=sorted(SIGNATURES))
    r.add_argument("--skill-file", required=True)
    r.add_argument("--skill-dir", help="the skill directory the replay reads references from (default: the skill file's directory)")
    r.add_argument("--out", required=True)
    r.add_argument("--harness", default="auto", choices=REPLAY_HARNESSES, help="replay CLI harness (auto|agy|codex|grok|claude)")
    r.add_argument("--model", default="")
    r.add_argument("--max-turns", type=int, default=16)
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_replay)

    c = sub.add_parser("score")
    c.add_argument("--results", required=True)
    c.set_defaults(fn=cmd_score)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
