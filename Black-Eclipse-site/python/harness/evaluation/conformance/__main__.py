"""``python -m harness.evaluation.conformance`` — the C8 conformance gate.

Exit codes: 0 pass, 1 failure/missing case, 2 malformed invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import run_conformance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C8 conformance suite")
    parser.add_argument("--quick", action="store_true", help="skip the slow contract checks")
    parser.add_argument("--only", action="append", default=[], help="case id/name (repeatable)")
    parser.add_argument("--json", type=Path, help="write the full result JSON")
    parser.add_argument("--list", action="store_true", help="list case ids and exit")
    args = parser.parse_args(argv)

    if args.list:
        from .cases import CASES

        for factory in CASES:
            print(factory.__name__)
        return 0

    suite = run_conformance(only=args.only, quick=args.quick)
    payload = suite.to_dict()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for case in payload["cases"]:
        print(f"{'PASS' if case['ok'] else 'FAIL'}  {case['id']:<38} {case['detail']}")
    if payload["missing"]:
        print(f"MISSING cases: {', '.join(payload['missing'])}")
    if payload["extra"]:
        print(f"UNDECLARED cases: {', '.join(payload['extra'])}")
    print(f"conformance: {'PASS' if payload['ok'] else 'FAIL'} "
          f"({payload['passed']}/{payload['total']})")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
