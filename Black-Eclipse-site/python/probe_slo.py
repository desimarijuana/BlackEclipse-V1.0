"""C7 SLO probe / release-gate CLI.

Run from the repository (the Node wrappers pass the vendored interpreter):

    python/probe_slo.py --probe --out docs/harness/slo-report.json
    python/probe_slo.py --gate

Exit codes: 0 healthy, 1 breach/regression, 2 malformed report or config.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parent
ROOT = PYTHON_DIR.parent
DEFAULT_BUDGETS = ROOT / "docs" / "harness" / "slo-budgets.json"
DEFAULT_BASELINE = ROOT / "docs" / "harness" / "slo-baseline.json"

from harness.observability.gate import GateError, evaluate_gate, load_json  # noqa: E402
from harness.observability.probe import run_probe  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C7 observability SLO probe and release gate")
    parser.add_argument("--probe", action="store_true", help="run the deterministic probe")
    parser.add_argument("--gate", action="store_true", help="evaluate budgets and baseline")
    parser.add_argument("--runs", type=int, default=40)
    parser.add_argument("--report", type=Path, help="report JSON to read for --gate")
    parser.add_argument("--out", type=Path, help="write the probe report here")
    parser.add_argument("--write-report", type=Path, help="write the gated report here")
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    if not args.probe and not args.gate:
        parser.error("choose --probe and/or --gate")

    if args.probe:
        report = run_probe(runs=args.runs)
        if args.out:
            _write(args.out, report)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        if not args.gate:
            return 0
    else:
        if args.report:
            report = load_json(args.report)
        else:
            report = run_probe(runs=args.runs)

    try:
        budgets = load_json(args.budgets)
        baseline = load_json(args.baseline) if args.baseline.exists() else None
    except GateError as exc:
        print(f"[slo-gate] configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        result = evaluate_gate(report, budgets, baseline)
    except GateError as exc:
        print(f"[slo-gate] invalid report: {exc}", file=sys.stderr)
        return 2

    if args.write_report:
        _write(args.write_report, report)

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.ok:
        print(f"[slo-gate] PASS — {len(result.checks)} check(s)")
        return 0
    print(f"[slo-gate] FAIL — {len(result.failures)} of {len(result.checks)} check(s)", file=sys.stderr)
    for failure in result.failures:
        print(f"  - {failure.name}: {failure.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
