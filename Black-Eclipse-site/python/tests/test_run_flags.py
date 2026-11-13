"""W0: the run-level flag snapshot is additive and durable."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.events import RunEmitter
from harness.persistence import AgentMemoryStore
from harness.run_flags import merge_context, record_run_flags, with_flags
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry


class ScriptedModel:
    def __init__(self, answer: str = "ok"):
        self._answer = answer

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content=self._answer)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-run-flags-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _req(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="hello"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(
            provider="ollama", model="m", base_url="http://localhost:11434/v1"
        ),
        callbackBaseUrl="http://localhost:3000",
    )


def test_merge_context_preserves_existing_keys():
    merged = merge_context(
        {"status": "completed", "windowKnown": True},
        {"HARNESS_MODEL_GATEWAY": "shadow"},
    )
    assert merged["status"] == "completed"
    assert merged["windowKnown"] is True
    assert merged["flags"]["HARNESS_MODEL_GATEWAY"] == "shadow"
    assert merged["flagsHash"].startswith("sha256:")


def test_with_flags_handles_none_context():
    merged = with_flags(None, {"HARNESS_PARALLEL_TOOLS": "off"})
    assert merged["flags"]["HARNESS_PARALLEL_TOOLS"] == "off"
    assert "flagsHash" in merged


@pytest.mark.asyncio
async def test_record_run_flags_emits_event_and_persists_context(store):
    store.create_run("run_flags", "eclipse-agent", {"query": "hello"})
    emitter = RunEmitter("run_flags", store)
    values = await record_run_flags(
        emitter, store, "run_flags", existing_context={"status": "created"}
    )

    assert values["HARNESS_MODEL_GATEWAY"] == "on"
    events = store.list_events("run_flags")
    flag_events = [e for e in events if e["type"] == "run.flags"]
    assert len(flag_events) == 1
    payload = flag_events[0]["data"]
    assert payload["flags"] == values
    assert payload["snapshotHash"].startswith("sha256:")

    context = store.get_run("run_flags")["context"]
    assert context["status"] == "created"
    assert context["flags"] == values
    assert context["flagsHash"] == payload["snapshotHash"]


@pytest.mark.asyncio
async def test_execute_run_emits_flags_and_keeps_them_in_context(store, monkeypatch):
    model = ScriptedModel("hello")
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    result = await graph_module.execute_run(
        _req("run_flags_graph"),
        ToolRegistry(),
        FakeBridge(),
        store,
    )
    assert result.status == "completed"

    events = store.list_events("run_flags_graph")
    assert any(e["type"] == "run.flags" for e in events)
    context = store.get_run("run_flags_graph")["context"]
    assert context["flags"]["HARNESS_MODEL_GATEWAY"] == "on"
    assert context["flagsHash"].startswith("sha256:")
