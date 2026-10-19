"""Round 4 (W12) live tier — the NON-scripted team comparison, pinned offline.

These tests pin the live tier's plumbing without touching a provider: without
model settings every live trial is `unmeasured`; with settings the subtask runs
resolve the operator's REAL model through the production `build_chat_model`
path (a stub here), never the script seam's pool; and the comparison publishes
token/cost usage only when a variant's real trajectories reported it.

The opt-in live smoke (`HARNESS_TEAM_LIVE_IT=1`) is the only test allowed to
reach a provider — never in CI.
"""

from __future__ import annotations

import os

import pytest

from harness.evaluation.environments import build_environment
from harness.evaluation.experiments import multi_agent_compare
from harness.evaluation.runner import EvaluationRunner, ScriptedModel
from harness.evaluation.tasks import load_builtin_dataset
from harness.evaluation.team_benchmark import (
    LIVE_TEAM_INVOKER_NAME,
    LiveTeamAgentInvoker,
    _TEAM_MODELS,
    measured_usage,
)
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings


@pytest.fixture()
def store(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


def _task(task_id: str):
    return next(t for t in load_builtin_dataset("team_v1").tasks if t.id == task_id)


def _settings(model: str = "live-stub") -> ModelSettings:
    return ModelSettings(provider="ollama", model=model, base_url="http://localhost:11434/v1")


def test_the_live_invoker_has_its_own_recorded_name():
    assert LiveTeamAgentInvoker.name == LIVE_TEAM_INVOKER_NAME == "team-live"


@pytest.mark.asyncio
async def test_without_model_settings_the_live_team_is_unmeasured():
    task = _task("team.multi_leg_build.001")
    environment = build_environment(task.environment or {})
    environment.reset(task.initial_state or {})
    try:
        result = await LiveTeamAgentInvoker().invoke(task, "t0", environment)
    finally:
        environment.teardown()
    assert result.status == "unmeasured"
    assert "model settings" in (result.unmeasured_reason or "")


@pytest.mark.asyncio
async def test_a_live_team_trial_uses_the_real_model_path_and_no_script_pool(store, monkeypatch):
    """The non-scripted invoker resolves the operator's model settings through
    the production build path; the seam's pool is never active, and the tier
    grades the REAL state — a model that does no work cannot pass."""
    from harness import graph as graph_module

    seen: list[str] = []

    def _stub_build(settings):
        assert _TEAM_MODELS.get() is None, "a live trial must never carry a script pool"
        seen.append(str(getattr(settings, "model", "")))
        return ScriptedModel([{"type": "final", "content": "live stub: no tool work"}])

    monkeypatch.setattr(graph_module, "build_chat_model", _stub_build)
    task = _task("team.multi_leg_build.001")
    runner = EvaluationRunner(store, invoker=LiveTeamAgentInvoker(store, _settings()))
    result = await runner.run_task(task, trials=1, persist=False)
    trial = result.trials[0]

    assert not trial.unmeasured
    assert seen and set(seen) == {"live-stub"}
    assert trial.trajectory.model.get("scripted") is False
    assert trial.trajectory.model.get("model") == "live-stub"
    # No tool work happened; the state grader fails it — the tier grades what
    # really happened, never the model's claim.
    assert not trial.passed
    assert "alpha.py" not in (trial.env_state or {}).get("paths", {})


def test_measured_usage_is_none_until_a_real_trajectory_reports_it():
    class _Trajectory:
        def __init__(self, metrics):
            self.metrics = metrics

    class _Trial:
        def __init__(self, metrics, unmeasured=False):
            self.trajectory = _Trajectory(metrics)
            self.unmeasured = unmeasured

    class _Task:
        def __init__(self, trials):
            self.trials = trials

    class _Suite:
        def __init__(self, trials):
            self.tasks = [_Task(trials)]

    # The scripted tier reports 0 usage (no model ran): unpublished, never a
    # fabricated 0.
    assert measured_usage(_Suite([_Trial({"toolCalls": 3, "totalTokens": 0, "cost": 0.0})])) == {
        "totalTokens": None, "cost": None,
    }

    # A live suite's trajectories carry the provider-reported usage: summed.
    assert measured_usage(_Suite([
        _Trial({"toolCalls": 3, "totalTokens": 120, "cost": 0.004}),
        _Trial({"toolCalls": 4, "totalTokens": 80, "cost": 0.002}),
    ])) == {"totalTokens": 200, "cost": 0.006}

    # An unmeasured trial contributes nothing — never a derived 0.
    assert measured_usage(_Suite([_Trial({"totalTokens": 500, "cost": 1.0}, unmeasured=True)])) == {
        "totalTokens": None, "cost": None,
    }


@pytest.mark.asyncio
async def test_the_live_comparison_without_settings_decides_nothing(store):
    """The 'publish unmeasured without a provider' rule at the compare level."""
    task = _task("team.multi_leg_build.001")
    result = await multi_agent_compare(
        store, [task], trials=1, team_invoker=LiveTeamAgentInvoker(store),
    )
    assert result["team"]["invoker"] == LIVE_TEAM_INVOKER_NAME
    assert result["team"]["measured"] == 0
    assert result["adoption"]["adopted"] is False
    assert "unmeasured" in result["adoption"]["reason"]
    # The scripted single-agent variant still publishes no token/cost estimate.
    assert result["single"]["totalTokens"] is None
    assert result["single"]["cost"] is None
    assert result["unmeasured"] == ["cost", "token_usage"]


_LIVE = os.environ.get("HARNESS_TEAM_LIVE_IT") == "1"


@pytest.mark.skipif(
    not _LIVE,
    reason="opt-in live smoke: set HARNESS_TEAM_LIVE_IT=1 (needs a real provider)",
)
@pytest.mark.asyncio
async def test_live_team_comparison_through_a_real_provider(store):
    """The opt-in live smoke: REAL models, one frozen task, one trial.

    Never in CI. Configure with `HARNESS_TEAM_LIVE_PROVIDER` (default ollama),
    `HARNESS_TEAM_LIVE_MODEL` (default llama3.1), `HARNESS_TEAM_LIVE_BASE_URL`
    and `HARNESS_TEAM_LIVE_API_KEY` when the provider needs them. A small local
    model may fail the task — the tier grades real work either way; what must
    hold is that real model steps were consumed and the result is MEASURED.
    """
    settings = ModelSettings(
        provider=os.environ.get("HARNESS_TEAM_LIVE_PROVIDER", "ollama"),
        model=os.environ.get("HARNESS_TEAM_LIVE_MODEL", "llama3.1"),
        base_url=os.environ.get("HARNESS_TEAM_LIVE_BASE_URL") or None,
        api_key=os.environ.get("HARNESS_TEAM_LIVE_API_KEY") or None,
    )
    task = _task("team.multi_leg_build.001")
    runner = EvaluationRunner(store, invoker=LiveTeamAgentInvoker(store, settings))
    result = await runner.run_task(task, trials=1, persist=False)
    trial = result.trials[0]

    assert not trial.unmeasured, trial.unmeasured_reason
    assert trial.trajectory.model.get("model") == settings.model
    metrics = trial.trajectory.metrics or {}
    assert int(metrics.get("modelSteps") or 0) >= 1, (
        "a live trial that consumed no model steps did not reach the provider"
    )
