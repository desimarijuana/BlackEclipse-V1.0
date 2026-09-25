"""CLI: `python -m harness.eclipse_memory.eval.contradictions_cli`.

Prints the contradiction dataset version, per-case expected/actual, aggregate
metrics and the threshold gate result. Report-only by default; the gate is the
release signal.
"""

from __future__ import annotations

import sys

from .contradictions import (
    check_contradiction_thresholds,
    format_contradiction_report,
    run_contradiction_evaluation,
)


def main() -> int:
    report = run_contradiction_evaluation()
    print(format_contradiction_report(report))
    gate = check_contradiction_thresholds(report)
    print(f"  contradiction gate: {'PASS' if gate['passed'] else 'FAIL'}")
    if not gate["passed"]:
        print(f"  failures: {gate['failures']}")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
