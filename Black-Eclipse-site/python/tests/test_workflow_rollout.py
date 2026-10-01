"""Harness closeout Phase 9: flag-gated rollout + rollback.

  * The workflow path is DISABLED by default (`HARNESS_WORKFLOWS_ENABLED` unset).
  * A run with no `workflowId` behaves exactly as today (the ordinary path) —
    this is the rollback path, and it must be exercised.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.service import _workflow_enabled
from harness.tools import DataBridge, ToolRegistry


class _Model:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="plain answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-rollout-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def test_workflow_path_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_WORKFLOWS_ENABLED", raising=False)
    assert _workflow_enabled() is False
    monkeypatch.setenv("HARNESS_WORKFLOWS_ENABLED", "1")
    assert _workflow_enabled() is True


def test_a_run_with_no_workflow_id_is_unchanged(store, monkeypatch):
    """The rollback path: no workflowId ⇒ today's single-agent behaviour."""
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: _Model())
    request = RunRequest(
        runId="plain_run",
        input=RunInput(query="hello"),
        agent=AgentConfig(id="a", name="A", systemPrompt="s", tools=[], maxSteps=2),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    registry = ToolRegistry()
    result = asyncio.run(graph_module.execute_run(request, registry, _Bridge(), store))
    assert result.status == "completed"
    assert result.output == "plain answer"
    # No workflow lineage was recorded — the run is a plain single-agent run.
    run = store.get_run("plain_run")
    assert run["workflowId"] is None
    assert run["parentRunId"] is None
