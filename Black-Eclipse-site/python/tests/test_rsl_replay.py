"""Replay selection and the forgetting gate."""

from __future__ import annotations

from types import SimpleNamespace

from harness.evaluation.tasks import Dataset, EvaluationTask
from harness.self_improvement.replay import (
    ReplaySuite,
    best_known,
    build_replay_suite,
    critical_task_ids,
    forgetting,
    replay_gate,
    task_rates,
)


def _task(task_id, *, category="core", split="validation", **metadata):
    return EvaluationTask(
        id=task_id,
        name=task_id,
        description="",
        category=category,
        difficulty="easy",
        input={"prompt": task_id},
        metadata={"split": split, **metadata},
    )


def test_replay_suite_excludes_optimization_and_dedupes():
    dataset = Dataset(
        name="fixture", version="1",
        tasks=[
            _task("val", split="validation"),
            _task("held", split="held_out"),
            _task("release", split="release"),
            _task("opt", split="optimization"),
        ],
    )

    suite = build_replay_suite(dataset=dataset, extra_tasks=[_task("val")])

    assert isinstance(suite, ReplaySuite)
    assert suite.taskIds == ("held", "release", "val")
    assert suite.checksum


def test_critical_tasks_include_safety_and_explicit_critical():
    tasks = [
        _task("safe", category="safety"),
        _task("adv", category="adversarial"),
        _task("marked", critical=True),
        _task("normal"),
    ]

    assert critical_task_ids(tasks) == ("adv", "marked", "safe")


def test_forgetting_counts_missing_tasks_as_a_full_drop():
    result = forgetting(
        {"a": 1.0, "b": 1.0},
        {"a": 1.0},
        critical_tasks=["b"],
    )

    assert result["mean"] == 0.5
    assert result["drops"] == {"b": 1.0}
    assert result["criticalDrops"] == {"b": 1.0}


def test_replay_gate_rejects_critical_forgetting():
    gate = replay_gate(
        {"safe": 1.0, "normal": 1.0},
        {"safe": 0.0, "normal": 1.0},
        critical_tasks=["safe"],
    )

    assert gate["passed"] is False
    assert "critical" in gate["reason"]


def test_replay_gate_rejects_mean_forgetting_above_threshold():
    gate = replay_gate(
        {"a": 1.0, "b": 1.0, "c": 1.0},
        {"a": 0.8, "b": 0.8, "c": 0.8},
        max_forgetting=0.05,
    )

    assert gate["passed"] is False
    assert "forgetting" in gate["reason"]


def test_replay_gate_passes_when_nothing_is_forgotten():
    gate = replay_gate({"a": 1.0, "b": 1.0}, {"a": 1.0, "b": 1.0})

    assert gate["passed"] is True
    assert gate["forgetting"]["mean"] == 0.0


def test_replay_gate_is_unmeasured_without_a_baseline():
    gate = replay_gate({}, {"a": 1.0})

    assert gate["passed"] is False
    assert gate["status"] == "unmeasured"

    optional = replay_gate({}, {"a": 1.0}, require_baseline=False)
    assert optional["passed"] is True
    assert optional["status"] == "no_baseline"


def test_best_known_retains_the_highest_rate():
    assert best_known({"a": 1.0, "b": 0.5}, {"a": 0.0, "b": 0.8}) == {
        "a": 1.0, "b": 0.8,
    }


def test_task_rates_uses_measured_trials_only():
    task = _task("a")
    suite = SimpleNamespace(tasks=[
        SimpleNamespace(
            task=task,
            trials=[
                SimpleNamespace(passed=True, unmeasured=False),
                SimpleNamespace(passed=False, unmeasured=False),
                SimpleNamespace(passed=True, unmeasured=True),
            ],
        ),
        SimpleNamespace(
            task=_task("unmeasured"),
            trials=[SimpleNamespace(passed=False, unmeasured=True)],
        ),
    ])

    assert task_rates(suite) == {"a": 0.5}
    assert task_rates({"a": 1, "bad": "x"}) == {"a": 1.0}
