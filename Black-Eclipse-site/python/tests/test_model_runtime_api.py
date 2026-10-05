"""Model Runtime HTTP API tests (the read-only inspection routes).

These hit the FastAPI app's `/model-runtime/*` surface with the operator token
the same way the TS front door does. No provider is called; `/route` is pure
routing computation. The suite must never depend on a network.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolate the harness DB so a test never writes the repo's agent-memory.db.
    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", str(tmp_path / "agent-memory.db"))
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    from harness.main import app

    # The model runtime is a process-wide singleton; reset so persistence wiring
    # for a previous test's store does not leak.
    from harness import model_runtime

    model_runtime.set_runtime(None)
    with TestClient(app) as test_client:
        yield test_client
    model_runtime.set_runtime(None)


def _operator_headers() -> dict[str, str]:
    """The runtime accepts a loopback/TCP client without a token in tests."""
    token = os.environ.get("HARNESS_OPERATOR_TOKEN") or os.environ.get("CRON_SECRET")
    return {"X-Harness-Operator": token} if token else {}


def test_providers_lists_catalog_without_credentials(client: TestClient) -> None:
    res = client.get("/model-runtime/providers", headers=_operator_headers())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    ids = {p["id"] for p in body["providers"]}
    assert {"openai", "anthropic", "google", "ollama"}.issubset(ids)
    # No provider payload may ever contain a key-shaped field.
    for provider in body["providers"]:
        assert "apiKey" not in provider
        assert "api_key" not in provider


def test_models_returns_normalized_models(client: TestClient) -> None:
    res = client.get("/model-runtime/models", headers=_operator_headers())
    assert res.status_code == 200, res.text
    models = res.json()["models"]
    assert models
    sample = models[0]
    assert "capabilities" in sample and "states" in sample["capabilities"]
    assert "pricing" in sample
    # Unknown pricing must never be fabricated to a number.
    assert sample["pricing"]["kind"] in {
        "per_token", "per_request", "free", "unknown", "custom",
    }


def test_models_filter_by_provider(client: TestClient) -> None:
    res = client.get("/model-runtime/models?provider=openai", headers=_operator_headers())
    assert res.status_code == 200
    models = res.json()["models"]
    assert models and all(m["providerId"] == "openai" for m in models)


def test_routing_lists_profiles_and_aliases(client: TestClient) -> None:
    res = client.get("/model-runtime/routing", headers=_operator_headers())
    assert res.status_code == 200, res.text
    body = res.json()
    assert "financial_research" in body["taskProfiles"]
    assert "eclipse-reasoning" in body["aliases"]


def test_route_is_pure_and_explains_the_choice(client: TestClient) -> None:
    res = client.post(
        "/model-runtime/route",
        json={"task": "coding"},
        headers=_operator_headers(),
    )
    assert res.status_code == 200, res.text
    decision = res.json()["decision"]
    assert decision["selected"] is not None
    assert decision["reason"]
    assert isinstance(decision["candidates"], list)
    # The trace must include per-candidate exclusion reasons for the debug view.
    assert any(c["excludedReason"] for c in decision["candidates"]) or decision["candidates"]


def test_route_with_explicit_model_honours_the_override(client: TestClient) -> None:
    res = client.post(
        "/model-runtime/route",
        json={"model": "openai/gpt-4o"},
        headers=_operator_headers(),
    )
    assert res.status_code == 200, res.text
    decision = res.json()["decision"]
    assert decision["selected"]["model"] == "openai/gpt-4o"
    assert "Explicit" in decision["reason"]


def test_health_and_usage_shapes(client: TestClient) -> None:
    health = client.get("/model-runtime/health", headers=_operator_headers())
    assert health.status_code == 200
    assert "providers" in health.json()

    usage = client.get("/model-runtime/usage", headers=_operator_headers())
    assert usage.status_code == 200
    body = usage.json()
    assert "requests" in body and "totalTokens" in body


def test_discover_unknown_provider_is_404(client: TestClient) -> None:
    res = client.post(
        "/model-runtime/providers/not-a-provider/discover",
        json={"baseUrl": "http://localhost:9/v1"},
        headers=_operator_headers(),
    )
    assert res.status_code == 404


def test_discover_reports_failure_honestly(client: TestClient) -> None:
    # A local server that is not listening must yield ok:false with a reason and
    # an empty model list — never a silent empty success.
    res = client.post(
        "/model-runtime/providers/ollama/discover",
        json={"baseUrl": "http://127.0.0.1:9/v1"},
        headers=_operator_headers(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["ok"] is False
    assert body["models"] == []
    assert body["detail"]
