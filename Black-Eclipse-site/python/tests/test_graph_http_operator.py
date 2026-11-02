"""Operator-run envelope + the HTTP node: network is denied by default, and an
explicit grant still passes SSRF/size/timeout checks."""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime import http_client
from harness.graph_runtime import nodes as graph_nodes
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None, version="1.0.0"):
    return {"id": node_id, "type": node_type, "version": version, "config": config or {}, "layout": {"x": 0, "y": 0}}


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


def _exec(config: dict, inputs: dict | None = None, version: str = "1.0.0"):
    definition = REGISTRY.get("integration.http", version)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="http", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config, node_version=version,
    ))


class _Headers:
    def __init__(self, content_type="application/json", extra: dict | None = None):
        self._content_type = content_type
        self._extra = dict(extra or {})

    def get_content_type(self):
        return self._content_type

    def items(self):
        return [("Content-Type", self._content_type), *self._extra.items()]


class _Response:
    def __init__(self, body: bytes, status: int = 200, content_type="application/json", extra=None):
        self._body = body
        self.status = status
        self.headers = _Headers(content_type, extra)

    def read(self, size=-1):
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Opener:
    """A deterministic transport: one handler called once per hop."""

    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return self.handler(request, timeout)


def _use(monkeypatch, handler):
    opener = _Opener(handler)
    monkeypatch.setattr(http_client, "_OPENER", opener)
    return opener


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

    def handler(request, timeout):
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _Response(json.dumps({"ok": True}).encode())

    _use(monkeypatch, handler)
    result = _exec({"url": "https://example.com/api", "method": "GET"})
    assert result == {"status": 200, "body": {"ok": True}}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://example.com/api"
    assert captured["timeout"] == 10.0


def test_http_v1_1_returns_the_richer_outputs(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    _use(monkeypatch, lambda _request, _timeout: _Response(
        b'{"ok": true}', extra={"X-Request-Id": "abc"},
    ))
    result = _exec({"url": "https://example.com/api"}, version="1.1.0")
    assert result["status"] == 200
    assert result["ok"] is True
    assert result["body"] == {"ok": True}
    assert result["headers"]["x-request-id"] == "abc"
    assert result["contentType"] == "application/json"
    assert result["truncated"] is False
    assert isinstance(result["durationMs"], int)


def test_http_post_sends_the_input_body(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    captured = {}

    def handler(request, _timeout):
        captured["method"] = request.get_method()
        captured["body"] = request.data
        return _Response(json.dumps({"accepted": True}).encode(), status=201)

    _use(monkeypatch, handler)
    result = _exec(
        {"url": "https://example.com/api", "method": "POST"},
        {"body": {"query": "AAPL"}},
    )
    assert result["status"] == 201
    assert json.loads(captured["body"].decode()) == {"query": "AAPL"}
    assert captured["method"] == "POST"


def test_http_sends_custom_plain_headers(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    captured = {}

    def handler(request, _timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return _Response(b"{}")

    _use(monkeypatch, handler)
    _exec({
        "url": "https://example.com/api",
        "method": "GET",
        "headersJson": json.dumps({"X-Tenant": "desk-1"}),
    })
    assert captured["headers"]["x-tenant"] == "desk-1"


def test_http_merges_query_params(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    captured = {}

    def handler(request, _timeout):
        captured["url"] = request.full_url
        return _Response(b"{}")

    _use(monkeypatch, handler)
    _exec({
        "url": "https://example.com/api?keep=1",
        "queryJson": json.dumps({"q": "aapl", "tag": ["a", "b"]}),
    })
    assert captured["url"] == "https://example.com/api?keep=1&q=aapl&tag=a&tag=b"


def test_http_refuses_credential_or_transport_headers(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    with pytest.raises(ValueError, match="credentials"):
        _exec({"url": "https://example.com/api", "headersJson": '{"Authorization": "Bearer x"}'})
    with pytest.raises(ValueError, match="transport"):
        _exec({"url": "https://example.com/api", "headersJson": '{"Host": "evil"}'})
    with pytest.raises(ValueError, match="not valid JSON"):
        _exec({"url": "https://example.com/api", "headersJson": "{not json"})


def test_http_resolves_credential_env_references(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    monkeypatch.setenv("TEST_API_TOKEN", "secret-value")
    captured = {}

    def handler(request, _timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return _Response(b"{}")

    _use(monkeypatch, handler)
    _exec({
        "url": "https://example.com/api",
        "credentialEnvJson": json.dumps({"Authorization": "TEST_API_TOKEN"}),
    })
    assert captured["headers"]["authorization"] == "secret-value"

    monkeypatch.delenv("TEST_API_TOKEN")
    with pytest.raises(ValueError, match="TEST_API_TOKEN"):
        _exec({
            "url": "https://example.com/api",
            "credentialEnvJson": json.dumps({"Authorization": "TEST_API_TOKEN"}),
        })


def test_http_refuses_ambiguous_header_sources(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    monkeypatch.setenv("TEST_API_TOKEN", "secret-value")
    with pytest.raises(ValueError, match="both"):
        _exec({
            "url": "https://example.com/api",
            "headersJson": json.dumps({"X-Tenant": "plain"}),
            "credentialEnvJson": json.dumps({"x-tenant": "TEST_API_TOKEN"}),
        })


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
    _use(monkeypatch, lambda _request, _timeout: _Response(b"x" * (http_client.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(ValueError, match="exceeds"):
        _exec({"url": "https://example.com/big"})


def test_http_truncates_an_oversized_response_when_asked(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    _use(monkeypatch, lambda _request, _timeout: _Response(b"x" * 1_500))
    result = _exec(
        {"url": "https://example.com/big", "maxResponseBytes": 1_000, "onOversize": "truncate"},
        version="1.1.0",
    )
    assert result["truncated"] is True
    assert len(result["body"]) == 1_000


def test_http_rechecks_every_redirect_hop(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    _use(monkeypatch, lambda _request, _timeout: _Response(
        b"", status=302, extra={"Location": "https://127.0.0.1/secret"},
    ))
    with pytest.raises(ValueError, match="loopback"):
        _exec({
            "url": "https://example.com/api",
            "followRedirects": True,
            "maxRedirects": 3,
        }, version="1.1.0")


def test_http_refuses_https_to_http_downgrade(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    _use(monkeypatch, lambda _request, _timeout: _Response(
        b"", status=302, extra={"Location": "http://example.com/next"},
    ))
    with pytest.raises(ValueError, match="downgrade"):
        _exec({
            "url": "https://example.com/api",
            "followRedirects": True,
        }, version="1.1.0")


def test_http_retries_a_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    monkeypatch.setattr(http_client.time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def handler(_request, _timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return _Response(b"slow down", status=429)
        return _Response(b'{"ok":true}')

    _use(monkeypatch, handler)
    result = _exec({"url": "https://example.com/api", "retries": 2}, version="1.1.0")
    assert calls["n"] == 3
    assert result["status"] == 200


def test_http_fails_on_4xx_when_asked(monkeypatch):
    monkeypatch.setattr("harness.mcp.ssrf.check_outbound_url", lambda _url: (True, None))
    _use(monkeypatch, lambda _request, _timeout: _Response(b'{"error":"nope"}', status=404))
    with pytest.raises(ValueError, match="HTTP 404"):
        _exec({"url": "https://example.com/api", "failOnHttpError": True}, version="1.1.0")


def test_webhook_trigger_emits_verified_context():
    definition = REGISTRY.get("trigger.webhook", "1.0.0")
    assert definition is not None and definition.executor is not None
    result = definition.executor(NodeExecContext(
        node_id="hook", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={}, run_input={"hello": "world"},
        trigger_context={
            "body": {"hello": "world"},
            "headers": {"content-type": "application/json"},
            "query": {"source": "stripe"},
            "method": "POST",
            "receivedAt": "2026-11-01T12:00:00+00:00",
            "webhookId": "wh_1",
            "deliveryId": "evt_1",
            "signatureVerified": True,
        },
    ))
    assert result["start"] == {"hello": "world"}
    assert result["method"] == "POST"
    assert result["query"] == {"source": "stripe"}
    assert result["meta"]["signatureVerified"] is True
    assert result["receivedAt"].startswith("2026-11-01")


def test_webhook_trigger_still_emits_a_datetime_without_context():
    definition = REGISTRY.get("trigger.webhook", "1.0.0")
    assert definition is not None and definition.executor is not None
    result = definition.executor(NodeExecContext(
        node_id="hook", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={}, run_input={"hello": "test"},
    ))
    assert result["start"] == {"hello": "test"}
    assert result["method"] == "POST"
    assert result["meta"]["webhookId"] == ""
    # ISO-8601, so the declared datetime port validates.
    assert "T" in result["receivedAt"]
