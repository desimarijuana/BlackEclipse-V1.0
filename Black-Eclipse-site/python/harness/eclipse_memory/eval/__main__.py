"""CLI runner for the Eclipse-Memory retrieval evaluation.

    python -m harness.eclipse_memory.eval

Prints the dataset version, per-case precision/recall and the aggregate metrics
(recall, topical precision, scope leakage, forbidden hits, no-match cleanliness,
context-budget behaviour). Report-only: the set is small and human-reviewed, so
no single pass/fail is implied. A forbidden hit or a scope leak is the signal to
watch.
"""

from __future__ import annotations

import json
import sys

from . import format_report, run_evaluation


def main() -> int:
    report = run_evaluation()
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
