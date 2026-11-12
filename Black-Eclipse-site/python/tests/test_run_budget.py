"""Token budget: once spent, the next step answers instead of calling tools."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class BudgetModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "counting_tool", "args": {}}],
                response_metadata={"token_usage": {"prompt_tokens": 600, "completion_tokens": 600}},
            )
        return AIMessage(content="answer within the remaining budget")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "OK"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-budget-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.mark.asyncio
async def test_token_budget_forces_a_tool_free_final_answer(store, monkeypatch):
    counter = {"executed": 0}
    registry = ToolRegistry()

    async def counting_tool(args, ctx):
        counter["executed"] += 1
        return "counted", {"status": "OK"}

    registry.register(ToolDefinition(
        name="counting_tool", description="c", input_schema={"type": "object", "properties": {}},
        handler=counting_tool, permission="read", risk="low",
    ))
    request = RunRequest(
        runId="run_budget",
        input=RunInput(query="go"),
        agent=AgentConfig(
            id="budget-test", name="Budget", systemPrompt="sys",
            tools=["counting_tool"], maxSteps=4, maxTokens=1_000,
        ),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: BudgetModel())

    result = await graph_module.execute_run(request, registry, _Bridge(), store)

    assert result.status == "completed"
    assert result.output == "answer within the remaining budget"
    assert result.totalTokens >= 1_200
    # The tool ran on the pre-budget step; the post-budget step did not call it
    # again (the second model turn was tool-free).
    assert counter["executed"] == 1
