"""Paired bootstrap, McNemar and the sample-size planning aid."""

from __future__ import annotations

from harness.evaluation.significance import (
    mcnemar,
    paired_bootstrap,
    paired_rates,
    required_trials,
)


def _rates(value: float, count: int = 20) -> dict[str, float]:
    return {f"t{index}": value for index in range(count)}


def test_paired_bootstrap_finds_a_real_lift():
    result = paired_bootstrap(_rates(0.5), _rates(1.0), n=2000, seed=3)
    assert result["pairedTasks"] == 20
    assert result["delta"] == 0.5
    assert result["ciLow"] > 0
    assert result["pValue"] == 0.0
    assert result["insufficient"] is False


def test_paired_bootstrap_is_seed_deterministic():
    first = paired_bootstrap(_rates(0.4), _rates(0.7), n=500, seed=9)
    second = paired_bootstrap(_rates(0.4), _rates(0.7), n=500, seed=9)
    assert first == second
    assert first["ciLow"] <= first["delta"] <= first["ciHigh"]


def test_paired_bootstrap_needs_two_paired_tasks():
    result = paired_bootstrap({"a": 0.5}, {"a": 1.0})
    assert result["insufficient"] is True
    assert result["ciLow"] is None
    assert result["pairedTasks"] == 1


def test_paired_rates_reads_a_suite_result():
    class _Trial:
        def __init__(self, passed, unmeasured=False):
            self.passed = passed
            self.unmeasured = unmeasured

    class _Task:
        def __init__(self, task_id):
            self.id = task_id

    class _TaskResult:
        def __init__(self, task_id, trials):
            self.task = _Task(task_id)
            self.trials = trials

    class _Suite:
        def __init__(self):
            self.tasks = [
                _TaskResult("a", [_Trial(True), _Trial(False)]),
                _TaskResult("b", [_Trial(True), _Trial(True)]),
                _TaskResult("c", [_Trial(True, unmeasured=True)]),
            ]

    assert paired_rates(_Suite()) == {"a": 0.5, "b": 1.0}


def test_mcnemar_exact_and_empty():
    assert mcnemar({}, {})["pValue"] == 1.0
    result = mcnemar(
        {"a": False, "b": False, "c": True},
        {"a": True, "b": True, "c": True},
    )
    assert result["candidateOnlyPass"] == 2
    assert result["baseOnlyPass"] == 0
    assert result["discordant"] == 2
    assert result["method"] == "exact"


def test_required_trials_is_a_planning_estimate():
    assert required_trials(0.1) is not None
    assert required_trials(0.1) > 300
    assert required_trials(0.0) is None
