"""Tests for the auto-run: the policy, the budget and the loop.

The point of these tests is the SAFETY, not the convenience: a project that
acts on its own must be off by default, must only run compute tools, and must
stop when its budget is spent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.projects import ProjectStore
from harness.projects.auto import tick_projects
from harness.projects.policy import (
    AUTO_RUNNABLE_TOOLS,
    AutoRunStore,
)
from harness.tools import ToolResult


@pytest.fixture()
def stores(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ProjectStore(ams), AutoRunStore(ams)


def _ok(experiment_id="exp_new"):
    return ToolResult(tool_call_id="c1", name="run_backtest", ok=True,
                      text="Backtest complete",
                      data={"status": "OK", "experimentId": experiment_id})


class _Registry:
    def __init__(self, result=None, names=AUTO_RUNNABLE_TOOLS) -> None:
        self.result = result or _ok()
        self._names = tuple(names)
        self.calls: list[tuple[str, dict]] = []

    def names(self):
        return list(self._names)

    async def execute(self, name, call_id, arguments, ctx, **_kw):
        self.calls.append((name, dict(arguments)))
        return self.result


def _ctx(project_store, policy_store, registry, quant_store=None):
    return SimpleNamespace(project_store=project_store, auto_run_store=policy_store,
                           quant_store=quant_store, tool_registry=registry,
                           run_id="run_1")


# ── the policy ───────────────────────────────────────────────────────────────

def test_auto_run_is_off_for_every_project_by_default(stores):
    project_store, policy_store = stores
    project = project_store.create("p")
    policy = policy_store.get_policy(project.id)
    assert policy.enabled is False
    assert policy_store.enabled_policies() == []


def test_the_policy_can_be_enabled_and_narrowed(stores):
    project_store, policy_store = stores
    project = project_store.create("p")
    policy = policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=5,
                                     minIntervalMinutes=15,
                                     allowedTools=["run_backtest", "run_world"])
    assert policy.enabled is True
    assert policy.max_runs_per_day == 5
    assert policy.min_interval_minutes == 15
    # A tool that is not a compute is never allowed, whatever the caller asks.
    assert "run_world" not in policy.allowed_tools
    assert policy.allowed_tools == ["run_backtest"]


def test_the_budget_counts_the_runs_of_the_last_day(stores):
    project_store, policy_store = stores
    project = project_store.create("p")
    policy = policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=2,
                                     minIntervalMinutes=0)
    assert policy_store.budget_state(policy)["mayRun"] is True
    policy_store.record_run(project.id, "p1", "run_backtest", "completed")
    assert policy_store.budget_state(policy)["usedRuns"] == 1
    policy_store.record_run(project.id, "p2", "run_backtest", "completed")
    state = policy_store.budget_state(policy)
    assert state["usedRuns"] == 2
    assert state["mayRun"] is False
    assert "daily_run_budget" in state["blockedBy"]


def test_the_minimum_interval_holds_a_project_back(stores):
    project_store, policy_store = stores
    project = project_store.create("p")
    policy = policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=10,
                                     minIntervalMinutes=60)
    policy_store.record_run(project.id, "p1", "run_backtest", "completed")
    state = policy_store.budget_state(policy)
    assert state["mayRun"] is False
    assert "min_interval" in state["blockedBy"]
    assert state["waitSeconds"] > 0


def test_every_auto_run_is_recorded(stores):
    project_store, policy_store = stores
    project = project_store.create("p")
    policy_store.record_run(project.id, "p1", "run_backtest", "completed",
                            summary="done", experiment_id="exp_1")
    last = policy_store.last_run(project.id)
    assert last["tool"] == "run_backtest"
    assert last["status"] == "completed"
    assert last["experimentId"] == "exp_1"


# ── the tick ─────────────────────────────────────────────────────────────────

async def test_a_disabled_project_never_acts(stores, monkeypatch):
    project_store, policy_store = stores
    project = project_store.create("p")
    registry = _Registry()
    report = await tick_projects(_ctx(project_store, policy_store, registry))
    assert report["ran"] == []
    assert registry.calls == []


async def test_an_enabled_project_runs_its_top_proposal(stores, monkeypatch):
    from harness.projects import propose as propose_module

    project_store, policy_store = stores
    project = project_store.create("p")
    policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=5,
                             minIntervalMinutes=0)
    proposal = {"id": "result:x", "title": "t", "rationale": "r",
                "evidence": ["e"],
                "action": {"tool": "run_backtest", "args": {"strategyId": "x"}},
                "priority": 90}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry()
    report = await tick_projects(_ctx(project_store, policy_store, registry))
    assert len(report["ran"]) == 1
    assert registry.calls[0][0] == "run_backtest"
    assert policy_store.last_run(project.id)["status"] == "completed"


async def test_a_proposal_the_policy_does_not_allow_is_not_run(stores, monkeypatch):
    from harness.projects import propose as propose_module

    project_store, policy_store = stores
    project = project_store.create("p")
    policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=5,
                             minIntervalMinutes=0, allowedTools=["run_backtest"])
    proposal = {"id": "danger:x", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {"tool": "run_world", "args": {}}, "priority": 90}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry()
    report = await tick_projects(_ctx(project_store, policy_store, registry))
    assert report["ran"] == []
    assert registry.calls == []
    assert report["skipped"][0]["reason"] == "no_runnable_proposal"


async def test_a_project_past_its_budget_does_not_act(stores, monkeypatch):
    from harness.projects import propose as propose_module

    project_store, policy_store = stores
    project = project_store.create("p")
    policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=1,
                             minIntervalMinutes=0)
    policy_store.record_run(project.id, "earlier", "run_backtest", "completed")
    proposal = {"id": "result:x", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {"tool": "run_backtest", "args": {}}, "priority": 90}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry()
    report = await tick_projects(_ctx(project_store, policy_store, registry))
    assert report["ran"] == []
    assert "daily_run_budget" in report["skipped"][0]["reason"]


async def test_a_failed_run_is_recorded_as_a_failure(stores, monkeypatch):
    from harness.projects import propose as propose_module

    project_store, policy_store = stores
    project = project_store.create("p")
    policy_store.set_policy(project.id, enabled=True, maxRunsPerDay=5,
                             minIntervalMinutes=0)
    proposal = {"id": "result:x", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {"tool": "run_backtest", "args": {}}, "priority": 90}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry(ToolResult(tool_call_id="c1", name="run_backtest", ok=False,
                                   text="Tool error (X): refused",
                                   error=SimpleNamespace(code="X", message="refused")))
    report = await tick_projects(_ctx(project_store, policy_store, registry))
    assert report["ran"][0]["status"] == "refused"
    assert policy_store.last_run(project.id)["status"] == "refused"
