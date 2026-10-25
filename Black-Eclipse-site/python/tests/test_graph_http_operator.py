"""Operator-run envelope + the HTTP node: network is denied by default, and an
explicit grant still passes SSRF/size/timeout checks."""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime import nodes as graph_nodes
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir():
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_http", "name": "HTTP",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual"),
            _node("http", "integration.http", {"url": "https://example.com/api", "method": "GET"}),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "http", "body"),
            _edge("e2", "http", "body", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["network.egress"],
    })


def _exec(config: dict, inputs: dict | None = None):
    definition = REGISTRY.get("integration.http")
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="http", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config,
    ))


class _Headers:
    def __init__(self, content_type="application/json"):
        self._content_type = content_type

    def get_content_type(self):
        return self._content_type


class _Response:
    def __init__(self, body: bytes, status: int = 200, content_type="application/json"):
        self._body = body
        self.status = status
        self.headers = _Headers(content_type)

    def read(self, size=-1):
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_network_is_denied_in_a_test_run_and_allowed_with_a_grant():
    denied = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "permission_denied" for d in denied.diagnostics)

    allowed = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(
            test_run=False,
            granted_capabilities=frozenset({"network.egress"}),
            allow_network=True,
        ),
    )
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]


def test_http_get_returns_json(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _Response(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(graph_nodes.urllib.request, "urlopen", fake_urlopen)
    result = _exec({"url": "https://example.com/api", "method": "GET"})
    assert result == {"status": 200, "body": {"ok": True}}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.com/api"


def test_http_post_sends_the_input_body(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.get_method()
        captured["body"] = request.data
        return _Response(json.dumps({"accepted": True}).encode(), status=201)

    monkeypatch.setattr(graph_nodes.urllib.request, "urlopen", fake_urlopen)
    result = _exec(
        {"url": "https://example.com/api", "method": "POST"},
        {"body": {"query": "AAPL"}},
    )
    assert result["status"] == 201
    assert json.loads(captured["body"].decode()) == {"query": "AAPL"}
    assert captured["method"] == "POST"


def test_http_refuses_blocked_and_loopback_urls(monkeypatch):
    monkeypatch.setattr(
        "harness.mcp.ssrf.check_outbound_url",
        lambda _url: (False, "Blocked private host"),
    )
    with pytest.raises(ValueError, match="blocked URL"):
        _exec({"url": "https://127.0.0.1/api"})

    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    with pytest.raises(ValueError, match="loopback"):
        _exec({"url": "http://localhost:3000/api"})


def test_http_refuses_an_oversized_response(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    monkeypatch.setattr(
        graph_nodes.urllib.request, "urlopen",
        lambda request, timeout: _Response(b"x" * (graph_nodes.MAX_HTTP_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(ValueError, match="exceeds"):
        _exec({"url": "https://example.com/big"})
