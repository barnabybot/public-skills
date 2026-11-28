#!/usr/bin/env python3
"""Discover human-driven agent sessions across harnesses and the Agents vault.

Scans Claude Code, Codex, Grok, Muse, and Antigravity (T3 Code and standalone)
transcripts plus session notes and optional scheduled-job health, keeps
substantive sessions, enriches matched transcripts with vault status and
outcomes, ranks them by driving-signal score, and writes one compact digest per
session under <root>/data/digests/.

  python3 discover.py --root <run-dir> [--sources all] [--since-days 31] [--min-turns 5] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sources


def parse_sources_arg(raw: str) -> set[str]:
    val = (raw or "all").strip().lower()
    if val == "all":
        return set(sources.ALL_SOURCES)
    if val == "transcripts":
        return set(sources.RAW_HARNESSES)
    if val == "vault-only":
        return {"vault", "cron"}
    chosen = {p.strip() for p in val.split(",") if p.strip()}
    unknown = chosen - set(sources.ALL_SOURCES)
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(sorted(unknown))} (valid: {', '.join(sources.ALL_SOURCES)})")
    return chosen


def render_digest(meta: dict, sess: dict) -> str:
    lines = [
        f"SESSION {meta['session_id']}",
        f"harness: {meta['harness']}" + (f" ({meta['host']})" if meta.get("host") else "")
        + f"  project: {meta['project']}  domain: {meta['vault_domain']}  date: {meta['date']}",
        f"turns: human={sess['human']} assistant={sess['assistant']} tools={sess['tools']}  "
        f"span: {sess['first_ts']}..{sess['last_ts']}",
        f"detected_skills: {', '.join(sess['skills']) or '(none)'}",
    ]
    if meta.get("vault_note"):
        lines.append(f"vault_note: {meta['vault_note']}  status: {meta.get('vault_status') or '(unset)'}")
    if sess.get("vault_goal"):
        lines.append(f"vault_goal: {' '.join(sess['vault_goal'].split())[:240]}")
    if sess.get("vault_outcome"):
        lines.append(f"vault_outcome: {' '.join(sess['vault_outcome'].split())[:300]}")
    lines.append("=== TIMELINE ===")
    tl = sess["timeline"]
    body = (tl[:500] + [("--:--", "NOTE", f"[{len(tl) - 650} entries omitted]")] + tl[-150:]) if len(tl) > 700 else tl
    for hhmm, kind, txt in body:
        pre = {"USER": "USER: ", "AI": "AI: ", "TOOL": ". "}.get(kind, "")
        lines.append(f"[{hhmm}] {pre}{txt}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="run directory where data/ is written")
    ap.add_argument(
        "--sources",
        default="all",
        help="comma-separated sources (claude,codex,grok,muse,antigravity,vault,cron) or 'all', 'transcripts', 'vault-only'",
    )
    ap.add_argument("--projects-dir", default="", help="override Claude Code projects directory (default: ~/.claude/projects)")
    ap.add_argument("--agents-vault", default="", help="override agent notes directory (default: $AGENT_NOTES or ~/agent-notes)")
    ap.add_argument("--project-filter", default="", help="keep only sessions whose project or cwd contains this substring")
    ap.add_argument("--harness-filter", default="", help="keep only sessions whose harness contains this substring")
    ap.add_argument("--since-days", type=int, default=31, help="lookback window in days (0 = all time)")
    ap.add_argument("--min-turns", type=int, default=5, help="minimum human turns for raw transcripts")
    ap.add_argument("--pilot", type=int, default=20, help="number of top-ranked sessions to write to pilot.json")
    ap.add_argument("--dry-run", action="store_true", help="discover and print counts without writing files")
    args = ap.parse_args(argv)

    enabled = parse_sources_arg(args.sources)
    roots = sources.default_roots(
        claude_projects=args.projects_dir or None,
        agents_vault=args.agents_vault or None,
    )
    since_ts = None if args.since_days <= 0 else (time.time() - args.since_days * 86400)
    found, cron_health = sources.discover_sessions(
        roots=roots,
        enabled_sources=enabled,
        since_ts=since_ts,
        min_turns=args.min_turns,
        project_filter=args.project_filter,
        harness_filter=args.harness_filter,
    )

    out = Path(args.root).expanduser() / "data"
    records = []
    for sess in found:
        sid = sess["session_id"]
        score = round(sess["human"] + 2 * sess["correction_hits"] + sess["human_chars"] / 1000.0, 2)
        meta = {
            "session_id": sid,
            "harness": sess["harness"],
            "host": sess.get("host", ""),
            "source_kind": sess.get("source_kind", "transcript"),
            "project": sess["project"],
            "vault_domain": sess["vault_domain"],
            "date": (sess["first_ts"] or "")[:10],
            "started_at": sess["first_ts"],
            "ended_at": sess["last_ts"],
            "human_turns": sess["human"],
            "assistant_turns": sess["assistant"],
            "tool_calls": sess["tools"],
            "detected_skills": sess["skills"],
            "correction_hits": sess["correction_hits"],
            "score": score,
            "first_message": sess["first_msg"],
            "source_path": sess["source_path"],
            "resume_cmd": sess["resume_cmd"],
            "vault_note": sess.get("vault_note", ""),
            "vault_status": sess.get("vault_status", ""),
            "digest_path": str((out / "digests" / f"{sid}.txt").resolve()),
        }
        records.append((meta, sess))

    records.sort(key=lambda pair: pair[0]["score"], reverse=True)
    metas = [m for m, _ in records]

    by_harness = Counter(m["harness"] for m in metas)
    by_domain = Counter(m["vault_domain"] for m in metas)
    vault_enriched = sum(1 for m in metas if m.get("vault_note"))

    if not args.dry_run:
        (out / "digests").mkdir(parents=True, exist_ok=True)
        for meta, sess in records:
            (out / "digests" / f"{meta['session_id']}.txt").write_text(render_digest(meta, sess), encoding="utf-8")
        with (out / "work-list.jsonl").open("w", encoding="utf-8") as fh:
            for m in metas:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        (out / "missing-full.json").write_text(
            json.dumps([{"session_id": m["session_id"]} for m in metas], ensure_ascii=False),
            encoding="utf-8",
        )
        (out / "pilot.json").write_text(json.dumps(metas[: args.pilot], ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "cron-health.json").write_text(json.dumps(cron_health, ensure_ascii=False, indent=2), encoding="utf-8")

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}sessions discovered: {len(metas)} (vault-linked: {vault_enriched})")
    print(f"{prefix}by harness: {dict(by_harness)}")
    print(f"{prefix}by domain: {dict(by_domain)}")
    print(f"{prefix}scheduled jobs in window: {cron_health['total_runs']} runs, {cron_health['total_failures']} failures")
    if not args.dry_run:
        print(f"-> {out / 'work-list.jsonl'} | {out / 'missing-full.json'} ({len(metas)} to extract)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
