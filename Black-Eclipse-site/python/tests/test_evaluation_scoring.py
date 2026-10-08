"""Statistics, scoring, thresholds and the failure taxonomy."""

from __future__ import annotations

from harness.evaluation.graders import GraderResult
from harness.evaluation.scoring import (
    DEFAULT_THRESHOLDS,
    EvaluationScore,
    Threshold,
    check_thresholds,
    score_trial,
    weighted_composite,
)
from harness.evaluation.stats import (
    FLAKY,
    STABLE_FAILURE,
    STABLE_PASS,
    UNMEASURED,
    aggregate_trials,
    classify_flakiness,
    pass_at_k,
    wilson_interval,
)
from harness.evaluation.taxonomy import classify_failure
from eval_helpers import make_task, make_trajectory, tool_call


def test_pass_at_k_estimator():
    assert pass_at_k(5, 0, 1) == 0.0
    assert pass_at_k(5, 5, 1) == 1.0
    assert pass_at_k(3, 1, 3) == 1.0  # n - c < k
    assert 0 < pass_at_k(5, 2, 3) < 1
    assert pass_at_k(0, 0, 1) is None


def test_wilson_interval_bounds():
    low, high = wilson_interval(5, 5)
    assert low is not None and high is not None and low < high <= 1.0
    assert wilson_interval(0, 0) == (None, None)


def test_flakiness_classification_repeated_trials():
    assert classify_flakiness([True, True, True]) == STABLE_PASS
    assert classify_flakiness([False, False]) == STABLE_FAILURE
    assert classify_flakiness([True, False, True, False]) == FLAKY
    assert classify_flakiness([]) == UNMEASURED


def test_aggregate_trials_reports_ci_and_variance():
    stats = aggregate_trials([True, True, False, True, False], k=3)
    assert stats.n == 5 and stats.successes == 3
    assert stats.flakiness == FLAKY
    assert stats.ci_low is not None and stats.ci_high is not None
    payload = stats.to_dict()
    assert payload["passRate"] == 0.6
    assert payload["passAtK"] is not None


def test_weighted_composite_guard_blocks_critical_failures():
    assert weighted_composite({"task_success": 0.5, "tool_accuracy": 1.0}) is None
    assert weighted_composite({"task_success": 1.0, "safety_score": 0.0}) is None
    assert weighted_composite({"task_success": 1.0, "safety_score": 1.0, "tool_accuracy": 1.0}) == 1.0


def test_score_trial_maps_dimensions_and_inverts_hallucination():
    task = make_task(category="adversarial")
    results = [
        GraderResult("tool", 0.9, True, details={}, failures=[]),
        GraderResult("hallucination", 0.8, True, details={}, failures=[]),
    ]
    score = score_trial(task, make_trajectory(metrics={"cost": 0.02, "totalTokens": 100}), results)
    assert score.dimensions["tool_accuracy"] == 0.9
    # hallucination grader score 0.8 => rate 0.2
    assert abs(score.dimensions["hallucination_rate"] - 0.2) < 1e-9
    assert score.passed is True


def test_score_trial_requires_at_least_one_measured_grader():
    task = make_task()
    unmeasured = [GraderResult("exact", 0.0, False, unmeasured=True, failures=["none"])]
    score = score_trial(task, make_trajectory(), unmeasured)
    assert score.passed is False
    assert score.unmeasured is True


def test_check_thresholds_names_failures():
    outcome = check_thresholds({"safety_score": 0.0, "hallucination_rate": 0.5, "task_success": 0.9})
    assert not outcome["passed"]
    assert any("safety_score" in f for f in outcome["failures"])
    assert any("hallucination_rate" in f for f in outcome["failures"])
    ok = check_thresholds({"safety_score": 1.0, "hallucination_rate": 0.0, "task_success": 0.0})
    assert ok["passed"]


def test_unmeasured_critical_dimension_is_unknown_not_a_failure():
    # A floor that was never exercised cannot be violated; it is reported UNKNOWN.
    outcome = check_thresholds({"safety_score": None, "hallucination_rate": 0.0, "task_success": 0.5})
    assert outcome["passed"]
    assert outcome["failures"] == []


def test_threshold_individual_evaluate():
    assert Threshold("x", minimum=1.0).evaluate(0.5) is not None
    assert Threshold("x", maximum=0.0).evaluate(0.2) is not None
    # An unmeasured value is UNKNOWN, not a violation.
    assert Threshold("x", minimum=1.0, critical=True).evaluate(None) is None
    assert Threshold("x", minimum=1.0).evaluate(1.0) is None


def test_taxonomy_labels_from_graders_and_events():
    results = [GraderResult("tool", 0.0, False, failures=["tool call a not found"])]
    labels = classify_failure(results, make_trajectory(), {"status": "completed"})
    assert "tool_selection" in labels and "tool_arguments" in labels

    events = tool_call("boom", {}, call_id="c1", status="failed", code="TOOL_ERROR")
    labels2 = classify_failure([], make_trajectory(tool_events=events), {"status": "completed"})
    assert "tool_execution" in labels2

    labels3 = classify_failure([], make_trajectory(status="timeout"), {"status": "timeout"})
    assert "timeout" in labels3
