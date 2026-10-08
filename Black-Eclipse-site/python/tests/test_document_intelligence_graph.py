"""Graph-level document integration: a `document_*` tool call reaches the run blob.

Proves the SAME wiring the spec requires — a document tool's structured result is
collected onto the run and returned on `RunResult.documents` (and persisted) for
the right sidebar. Uses the real tool registry, real orchestrator and real graph;
the tool-loop model is a scripted fake.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.document_intelligence.tools import register_document_tools

import document_intelligence_helpers as fx


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return self._responses.pop(0) if self._responses else AIMessage(content="(done)")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-doc-graph-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.mark.asyncio
async def test_document_tool_result_reaches_run_blob(store, monkeypatch, tmp_path):
    doc_path = fx.write_temp(tmp_path, "report.md", b"# Summary\n\nRevenue rose 18 percent in 2023.\n")

    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "d1", "name": "document_open",
                     "args": {"source": doc_path, "include_ir": True}}],
    )
    graph_model = ScriptedModel([tool_call, AIMessage(content="I read the document.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: graph_model)

    registry = ToolRegistry()
    register_document_tools(registry)
    agent = AgentConfig(
        id="doc-test", name="Doc Test", systemPrompt="sys",
        tools=["document_open"], maxSteps=4,
    )
    request = RunRequest(
        runId="run_doc_graph",
        input=RunInput(query="read this document"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        agent=agent,
    )
    result = await graph_module.execute_run(request, registry, FakeBridge(), store)
    assert result.status == "completed"
    assert result.documents is not None
    assert result.documents["count"] == 1
    primary = result.documents["documents"][0]
    assert primary["kind"] in ("md", "markdown", "txt")
    assert primary["state"] in ("READY", "PARTIALLY_READY")

    run_row = store.get_run("run_doc_graph")
    assert run_row["documents"] is not None


@pytest.mark.asyncio
async def test_run_without_document_has_no_blob(store, monkeypatch):
    graph_model = ScriptedModel([AIMessage(content="No document needed.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: graph_model)
    registry = ToolRegistry()
    register_document_tools(registry)
    request = RunRequest(
        runId="run_no_doc",
        input=RunInput(query="hello"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        agentId="eclipse-agent",
    )
    result = await graph_module.execute_run(request, registry, FakeBridge(), store)
    assert result.status == "completed"
    assert result.documents is None
