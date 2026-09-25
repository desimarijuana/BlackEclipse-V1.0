"""CLI: `python -m harness.eclipse_memory.eval.semantic_cli`.

Prints the semantic dataset version, per-case lexical-only vs semantic-enabled
outcomes, the semantic discovery metrics and the threshold gate result. The gate
is the release signal; safety floors are absolute.
"""

from __future__ import annotations

import sys

from .semantic import (
    check_semantic_thresholds,
    format_semantic_report,
    run_semantic_evaluation,
)


def main() -> int:
    report = run_semantic_evaluation()
    print(format_semantic_report(report))
    gate = check_semantic_thresholds(report)
    print(f"  semantic gate: {'PASS' if gate['passed'] else 'FAIL'}")
    if not gate["passed"]:
        print(f"  failures: {gate['failures']}")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
