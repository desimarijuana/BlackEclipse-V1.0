"""CLI runner for the code-verification evaluation.

    python -m harness.code.eval

Prints the dataset version, per-case slices and the aggregate metrics
(claimRecall, falseVerifiedRate, digestStability). Exits non-zero when a floor is
violated so `scripts/test-evals.js` picks it up.
"""

from __future__ import annotations

import sys

from . import check_thresholds, format_report, run_evaluation


def main() -> int:
    metrics = run_evaluation()
    print(format_report(metrics))
    gate = check_thresholds(metrics)
    if gate["passed"]:
        print("  verification gate: PASS")
    else:
        print(f"  verification gate: FAIL - {gate['failures']}")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
