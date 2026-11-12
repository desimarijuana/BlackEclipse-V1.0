"""``python -m harness.evaluation.compare_release`` — release comparability.

Exit codes: 0 comparable, 1 incomparable, 2 malformed input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare_release import CompareError, compare, load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two release evaluation reports")
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(load(args.current), load(args.previous))
    except CompareError as exc:
        print(f"[compare] {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["comparable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
