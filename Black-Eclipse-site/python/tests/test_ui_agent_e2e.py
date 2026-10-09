"""UI Engineering end-to-end: a natural-language request drives the REAL graph.

This exercises the whole agent path WITHOUT a network model: a scripted chat model
emits `ui_*` tool calls, the real `execute_run` graph executes them through the
real `ToolRegistry`, and the resulting page is committed to the real UI store.
It is the local proof of the Phase 5/7 contract — the agent composes UI state
through its tools — that a live provider run would otherwise be needed to show.
"""

from __future__ import annotations

import os
import re
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.ui.bootstrap import set_ui_service
from harness.ui.catalog import UiCatalog
from harness.ui.service import UiService
from harness.ui.store import UiStore
from harness.ui.tools import register_ui_tools


class _Bridge(DataBridge):
    async def fetch(self, capability, params):  # noqa: ANN001
        return {}


class UiComposeModel:
    """A scripted model that composes a page through the UI tools.

    State is derived from the CONVERSATION (which tool calls have happened), not
    a call counter, so an extra graph invocation cannot desync it. The page id is
    read back out of the tool result, so `ui_add_widget` targets the real page.
    """

    def bind_tools(self, tools):  # noqa: ANN001
        return self

    @staticmethod
    def _state(messages):  # noqa: ANN001
        called: set[str] = set()
        created: str | None = None
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                called.add(call.get("name"))
            content = getattr(message, "content", "")
            if isinstance(content, str) and "uibp" in content:
                found = re.search(r"uibp[_-][A-Za-z0-9-]+", content)
                if found:
                    created = found.group(0)
        return called, created

    async def ainvoke(self, messages):  # noqa: ANN001
        called, created = self._state(messages)
        if "ui_classify_request" not in called:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": "ui_classify_request", "args": {"text": "create a dashboard page and add a metric card"}}])
        if "ui_create_page" not in called:
            return AIMessage(content="", tool_calls=[{"id": "c2", "name": "ui_create_page", "args": {"title": "Ops Dashboard"}}])
        if created and "ui_add_widget" not in called:
            return AIMessage(content="", tool_calls=[{"id": "c3", "name": "ui_add_widget", "args": {"blueprintId": created, "componentId": "metric-card"}}])
        return AIMessage(content="Created the page and added a metric card.")

    async def astream(self, messages):  # noqa: ANN001
        message = await self.ainvoke(messages)
        yield message


@pytest.fixture()
def ui_service():
    directory = tempfile.mkdtemp(prefix="be-ui-e2e-")
    memory = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    service = UiService(UiStore(memory), UiCatalog(), tasks=None)
    set_ui_service(service)
    yield memory, service
    set_ui_service(None)
    memory.close()


def _request() -> RunRequest:
    return RunRequest(
        runId="run_ui",
        input=RunInput(query="create a dashboard page and add a metric card"),
        agentId="eclipse-agent",
        modelSettings=ModelSettings(provider="ollama", model="llama3.1", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


@pytest.mark.asyncio
async def test_natural_language_request_composes_and_persists(ui_service, monkeypatch):
    memory, ui = ui_service
    model = UiComposeModel()
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    registry = ToolRegistry()
    register_ui_tools(registry)

    result = await graph_module.execute_run(
        _request(), registry, _Bridge(), memory, ui_service=ui,
    )
    assert result.status == "completed"
    assert result.toolCalls == 3
    assert result.toolErrors == 0

    # The real state exists: a page with one metric-card instance, persisted.
    listing = ui.list_blueprints()
    assert listing["total"] == 1
    blueprint_id = listing["blueprints"][0]["id"]
    instances = ui.get_current_page(blueprint_id=blueprint_id)["instances"]
    assert [i["componentId"] for i in instances] == ["metric-card"]

    # A fresh service over the SAME db sees the same page (durable).
    reopened = UiService(UiStore(memory), UiCatalog())
    assert reopened.list_blueprints()["total"] == 1
