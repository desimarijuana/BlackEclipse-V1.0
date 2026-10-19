"""Round 4 (W12) — multi-agent orchestration, adopted only where measured.

The team / A2A / task layers already existed; W12 adds the EVIDENCE. These tests
pin the comparison harness: a multi-step build is run BOTH ways on the SAME
frozen task — one agent, and a 2-3 specialist team — through the REAL runtime,
graded on the REAL resulting state, and the adoption verdict is computed strictly
from the measurements (ADR-H213).

The decisive property: the benchmark grades what actually happened. A team run
that CLAIMS completion while a subtask's work never happened FAILS the state
grader; a measured gain that does not exist is never adopted.
"""

from __future__ import annotations

import copy

import pytest

from harness.evaluation.environments import build_environment
from harness.evaluation.experiments import multi_agent_compare
from harness.evaluation.runner import EvaluationRunner
from harness.evaluation.tasks import load_builtin_dataset
from harness.evaluation.team_benchmark import (
    TeamAgentInvoker,
    adoption_verdict,
    variant_axes,
)
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


def _team_tasks():
    return load_builtin_dataset("team_v1").tasks


def _task(task_id: str):
    return next(task for task in _team_tasks() if task.id == task_id)


def _axes(success, wall_ms, tool_calls, *, measured: int = 2) -> dict:
    return {
        "taskSuccess": success, "wallMs": wall_ms, "toolCalls": tool_calls,
        "measured": measured, "modelSteps": 0, "trials": measured, "failures": 0,
    }


def test_the_frozen_set_declares_both_variants():
    dataset = load_builtin_dataset("team_v1")
    assert len(dataset.tasks) == 2
    for task in dataset.tasks:
        assert task.agent_script, task.id
        spec = TeamAgentInvoker.team_spec(task)
        assert spec is not None, task.id
        assert 2 <= len(spec["members"]) <= 3, task.id
        assert spec["subtasks"], task.id
        for subtask in spec["subtasks"]:
            assert subtask["id"] in spec["scripts"], (task.id, subtask["id"])


@pytest.mark.asyncio
async def test_the_team_run_is_the_real_stack_and_grades_real_state(store):
    task = _task("team.multi_leg_build.001")
    runner = EvaluationRunner(store, invoker=TeamAgentInvoker(store))
    result = await runner.run_task(task, trials=1, persist=False)
    trial = result.trials[0]

    assert trial.status == "completed"
    assert trial.passed, trial.score.grader_results
    assert set(trial.env_state["paths"]) == {"alpha.py", "beta.py", "report.txt"}

    # The aggregated trajectory proves the child runs really executed the tools
    # (and the registry-bound argument capture folded their args back in).
    calls = trial.trajectory.tool_calls()
    assert [c["name"] for c in calls].count("eval_fs_write") == 3
    assert [c["name"] for c in calls].count("eval_run") == 2
    assert all(c["args"] for c in calls), calls


@pytest.mark.asyncio
async def test_two_team_trials_see_isolated_worlds(store):
    task = _task("team.verified_fix.001")
    runner = EvaluationRunner(store, invoker=TeamAgentInvoker(store))
    first = await runner.run_task(task, trials=1, persist=False)
    second = await runner.run_task(task, trials=1, persist=False)
    assert first.trials[0].passed, first.trials[0].score.grader_results
    assert second.trials[0].passed, second.trials[0].score.grader_results
    assert set(first.trials[0].env_state["paths"]) == {"calc.py", "VERIFIED.txt"}
    assert set(second.trials[0].env_state["paths"]) == {"calc.py", "VERIFIED.txt"}


@pytest.mark.asyncio
async def test_concurrent_team_trials_do_not_share_model_scripts(store):
    from harness.evaluation.config import EvaluationConfig

    runner = EvaluationRunner(
        store, invoker=TeamAgentInvoker(store),
        config=EvaluationConfig.from_env({"max_concurrency": 2}),
    )
    suite = await runner.run_suite(_team_tasks(), trials=1, persist=False, concurrency=2)
    assert suite.aggregates["task_success"] == 1.0, suite.failures


@pytest.mark.asyncio
async def test_a_team_that_claims_done_without_the_work_fails_the_grader(store, monkeypatch):
    """The restored defect: the decomposed build silently drops one leg while the
    team still reports COMPLETED. The suite must fail on the REAL state, not the
    team's own status."""
    original = TeamAgentInvoker._definition

    def _drop_alpha(self, task, spec):
        if "alpha" not in spec.get("scripts", {}):
            return original(self, task, spec)
        broken = copy.deepcopy(spec)
        broken["subtasks"] = [s for s in broken["subtasks"] if s["id"] != "alpha"]
        for subtask in broken["subtasks"]:
            subtask["dependsOn"] = [
                dep for dep in subtask.get("dependsOn") or [] if dep != "alpha"
            ]
        return original(self, task, broken)

    monkeypatch.setattr(TeamAgentInvoker, "_definition", _drop_alpha)
    task = _task("team.multi_leg_build.001")
    runner = EvaluationRunner(store, invoker=TeamAgentInvoker(store))
    result = await runner.run_task(task, trials=1, persist=False)
    trial = result.trials[0]

    assert not trial.passed
    assert "alpha.py" not in trial.env_state["paths"]
    failures = [
        message
        for grader in trial.score.grader_results if grader.get("grader") == "state"
        for message in (grader.get("failures") or [])
    ]
    assert any("alpha.py" in message for message in failures), trial.score.grader_results


@pytest.mark.asyncio
async def test_a_task_without_a_decomposition_is_unmeasured():
    task = load_builtin_dataset("benchmark_v1").tasks[0]
    environment = build_environment(task.environment or {})
    environment.reset(task.initial_state or {})
    try:
        result = await TeamAgentInvoker().invoke(task, "t0", environment)
    finally:
        environment.teardown()
    assert result.status == "unmeasured"
    assert "no team decomposition" in (result.unmeasured_reason or "")


@pytest.mark.asyncio
async def test_the_comparison_records_both_variants_and_an_honest_verdict(store):
    result = await multi_agent_compare(store, _team_tasks(), trials=1, persist=True)

    assert result["single"]["measured"] == 2
    assert result["team"]["measured"] == 2
    assert result["single"]["taskSuccess"] == 1.0, result["single"]
    assert result["team"]["taskSuccess"] == 1.0, result["team"]
    # The team does the same work split across child runs: the aggregate call
    # count is measured from the REAL trajectories, not from a script's length.
    assert result["single"]["toolCalls"] == 9, result["single"]
    assert result["team"]["toolCalls"] == 10, result["team"]

    comparison = result["comparison"]
    assert comparison["passRateDelta"] == 0.0
    assert comparison["deltas"]["task_success"] == 0.0

    adoption = result["adoption"]
    assert isinstance(adoption["adopted"], bool)
    assert adoption["reason"]
    assert adoption["axes"]["quality"] == {"single": 1.0, "team": 1.0}
    if not adoption["adopted"]:
        assert "no measured gain" in adoption["reason"] or "quality regression" in adoption["reason"]

    # Tokens/cost are not reported by the scripted tier — published as unmeasured.
    assert result["unmeasured"] == ["cost", "token_usage"]
    assert "never estimated" in result["unmeasuredReason"]

    # "Recorded with the frozen-set results": both variants' metrics are durable.
    from harness.evaluation.store import EvaluationStore

    eval_store = EvaluationStore(store)
    single_rows = eval_store.list_model_results(run_id=result["single"]["runId"])
    team_rows = eval_store.list_model_results(run_id=result["team"]["runId"])
    assert single_rows and single_rows[0]["model"] == "single-agent"
    assert team_rows and team_rows[0]["model"] == "team-agents"
    assert team_rows[0]["metrics"]["taskSuccess"] == 1.0


def test_variant_axes_sum_the_real_trajectories():
    class _Trajectory:
        metrics = {"toolCalls": 3, "modelSteps": 4, "toolErrors": 1}

    class _Trial:
        unmeasured = False
        trajectory = _Trajectory()

    class _Task:
        trials = [_Trial()]

    class _Suite:
        tasks = [_Task()]
        aggregates = {"task_success": 1.0}
        failures = []

    axes = variant_axes(_Suite(), wall_ms=123)
    assert axes == {
        "taskSuccess": 1.0, "trials": 1, "measured": 1, "wallMs": 123,
        "toolCalls": 3, "modelSteps": 4, "toolErrors": 1, "failures": 0,
    }


def test_a_quality_regression_is_never_adopted():
    verdict = adoption_verdict(_axes(1.0, 1000, 10), _axes(0.5, 100, 2))
    assert not verdict["adopted"]
    assert "quality regression" in verdict["reason"]


def test_a_measured_latency_gain_adopts():
    verdict = adoption_verdict(_axes(1.0, 1000, 10), _axes(1.0, 700, 10))
    assert verdict["adopted"]
    assert "wall clock improved" in verdict["reason"]
    assert verdict["axes"]["latency"]["improvement"] == 0.3


def test_a_measured_tool_call_gain_adopts():
    verdict = adoption_verdict(_axes(1.0, 1000, 10), _axes(1.0, 1100, 8))
    assert verdict["adopted"]
    assert "tool calls fell by 2" in verdict["reason"]


def test_overhead_without_a_gain_is_not_adopted():
    verdict = adoption_verdict(_axes(1.0, 1000, 10), _axes(1.0, 1300, 12))
    assert not verdict["adopted"]
    assert "no measured gain" in verdict["reason"]
    assert verdict["axes"]["cost"]["delta"] == -2


def test_an_unmeasured_variant_decides_nothing():
    verdict = adoption_verdict(_axes(1.0, 1000, 10), _axes(None, 100, 2, measured=0))
    assert not verdict["adopted"]
    assert "unmeasured" in verdict["reason"]
