"""Contradiction-detection baseline (Phase 1) — the labeled set and its metrics.

This locks in the evaluation harness and records the baseline before the Phase 2
normalization work. The *contract* asserted here is the safety floor (scope
isolation, no unauthorized/automatic-over-explicit supersede, unrelated-memory
safety). Recall/confirmation are floors that improve over time; the exact
baseline numbers are recorded in
`docs/harness/memory-contradiction-detection.md`.
"""

from __future__ import annotations

from harness.eclipse_memory.eval.contradictions import (
    CONTRADICTION_THRESHOLDS,
    check_contradiction_thresholds,
    format_contradiction_report,
    load_contradiction_dataset,
    run_contradiction_evaluation,
)


def test_contradiction_dataset_is_versioned_and_has_all_kinds():
    dataset = load_contradiction_dataset()
    assert dataset["name"] == "memory-contradictions"
    assert dataset["version"] >= 1
    kinds = {case["kind"] for case in dataset["cases"]}
    for required in (
        "direct-polarity", "paraphrase-conflict", "confirmation", "unrelated",
        "different-subject", "different-scope", "temporary",
        "observation-vs-preference", "replacement", "ambiguous", "authority",
    ):
        assert required in kinds, required


def test_baseline_safety_is_absolute():
    report = run_contradiction_evaluation()
    metrics = report["metrics"]
    # These must never regress, at any detector setting.
    assert metrics["scopeIsolation"] == 1.0
    assert metrics["unrelatedMemorySafety"] == 1.0
    assert metrics["unauthorizedSupersessions"] == 0


def test_report_is_formattable():
    report = run_contradiction_evaluation()
    text = format_contradiction_report(report)
    assert "contradictionRecall" in text


def test_thresholds_are_declared():
    # Safety thresholds are absolute; recall/confirmation are floors.
    assert CONTRADICTION_THRESHOLDS["falseConflictRate"] == 0.0
    assert CONTRADICTION_THRESHOLDS["unauthorizedSupersessions"] == 0
    assert CONTRADICTION_THRESHOLDS["confirmationAccuracy"] == 1.0
    assert CONTRADICTION_THRESHOLDS["contradictionRecall"] > 0.0


def test_gate_reports_failures_without_raising():
    report = run_contradiction_evaluation()
    # A report with a forced unsafe metric must fail the gate, never raise.
    metrics = dict(report["metrics"])
    metrics["unauthorizedSupersessions"] = 1
    gate = check_contradiction_thresholds({**report, "metrics": metrics})
    assert gate["passed"] is False
    assert any("unauthorizedSupersessions" in f for f in gate["failures"])
