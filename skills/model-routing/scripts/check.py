#!/usr/bin/env python3
"""Validate model-routing SKILL.md table and references/routing-catalog.json alignment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import routing_catalog as rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate routing-catalog.json and SKILL.md table alignment.")
    parser.add_argument("--no-live", action="store_true", help="skip live host probes")
    parser.add_argument("--no-log", action="store_true", help="skip route log checks")
    parser.parse_args(argv)
    try:
        catalog = rc.load_catalog(require_skill_table=True)
    except (OSError, ValueError) as exc:
        print(f"FAIL  model-routing check: {exc}", file=sys.stderr)
        return 1
    print(
        f"PASS  model-routing catalog ({len(catalog['providers'])} providers, "
        f"{len(catalog['models'])} models, {len(catalog['categories'])} categories)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
