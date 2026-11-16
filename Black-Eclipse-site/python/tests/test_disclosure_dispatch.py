"""Progressive disclosure hides an ADVERTISEMENT, not the tool.

A schema-narrowed surface must still dispatch a direct call to a hidden
read-only tool (the catalogue names it, and `tool_invoke` can reach it). A
policy-removed tool stays absent from both surfaces; that is covered by the
surface tests.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.service import _HttpDataBridge
from harness.tool_surface import register_tool_surface_tools
from harness.tools import DataBridge, ToolDefinition, ToolRegistry


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="(exhausted)")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.mark.asyncio
async def test_a_hidden_read_tool_is_still_dispatchable(monkeypatch):
    directory = tempfile.mkdtemp(prefix="be-disclosure-dispatch-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        reg = ToolRegistry()
        register_tool_surface_tools(reg)

        async def hidden(_args, _ctx):
            return "HIDDEN_OK", {"status": "OK"}

        async def bulk(_args, _ctx):
            return "bulk", {"status": "OK"}

        reg.register(ToolDefinition(
            name="zz_hidden_target",
            description="A read-only target that is not on the first-ranked tail.",
            input_schema={"type": "object", "properties": {}},
            handler=hidden,
        ))
        for index in range(400):
            reg.register(ToolDefinition(
                name=f"bulk_read_{index}",
                description=(
                    "Long market data description with prices volume history and "
                    "filings. " * 8
                ),
                input_schema={"type": "object", "properties": {}},
                handler=bulk,
            ))

        model = ScriptedModel([
            AIMessage(content="", tool_calls=[{
                "id": "c1", "name": "zz_hidden_target", "args": {},
            }]),
            AIMessage(content="HIDDEN_OK"),
        ])
        monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

        agent = AgentConfig(
            id="ag", name="AG", systemPrompt="sys", tools=list(reg.names()),
            maxSteps=4,
        )
        request = RunRequest(
            runId="run_disclosure_dispatch",
            input=RunInput(query="what is the price?"),
            agent=agent,
            modelSettings=ModelSettings(
                provider="ollama", model="deepseek-v4.1-flash:cloud",
                base_url="http://localhost:11434/v1",
            ),
            callbackBaseUrl="http://localhost:3000",
        )
        result = await graph_module.execute_run(request, reg, FakeBridge(), store)
        assert result.status == "completed", result.error
        assert "HIDDEN_OK" in (result.output or "")

        import json

        surface = store.get_run("run_disclosure_dispatch")["surface"]
        if isinstance(surface, str):
            surface = json.loads(surface)
        assert surface["disclosure"]["enabled"] is True
        assert surface["disclosure"]["hiddenTools"] > 0
    finally:
        store.close()
