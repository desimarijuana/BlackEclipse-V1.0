"""CLI runner for the code-verification evaluation.

    python -m harness.code.eval

Prints the dataset version, per-case slices and the aggregate metrics
(claimRecall, falseVerifiedRate, digestStability). Exits non-zero when a floor is
violated so `scripts/test-evals.js` picks it up.
"""

from __future__ import annotations

import sys

from . import (
    check_code_thresholds,
    check_thresholds,
    format_code_report,
    format_report,
    run_code_evaluation,
    run_evaluation,
)


def main() -> int:
    # `--checksum` prints the reviewed task-dataset checksum (for the constant in
    # tasks.REVIEWED_TASKS_CHECKSUM) and exits, so a re-review is a deliberate act.
    if "--checksum" in sys.argv:
        from .tasks import load_task_dataset, tasks_checksum  # noqa: PLC0415

        print(tasks_checksum(load_task_dataset()))
        return 0
    # Phase 4 — the verification eval (kept).
    metrics = run_evaluation()
    print(format_report(metrics))
    gate = check_thresholds(metrics)
    if gate["passed"]:
        print("  verification gate: PASS")
    else:
        print(f"  verification gate: FAIL - {gate['failures']}")
    # Phase 12 — the task + safety eval.
    print("")
    code = run_code_evaluation()
    print(format_code_report(code))
    code_gate = check_code_thresholds(code)
    if code_gate["passed"]:
        print("  code gate: PASS")
    else:
        print(f"  code gate: FAIL - {code_gate['failures']}")
    return 0 if (gate["passed"] and code_gate["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
