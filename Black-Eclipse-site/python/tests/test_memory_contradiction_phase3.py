"""Phase 3 (final hardening) — expanded contradiction/paraphrase evaluation.

Proves the labeled set now covers paraphrase, negation, numeric-value,
subject-alias and temporal cases, that the required metrics exist and the release
gate passes, and that the deterministic safety floors are unchanged. Semantic
candidates cannot authorize a write.
"""

from __future__ import annotations

from harness.eclipse_memory.eval.contradictions import (
    CONTRADICTION_MAX_THRESHOLDS,
    CONTRADICTION_THRESHOLDS,
    check_contradiction_thresholds,
    format_contradiction_report,
    load_contradiction_dataset,
    run_contradiction_evaluation,
)


def test_dataset_covers_all_required_kinds():
    dataset = load_contradiction_dataset()
    assert dataset["version"] >= 2
    kinds = {case["kind"] for case in dataset["cases"]}
    for required in (
        "paraphrase-conflict", "negation", "numeric-value", "subject-alias",
        "temporal",
    ):
        assert required in kinds, required


def test_required_metrics_are_reported():
    metrics = run_contradiction_evaluation()["metrics"]
    for key in (
        "contradictionRecall", "missedConflictRate", "falseConflictRate",
        "confirmationAccuracy", "scopeLeakage", "forbiddenHits",
        "unauthorizedSupersessions", "conflictPrecision",
    ):
        assert key in metrics, key


def test_safety_floors_unchanged():
    metrics = run_contradiction_evaluation()["metrics"]
    assert metrics["scopeLeakage"] == 0
    assert metrics["forbiddenHits"] == 0
    assert metrics["falseConflictRate"] == 0.0
    assert metrics["unauthorizedSupersessions"] == 0


def test_release_gate_passes():
    report = run_contradiction_evaluation()
    gate = check_contradiction_thresholds(report)
    assert gate["passed"] is True, gate["failures"]


def test_max_threshold_fails_when_exceeded():
    report = run_contradiction_evaluation()
    metrics = dict(report["metrics"])
    metrics["missedConflictRate"] = 0.99
    gate = check_contradiction_thresholds({**report, "metrics": metrics})
    assert gate["passed"] is False
    assert any("missedConflictRate" in f for f in gate["failures"])
    assert CONTRADICTION_MAX_THRESHOLDS["missedConflictRate"] < 0.99


def test_thresholds_declare_absolute_safety():
    assert CONTRADICTION_THRESHOLDS["scopeLeakage"] == 0.0
    assert CONTRADICTION_THRESHOLDS["forbiddenHits"] == 0
    assert CONTRADICTION_THRESHOLDS["falseConflictRate"] == 0.0


def test_report_explains_when_semantics_are_useful():
    report = run_contradiction_evaluation()
    interpretation = report["interpretation"]
    assert "lexicalMisses" in interpretation
    assert "deepMisses" in interpretation
    # The report never claims semantic auto-resolution is safe.
    assert "auto" in interpretation["semanticNotUsefulFor"].lower()
    text = format_contradiction_report(report)
    assert "interpretation" in text


def test_every_case_has_an_explanation():
    report = run_contradiction_evaluation()
    assert all(case.get("explanation") for case in report["cases"])
    # An uncertain conflict is explained as needing review, preferring a visible
    # review over an unsafe replacement.
    proposed = [c for c in report["cases"] if c["actual"] == "propose"]
    assert proposed and all("review" in c["explanation"].lower() for c in proposed)
