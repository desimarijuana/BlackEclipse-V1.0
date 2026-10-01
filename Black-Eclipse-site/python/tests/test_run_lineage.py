"""Phase 1: run lineage — parent/child recording, checkpoints, bounded reads.

Offline and deterministic: the model is a scripted fake and the data bridge is a
stub, so the assertions are on PERSISTED ROWS, never on model prose.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage, bound_checkpoint_payload, idempotency_key
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools


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
    directory = tempfile.mkdtemp(prefix="be-lineage-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    return reg


def _req(run_id: str, **kwargs) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="hi"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
        **kwargs,
    )


# ── Lineage store ────────────────────────────────────────────────────────────


def test_set_run_parent_and_lineage_round_trip(store):
    store.create_run("parent", "a", {"query": "x"})
    store.create_run("child", "a", {"query": "y"})
    lineage = RunLineage(store)
    lineage.set_run_parent("child", "parent", "wf_1")
    child = store.get_run("child")
    assert child["parentRunId"] == "parent"
    assert child["workflowId"] == "wf_1"
    info = lineage.lineage("child")
    assert info["parents"][0]["id"] == "parent"
    assert info["children"] == []
    parent_info = lineage.lineage("parent")
    assert "child" in parent_info["children"]


def test_lineage_walk_is_cycle_safe(store):
    store.create_run("a", "x", {"query": "a"})
    store.create_run("b", "x", {"query": "b"})
    lineage = RunLineage(store)
    # A misconfigured cycle must not loop forever.
    lineage.set_run_parent("a", "b")
    lineage.set_run_parent("b", "a")
    info = lineage.lineage("a", max_depth=10)
    assert len(info["parents"]) <= 2


def test_checkpoint_round_trip_and_bounded_payload(store):
    store.create_run("r", "a", {"query": "x"})
    lineage = RunLineage(store)
    lineage.save_checkpoint("r", "agent_step", {"step": 1, "allowlist": [f"t{i}" for i in range(500)]})
    lineage.save_checkpoint("r", "tool_results", {"step": 1, "toolCalls": 2})
    latest = lineage.latest_checkpoint("r")
    assert latest["kind"] == "tool_results"
    assert latest["seq"] == 1
    assert latest["createdAt"]
    # The payload is bounded — a runaway allowlist cannot bloat the table.
    first = lineage.list_checkpoints("r")[0]
    assert len(first["payload"]["allowlist"]) <= 200


def test_bound_checkpoint_payload_caps_pending_calls():
    payload = bound_checkpoint_payload({"pendingToolCalls": list(range(200))})
    assert len(payload["pendingToolCalls"]) == 50


def test_idempotency_key_is_stable_and_scoped():
    a = idempotency_key("r", 1, "c1")
    assert a == idempotency_key("r", 1, "c1")
    assert a != idempotency_key("r", 2, "c1")
    assert a != idempotency_key("other", 1, "c1")


# ── End-to-end: a child run records its parent ───────────────────────────────


@pytest.mark.asyncio
async def test_child_run_records_parent_and_appears_in_lineage(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="answer")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    # Parent row exists first (a real skill invocation is spawned by a parent run).
    store.create_run("parent_run", "eclipse-agent", {"query": "root"})
    result = await graph_module.execute_run(
        _req("child_run", parentRunId="parent_run"), _registry(), FakeBridge(), store,
    )
    assert result.status == "completed"
    assert result.parentRunId == "parent_run"
    child = store.get_run("child_run")
    assert child["parentRunId"] == "parent_run"
    lineage = RunLineage(store)
    assert "child_run" in lineage.lineage("parent_run")["children"]


# ── Checkpoints are written at durable boundaries ────────────────────────────


@pytest.mark.asyncio
async def test_checkpoints_written_at_agent_and_terminal_boundaries(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="final answer")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    result = await graph_module.execute_run(_req("run_ckpt"), _registry(), FakeBridge(), store)
    assert result.status == "completed"
    checkpoints = RunLineage(store).list_checkpoints("run_ckpt")
    kinds = [c["kind"] for c in checkpoints]
    assert "agent_final" in kinds
    assert "terminal_completed" in kinds
    # Every checkpoint is bounded and ordered.
    seqs = [c["seq"] for c in checkpoints]
    assert seqs == sorted(seqs)
