"""C4.3: bind a run to a goal step and record its evidence."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.goals import GoalStore, PlanRuntime
from harness.persistence import AgentMemoryStore
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
    directory = tempfile.mkdtemp(prefix="be-plan-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _request(context: dict, agent: AgentConfig) -> RunRequest:
    return RunRequest(
        runId="run_plan",
        input=RunInput(query="do the plan", context=context),
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


def test_from_request_creates_a_goal_plan_and_prompt_block(store):
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=[])
    runtime = PlanRuntime.from_request(store, _request({
        "c4Plan": {
            "objective": "Produce a risk brief",
            "acceptance": ["drawdown"],
            "steps": [
                {"title": "Pull prices", "objective": "Fetch bars"},
                {"title": "Compute risk", "objective": "Drawdown"},
            ],
        },
    }, agent))
    assert runtime is not None
    assert runtime.goal.objective == "Produce a risk brief"
    assert len(runtime.plan.steps) == 2
    assert runtime.current_step.title == "Pull prices"
    block = runtime.prompt_block()
    assert "Produce a risk brief" in block
    assert "Current step 1/2" in block


def test_a_tool_result_with_a_handle_supports_the_step(store):
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=[])
    runtime = PlanRuntime.from_request(store, _request({
        "c4Plan": {"objective": "x", "steps": [{"title": "s", "objective": "s"}]},
    }, agent))

    class Result:
        ok = True
        name = "probe"
        text = "probe ok"
        output_id = None
        data = {"path": "data.csv", "sha256": "abc123"}

    runtime.record_tool_result(Result(), "run_plan")
    claims = runtime.ledger.claims("run_plan")
    assert len(claims) == 1
    assert claims[0].status == "supported"
    assert claims[0].step_id == runtime.current_step.id
    assert runtime.settle("run_plan", ok=True) == "verified"


def test_a_step_with_no_evidence_cannot_be_verified(store):
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=[])
    runtime = PlanRuntime.from_request(store, _request({
        "c4Plan": {"objective": "x", "steps": [{"title": "s", "objective": "s"}]},
    }, agent))
    assert runtime.settle("run_plan", ok=True) == "failed"


def test_no_context_means_no_plan_runtime(store):
    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=[])
    assert PlanRuntime.from_request(store, _request({}, agent)) is None


@pytest.mark.asyncio
async def test_the_graph_verifies_the_step_when_a_tool_provided_evidence(store, monkeypatch):
    goals = GoalStore(store)
    goal = goals.create_goal("Produce a risk brief", acceptance=["drawback"])
    plan = goals.create_plan(goal.id, [{"title": "Probe", "objective": "run probe"}])

    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=["probe"], maxSteps=3)
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "probe", "args": {}}]),
        AIMessage(content="The probe ran and the data is in data.csv."),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        _request({"c4Plan": {"planId": plan.id}}, agent),
        _registry(), FakeBridge(), store,
    )
    assert result.status == "completed"

    loaded = goals.get_plan(plan.id)
    assert loaded is not None
    assert loaded.steps[0].status == "verified"
    claims = GoalStore(store).list_claims("run_plan")
    assert any(claim.step_id == loaded.steps[0].id and claim.status == "supported" for claim in claims)
