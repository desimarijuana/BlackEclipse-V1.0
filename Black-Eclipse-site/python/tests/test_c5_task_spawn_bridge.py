"""C5.6: A2A/team tasks execute through the spawn primitive."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.fabric import tools as fabric_tools
from harness.persistence import AgentMemoryStore
from harness.tasks.scheduler import TaskRunOutcome
from harness.tasks.spawn_bridge import wrap_task_executor


class FakeFabric:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def submit(self, job_type, payload, **kwargs):
        self.calls.append({"jobType": job_type, "payload": payload, **kwargs})
        return {
            "status": "SUCCEEDED", "jobId": "job_spawn", "output": "spawned answer",
            "outcome": {"metrics": {"runId": "child_run", "totalTokens": 42}},
        }


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-task-spawn-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("child_run", "eclipse-agent", {"query": "child"})
    yield s
    s.close()
    fabric_tools.set_fabric_manager(None)


def _task(metadata):
    return SimpleNamespace(
        id="task_1", title="Do it", objective="Check AAPL",
        description="", assigned_agent_id="eclipse-agent", metadata=metadata,
        plan_id="plan_1",
    )


class _Service:
    def __init__(self, store, fabric=None):
        self.store = store
        self.fabric = fabric


@pytest.mark.asyncio
async def test_an_a2a_task_executes_as_a_spawn_fabric_job(store, monkeypatch):
    fabric = FakeFabric()
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    base_calls = {"n": 0}

    async def base(task, context, run_id):
        base_calls["n"] += 1
        return TaskRunOutcome(status="completed", output="inline", run_id=run_id)

    executor = wrap_task_executor(_Service(store, fabric), base)
    outcome = await executor(_task({"a2a": True}), None, "run_task")

    assert outcome.status == "completed"
    assert outcome.output == "spawned answer"
    assert outcome.metrics["spawned"] is True
    assert base_calls["n"] == 0
    assert fabric.calls[0]["jobType"] == "agent"
    assert fabric.calls[0]["payload"]["parentRunId"] == "run_task"
    assert fabric.calls[0]["payload"]["agentId"] == "eclipse-agent"


@pytest.mark.asyncio
async def test_a_team_task_also_uses_spawn(store, monkeypatch):
    fabric = FakeFabric()
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)

    async def base(task, context, run_id):
        return TaskRunOutcome(status="completed", output="inline", run_id=run_id)

    outcome = await wrap_task_executor(_Service(store, fabric), base)(
        _task({"team": True}), None, "run_team",
    )
    assert outcome.output == "spawned answer"
    assert len(fabric.calls) == 1


@pytest.mark.asyncio
async def test_an_ordinary_task_keeps_the_existing_executor(store, monkeypatch):
    fabric = FakeFabric()
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)

    async def base(task, context, run_id):
        return TaskRunOutcome(status="completed", output="inline", run_id=run_id)

    outcome = await wrap_task_executor(_Service(store, fabric), base)(
        _task({"source": "chat"}), None, "run_plain",
    )
    assert outcome.output == "inline"
    assert fabric.calls == []


@pytest.mark.asyncio
async def test_without_a_fabric_the_a2a_task_falls_back_inline(store, monkeypatch):
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: None)

    async def base(task, context, run_id):
        return TaskRunOutcome(status="completed", output="inline", run_id=run_id)

    outcome = await wrap_task_executor(_Service(store, None), base)(
        _task({"a2a": True}), None, "run_fallback",
    )
    assert outcome.output == "inline"
