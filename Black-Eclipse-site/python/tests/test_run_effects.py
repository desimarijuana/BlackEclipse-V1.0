"""Effect ledger: an unconfirmed effect is not re-executed on resume."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.run_effects import RunEffects
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class ToolThenAnswer:
    def __init__(self, tool_name: str):
        self.calls = 0
        self.tool_name = tool_name

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": self.tool_name, "args": {}}])
        return AIMessage(content="final answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "OK"}


def _req(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="run the effect tool"),
        agent=AgentConfig(
            id="effect-test", name="Effect", systemPrompt="sys",
            tools=["effect_tool"], maxSteps=3,
        ),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


def _registry(counter):
    registry = ToolRegistry()

    async def effect_tool(args, ctx):
        counter["executed"] += 1
        return "done", {"status": "OK"}

    # `permission=read` keeps the test free of an approval authorizer while the
    # `effect` field still classifies the call as effectful for the ledger.
    registry.register(ToolDefinition(
        name="effect_tool", description="effect", input_schema={"type": "object", "properties": {}},
        handler=effect_tool, permission="read", risk="low", effect="external_action",
    ))
    return registry


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-effects-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.mark.asyncio
async def test_confirmed_effect_is_recorded_done(store, monkeypatch):
    counter = {"executed": 0}
    effects = RunEffects(store)
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ToolThenAnswer("effect_tool"))

    result = await graph_module.execute_run(
        _req("run_confirmed"), _registry(counter), _Bridge(), store,
    )

    assert result.status == "completed", store.get_run("run_confirmed").get("error")
    assert counter["executed"] == 1
    states = [
        effects.state("run_confirmed", step, "c1") for step in (0, 1, 2)
    ]
    assert "done" in states


@pytest.mark.asyncio
async def test_started_without_a_result_is_not_executed_again(store, monkeypatch):
    counter = {"executed": 0}
    effects = RunEffects(store)
    # A previous process dispatched the effect and died before recording it.
    for step in (0, 1, 2):
        effects.begin("run_unknown", step, "c1", "effect_tool", "external_action")

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ToolThenAnswer("effect_tool"))
    result = await graph_module.execute_run(
        _req("run_unknown"), _registry(counter), _Bridge(), store,
    )

    assert result.status == "completed"
    assert counter["executed"] == 0  # at-most-once: never re-dispatched
    assert result.output == "final answer"
    assert any(effects.state("run_unknown", step, "c1") == "unknown" for step in (0, 1, 2))
