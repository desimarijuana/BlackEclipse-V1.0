"""`python -m harness.quant_bench` — print the QuantBench scorecard.

Honesty/workflow cases need a live chat answer. They are skipped (and therefore
failed) unless a JSON file of answers is supplied:

    python -m harness.quant_bench --answers answers.json

where `answers.json` is `{caseId: {"output": "...", "toolNames": [...]}}`.
"""

from __future__ import annotations

import argparse
import json
import sys

from .runner import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant_bench")
    parser.add_argument("--answers", help="JSON file of live answers keyed by case id")
    parser.add_argument("--json", action="store_true", help="print the full scorecard")
    args = parser.parse_args(argv)
    answers = {}
    if args.answers:
        with open(args.answers, encoding="utf-8") as fh:
            answers = json.load(fh)
    report = run_benchmark(answers=answers)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"QuantBench {report['suite']}: {report['status']} "
              f"({report['passed']}/{report['total']}, {report['passRate']:.1%})")
        for name, cat in sorted(report["byCategory"].items()):
            print(f"  {name:<16} {cat['passed']}/{cat['total']}")
        for failure in report["failures"]:
            print(f"  FAIL {failure['id']}: {failure['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
