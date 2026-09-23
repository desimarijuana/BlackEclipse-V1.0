"""Phase 5 — escalation evaluation set (source hierarchy + false-acceptance)."""

from __future__ import annotations

from harness.research.eval.escalation import (
    dataset_checksum,
    load_escalation_dataset,
    run_escalation_evaluation,
)


def test_dataset_versioned_and_checksummed():
    dataset = load_escalation_dataset()
    assert dataset["datasetVersion"]
    assert dataset["reviewed"] is True
    assert len(dataset_checksum(dataset)) == 32
    for case in dataset["cases"]:
        assert case["rationale"]


def test_no_false_accepts_on_escalation_set():
    """The safety property: no fabricated/unsupported web value is admitted."""
    metrics = run_escalation_evaluation()
    assert metrics.falseAccepts == 0
    assert metrics.total == 8


def test_metrics_report_precision_and_coverage():
    data = run_escalation_evaluation().to_dict()
    assert "precision" in data
    assert "accuracy" in data
    assert "tierCorrect" in data


def test_primary_and_secondary_tiers_distinguished():
    metrics = run_escalation_evaluation()
    # The accepted primary and secondary cases both label the correct evidence kind.
    assert metrics.tierCorrect >= 2
