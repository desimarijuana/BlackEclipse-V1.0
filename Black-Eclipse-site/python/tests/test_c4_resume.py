"""C4.6: the plan/step cursor is durable and a later run continues it."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.goals import GoalStore, PlanRuntime
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, _messages):
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-resume-c4-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _request(plan_id: str, run_id: str, agent: AgentConfig) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="continue the plan", context={"c4Plan": {"planId": plan_id}}),
        agent=agent,
        modelSettings=ModelSettings(
            provider="ollama", model="m", base_url="http://localhost:11434/v1",
        ),
        callbackBaseUrl="http://localhost:3000",
    )


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def probe(_args, _ctx):
        return "probe ok", {"path": "data.csv", "sha256": "abc123"}

    reg.register(ToolDefinition(
        name="probe", description="probe", input_schema={"type": "object", "properties": {}},
        handler=probe, permission="read",
    ))
    return reg


def _model() -> ScriptedModel:
    return ScriptedModel([
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "probe", "args": {}}]),
        AIMessage(content="The probe shows the reading returned 18.4%."),
    ])


@pytest.mark.asyncio
async def test_two_runs_continue_the_same_plan_step_by_step(store, monkeypatch):
    goals = GoalStore(store)
    goal = goals.create_goal("Two-step brief", acceptance=["number"])
    plan = goals.create_plan(goal.id, [
        {"title": "First", "objective": "probe once"},
        {"title": "Second", "objective": "probe again"},
    ])
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=["probe"], maxSteps=4)

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: _model())
    first = await graph_module.execute_run(
        _request(plan.id, "run_step1", agent), _registry(), FakeBridge(), store,
    )
    assert first.status == "completed"
    loaded = goals.get_plan(plan.id)
    assert loaded.steps[0].status == "verified"
    assert loaded.steps[1].status == "pending"

    # A NEW run with the same plan resumes at the next unverified step.
    resumed = PlanRuntime.from_request(
        store, _request(plan.id, "run_step2", agent),
    )
    assert resumed is not None
    assert resumed.current_step.title == "Second"

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: _model())
    second = await graph_module.execute_run(
        _request(plan.id, "run_step2", agent), _registry(), FakeBridge(), store,
    )
    assert second.status == "completed"
    loaded = goals.get_plan(plan.id)
    assert loaded.steps[0].status == "verified"
    assert loaded.steps[1].status == "verified"
    assert loaded.complete is True


class KillModel:
    """First turn calls the tool; second raises a hard kill (BaseException)."""

    def __init__(self):
        self.n = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, _messages):
        self.n += 1
        if self.n == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": "probe", "args": {}}])
        raise ProcessKilled("simulated kill")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class ProcessKilled(BaseException):
    pass


@pytest.mark.asyncio
async def test_a_killed_step_resumes_in_a_new_run_without_losing_the_plan(store, monkeypatch):
    goals = GoalStore(store)
    goal = goals.create_goal("Crash-safe brief")
    plan = goals.create_plan(goal.id, [{"title": "Only", "objective": "probe"}])
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=["probe"], maxSteps=4)

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: KillModel())
    with pytest.raises(ProcessKilled):
        await graph_module.execute_run(
            _request(plan.id, "run_killed", agent), _registry(), FakeBridge(), store,
        )

    # The step is still running (not falsely verified) and the plan survived.
    loaded = goals.get_plan(plan.id)
    assert loaded.steps[0].status == "running"

    # A new run with the same plan continues the step and verifies it.
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: _model())
    resumed = await graph_module.execute_run(
        _request(plan.id, "run_after_kill", agent), _registry(), FakeBridge(), store,
    )
    assert resumed.status == "completed"
    loaded = goals.get_plan(plan.id)
    assert loaded.steps[0].status == "verified"


@pytest.mark.asyncio
async def test_the_checkpoint_names_the_plan_and_step_cursor(store, monkeypatch):
    goals = GoalStore(store)
    goal = goals.create_goal("One step")
    plan = goals.create_plan(goal.id, [{"title": "Only", "objective": "probe"}])
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=["probe"], maxSteps=4)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: _model())

    await graph_module.execute_run(
        _request(plan.id, "run_ckpt", agent), _registry(), FakeBridge(), store,
    )
    checkpoint = RunLineage(store).latest_checkpoint("run_ckpt")
    assert checkpoint is not None
    payload = checkpoint["payload"]
    assert payload["planId"] == plan.id
    assert payload["stepId"] == plan.steps[0].id
