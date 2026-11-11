"""C4.5: an evidence failure triggers one bounded replan, then a real answer."""

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
    directory = tempfile.mkdtemp(prefix="be-replan-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _request(plan_id: str, agent: AgentConfig) -> RunRequest:
    return RunRequest(
        runId="run_replan",
        input=RunInput(query="answer", context={"c4Plan": {"planId": plan_id}}),
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


def test_the_runtime_supersedes_the_failed_draft_and_resets_the_step(store):
    goal = GoalStore(store).create_goal("x")
    plan = GoalStore(store).create_plan(goal.id, [{"title": "s", "objective": "s"}])
    runtime = PlanRuntime.from_request(store, _request(plan.id, AgentConfig(
        id="a", name="A", systemPrompt="s", tools=[],
    )))
    assert runtime is not None
    assert runtime.can_replan() is True

    runtime.record_answer_claims("run_replan", "AAPL returned 18.4% last year.")
    runtime.settle("run_replan", ok=False)
    verdict = runtime.verify_current_step("run_replan")
    assert verdict.ok is False

    runtime.replan(run_id="run_replan", reason="evidence")
    assert runtime.replans_used() == 1
    assert runtime.current_step.status == "running"
    superseded = [c for c in runtime.ledger.claims("run_replan") if c.status == "superseded"]
    assert superseded

    runtime.replan(run_id="run_replan", reason="evidence")
    assert runtime.can_replan() is False


@pytest.mark.asyncio
async def test_the_graph_replans_then_accepts_an_evidence_backed_answer(store, monkeypatch):
    goals = GoalStore(store)
    goal = goals.create_goal("Produce a risk brief", acceptance=["number"])
    plan = goals.create_plan(goal.id, [{"title": "Quote", "objective": "quote AAPL"}])

    agent = AgentConfig(id="a", name="A", systemPrompt="s", tools=["probe"], maxSteps=5)
    model = ScriptedModel([
        AIMessage(content="AAPL returned 18.4% last year."),
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "probe", "args": {}}]),
        AIMessage(content="The probe shows AAPL returned 18.4% last year."),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        _request(plan.id, agent), _registry(), FakeBridge(), store,
    )
    assert result.status == "completed"
    assert "The probe shows" in (result.output or "")

    loaded = GoalStore(store).get_plan(plan.id)
    assert loaded.steps[0].status == "verified"
    assert GoalStore(store).count_iterations(plan.id) == 1

    events = [event["type"] for event in store.list_events("run_replan")]
    assert "run.replanned" in events
