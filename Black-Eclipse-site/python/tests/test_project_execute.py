"""Tests for closing the loop: running a project's own proposal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.projects import ProjectStore
from harness.projects.execute import ProposalRun, run_project_proposal
from harness.tools import ToolResult


@pytest.fixture()
def store(tmp_path) -> ProjectStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ProjectStore(ams)


class _Registry:
    """A registry that runs one tool and remembers the call."""

    def __init__(self, result: ToolResult, names=("run_backtest",)) -> None:
        self.result = result
        self._names = tuple(names)
        self.calls: list[tuple[str, dict]] = []

    def names(self):
        return list(self._names)

    async def execute(self, name, call_id, arguments, ctx, **_kw):
        self.calls.append((name, dict(arguments)))
        return self.result


def _ctx(store, registry, quant_store=None):
    return SimpleNamespace(project_store=store, quant_store=quant_store,
                           tool_registry=registry, run_id="run_1")


def _ok(experiment_id="exp_new"):
    return ToolResult(tool_call_id="c1", name="run_backtest", ok=True,
                      text="Backtest complete",
                      data={"status": "OK", "experimentId": experiment_id})


def _err():
    return ToolResult(tool_call_id="c1", name="run_backtest", ok=False,
                      text="Tool error (X): refused",
                      error=SimpleNamespace(code="X", message="refused"))


# ── the executor ─────────────────────────────────────────────────────────────

async def test_a_completed_run_is_recorded_as_an_experiment(store, monkeypatch):
    from harness.projects import propose as propose_module

    proposal = {
        "id": "result:ema_cross",
        "title": "Test ema_cross",
        "rationale": "it has never been run",
        "evidence": ["strategy:ema_cross"],
        "action": {"tool": "run_backtest",
                   "args": {"strategyId": "ema_cross", "symbols": ["NQ"]}},
        "priority": 90,
    }
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    project = store.create("NQ momentum")
    registry = _Registry(_ok())
    run = await run_project_proposal(_ctx(store, registry), project.id,
                                     "result:ema_cross")
    assert run.status == "completed"
    assert run.experiment_id == "exp_new"
    assert registry.calls[0][0] == "run_backtest"
    assert registry.calls[0][1]["strategyId"] == "ema_cross"
    assert run.attached["kind"] == "experiment"
    assert run.attached["ref"] == "exp_new"


async def test_a_refused_run_is_recorded_as_a_failure_not_a_result(store, monkeypatch):
    from harness.projects import propose as propose_module

    proposal = {
        "id": "result:ema_cross", "title": "t", "rationale": "r",
        "evidence": ["strategy:ema_cross"],
        "action": {"tool": "run_backtest", "args": {"strategyId": "ema_cross"}},
        "priority": 90,
    }
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    project = store.create("NQ momentum")
    registry = _Registry(_err())
    run = await run_project_proposal(_ctx(store, registry), project.id,
                                     "result:ema_cross")
    assert run.status == "refused"
    assert run.experiment_id is None
    assert run.attached["kind"] == "note"


async def test_a_proposal_that_names_no_tool_is_not_run(store, monkeypatch):
    from harness.projects import propose as propose_module

    project = store.create("p")
    proposal = {"id": "p1", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {}, "priority": 10}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry(_ok())
    run = await run_project_proposal(_ctx(store, registry), "proj_1", "p1")
    assert run.status == "not_runnable"
    assert registry.calls == []


async def test_an_unknown_proposal_is_reported_not_run(store, monkeypatch):
    from harness.projects import propose as propose_module

    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": "proj_1", "summary": "",
        "proposals": [], "proposalCount": 0, "skipped": [],
    })
    registry = _Registry(_ok())
    run = await run_project_proposal(_ctx(store, registry), "proj_1", "nope")
    assert run.status == "not_runnable"
    assert registry.calls == []


async def test_a_tool_that_is_not_registered_is_not_run(store, monkeypatch):
    from harness.projects import propose as propose_module

    project = store.create("p")
    proposal = {"id": "p1", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {"tool": "not_a_tool", "args": {}}, "priority": 10}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry(_ok(), names=("run_backtest",))
    run = await run_project_proposal(_ctx(store, registry), "proj_1", "p1")
    assert run.status == "not_runnable"
    assert "not registered" in run.summary
    assert registry.calls == []


async def test_a_project_that_does_not_exist_is_not_run(store):
    registry = _Registry(_ok())
    run = await run_project_proposal(_ctx(store, registry), "proj_nope", "p1")
    assert run.status == "not_runnable"
    assert registry.calls == []


async def test_the_run_is_recorded_in_the_project_it_belongs_to(store, monkeypatch):
    from harness.projects import propose as propose_module

    project = store.create("NQ momentum")
    proposal = {"id": "p1", "title": "t", "rationale": "r", "evidence": ["e"],
                "action": {"tool": "run_backtest", "args": {"strategyId": "x"}},
                "priority": 10}
    monkeypatch.setattr(propose_module, "propose_next", lambda *a, **k: {
        "available": True, "projectId": project.id, "summary": "",
        "proposals": [proposal], "proposalCount": 1, "skipped": [],
    })
    registry = _Registry(_ok())
    run = await run_project_proposal(_ctx(store, registry), project.id, "p1")
    assert run.status == "completed"
    refs = [m.ref for m in store.members(project.id)]
    assert "exp_new" in refs
