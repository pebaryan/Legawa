"""Validate and scaffold entries in ``legawa.tools.trusted_recent``.

Usage:
    python scripts/validate_trusted_recent.py
    python scripts/validate_trusted_recent.py --template "Perpres 9/2027"

Exit codes:
    0 - all entries are structurally valid
    1 - one or more entries are invalid
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.tools.trusted_recent import (  # noqa: E402
    TRUSTED_RECENT,
    render_trusted_entry_template,
    trusted_entry_warnings,
    validate_trusted_entry,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        metavar="REFERENCE",
        help="emit a paste-ready trusted_recent entry template and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    if args.template:
        print(render_trusted_entry_template(args.template))
        return 0

    problems: list[str] = []
    warnings: list[str] = []
    for reference, entry in sorted(TRUSTED_RECENT.items()):
        entry_problems = validate_trusted_entry(reference, entry)
        if entry_problems:
            problems.extend(f"{reference}: {problem}" for problem in entry_problems)
        for warning in trusted_entry_warnings(reference, entry):
            warnings.append(f"{reference}: {warning}")

    if warnings:
        for warning in warnings:
            print(f"WARN: {warning}")

    if problems:
        print("INVALID trusted_recent entries:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"OK: {len(TRUSTED_RECENT)} trusted_recent entries validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
