#!/usr/bin/env python3
"""Portable skill-tree audit helper and multi-harness CLI runner.

Discovers SKILL.md files under a skills root ($SKILLS_ROOT or ~/my-skills),
supporting both flat (<root>/<skill>/SKILL.md) and family-grouped
(<root>/<family>/<skill>/SKILL.md) layouts. Provides scoring schemas, rubric
prompts, 35-point score aggregation, HTML report rendering, and headless
execution across agy, claude, codex, grok, or muse.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS_CHOICES = ("auto", "agy", "claude", "codex", "grok", "muse")
HARNESS_ORDER = ("agy", "claude", "codex", "grok", "muse")

EXCLUDED_TOP_DIRS = frozenset(
    {
        ".retired",
        "audits",
        "bin",
        "docs",
        "hooks",
        "output",
        "publish",
        "scripts",
        "vendor",
    }
)
EXCLUDED_CHILD_DIRS = frozenset({".retired", "tests", "test", "fixtures", "__pycache__", "node_modules"})

DIMENSIONS: tuple[str, ...] = (
    "description",
    "line_budget",
    "progressive_disclosure",
    "self_containment",
    "naming",
    "freshness",
    "signal_density",
)

DIMENSION_SLIM_KEYS: dict[str, str] = {
    "description": "desc",
    "line_budget": "budget",
    "progressive_disclosure": "prog",
    "self_containment": "self",
    "naming": "name",
    "freshness": "fresh",
    "signal_density": "sig",
}

MAX_TOTAL = len(DIMENSIONS) * 5


def _score_dim_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["score", "note"],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 5, "description": description},
            "note": {"type": "string"},
        },
    }


SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name",
        "family",
        "lines",
        *DIMENSIONS,
        "top_fix",
    ],
    "properties": {
        "name": {"type": "string", "description": "skill folder name"},
        "family": {"type": "string"},
        "lines": {"type": "integer", "description": "SKILL.md total line count"},
        "description": _score_dim_schema(
            "5 = <=1024 chars, third person, concrete triggers; lower for missing triggers, first person, over length, vague"
        ),
        "line_budget": _score_dim_schema(
            "5 = <100 lines; 3 = 100-200; 1 = >200 and not a justified parent router"
        ),
        "progressive_disclosure": _score_dim_schema(
            "5 = detail pushed into references/docs/workflows, SKILL.md is a router; low = framework detail inline"
        ),
        "self_containment": _score_dim_schema(
            "5 = everything the skill needs lives in its folder or shared family scripts; low = dangling refs, missing scripts"
        ),
        "naming": _score_dim_schema(
            "5 = clear name, parent: set for family children, no concept collisions; low = ambiguous or prefix missing"
        ),
        "freshness": _score_dim_schema(
            "5 = no dated/stale claims, no dead content; low = time-sensitive claims, stale migration notes, contradictions"
        ),
        "signal_density": _score_dim_schema(
            "5 = every line changes behaviour; penalise no-op truisms, restated rules, and content duplicated across sections"
        ),
        "top_fix": {"type": "string", "description": "the single highest-value change for THIS skill, one sentence"},
    },
}

SYNTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline_fix", "top_five", "themes"],
    "properties": {
        "headline_fix": {
            "type": "object",
            "additionalProperties": False,
            "required": ["skill", "what", "why"],
            "properties": {
                "skill": {"type": "string"},
                "what": {"type": "string"},
                "why": {"type": "string"},
            },
        },
        "top_five": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["skill", "fix", "impact"],
                "properties": {
                    "skill": {"type": "string"},
                    "fix": {"type": "string"},
                    "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["theme", "count", "note"],
                "properties": {
                    "theme": {"type": "string"},
                    "count": {"type": "integer"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

RUBRIC = """You are auditing one agent skill against the skill-manager quality rubric.
Read its SKILL.md in full and use the supplied exact line count.
Score each dimension 0-5 (integer). Be a tough but fair grader; reserve 5 for genuinely clean.
Dimensions:
- description: the frontmatter description field. 5 = <=1024 chars, third person, names concrete user phrases/file types/task shapes as triggers. Penalise first person, vagueness, missing triggers, over-length.
- line_budget: 5 = <100 content lines; 3 = 100-200; 1 = >200 unless a justified parent router (parent routers carrying a console/lifecycle/routing table may stay up to 200).
- progressive_disclosure: 5 = SKILL.md is a router and detail lives in references/docs/workflows; low if framework detail, long tables, or edge cases sit inline.
- self_containment: 5 = everything the skill needs is reachable; penalise genuinely dangling references, missing scripts, and host-specific absolute paths in headless skills. Do not penalise scripts deliberately shared at a family's parent level (e.g. <skills-root>/<family>/scripts/) or documented companion skill references.
- naming: 5 = clear unambiguous name, parent: set for family children, no concept collision with other skills; penalise ambiguous naming.
- freshness: 5 = no time-sensitive/dated claims, no dead content, no stale migration notes or contradictions; penalise dated claims that belong in notes, stale migration text, contradictions.
- signal_density: 5 = every line earns its place and changes behaviour; penalise no-op truisms ("be thorough", "write a clear commit message", "make it readable"), restated rules (a single HARD GATE may earn one echo, nothing else), and guidance duplicated across sections or already owned by a referenced file. The test: would a competent agent act identically with the line removed? If yes, it is a no-op.
Also give top_fix: the single highest-value change for THIS skill in one sentence."""


def default_skills_root() -> Path:
    override = os.environ.get("SKILLS_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "my-skills"


def discover_skills(
    skills_root: Path | str | None = None,
    *,
    families: list[str] | None = None,
    include_parents: bool = False,
) -> list[dict[str, Any]]:
    root = Path(skills_root).expanduser().resolve() if skills_root else default_skills_root().resolve()
    if not root.is_dir():
        return []

    selected = set(families) if families else None
    discovered: list[dict[str, Any]] = []

    for top_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if not top_dir.is_dir():
            continue
        top_name = top_dir.name
        if top_name.startswith(".") or top_name in EXCLUDED_TOP_DIRS:
            continue

        child_skills: list[dict[str, Any]] = []
        for child in sorted(top_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name.startswith("_archive") or child.name in EXCLUDED_CHILD_DIRS:
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            lines = len(skill_md.read_text(encoding="utf-8", errors="replace").splitlines())
            child_skills.append(
                {
                    "path": str(skill_md),
                    "family": top_name,
                    "name": child.name,
                    "lines": lines,
                }
            )

        if child_skills:
            if selected is not None and top_name not in selected:
                continue
            if include_parents:
                parent_md = top_dir / "SKILL.md"
                if parent_md.is_file():
                    lines = len(parent_md.read_text(encoding="utf-8", errors="replace").splitlines())
                    discovered.append(
                        {
                            "path": str(parent_md),
                            "family": top_name,
                            "name": top_name,
                            "lines": lines,
                        }
                    )
            discovered.extend(child_skills)
            continue

        flat_md = top_dir / "SKILL.md"
        if flat_md.is_file():
            flat_family = root.name
            if selected is not None and flat_family not in selected and top_name not in selected:
                continue
            lines = len(flat_md.read_text(encoding="utf-8", errors="replace").splitlines())
            discovered.append(
                {
                    "path": str(flat_md),
                    "family": flat_family,
                    "name": top_name,
                    "lines": lines,
                }
            )

    discovered.sort(key=lambda item: (item["family"], item["name"]))
    return discovered


def score_prompt(skill: dict[str, Any]) -> str:
    return (
        f"{RUBRIC}\n\n"
        f"The skill SKILL.md is at:\n{skill['path']}\n"
        f"Exact line count: {skill['lines']}\n\n"
        f"Return the structured score. Set family to \"{skill['family']}\", "
        f"name to \"{skill['name']}\", and lines to {skill['lines']}."
    )


def aggregate_scores(scored: list[Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in scored:
        if not isinstance(item, dict):
            continue
        if any(not isinstance(item.get(dim), dict) for dim in DIMENSIONS):
            continue
        total = sum(int(item[dim].get("score", 0)) for dim in DIMENSIONS)
        ranked.append({**item, "total": total})
    ranked.sort(key=lambda s: (s["total"], str(s.get("name", "")), str(s.get("family", ""))))
    return ranked


def slim_scores(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": s["name"],
            "family": s["family"],
            "total": s["total"],
            "lines": s["lines"],
            "scores": {short: s[dim]["score"] for dim, short in DIMENSION_SLIM_KEYS.items()},
            "top_fix": s["top_fix"],
        }
        for s in ranked
    ]


def synthesis_prompt(slim: list[dict[str, Any]]) -> str:
    return (
        f"You are the lead skill maintainer. Below are {len(slim)} skills scored against the rubric "
        f"(each dimension 0-5, total /{MAX_TOTAL}, worst first).\n"
        "Name the SINGLE highest-value fix across the whole tree (the one change that most improves the fleet), "
        "then the top 5 fixes to action in priority order, then the recurring weakness themes with how many skills each touches.\n"
        "Judge by leverage: a weak description on a heavily-used router hurts more than a long file on a rarely-called skill. "
        "Be concrete and specific to the named skills.\n\n"
        f"DATA:\n{json.dumps(slim, ensure_ascii=False)}"
    )


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value), quote=True)


def _score_cell(dim_obj: dict[str, Any]) -> str:
    score = int(dim_obj.get("score", 0))
    colour = "#1a7f37" if score >= 4 else "#9a6700" if score >= 3 else "#cf222e"
    return (
        f'<td style="text-align:center;color:{colour};font-weight:600" '
        f'title="{_esc(dim_obj.get("note", ""))}">{score}</td>'
    )


def render_html(rows: list[dict[str, Any]], syn: dict[str, Any] | None, count: int) -> str:
    synthesis = syn if isinstance(syn, dict) else {}
    headline = synthesis.get("headline_fix") if isinstance(synthesis.get("headline_fix"), dict) else {}

    theme_rows = "".join(
        f'<tr><td>{_esc(t.get("theme"))}</td><td style="text-align:center">{_esc(t.get("count"))}</td>'
        f'<td>{_esc(t.get("note"))}</td></tr>'
        for t in (synthesis.get("themes") or [])
        if isinstance(t, dict)
    )

    five_rows_parts: list[str] = []
    for idx, fix in enumerate(synthesis.get("top_five") or [], start=1):
        if not isinstance(fix, dict):
            continue
        impact = str(fix.get("impact") or "")
        col = "#cf222e" if impact == "high" else "#9a6700" if impact == "medium" else "#57606a"
        five_rows_parts.append(
            f'<tr><td style="text-align:center;color:#57606a">{idx}</td>'
            f'<td style="font-weight:600">{_esc(fix.get("skill"))}</td>'
            f'<td>{_esc(fix.get("fix"))}</td>'
            f'<td style="text-align:center;color:{col};font-weight:600;text-transform:uppercase;font-size:11px">{_esc(impact)}</td></tr>'
        )
    five_rows = "".join(five_rows_parts)

    table_rows_parts: list[str] = []
    for row in rows:
        total = int(row.get("total", 0))
        tc = "#1a7f37" if total >= 28 else "#9a6700" if total >= 21 else "#cf222e"
        cells = "".join(_score_cell(row[dim]) for dim in DIMENSIONS)
        table_rows_parts.append(
            f'<tr><td style="font-weight:600">{_esc(row.get("name"))}</td>'
            f'<td style="color:#57606a">{_esc(row.get("family"))}</td>'
            f'<td style="text-align:center;color:{tc};font-weight:700">{total}</td>'
            f'<td style="text-align:center;color:#57606a">{_esc(row.get("lines"))}</td>'
            f"{cells}"
            f'<td style="color:#24292f;font-size:13px">{_esc(row.get("top_fix"))}</td></tr>'
        )
    table_rows = "".join(table_rows_parts)

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Skill audit ({count} skills)</title>\n"
        "<style>\n"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#24292f;max-width:1100px;margin:0 auto;padding:32px 24px;line-height:1.5;background:#fff}\n"
        "h1{font-size:28px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 12px;border-bottom:1px solid #d0d7de;padding-bottom:6px}\n"
        ".sub{color:#57606a;margin:0 0 8px}\n"
        ".headline{background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:16px 18px;margin:18px 0}\n"
        ".headline .what{font-size:17px;font-weight:700;margin:0 0 6px} .headline .why{margin:0;color:#3d3d3d}\n"
        "table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}\n"
        "th,td{border:1px solid #d0d7de;padding:6px 8px;vertical-align:top} th{background:#f6f8fa;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.3px;color:#57606a}\n"
        ".scorehead th{text-align:center} caption{caption-side:bottom;color:#8b949e;font-size:12px;padding-top:8px;text-align:left}\n"
        "code{background:#f6f8fa;padding:1px 5px;border-radius:4px;font-size:12px}\n"
        "</style></head><body>\n"
        "<h1>Skill-tree audit</h1>\n"
        f'<p class="sub">{count} skills scored against the skill-manager rubric. '
        "Generated by the <code>skill-audit</code> portable workflow. Hover any cell for the grader note.</p>\n"
        "<h2>The single highest-value fix</h2>\n"
        f'<div class="headline"><p class="what">{_esc(headline.get("skill"))}: {_esc(headline.get("what"))}</p>'
        f'<p class="why">{_esc(headline.get("why"))}</p></div>\n'
        "<h2>Top 5 to action</h2>\n"
        f"<table><thead><tr><th>#</th><th>Skill</th><th>Fix</th><th>Impact</th></tr></thead><tbody>{five_rows}</tbody></table>\n"
        "<h2>Recurring weakness themes</h2>\n"
        f"<table><thead><tr><th>Theme</th><th>Skills</th><th>Note</th></tr></thead><tbody>{theme_rows}</tbody></table>\n"
        "<h2>Every skill, worst to best</h2>\n"
        f"<table><thead><tr><th>Skill</th><th>Family</th><th>Total /{MAX_TOTAL}</th><th>Lines</th>"
        '<th colspan="7" style="text-align:center">Dimensions (0-5)</th><th>Notes</th></tr></thead>\n'
        '<thead class="scorehead"><tr><th></th><th></th><th></th><th></th>'
        "<th>Desc</th><th>Budget</th><th>Prog</th><th>Self</th><th>Name</th><th>Fresh</th><th>Signal</th>"
        '<th style="text-align:left">Top fix for this skill</th></tr></thead>\n'
        f"<tbody>{table_rows}</tbody>\n"
        f"<caption>Each dimension scored 0-5: green &ge;4, amber 3, red &le;2. Total out of {MAX_TOTAL}.</caption></table>\n"
        "</body></html>"
    )


def find_binary(harness: str) -> str | None:
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
    local_bin = Path.home() / ".local" / "bin" / harness
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
    resolved = detect_cli_harness(harness)
    binary = find_binary(resolved) or resolved
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""

    if resolved == "agy":
        cmd = [binary, "-p", prompt_text, "--disable-slash-commands"]
        if model:
            cmd += ["--model", model]
        if json_schema_path:
            cmd += ["--json-schema", str(json_schema_path), "--output-format", "json"]
        return cmd, None

    if resolved == "codex":
        cmd = [binary, "exec", "--sandbox", "read-only", "-C", str(cwd)]
        if model:
            cmd += ["--model", model]
        if json_schema_path:
            cmd += ["--output-schema", str(json_schema_path)]
        cmd.append("-")
        return cmd, prompt_text

    if resolved == "grok":
        cmd = [binary, "--cwd", str(cwd), "--prompt-file", str(prompt_path)]
        if model:
            cmd += ["--model", model]
        return cmd, None

    if resolved == "muse":
        cmd = [binary, "exec", "--prompt-file", str(prompt_path)]
        if model:
            cmd += ["--model", model]
        return cmd, None

    cmd = [binary, "-p", prompt_text]
    if model:
        cmd += ["--model", model]
    return cmd, None


def parse_json_output(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    for cand in [text, *reversed(fenced)]:
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


def _run_structured_cli(
    name: str,
    prompt_text: str,
    schema: dict[str, Any],
    workdir: Path,
    harness: str,
    model: str,
    timeout: int = 1800,
) -> dict[str, Any]:
    pfile = workdir / f"{name}.prompt.md"
    strict_prompt = (
        prompt_text
        + "\n\nReturn ONLY one valid JSON object matching this schema with no markdown fences:\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    pfile.write_text(strict_prompt, encoding="utf-8")
    tmp_schema = tempfile.NamedTemporaryFile("w", suffix=".schema.json", delete=False)
    tmp_schema.write(json.dumps(schema, ensure_ascii=False))
    tmp_schema.close()
    schema_path = Path(tmp_schema.name)
    try:
        cmd, stdin_text = build_command(harness, pfile, workdir, model=model, json_schema_path=schema_path)
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        (workdir / f"{name}.log").write_text(combined, encoding="utf-8")
        if proc.returncode != 0:
            return {}
        return parse_json_output(proc.stdout or "")
    finally:
        schema_path.unlink(missing_ok=True)


def _cmd_detect(parsed: argparse.Namespace) -> int:
    payload = {
        "detected": detect_cli_harness("auto"),
        "available": {h: find_binary(h) for h in HARNESS_ORDER},
    }
    print(json.dumps(payload, indent=None if parsed.json else 2))
    return 0


def _cmd_discover(parsed: argparse.Namespace) -> int:
    root = Path(parsed.root).expanduser().resolve() if parsed.root else default_skills_root().resolve()
    skills = discover_skills(root, families=parsed.family, include_parents=parsed.include_parents)
    payload = {"root": str(root), "count": len(skills), "skills": skills}
    if parsed.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for item in skills:
            print(f"{item['family']}/{item['name']} ({item['lines']} lines): {item['path']}")
        print(f"Discovered {len(skills)} SKILL.md files under {root}")
    return 0


def _cmd_render(parsed: argparse.Namespace) -> int:
    src = Path(parsed.input_json).expanduser()
    if not src.is_file():
        print(f"Input JSON file not found at {src}. Pass --input-json with an existing audit payload.", file=sys.stderr)
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    ranked = aggregate_scores(data.get("ranked") or [])
    synthesis = data.get("synthesis") or {}
    count = int(data.get("count") or len(ranked))
    rendered = render_html(ranked, synthesis, count)
    out_html = Path(parsed.out_html).expanduser()
    if not parsed.dry_run:
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(rendered, encoding="utf-8")
    payload = {"out_html": str(out_html), "count": count, "dry_run": parsed.dry_run}
    if parsed.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        verb = "Would write" if parsed.dry_run else "Wrote"
        print(f"{verb} HTML audit report for {count} skills to {out_html}")
    return 0


def _cmd_run(parsed: argparse.Namespace) -> int:
    root = Path(parsed.root).expanduser().resolve() if parsed.root else default_skills_root().resolve()
    skills = discover_skills(root, families=parsed.family, include_parents=parsed.include_parents)
    resolved_harness = detect_cli_harness(parsed.harness)
    if parsed.dry_run:
        payload = {
            "dry_run": True,
            "harness": resolved_harness,
            "root": str(root),
            "count": len(skills),
            "skills": [f"{s['family']}/{s['name']}" for s in skills],
            "out_html": parsed.out_html or None,
            "out_json": parsed.out_json or None,
        }
        if parsed.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"dry run ({resolved_harness}): would score {len(skills)} skills under {root} and synthesise report")
        return 0

    if not skills:
        print(f"No SKILL.md files found under {root}. Pass --root pointing to a skills tree.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="skill-audit-") as tmpdir:
        work = Path(tmpdir)

        def score_one(item: dict[str, Any]) -> dict[str, Any] | None:
            slug = f"{item['family']}-{item['name']}".replace("/", "-")
            res = _run_structured_cli(
                f"score-{slug}",
                score_prompt(item),
                SCORE_SCHEMA,
                work,
                resolved_harness,
                parsed.score_model,
            )
            return {**res, "path": item["path"]} if res else None

        scored: list[dict[str, Any] | None] = []
        if parsed.concurrency <= 1:
            scored = [score_one(item) for item in skills]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=parsed.concurrency) as pool:
                scored = list(pool.map(score_one, skills))

        ranked = aggregate_scores(scored)
        slim = slim_scores(ranked)
        synthesis = _run_structured_cli(
            "synthesis",
            synthesis_prompt(slim),
            SYNTH_SCHEMA,
            work,
            resolved_harness,
            parsed.synth_model,
        )
        rendered = render_html(ranked, synthesis, len(skills))
        result = {"count": len(skills), "ranked": ranked, "synthesis": synthesis, "html": rendered}

        if parsed.out_html:
            out_html = Path(parsed.out_html).expanduser()
            out_html.parent.mkdir(parents=True, exist_ok=True)
            out_html.write_text(rendered, encoding="utf-8")
        if parsed.out_json:
            out_json = Path(parsed.out_json).expanduser()
            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        if parsed.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            worst = ranked[0]["total"] if ranked else "n/a"
            print(f"Audited {len(ranked)}/{len(skills)} skills ({resolved_harness}); worst score {worst}/{MAX_TOTAL}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover, score, synthesise, and render portable skill-tree audits across local CLI harnesses.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    det = sub.add_parser("detect", help="detect active and installed CLI harnesses")
    det.add_argument("--json", action="store_true", help="emit compact JSON output")
    det.set_defaults(fn=_cmd_detect)

    disc = sub.add_parser("discover", help="list SKILL.md files and line counts deterministically")
    disc.add_argument("--root", default="", help="skills tree root (default: $SKILLS_ROOT or ~/my-skills)")
    disc.add_argument("--family", action="append", default=None, help="limit discovery to one or more family folders")
    disc.add_argument("--include-parents", action="store_true", help="include top-level <family>/SKILL.md parent routers")
    disc.add_argument("--json", action="store_true", help="emit JSON output")
    disc.set_defaults(fn=_cmd_discover)

    run = sub.add_parser("run", help="discover, score in parallel, synthesise, and render the HTML audit report")
    run.add_argument("--root", default="", help="skills tree root (default: $SKILLS_ROOT or ~/my-skills)")
    run.add_argument("--family", action="append", default=None, help="limit audit to one or more family folders")
    run.add_argument("--include-parents", action="store_true", help="include top-level <family>/SKILL.md parent routers")
    run.add_argument("--harness", default="auto", choices=HARNESS_CHOICES, help="CLI harness to invoke")
    run.add_argument("--score-model", default="", help="optional model override for per-skill scoring")
    run.add_argument("--synth-model", default="", help="optional model override for synthesis")
    run.add_argument("--concurrency", type=int, default=4, help="parallel scoring worker count")
    run.add_argument("--out-html", default="", help="optional destination path for the rendered HTML report")
    run.add_argument("--out-json", default="", help="optional destination path for the full JSON payload")
    run.add_argument("--dry-run", action="store_true", help="preview discovered skills without running models or writing files")
    run.add_argument("--json", action="store_true", help="emit JSON output")
    run.set_defaults(fn=_cmd_run)

    ren = sub.add_parser("render", help="render an HTML audit report from a saved JSON payload")
    ren.add_argument("--input-json", required=True, help="path to saved audit JSON payload")
    ren.add_argument("--out-html", required=True, help="destination path for the rendered HTML report")
    ren.add_argument("--dry-run", action="store_true", help="validate input without writing the HTML file")
    ren.add_argument("--json", action="store_true", help="emit JSON output")
    ren.set_defaults(fn=_cmd_render)

    parsed = parser.parse_args(argv)
    return parsed.fn(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
