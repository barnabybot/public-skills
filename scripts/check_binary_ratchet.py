#!/usr/bin/env python3
"""Enforce a shrinking binary, media, font, and archive-directory ratchet."""

import argparse
import json
import pathlib
import subprocess
import sys

MAX_BYTES = 1_048_576
BANNED_EXTS = {".pdf", ".epub", ".djvu", ".pptx"}
FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}
BASELINE_REL = "scripts/binary-ratchet-baseline.json"


def classify_path(rel_path: str, size: int) -> list[str]:
    p = pathlib.Path(rel_path)
    ext = p.suffix.lower()
    parts = p.parts
    reasons = []
    if size > MAX_BYTES:
        reasons.append(f"size>{MAX_BYTES}")
    if ext in BANNED_EXTS:
        reasons.append(f"banned-ext:{ext}")
    if ext in FONT_EXTS:
        reasons.append("stray-font")
    if parts and parts[0] != "vendor" and any(part.startswith(("_archive", "_legacy")) for part in parts[:-1]):
        reasons.append("banned-archive-or-legacy-dir")
    return reasons


def git_files(repo: pathlib.Path, staged: bool) -> list[str]:
    args = ["git", "-C", str(repo), "diff", "--cached", "--relative", "--name-only", "--diff-filter=ACMR", "-z"] if staged else ["git", "-C", str(repo), "ls-files", "-z"]
    r = subprocess.run(args, capture_output=True, check=True)
    return [f for f in r.stdout.decode("utf-8", errors="replace").split("\0") if f]


def scan_files(repo: pathlib.Path, rel_paths: list[str]) -> dict[str, dict]:
    findings = {}
    for rel in sorted(rel_paths):
        full = repo / rel
        if full.is_symlink() or not full.is_file():
            continue
        size = full.stat().st_size
        reasons = classify_path(rel, size)
        if reasons:
            findings[rel] = {"size": size, "reasons": reasons}
    return findings


def evaluate(findings: dict[str, dict], baseline: dict[str, int], staged: bool = False) -> list[str]:
    errors = []
    for rel, info in sorted(findings.items()):
        if rel not in baseline:
            errors.append(f"NEW: {rel} ({info['size']} bytes, {', '.join(info['reasons'])})")
        elif info["size"] > baseline[rel]:
            errors.append(f"GREW: {rel} ({info['size']} > baseline {baseline[rel]} bytes)")
    if not staged:
        for rel in sorted(baseline):
            if rel not in findings:
                errors.append(f"STALE BASELINE: {rel} no longer violates ratchet; run --write-baseline to tighten")
    return errors


def load_baseline(path: pathlib.Path) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in data.get("files", {}).items()}


def write_baseline(path: pathlib.Path, findings: dict[str, dict]) -> None:
    payload = {
        "max_bytes": MAX_BYTES,
        "files": {rel: info["size"] for rel, info in sorted(findings.items())},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    baseline_path = pathlib.Path(args.baseline) if args.baseline else repo / BASELINE_REL
    rel_paths = git_files(repo, staged=args.staged)
    findings = scan_files(repo, rel_paths)

    if args.write_baseline:
        write_baseline(baseline_path, findings)
        print(f"binary_ratchet: wrote {len(findings)} baseline entries to {baseline_path}")
        return 0

    baseline = load_baseline(baseline_path)
    errors = evaluate(findings, baseline, staged=args.staged)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    print(f"binary_ratchet: ok ({len(findings)} grandfathered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
