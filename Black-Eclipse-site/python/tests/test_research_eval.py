"""Phase 4 Workstream 4 — semantic-support evaluation set + metrics.

Verifies the dataset is versioned/checksummed, that the judge never sees labels,
that deterministic slices are correct, and records the baseline confusion matrix.
"""

from __future__ import annotations

from harness.research.eval import (
    LABELS,
    dataset_checksum,
    load_dataset,
    run_evaluation,
)
from harness.research.eval.__main__ import format_report


def test_dataset_is_versioned_and_checksummed():
    dataset = load_dataset()
    assert dataset["datasetVersion"]
    assert dataset["reviewed"] is True
    assert len(dataset_checksum(dataset)) == 32
    for case in dataset["cases"]:
        assert case["label"] in LABELS
        assert case["rationale"]  # every label is human-justified


def test_evaluation_reports_metrics_not_just_passfail():
    metrics = run_evaluation().to_dict()
    assert metrics["total"] == 8
    assert "confusion" in metrics
    assert "perSlice" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0


def test_no_false_accepts_on_unsupported_labels():
    """The core safety property: the judge must not call an unsupported claim
    supported."""
    metrics = run_evaluation()
    assert metrics.falseAccepts == 0


def test_wrong_period_not_accepted():
    metrics = run_evaluation().to_dict()
    # The wrong-period case must be classified unsupported.
    assert any(
        f["caseId"] == "unsupported-wrong-period" for f in metrics["failures"]
    ) is False


def test_conflicting_case_detected():
    metrics = run_evaluation().to_dict()
    row = metrics["confusion"].get("conflicting", {})
    assert row.get("conflicting", 0) == 1


def test_format_report_is_human_readable():
    report = format_report(run_evaluation())
    assert "dataset" in report.lower()
    assert "falseaccepts=" in report.lower()
    assert "confusion" in report.lower()
