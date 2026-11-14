#!/usr/bin/env python3
"""Advisory lint for the small CLI standard in references/cli-standard.md.

Scans a skill directory, or a repository root, for Python entrypoints that a
SKILL.md, workflow, or reference tells an agent to run. Reports gaps in
--help, --json, --dry-run on writers, and terse errors. Exit 0 when clean,
1 when findings exist, 2 on a bad invocation. Findings never block
scripts/validate.sh.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cli_standard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report advisory gaps against the small CLI standard. "
            "Pass a skill directory or a repository root."
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Skill directory or repository root to scan",
    )
    parser.add_argument("--json", action="store_true", help="Print findings as JSON")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 2
    root = Path(args.root)
    if not root.is_dir():
        print(
            f"cli lint root is not a directory: {root}. Pass a skill directory or the repository root.",
            file=sys.stderr,
        )
        return 2
    count, gaps = cli_standard.audit(root)
    rows = [{"path": path, "gap": message} for path, message in gaps]
    if args.json:
        json.dump({"entrypoints": count, "findings": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for row in rows:
            print(f"{row['path']}: {row['gap']}")
        print(f"entrypoints: {count}; findings: {len(rows)}")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
