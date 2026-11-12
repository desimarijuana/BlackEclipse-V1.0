"""End-to-end: a bot team runs through the REAL runtime.

A real `AgenticService`, the real A2A delegation layer, the real Task runtime and
the real `TaskScheduler` → `service.run` → `execute_run` graph. Only the LLM is a
scripted model (monkeypatched at the ONE `build_chat_model` seam), so no network or
provider is required — but every other layer is the shipped implementation.

This proves a delegated Bot runs as itself (its own run + agent id), independent
bots overlap in execution, and the run rolls up to a terminal review.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.a2a.bootstrap import install_a2a_layer
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.run_lineage import RunLineage
from harness.service import AgenticService
from harness.tasks.model import PlanStatus, TaskStatus
from harness.team.bootstrap import install_team_layer
from harness.team.model import TeamDefinition, TeamRunStatus

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-team-e2e-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


class ScriptedModel:
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
    install_a2a_layer(svc)
    install_team_layer(svc)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel())
    yield svc
    svc.store.close()


async def _drain(service, rounds: int = 60) -> None:
    for _ in range(rounds):
        await service.task_scheduler.tick()
        await service.task_scheduler.wait_idle()
        if not service.tasks.runnable_tasks():
            break


def _team():
    return TeamDefinition(
        id="desk", name="Markets Desk", agent_id="eclipse-orchestrator",
        objective="Produce a short desk note",
        members=[
            {"agentId": "research-agent", "capabilities": ["web_research"]},
            {"agentId": "valuation-agent", "capabilities": ["dcf"]},
            {"agentId": "risk-agent", "capabilities": ["risk_analysis"]},
        ],
        subtasks=[
            {"id": "research", "objective": "Summarize the latest developments",
             "assignedAgentId": "research-agent"},
            {"id": "value", "objective": "Give a valuation view",
             "assignedAgentId": "valuation-agent", "dependsOn": ["research"]},
            {"id": "risk", "objective": "State the key risks",
             "assignedAgentId": "risk-agent"},
        ],
    )


@pytest.mark.asyncio
async def test_team_runs_through_the_real_runtime(service):
    active = {"now": 0, "max": 0}
    original = service.run

    async def instrumented(request):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        try:
            await asyncio.sleep(0.03)
            return await original(request)
        finally:
            active["now"] -= 1

    service.run = instrumented  # type: ignore[assignment]

    run = await service.team.run(_team())
    assert run.plan_id
    await _drain(service)

    manager = service.tasks
    assert manager.get_plan(run.plan_id).status is PlanStatus.COMPLETED
    for sid, tid in run.subtask_task_ids.items():
        task = manager.get_task(tid)
        assert task.status is TaskStatus.COMPLETED, (sid, task.status, task.error)
        executions = manager.list_executions(tid)
        assert executions and executions[-1].run_id
        # A delegated Bot ran as ITSELF: the run is a real HarnessRun row, and the
        # task was executed by its own assigned agent.
        assert service.store.get_run(executions[-1].run_id) is not None
        assert task.assigned_agent_id in {"research-agent", "valuation-agent", "risk-agent"}

    # Genuine overlap through the real runtime (research/risk start together).
    assert active["max"] >= 2

    final = await service.team.finalize(run.id)
    assert final["status"] == "COMPLETED"
    assert service.team.get_run(run.id).status is TeamRunStatus.COMPLETED


class _SpawnFabric:
    """A Fabric that records the spawn job and completes a real child run."""

    def __init__(self, store) -> None:
        self.store = store
        self.calls: list[dict] = []

    async def submit(self, job_type, payload, **kwargs):  # noqa: ANN001, ANN201
        index = len(self.calls) + 1
        run_id = f"spawn_child_{index}"
        self.calls.append({"jobType": job_type, "payload": payload, **kwargs})
        self.store.create_run(
            run_id, str(payload.get("agentId") or "eclipse-agent"),
            {"query": str(payload.get("query") or "")},
        )
        RunLineage(self.store).set_run_parent(run_id, str(payload.get("parentRunId") or ""))
        return {
            "status": "SUCCEEDED", "jobId": f"job_{index}", "output": "Done.",
            "outcome": {"metrics": {"runId": run_id, "totalTokens": 10}},
        }


@pytest.mark.asyncio
async def test_team_tasks_execute_through_the_spawn_primitive(service):
    fabric = _SpawnFabric(service.store)
    service.fabric = fabric

    run = await service.team.run(_team())
    await _drain(service)

    assert fabric.calls, "team tasks never reached the spawn primitive"
    assert all(call["jobType"] == "agent" for call in fabric.calls)
    assert all(call["payload"]["parentRunId"] for call in fabric.calls)
    assert service.tasks.get_plan(run.plan_id).status is PlanStatus.COMPLETED
    for tid in run.subtask_task_ids.values():
        assert service.tasks.get_task(tid).status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_existing_single_run_still_works(service):
    result = await service.run(RunRequest(
        runId="solo-run",
        input=RunInput(query="What is a stock split?"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="llama3.1"),
        callbackBaseUrl="http://127.0.0.1:3000",
    ))
    dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    assert dumped.get("status") == "completed"
