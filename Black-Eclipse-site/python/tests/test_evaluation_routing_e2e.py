"""Round 4 (W3.2) — the end-to-end routing tier.

The W3.1 benchmark gates the classifier directly. These tests pin the second,
stronger tier: the SAME scenarios run through the REAL `execute_run` graph with
the REAL `ui_*` tools, the real catalog and the real durable task runtime, and
are graded on the REAL resulting state. A regression in the escalation path
(a witness-less Compose that refuses, or a false escalation) must FAIL the tier.
"""

from __future__ import annotations

import pytest

from harness.evaluation.runner import EvaluationRunner, ScriptedAgentInvoker, _build_registry
from harness.evaluation.tasks import load_builtin_dataset
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    runner = EvaluationRunner(store, invoker=ScriptedAgentInvoker(store))
    yield {"store": store, "runner": runner}
    store.close()


def _task(dataset, task_id):
    return next(t for t in dataset.tasks if t.id == task_id)


async def _run(env, task):
    result = await env["runner"].run_task(task, trials=1, persist=False)
    return result.trials[0]


def test_the_registry_exposes_the_ui_and_task_families():
    registry = _build_registry()
    names = set(registry.names())
    assert {"ui_classify_request", "ui_start_engineering", "create_goal", "create_task"} <= names


@pytest.mark.asyncio
async def test_ribbon_escalates_through_the_real_graph(env):
    dataset = load_builtin_dataset("routing_e2e_v1")
    trial = await _run(env, _task(dataset, "routing_e2e.ribbon_escalates.001"))
    assert trial.passed, trial.score.grader_results
    ui = trial.env_state["ui"]
    assert ui["engineeringTaskCount"] == 1
    created = ui["engineeringTasks"][0]
    assert created["capabilityGap"] is True
    assert created["kind"] == "ui-engineering"
    assert created["acceptanceCount"] == 4


@pytest.mark.asyncio
async def test_compose_scenarios_create_no_engineering_task(env):
    dataset = load_builtin_dataset("routing_e2e_v1")
    for task_id in (
        "routing_e2e.layout_composes.001",
        "routing_e2e.generic_widget_composes.001",
    ):
        trial = await _run(env, _task(dataset, task_id))
        assert trial.passed, (task_id, trial.score.grader_results)
        assert trial.env_state["ui"]["engineeringTaskCount"] == 0


@pytest.mark.asyncio
async def test_a_new_widget_escalates_without_a_capability_gap(env):
    dataset = load_builtin_dataset("routing_e2e_v1")
    trial = await _run(env, _task(dataset, "routing_e2e.new_widget_engineers.001"))
    assert trial.passed, trial.score.grader_results
    created = trial.env_state["ui"]["engineeringTasks"][0]
    assert created["capabilityGap"] is False


@pytest.mark.asyncio
async def test_a_misroute_regression_fails_the_tier(env, monkeypatch):
    """The release-gate property: restore the pre-W0 defect (a witness-less
    Compose verdict AND no catalog re-check) and the ribbon scenario FAILS on the
    real resulting state (no engineering task created)."""
    from harness.ui import engineering as engineering_module
    from harness.ui.service import UiService

    class _NoGap:
        capability_gap = False
        reason = "forced compose for the regression test"
        matched_components: list = []

    def _compose(self, text, *, blueprint_id=None, owner_id=None):
        return {
            "mode": "compose", "capabilityGap": False,
            "reasons": ["forced compose for the regression test"],
            "matchedComponents": [], "suggestedTools": [],
        }

    monkeypatch.setattr(UiService, "classify_request", _compose)
    monkeypatch.setattr(
        engineering_module, "assess_capability", lambda text, catalog=None: _NoGap()
    )
    dataset = load_builtin_dataset("routing_e2e_v1")
    trial = await _run(env, _task(dataset, "routing_e2e.ribbon_escalates.001"))
    assert not trial.passed
    failures = [
        f for g in trial.score.grader_results if g.get("grader") == "state"
        for f in (g.get("failures") or [])
    ]
    assert failures, trial.score.grader_results
    assert trial.env_state["ui"]["engineeringTaskCount"] == 0


@pytest.mark.asyncio
async def test_trials_are_isolated_from_each_other(env):
    """The shared trace store must not leak one trial's durable work into the
    next trial's graded state (the delta is what a trial did)."""
    dataset = load_builtin_dataset("routing_e2e_v1")
    first = await _run(env, _task(dataset, "routing_e2e.ribbon_escalates.001"))
    assert first.passed
    second = await _run(env, _task(dataset, "routing_e2e.layout_composes.001"))
    assert second.passed, second.score.grader_results
    assert second.env_state["ui"]["engineeringTaskCount"] == 0
