"""Chat workflow authoring — the `create_workflow` bridge to the front door.

The tool never writes JDDS itself: it posts an objective to
`/api/workflows/generate`, which plans + validates + saves through the SAME
planner and store the gallery uses. These tests pin the contract: required
objective, honest failure, and the created id/name surfaced back to the model.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from harness.graph_tools import (
    TOOL_NAME,
    create_workflow_handler,
    make_graph_authorizer,
    register_graph_tools,
)
from harness.tools import ToolRegistry


class _Response:
    def __init__(self, body, status: int = 201) -> None:
        self._body = body
        self.status_code = status
        self.content = b"{}"

    def json(self):
        return self._body


class _Client:
    calls: list[dict] = []
    response: _Response = _Response({})

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json, "headers": headers or {}})
        return type(self).response


def _run(handler, args):
    return asyncio.run(handler(args, SimpleNamespace()))


def test_tool_is_registered_once():
    registry = ToolRegistry()
    assert register_graph_tools(registry) == [TOOL_NAME]
    assert registry.get(TOOL_NAME) is not None
    assert register_graph_tools(registry) == []


def test_short_objective_is_refused_without_a_request(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr("harness.graph_tools.httpx.AsyncClient", _Client)
    text, data = _run(create_workflow_handler, {"objective": "hi"})
    assert data["created"] is False
    assert "NOT CREATED" in text
    assert _Client.calls == []


def test_created_workflow_returns_id_name_and_counts(monkeypatch):
    _Client.calls = []
    _Client.response = _Response({
        "workflow": {"id": "wf_abc", "name": "AAPL momentum", "description": "d"},
        "plan": {"nodeCount": 4, "edgeCount": 3, "executionMode": "research", "warnings": []},
    })
    monkeypatch.setattr("harness.graph_tools.httpx.AsyncClient", _Client)
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("CRON_SECRET", "s3cret")

    text, data = _run(create_workflow_handler, {
        "objective": "Fetch AAPL daily bars, compute an SMA z-score and report it.",
        "name": "AAPL momentum",
    })

    assert data["created"] is True
    assert data["workflowId"] == "wf_abc"
    assert data["name"] == "AAPL momentum"
    assert data["nodeCount"] == 4
    assert "AAPL momentum" in text
    assert "wf_abc" in text

    call = _Client.calls[0]
    assert call["url"] == "http://127.0.0.1:3000/api/workflows/generate"
    assert call["json"]["objective"].startswith("Fetch AAPL")
    assert call["json"]["name"] == "AAPL momentum"
    assert call["headers"]["Authorization"] == "Bearer s3cret"


def test_rejected_plan_is_an_honest_failure(monkeypatch):
    _Client.calls = []
    _Client.response = _Response(
        {"error": 'node "x" has an invalid config: period must be > 0'},
        status=422,
    )
    monkeypatch.setattr("harness.graph_tools.httpx.AsyncClient", _Client)

    text, data = _run(create_workflow_handler, {
        "objective": "Build a workflow with an invalid indicator config.",
    })

    assert data["created"] is False
    assert "NOT CREATED" in text
    assert "invalid config" in text


def test_unreachable_app_is_an_honest_failure(monkeypatch):
    class _Broken:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise OSError("connection refused")

    monkeypatch.setattr("harness.graph_tools.httpx.AsyncClient", _Broken)
    text, data = _run(create_workflow_handler, {
        "objective": "Build a workflow that reports the latest quote.",
    })
    assert data["created"] is False
    assert data["error"] == "app_unavailable"
    assert "did not answer" in text


def test_authorizer_admits_only_create_workflow():
    auth = make_graph_authorizer()

    async def run(name):
        return await auth(SimpleNamespace(name=name), {}, None)

    assert asyncio.run(run("create_workflow")) is True
    assert asyncio.run(run("something_else")) is False
