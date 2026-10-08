"""End-to-end: a durable plan executes through the REAL runtime.

This is the production path, deterministically: a real `AgenticService`, the real
`TaskScheduler`, and the real `service.run` -> `execute_run` graph. Only the LLM
is a scripted model (monkeypatched at the ONE `build_chat_model` seam), so no
network or provider is required — but every other layer (state machine, store,
claim/lease, dispatch, run graph, completion verification, plan roll-up) is the
shipped implementation.

It also proves a plan reaches COMPLETED on its own once its tasks do, and that
each task produced a real `HarnessRun` row.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.service import AgenticService
from harness.tasks.bootstrap import _task_model_settings
from harness.tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    PlanStatus,
    TaskStatus,
)
from harness.schemas import ModelSettings

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-tasks-e2e-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


class ScriptedModel:
    """A chat model that immediately returns a final answer (no tool calls)."""

    def bind_tools(self, tools):  # noqa: ANN001, ANN201
        return self

    async def ainvoke(self, messages):  # noqa: ANN001, ANN201
        return AIMessage(content="Done.")

    async def astream(self, messages):  # noqa: ANN001, ANN201
        yield await self.ainvoke(messages)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    svc = AgenticService(store=store)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel())
    yield svc
    svc.store.close()


async def _drain(scheduler, manager, rounds: int = 40) -> None:
    for _ in range(rounds):
        await scheduler.tick()
        await scheduler.wait_idle()
        if not manager.runnable_tasks():
            break


@pytest.mark.asyncio
async def test_plan_runs_and_completes_through_the_real_service(service):
    manager = service.tasks
    plan = manager.create_plan(CreatePlanInput(name="Compare", objective="compare"))
    a = manager.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    b = manager.create_task(CreateTaskInput(
        title="B", plan_id=plan.id, dependencies=[a.id],
        acceptance_criteria=[{"text": "answer produced"}],
    ))
    manager.start_plan(plan.id)
    assert manager.get_plan(plan.id).status == PlanStatus.RUNNING

    await _drain(service.task_scheduler, manager)

    # Both tasks completed (B only after A), and the PLAN rolled up on its own.
    assert manager.get_task(a.id).status == TaskStatus.COMPLETED
    assert manager.get_task(b.id).status == TaskStatus.COMPLETED
    assert manager.get_plan(plan.id).status == PlanStatus.COMPLETED

    # Each task produced a REAL HarnessRun row (a normal run, not a second ledger).
    for task in (a, b):
        executions = manager.list_executions(task.id)
        assert executions, f"{task.title} has no execution record"
        run_id = executions[-1].run_id
        assert run_id and service.store.get_run(run_id) is not None

    # The immutable history recorded the lifecycle.
    types = {e.type for e in manager._store.list_task_events(a.id)}  # noqa: SLF001
    assert "TASK_CREATED" in types and "TASK_COMPLETED" in types
    plan_events = {e.type for e in manager._store.list_plan_events(plan.id)}  # noqa: SLF001
    assert "PLAN_STATUS_CHANGED" in plan_events


@pytest.mark.asyncio
async def test_failed_task_fails_the_plan(service):
    manager = service.tasks
    plan = manager.create_plan(CreatePlanInput(name="Will fail"))
    task = manager.create_task(CreateTaskInput(
        title="never", plan_id=plan.id, max_retries=0,
        acceptance_criteria=[{"text": "impossible"}],
    ))
    # Force a deterministic failure: an explicit criterion the scripted run cannot
    # satisfy unless auto-verify is off, and completion is rejected.
    manager._store.update_task_fields(task.id, {"metadata": {"criteriaRequireExplicit": True}})  # noqa: SLF001
    manager.start_plan(plan.id)
    await _drain(service.task_scheduler, manager)
    assert manager.get_task(task.id).status == TaskStatus.FAILED
    assert manager.get_plan(plan.id).status == PlanStatus.FAILED


def test_task_model_settings_precedence(service):
    manager = service.tasks
    # Plan-level settings are used when the task declares none.
    plan = manager.create_plan(CreatePlanInput(
        name="pinned", metadata={"modelSettings": {"provider": "openai", "model": "gpt-x"}},
    ))
    task = manager.create_task(CreateTaskInput(title="t", plan_id=plan.id))
    resolved = _task_model_settings(manager, task)
    assert isinstance(resolved, ModelSettings)
    assert resolved.provider == "openai" and resolved.model == "gpt-x"
    # A task-level override wins over the plan.
    task = manager.update_task(task.id, {
        "metadata": {"modelSettings": {"provider": "ollama", "model": "llama3.1"}},
    })
    assert _task_model_settings(manager, task).provider == "ollama"
