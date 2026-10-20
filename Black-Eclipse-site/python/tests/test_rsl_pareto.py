"""v2 Pareto frontier: dominance is per measured objective, never invented."""

from __future__ import annotations

from harness.self_improvement.pareto import dominates, frontier, vector


def _metrics(**aggregates):
    return {"aggregates": dict(aggregates), "measuredTrials": 1}


def test_dominance_requires_no_worse_on_every_comparable_objective():
    strong = vector(_metrics(task_success=0.8, cost=0.5))
    weak = vector(_metrics(task_success=0.7, cost=0.8))
    assert dominates(strong, weak) is True
    assert dominates(weak, strong) is False


def test_a_tradeoff_is_not_dominance():
    cheap = vector(_metrics(task_success=0.8, cost=0.5))
    accurate = vector(_metrics(task_success=0.9, cost=0.9))
    assert dominates(cheap, accurate) is False
    assert dominates(accurate, cheap) is False


def test_missing_objective_is_neutral_not_zero():
    sparse = vector(_metrics(task_success=0.8))
    rich = vector(_metrics(task_success=0.7, cost=0.1))
    assert dominates(sparse, rich) is False
    assert dominates(rich, sparse) is False


def test_frontier_keeps_non_dominated_states_and_names_the_dominator():
    states = [
        {"id": "a", "metrics": _metrics(task_success=0.8, cost=0.5)},
        {"id": "b", "metrics": _metrics(task_success=0.7, cost=0.8)},
        {"id": "c", "metrics": _metrics(task_success=0.9, cost=0.9)},
    ]
    result = frontier(states)
    assert set(result["frontier"]) == {"a", "c"}
    assert result["dominated"] == {"b": "a"}
    assert result["objectives"]["cost"] == "min"
