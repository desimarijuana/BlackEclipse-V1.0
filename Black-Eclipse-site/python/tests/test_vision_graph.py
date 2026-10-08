"""Graph-level vision integration: a `vision_*` tool call reaches the run blob.

Proves the SAME wiring the spec requires — a vision tool's structured result is
collected onto the run and returned on `RunResult.vision` (and persisted) for the
right sidebar. Uses the real tool registry, real orchestrator and real graph; the
two models are scripted fakes (the graph's tool-loop model and the vision
orchestrator's analysis model).
"""

from __future__ import annotations

import base64
import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.vision.cache import reset_cache
from harness.vision.tools import register_vision_tools

from vision_helpers import png_b64


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


class VisionAnalysisModel:
    """The fake the vision orchestrator builds: returns analysis JSON."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        import json

        return AIMessage(content=json.dumps({
            "description": "A grey rectangle",
            "observations": [{"text": "grey area", "region": [0, 0, 60, 40], "confidence": 0.9}],
            "confidence": 0.9,
        }))


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-vision-graph-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset():
    reset_cache()
    yield
    reset_cache()


@pytest.mark.asyncio
async def test_vision_tool_result_reaches_run_blob(store, monkeypatch):
    # The graph's tool-loop model calls vision_analyze, then answers.
    tool_call = AIMessage(
        content="",
        tool_calls=[{
            "id": "v1", "name": "vision_analyze",
            "args": {"source": png_b64(), "question": "what is this?"},
        }],
    )
    graph_model = ScriptedModel([tool_call, AIMessage(content="I looked at the image.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: graph_model)

    # The vision orchestrator builds its model from `harness.models` (imported
    # inside the provider call), so patch that name to our analysis fake.
    import harness.models as models

    monkeypatch.setattr(models, "build_chat_model", lambda settings: VisionAnalysisModel())

    registry = ToolRegistry()
    register_vision_tools(registry)
    agent = AgentConfig(
        id="vision-test", name="Vision Test", systemPrompt="sys",
        tools=["vision_analyze"], maxSteps=4,
    )
    request = RunRequest(
        runId="run_vision_graph",
        input=RunInput(query="look at this image"),
        modelSettings=ModelSettings(provider="ollama", model="llava", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        agent=agent,
    )
    result = await graph_module.execute_run(request, registry, FakeBridge(), store)
    assert result.status == "completed"
    assert result.vision is not None
    assert result.vision["count"] == 1
    primary = result.vision["results"][0]
    assert primary["ok"] is True
    assert primary["description"] == "A grey rectangle"
    assert primary["observations"][0]["text"] == "grey area"

    # Persisted too, so the sidebar can reload it after the fact.
    run_row = store.get_run("run_vision_graph")
    assert run_row["vision"] is not None
    assert run_row["vision"]["count"] == 1


@pytest.mark.asyncio
async def test_run_without_vision_has_no_blob(store, monkeypatch):
    graph_model = ScriptedModel([AIMessage(content="No image needed.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: graph_model)
    registry = ToolRegistry()
    register_vision_tools(registry)
    request = RunRequest(
        runId="run_no_vision",
        input=RunInput(query="hello"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        agentId="eclipse-agent",
    )
    result = await graph_module.execute_run(request, registry, FakeBridge(), store)
    assert result.status == "completed"
    assert result.vision is None
