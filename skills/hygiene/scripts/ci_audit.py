#!/usr/bin/env python3
"""Audit GitHub Actions waiting, setup, running times, overlap, and billable minutes."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

SETUP_MARKERS = (
    "set up job",
    "checkout",
    "setup ",
    "set up ",
    "install ",
    "cache",
    "restore ",
    "configure ",
)


def parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    idx = (len(ordered) - 1) * (pct / 100.0)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(ordered[lo], 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo), 1)


def is_setup_step(name: str) -> bool:
    lower = name.strip().lower()
    return any(marker in lower for marker in SETUP_MARKERS)


def split_job_buckets(job: dict[str, Any]) -> dict[str, float]:
    created = parse_iso(job.get("created_at"))
    started = parse_iso(job.get("started_at"))
    completed = parse_iso(job.get("completed_at"))
    wait_s = max(0.0, started - created) if (created is not None and started is not None) else 0.0
    total_s = max(0.0, completed - started) if (started is not None and completed is not None) else 0.0

    setup_s = 0.0
    run_s = 0.0
    steps = job.get("steps") or []
    if steps:
        for step in steps:
            s_start = parse_iso(step.get("started_at"))
            s_end = parse_iso(step.get("completed_at"))
            if s_start is None or s_end is None:
                continue
            dur = max(0.0, s_end - s_start)
            step_name = str(step.get("name") or "")
            if step_name.lower().startswith("post ") or step_name.lower() == "complete job":
                continue
            if is_setup_step(step_name):
                setup_s += dur
            else:
                run_s += dur
    else:
        run_s = total_s

    billable_min = max(1, math.ceil(total_s / 60.0)) if total_s > 0 else 0
    return {
        "wait_s": round(wait_s, 1),
        "setup_s": round(setup_s, 1),
        "run_s": round(run_s, 1),
        "total_s": round(total_s, 1),
        "billable_min": float(billable_min),
    }


def count_pr_overlaps(runs: list[dict[str, Any]]) -> tuple[int, int]:
    pr_runs = [r for r in runs if r.get("event") == "pull_request"]
    by_branch: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for run in pr_runs:
        start = parse_iso(run.get("created_at"))
        end = parse_iso(run.get("updated_at"))
        if start is None or end is None:
            continue
        by_branch[str(run.get("head_branch") or "")].append((start, end))
    overlaps = 0
    for intervals in by_branch.values():
        intervals.sort()
        max_end = -1.0
        for start, end in intervals:
            if start < max_end:
                overlaps += 1
            if end > max_end:
                max_end = end
    return overlaps, len(pr_runs)


def summarise_runs(runs: list[dict[str, Any]], jobs_by_run: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    wall_all: list[float] = []
    wall_pr: list[float] = []
    billable_per_run: list[float] = []
    job_buckets: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"wait": [], "setup": [], "run": [], "total": []}
    )
    timestamps: list[float] = []

    for run in runs:
        run_id = int(run["id"])
        created = parse_iso(run.get("created_at"))
        updated = parse_iso(run.get("updated_at"))
        if created is not None:
            timestamps.append(created)
        if created is not None and updated is not None:
            wall = max(0.0, updated - created)
            wall_all.append(wall)
            if run.get("event") == "pull_request":
                wall_pr.append(wall)

        run_billable = 0.0
        for job in jobs_by_run.get(run_id, []):
            buckets = split_job_buckets(job)
            run_billable += buckets["billable_min"]
            name = str(job.get("name") or "unknown")
            job_buckets[name]["wait"].append(buckets["wait_s"])
            job_buckets[name]["setup"].append(buckets["setup_s"])
            job_buckets[name]["run"].append(buckets["run_s"])
            job_buckets[name]["total"].append(buckets["total_s"])
        billable_per_run.append(run_billable)

    span_days = max(1.0, (max(timestamps) - min(timestamps)) / 86400.0) if len(timestamps) >= 2 else 30.0
    runs_per_30d = round(len(runs) * (30.0 / span_days), 1) if runs else 0.0
    mean_billable = round(sum(billable_per_run) / len(billable_per_run), 2) if billable_per_run else 0.0
    overlaps, pr_count = count_pr_overlaps(runs)

    jobs_summary = []
    for name, series in job_buckets.items():
        jobs_summary.append(
            {
                "name": name,
                "n": len(series["total"]),
                "wait_p50": percentile(series["wait"], 50),
                "wait_p95": percentile(series["wait"], 95),
                "setup_p50": percentile(series["setup"], 50),
                "setup_p95": percentile(series["setup"], 95),
                "run_p50": percentile(series["run"], 50),
                "run_p95": percentile(series["run"], 95),
                "total_p50": percentile(series["total"], 50),
                "total_p95": percentile(series["total"], 95),
            }
        )
    jobs_summary.sort(key=lambda item: item["total_p50"], reverse=True)

    return {
        "run_count": len(runs),
        "pr_run_count": pr_count,
        "pr_overlap_count": overlaps,
        "span_days": round(span_days, 2),
        "runs_per_30d": runs_per_30d,
        "wall_p50_s": percentile(wall_all, 50),
        "wall_p95_s": percentile(wall_all, 95),
        "pr_wall_p50_s": percentile(wall_pr, 50),
        "pr_wall_p95_s": percentile(wall_pr, 95),
        "mean_billable_min": mean_billable,
        "est_monthly_billable_min": round(mean_billable * runs_per_30d, 1),
        "jobs": jobs_summary,
    }


def gh_json(endpoint: str) -> dict[str, Any]:
    proc = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {endpoint} failed (rc={proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def fetch_runs(repo: str, limit: int, workflow: str | None) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    page = 1
    while len(collected) < limit:
        per_page = min(100, limit - len(collected))
        base = f"repos/{repo}/actions/workflows/{workflow}/runs" if workflow else f"repos/{repo}/actions/runs"
        payload = gh_json(f"{base}?status=completed&per_page={per_page}&page={page}")
        batch = payload.get("workflow_runs") or []
        if not batch:
            break
        collected.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return collected[:limit]


def fetch_jobs(repo: str, runs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    jobs_by_run: dict[int, list[dict[str, Any]]] = {}
    for run in runs:
        run_id = int(run["id"])
        payload = gh_json(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        jobs_by_run[run_id] = payload.get("jobs") or []
    return jobs_by_run


def format_markdown(repo: str, summary: dict[str, Any]) -> str:
    lines = [
        f"# CI Audit: {repo}",
        "",
        f"- Runs audited: {summary['run_count']} ({summary['pr_run_count']} PR, {summary['pr_overlap_count']} overlapping PR runs)",
        f"- Wall-clock (all): p50 {summary['wall_p50_s']}s, p95 {summary['wall_p95_s']}s",
        f"- Wall-clock (PR): p50 {summary['pr_wall_p50_s']}s, p95 {summary['pr_wall_p95_s']}s",
        f"- Billable compute: {summary['mean_billable_min']} min/run (~{summary['est_monthly_billable_min']} min/30d at {summary['runs_per_30d']} runs/30d)",
        "",
        "| Job | n | Wait p50 | Setup p50 | Run p50 | Total p50 | Total p95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for job in summary["jobs"]:
        lines.append(
            f"| `{job['name']}` | {job['n']} | {job['wait_p50']}s | {job['setup_p50']}s | "
            f"{job['run_p50']}s | {job['total_p50']}s | {job['total_p95']}s |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit GitHub Actions waiting, setup, running times, overlap, and billable compute."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format.")
    parser.add_argument("--limit", type=int, default=150, help="Maximum completed workflow runs to inspect.")
    parser.add_argument("--workflow", default=None, help="Optional workflow filename or ID filter.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned GitHub API endpoints without fetching.")
    args = parser.parse_args(argv)

    if args.limit <= 0:
        print("ci_audit: --limit must be positive", file=sys.stderr)
        return 2

    if args.dry_run:
        base = (
            f"repos/{args.repo}/actions/workflows/{args.workflow}/runs"
            if args.workflow
            else f"repos/{args.repo}/actions/runs"
        )
        plan = {
            "dry_run": True,
            "repo": args.repo,
            "limit": args.limit,
            "workflow": args.workflow,
            "endpoints": [f"{base}?status=completed&per_page={min(100, args.limit)}&page=1"],
        }
        if args.as_json:
            print(json.dumps(plan, indent=2))
        else:
            print(f"DRY RUN: would query {plan['endpoints'][0]} (up to {args.limit} runs)")
        return 0

    runs = fetch_runs(args.repo, args.limit, args.workflow)
    jobs_by_run = fetch_jobs(args.repo, runs)
    summary = summarise_runs(runs, jobs_by_run)
    summary["repo"] = args.repo
    if args.as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_markdown(args.repo, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
