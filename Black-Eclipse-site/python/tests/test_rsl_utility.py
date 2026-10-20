"""Utility and acceptance: measured improvement, critical veto, honest UNMEASURED."""

from __future__ import annotations

from harness.self_improvement.utility import UtilityWeights, acceptance, utility


def _metrics(success, *, measured=10, successes=None, **extra):
    aggregates = {"task_success": success, **extra}
    if successes is not None:
        aggregates["successes"] = successes
        aggregates["sampleSize"] = measured
    return {"aggregates": aggregates, "measuredTrials": measured}


def test_utility_components_are_explainable():
    score = utility(
        _metrics(0.8, cost=2.0, latency=100.0),
        baseline=_metrics(0.8, cost=1.0, latency=100.0),
    )

    assert score["components"]["success"] == 0.8
    assert score["components"]["cost"] == 2.0
    assert score["components"]["latency"] == 1.0
    assert score["utility"] < 0.8
    assert score["unmeasured"] is False


def test_wilson_lower_bound_is_used_when_counts_exist():
    small = utility(_metrics(1.0, measured=1, successes=1))
    large = utility(_metrics(1.0, measured=100, successes=100))

    assert small["successSource"] == "wilson"
    assert small["components"]["success"] < large["components"]["success"]


def test_unmeasured_candidate_is_rejected():
    current = _metrics(0.8)
    candidate = {"aggregates": {"task_success": None}, "measuredTrials": 0}

    decision = acceptance(current, candidate)

    assert decision["accepted"] is False
    assert any("no measured trials" in reason for reason in decision["reasons"])


def test_critical_regression_vetoes_an_otherwise_better_candidate():
    current = _metrics(0.8, cost=1.0)
    candidate = _metrics(0.9, cost=1.0)
    candidate["aggregates"]["task_success"] = 0.70

    decision = acceptance(current, candidate, weights=UtilityWeights(minImprovement=-1.0))

    assert decision["accepted"] is False
    assert any("critical regression" in reason for reason in decision["reasons"])


def test_no_improvement_is_rejected():
    current = _metrics(0.8)
    candidate = _metrics(0.8)

    decision = acceptance(current, candidate)

    assert decision["accepted"] is False
    assert any("did not improve" in reason for reason in decision["reasons"])


def test_measured_improvement_is_accepted():
    current = _metrics(0.70)
    candidate = _metrics(0.80)

    decision = acceptance(current, candidate)

    assert decision["accepted"] is True
    assert decision["improvement"] > 0
    assert decision["reasons"] == []
