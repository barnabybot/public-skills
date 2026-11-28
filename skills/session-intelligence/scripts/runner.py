#!/usr/bin/env python3
"""Portable multi-harness CLI runner for Session Intelligence.

Runs single prompts (used by patterns.py) and full extract, synth, and life
stages across whichever local agent CLI is active or selected: agy, claude,
codex, grok, or muse.

  python3 runner.py detect
  python3 runner.py extract --root <dir> [--harness auto] [--model M] [--concurrency 4] [--dry-run]
  python3 runner.py synth   --root <dir> [--harness auto] [--model M] [--out FILE] [--dry-run]
  python3 runner.py life    --root <dir> [--harness auto] [--model M] [--out FILE] [--dry-run]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import prompts_lib

HARNESS_CHOICES = ("auto", "agy", "claude", "codex", "grok", "muse")
HARNESS_ORDER = ("agy", "claude", "codex", "grok", "muse")


def find_binary(harness: str) -> str | None:
    """Resolve the executable path for a named CLI harness."""
    env_keys = {
        "agy": "AGY_BIN",
        "claude": "CLAUDE_BIN",
        "codex": "CODEX_BIN",
        "grok": "GROK_BIN",
        "muse": "MUSE_BIN",
    }
    override = os.environ.get(env_keys.get(harness, ""), "").strip()
    if override:
        return override
    local_bin = Path.home() / ".local/bin" / harness
    if local_bin.is_file():
        return str(local_bin)
    found = shutil.which(harness)
    if found:
        return found
    homebrew = Path("/opt/homebrew/bin") / harness
    if homebrew.is_file():
        return str(homebrew)
    return None


def detect_cli_harness(preferred: str = "auto") -> str:
    """Pick the active or first available local CLI harness."""
    if preferred and preferred != "auto":
        return preferred
    env = os.environ
    if env.get("T3_ACP_MCP_NODE") or env.get("ANTIGRAVITY_CONVERSATION_ID"):
        if find_binary("agy"):
            return "agy"
    if env.get("CODEX_THREAD_ID") or env.get("CODEX_SANDBOX"):
        if find_binary("codex"):
            return "codex"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        if find_binary("claude"):
            return "claude"
    if env.get("GROK_SESSION_ID"):
        if find_binary("grok"):
            return "grok"
    if env.get("MUSE_SESSION_ID"):
        if find_binary("muse"):
            return "muse"
    for h in HARNESS_ORDER:
        if find_binary(h):
            return h
    return "claude"


def build_command(
    harness: str,
    prompt_path: Path,
    cwd: Path,
    model: str = "",
    json_schema_path: Path | None = None,
) -> tuple[list[str], str | None]:
    """Build the headless subprocess command and optional stdin payload for a harness."""
    resolved = detect_cli_harness(harness)
    binary = find_binary(resolved) or resolved
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""

    if resolved == "agy":
        cmd = [binary, "-p", prompt_text, "--dangerously-skip-permissions", "--disable-slash-commands"]
        if model:
            cmd += ["--model", model]
        if json_schema_path:
            cmd += ["--json-schema", str(json_schema_path), "--output-format", "json"]
        return cmd, None

    if resolved == "codex":
        cmd = [binary, "exec", "--dangerously-bypass-approvals-and-sandbox", "-C", str(cwd)]
        if model:
            cmd += ["--model", model]
        if json_schema_path:
            cmd += ["--output-schema", str(json_schema_path)]
        cmd.append("-")
        return cmd, prompt_text

    if resolved == "grok":
        cmd = [binary, "--always-approve", "--cwd", str(cwd), "--prompt-file", str(prompt_path)]
        if model:
            cmd += ["--model", model]
        return cmd, None

    if resolved == "muse":
        cmd = [binary, "exec", "--prompt-file", str(prompt_path)]
        if model:
            cmd += ["--model", model]
        return cmd, None

    cmd = [binary, "-p", prompt_text, "--permission-mode", "bypassPermissions"]
    if model:
        cmd += ["--model", model]
    return cmd, None


def run_prompt(
    prompt_path: Path,
    cwd: Path,
    *,
    harness: str = "auto",
    model: str = "",
    log_path: Path | None = None,
    dry_run: bool = False,
    timeout: int = 2400,
    json_schema: dict | None = None,
) -> tuple[int, str]:
    """Execute one prompt through the selected CLI harness."""
    resolved = detect_cli_harness(harness)
    schema_file: Path | None = None
    tmp_schema = None
    if json_schema is not None:
        tmp_schema = tempfile.NamedTemporaryFile("w", suffix=".schema.json", delete=False)
        tmp_schema.write(json.dumps(json_schema))
        tmp_schema.close()
        schema_file = Path(tmp_schema.name)

    try:
        cmd, stdin_text = build_command(resolved, prompt_path, cwd, model=model, json_schema_path=schema_file)
        if dry_run:
            shown = [arg if len(arg) < 80 else "<prompt>" for arg in cmd]
            print(f"dry run ({resolved}): cd {cwd} && {' '.join(shown)}")
            return 0, ""
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(combined, encoding="utf-8")
        return proc.returncode, proc.stdout or ""
    finally:
        if tmp_schema is not None:
            Path(tmp_schema.name).unlink(missing_ok=True)


def parse_json_output(raw: str) -> dict:
    """Extract the final JSON object from CLI stdout."""
    text = (raw or "").strip()
    if not text:
        return {}
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = [text] + list(reversed(fenced))
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                if isinstance(obj.get("result"), dict):
                    return obj["result"]
                if isinstance(obj.get("result"), str):
                    try:
                        inner = json.loads(obj["result"])
                        if isinstance(inner, dict):
                            return inner
                    except json.JSONDecodeError:
                        pass
                return obj
        except json.JSONDecodeError:
            pass
    lo, hi = text.find("{"), text.rfind("}")
    if lo >= 0 and hi > lo:
        try:
            obj = json.loads(text[lo : hi + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {}


def _run_structured_task(
    name: str,
    prompt_text: str,
    schema: dict,
    workdir: Path,
    harness: str,
    model: str,
    dry_run: bool,
) -> dict:
    pfile = workdir / f"{name}.prompt.md"
    strict_prompt = (
        prompt_text
        + "\n\nReturn ONLY one valid JSON object matching this schema with no markdown fences:\n"
        + json.dumps(schema)
    )
    pfile.write_text(strict_prompt, encoding="utf-8")
    rc, out = run_prompt(
        pfile,
        workdir,
        harness=harness,
        model=model,
        log_path=workdir / f"{name}.log",
        dry_run=dry_run,
        json_schema=schema,
    )
    if dry_run or rc != 0:
        return {}
    return parse_json_output(out)


def cmd_detect(args: argparse.Namespace) -> int:
    chosen = detect_cli_harness("auto")
    available = {h: find_binary(h) for h in HARNESS_ORDER}
    payload = {"detected": chosen, "available": available}
    print(json.dumps(payload, indent=2 if not getattr(args, "json", False) else None))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    missing_path = root / "data" / "missing-full.json"
    if not missing_path.is_file():
        print(f"missing {missing_path}; run discover.py and build.py assemble first", file=sys.stderr)
        return 1
    items = json.loads(missing_path.read_text(encoding="utf-8"))
    count = min(len(items), args.limit) if args.limit > 0 else len(items)
    if count == 0:
        if getattr(args, "json", False):
            print(json.dumps({"harness": detect_cli_harness(args.harness), "attempted": 0, "completed": 0}))
        else:
            print("0 sessions missing; nothing to extract")
        return 0
    work = root / "data" / ".runner" / "extract"
    work.mkdir(parents=True, exist_ok=True)
    (root / "data" / "runs").mkdir(parents=True, exist_ok=True)

    def one(idx: int) -> tuple[int, int]:
        pfile = work / f"extract-{idx}.prompt.md"
        pfile.write_text(prompts_lib.extract_prompt(str(HERE), str(root), idx), encoding="utf-8")
        rc, _ = run_prompt(
            pfile,
            root,
            harness=args.harness,
            model=args.model,
            log_path=work / f"extract-{idx}.log",
            dry_run=args.dry_run,
        )
        return idx, rc

    ok = 0
    if args.dry_run or args.concurrency <= 1:
        for i in range(count):
            _, rc = one(i)
            ok += int(rc == 0)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for _, rc in pool.map(one, range(count)):
                ok += int(rc == 0)
    resolved = detect_cli_harness(args.harness)
    if getattr(args, "json", False):
        print(json.dumps({"harness": resolved, "attempted": count, "completed": ok, "dry_run": args.dry_run}))
    else:
        print(f"extract ({resolved}): {ok}/{count} completed")
    return 0 if ok == count else 1


def cmd_synth(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    work = root / "data" / ".runner" / "synth"
    work.mkdir(parents=True, exist_ok=True)
    tasks = prompts_lib.synth_tasks(str(root))
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.concurrency, len(tasks))) as pool:
        futs = {
            pool.submit(
                _run_structured_task,
                t["key"],
                t["prompt"],
                t["schema"],
                work,
                args.harness,
                args.model,
                args.dry_run,
            ): t["key"]
            for t in tasks
        }
        for fut in concurrent.futures.as_completed(futs):
            results[futs[fut]] = fut.result()
    out_path = Path(args.out).expanduser() if args.out else root / "data" / "synth-raw.json"
    if not args.dry_run:
        out_path.write_text(json.dumps({"result": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    if getattr(args, "json", False):
        print(json.dumps({"out": str(out_path), "dry_run": args.dry_run}))
    elif not args.dry_run:
        print(f"wrote {out_path}")
    return 0


def cmd_life(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    work = root / "data" / ".runner" / "life"
    work.mkdir(parents=True, exist_ok=True)
    lenses = prompts_lib.life_lenses(str(root))
    merged: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.concurrency, len(lenses))) as pool:
        futs = {
            pool.submit(
                _run_structured_task,
                f"lens-{lens['key']}",
                prompts_lib.life_lens_prompt(lens),
                prompts_lib.FIND_SCHEMA,
                work,
                args.harness,
                args.model,
                args.dry_run,
            ): lens["key"]
            for lens in lenses
        }
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            data = fut.result()
            for pat in data.get("patterns") or []:
                merged.append({"lens": key, **pat})
    profile = _run_structured_task(
        "portrait",
        prompts_lib.life_portrait_prompt(json.dumps(merged, ensure_ascii=False)),
        prompts_lib.PROFILE_SCHEMA,
        work,
        args.harness,
        args.model,
        args.dry_run,
    )
    out_path = Path(args.out).expanduser() if args.out else root / "data" / "life-raw.json"
    if not args.dry_run:
        out_path.write_text(
            json.dumps({"result": {"profile": profile, "lens_findings": merged}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if getattr(args, "json", False):
        print(json.dumps({"out": str(out_path), "dry_run": args.dry_run}))
    elif not args.dry_run:
        print(f"wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="detect active and installed CLI harnesses")
    d.add_argument("--json", action="store_true", help="emit compact JSON output")
    d.set_defaults(fn=cmd_detect)

    for name, fn, help_text in (
        ("extract", cmd_extract, "extract structured findings for every missing session digest"),
        ("synth", cmd_synth, "synthesise roadmap, skill backlog, new work, and AGENTS.md rules"),
        ("life", cmd_life, "run the 7 behavioural lenses and synthesise the life portrait"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--root", required=True, help="run directory containing data/")
        p.add_argument("--harness", default="auto", choices=HARNESS_CHOICES, help="CLI harness to invoke")
        p.add_argument("--model", default="", help="optional model override for the chosen harness")
        p.add_argument("--concurrency", type=int, default=4, help="parallel CLI worker count")
        p.add_argument("--dry-run", action="store_true", help="print commands without executing")
        p.add_argument("--json", action="store_true", help="emit JSON summary output")
        if name == "extract":
            p.add_argument("--limit", type=int, default=0, help="optional cap on sessions extracted this round")
        else:
            p.add_argument("--out", default="", help="output JSON file for build.py merge / merge-life")
        p.set_defaults(fn=fn)

    parsed = ap.parse_args(argv)
    return parsed.fn(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
