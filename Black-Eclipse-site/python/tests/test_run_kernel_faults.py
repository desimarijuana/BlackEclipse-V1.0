"""W6 — a failed durable boundary stops the run honestly."""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.run_lineage import CheckpointWriteFailed
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="done")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-w6-faults-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _req(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="hi"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(
            provider="ollama", model="m", base_url="http://localhost:11434/v1",
        ),
        callbackBaseUrl="http://localhost:3000",
    )


@pytest.mark.asyncio
async def test_a_failed_boundary_fails_the_run_with_checkpoint_write_failed(
    store, monkeypatch,
):
    model = ScriptedModel([AIMessage(content="final answer")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    from harness.run_lineage import RunLineage

    def boom(self, *args, **kwargs):
        raise CheckpointWriteFailed("disk full")

    monkeypatch.setattr(RunLineage, "save_boundary", boom)
    result = await graph_module.execute_run(
        _req("run_ckpt_fail"), ToolRegistry(), FakeBridge(), store,
    )
    assert result.status == "failed"
    assert result.error is not None and result.error.code == "CHECKPOINT_WRITE_FAILED"
    run = store.get_run("run_ckpt_fail")
    assert run["status"] == "failed"
    assert run["error"]["code"] == "CHECKPOINT_WRITE_FAILED"
