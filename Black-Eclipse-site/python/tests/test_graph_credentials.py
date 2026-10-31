"""Run-scoped credential re-resolution for durable graph jobs."""

from __future__ import annotations

import pytest

from harness.graph_runtime import service as service_module
from harness.graph_runtime.service import GraphService


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _Client:
    calls: list[tuple[str, dict, dict]] = []
    response = _Response(200, {"modelSettings": {"provider": "ollama", "model": "llama3"}})

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def post(self, url, headers=None, json=None):
        type(self).calls.append((url, dict(headers or {}), dict(json or {})))
        return type(self).response


@pytest.fixture(autouse=True)
def _fake_http(monkeypatch):
    _Client.calls = []
    _Client.response = _Response(200, {"modelSettings": {"provider": "ollama", "model": "llama3"}})
    monkeypatch.setattr(service_module.httpx, "Client", _Client)
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    yield


def test_resolves_the_vault_from_the_persisted_callback_url():
    service = GraphService(object(), registry=object())  # type: ignore[arg-type]
    settings = service._resolve_model_settings(
        "grun_1", {"callbackBaseUrl": "http://127.0.0.1:3000"},
    )
    assert settings == {"provider": "ollama", "model": "llama3"}
    url, headers, body = _Client.calls[0]
    assert url == "http://127.0.0.1:3000/api/graph-runs/grun_1/credentials"
    assert headers["Authorization"] == "Bearer test-secret"
    assert headers["X-Harness-Operator"] == "test-secret"
    assert body == {}


def test_a_non_200_is_no_credentials_not_a_fabricated_config():
    _Client.response = _Response(403, {"error": "operator authorization required"})
    service = GraphService(object(), registry=object())  # type: ignore[arg-type]
    assert service._resolve_model_settings("grun_2", {"callbackBaseUrl": "http://x"}) is None


def test_a_transport_error_is_swallowed_and_the_node_fails_honestly(monkeypatch):
    class _Broken(_Client):
        def post(self, url, headers=None, json=None):
            raise ConnectionError("front door is down")

    monkeypatch.setattr(service_module.httpx, "Client", _Broken)
    service = GraphService(object(), registry=object())  # type: ignore[arg-type]
    assert service._resolve_model_settings("grun_3", {"callbackBaseUrl": "http://x"}) is None
