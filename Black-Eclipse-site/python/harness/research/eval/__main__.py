"""CLI runner for the Phase 4 semantic-support evaluation.

    python -m harness.research.eval

Prints the dataset version/checksum, the deterministic-slice metrics, and the
confusion matrix. It reports counts, false accepts and false rejects per slice —
never a single pass/fail — because the label set is small and human-reviewed.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import EvalMetrics, run_evaluation
from .escalation import run_escalation_evaluation
from .nvda import run_nvda_evaluation


def format_report(metrics: EvalMetrics) -> str:
    data = metrics.to_dict()
    lines = [
        f"Phase 4 semantic-support evaluation",
        f"dataset={data['datasetVersion']} checksum={data['checksum']}",
        f"cases={data['total']} correct={data['correct']} accuracy={data['accuracy']}",
        f"falseAccepts={data['falseAccepts']} falseRejects={data['falseRejects']} "
        f"precisionNoFalseAccept={data['precisionNoFalseAccept']}",
        "",
        "confusion (label -> prediction: count):",
    ]
    for label, row in data["confusion"].items():
        lines.append(f"  {label}: " + ", ".join(f"{k}={v}" for k, v in row.items()))
    lines.append("")
    lines.append("per-slice (claim kind):")
    for slice_name, row in data["perSlice"].items():
        lines.append(f"  {slice_name}: {row['correct']}/{row['total']}")
    if data["failures"]:
        lines.append("")
        lines.append("failures:")
        for failure in data["failures"]:
            lines.append(f"  {failure['caseId']}: label={failure['label']} predicted={failure['prediction']}")
    return "\n".join(lines)


def format_escalation_report(metrics: Any) -> str:
    data = metrics.to_dict()
    lines = [
        "",
        "Phase 5 escalation evaluation (source hierarchy + false-acceptance)",
        f"dataset={data['datasetVersion']} checksum={data['checksum']}",
        f"cases={data['total']} correct={data['correct']} accuracy={data['accuracy']}",
        f"precision={data['precision']} falseAccepts={data['falseAccepts']} "
        f"falseRejects={data['falseRejects']} tierCorrect={data['tierCorrect']}",
    ]
    if data["failures"]:
        lines.append("failures:")
        for failure in data["failures"]:
            lines.append(
                f"  {failure['caseId']}: expected={failure['expected']} "
                f"predicted={failure['predicted']} ({failure['reason']})"
            )
    return "\n".join(lines)


def format_nvda_report(metrics: Any) -> str:
    data = metrics.to_dict()
    lines = [
        "",
        "Phase 6 NVDA labeled regression (issuer-reported FY2024/FY2025)",
        f"dataset={data['datasetVersion']} checksum={data['checksum']}",
        f"cases={data['total']} correct={data['correct']} coverageAccuracy={data['coverageAccuracy']}",
        f"precision={data['precision']} falseAccepts={data['falseAccepts']} "
        f"falseRejects={data['falseRejects']} tierCompliant={data['tierCompliant']}",
    ]
    if data["failures"]:
        lines.append("failures:")
        for failure in data["failures"]:
            lines.append(
                f"  {failure['caseId']}: expected={failure['expected']} "
                f"predicted={failure['predicted']} ({failure['reason']})"
            )
    return "\n".join(lines)


def main() -> int:
    print(format_report(run_evaluation()))
    print(format_escalation_report(run_escalation_evaluation()))
    print(format_nvda_report(run_nvda_evaluation()))
    # All evaluations are informational; a false accept is the signal to watch.
    return 0


if __name__ == "__main__":
    sys.exit(main())
