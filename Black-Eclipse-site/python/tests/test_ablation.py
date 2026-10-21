"""Three-arm ablation: projection, comparison and report rendering."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from harness.evaluation.ablation import (
    AblationArm,
    arm_evidence,
    compare_arms,
    load_snapshot,
    run_ablation,
)
from harness.evaluation.candidate_invoker import CandidateAgentInvoker, SnapshotError
from harness.self_improvement.models import HarnessSnapshot


def _trial(passed: bool, *, unmeasured: bool = False, cost=None, latency=None):
    return SimpleNamespace(
        passed=passed,
        unmeasured=unmeasured,
        score=SimpleNamespace(cost=cost, latency_ms=latency),
    )


def _suite(
    *, run_id: str, task_success: float, tasks: list[tuple[str, str, list]],
    categories: dict | None = None,
):
    task_results = [
        SimpleNamespace(
            task=SimpleNamespace(id=task_id, category=category),
            trials=trials,
        )
        for task_id, category, trials in tasks
    ]
    measured = [trial for _, _, trials in tasks for trial in trials if not trial.unmeasured]
    passed = sum(1 for trial in measured if trial.passed)
    return SimpleNamespace(
        run_id=run_id,
        aggregates={
            "task_success": task_success,
            "safety_score": 1.0 if passed else 0.0,
        },
        categories=categories or {},
        tasks=task_results,
    )


def test_arm_evidence_keeps_unmeasured_and_costs_separate():
    suite = _suite(
        run_id="run-1",
        task_success=0.5,
        tasks=[
            ("t1", "safety", [_trial(True, cost=0.10, latency=100)]),
            ("t2", "core", [_trial(False, cost=None, latency=200)]),
            ("t3", "core", [_trial(False, unmeasured=True)]),
        ],
    )
    evidence = arm_evidence(suite, "baseline")
    assert evidence.successes == 1
    assert evidence.measured_trials == 2
    assert evidence.total_trials == 3
    assert evidence.task_rates == {"t1": 1.0, "t2": 0.0}
    assert evidence.cost_usd == 0.10
    assert evidence.latency_ms == 150.0


def test_a_critical_regression_vetoes_an_otherwise_improved_arm():
    baseline = _suite(
        run_id="b", task_success=0.5,
        tasks=[("safe", "safety", [_trial(True)]), ("core", "core", [_trial(False)])],
    )
    candidate = _suite(
        run_id="c", task_success=1.0,
        tasks=[("safe", "safety", [_trial(False)]), ("core", "core", [_trial(True)])],
    )
    arms = [arm_evidence(baseline, "baseline"), arm_evidence(candidate, "surface")]
    comparisons = compare_arms(arms)
    assert comparisons["surface"]["delta"] == 0.5
    assert comparisons["surface"]["verdict"] == "vetoed"
    assert comparisons["surface"]["criticalRegressions"] == ["safe"]


def test_a_measured_gain_is_improved():
    baseline = _suite(
        run_id="b", task_success=0.5,
        tasks=[("a", "core", [_trial(True)]), ("b", "core", [_trial(False)])],
    )
    candidate = _suite(
        run_id="c", task_success=1.0,
        tasks=[("a", "core", [_trial(True)]), ("b", "core", [_trial(True)])],
    )
    comparisons = compare_arms([
        arm_evidence(baseline, "baseline"), arm_evidence(candidate, "surface"),
    ])
    assert comparisons["surface"]["verdict"] == "improved"
    assert comparisons["surface"]["criticalRegressions"] == []


class _Task:
    def __init__(self, task_id: str) -> None:
        self.id = task_id
        self.category = "core"
        self.name = task_id

    def to_dict(self):
        return {"id": self.id, "category": self.category}


class _FakeRunner:
    def __init__(self, arm: str) -> None:
        self.arm = arm

    async def run_suite(self, tasks, **kwargs):
        failed = self.arm == "surface"
        return _suite(
            run_id=f"run-{self.arm}",
            task_success=0.0 if failed else 1.0,
            tasks=[("t1", "core", [_trial(not failed)])],
        )


@pytest.mark.asyncio
async def test_run_ablation_runs_every_arm_and_compares():
    snapshot = HarnessSnapshot(systemPrompt="Do the task.")
    report = await run_ablation(
        store=None,
        tasks=[_Task("t1")],
        arms=[
            AblationArm(name="baseline", snapshot=snapshot),
            AblationArm(name="surface", snapshot=snapshot),
        ],
        dataset_name="fixture",
        dataset_version="1",
        runner_factory=lambda arm: _FakeRunner(arm.name),
    )
    assert [arm.arm for arm in report.arms] == ["baseline", "surface"]
    assert report.comparisons["surface"]["verdict"] == "regressed"
    assert "task success" in report.to_markdown()


def test_live_candidate_requires_explicit_model_settings():
    snapshot = HarnessSnapshot(systemPrompt="Follow the task.")
    with pytest.raises(SnapshotError):
        CandidateAgentInvoker(
            None, snapshot, base=snapshot, live=True, model_settings=None,
        )


def test_snapshot_json_round_trips(tmp_path):
    snapshot = HarnessSnapshot(systemPrompt="Follow the task.", maxSteps=4)
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot.to_dict()), encoding="utf-8")
    loaded = load_snapshot(str(path))
    assert loaded.sourceDigest == snapshot.sourceDigest
