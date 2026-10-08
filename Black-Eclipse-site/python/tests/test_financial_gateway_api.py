"""Financial Data Gateway route tests — `GET /financial/providers`.

Thin route over the SAME provider registry the layer and the agent tool use.
No credentials ever cross: the route reports presence only, and the registry holds
references, not values.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness import deps
from harness.routers import financial as financial_router
from harness.service import AgenticService
from harness.persistence import AgentMemoryStore


def _client(tmp_path, monkeypatch) -> TestClient:
    service = AgenticService(AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db")))
    service.provider_registry = __import__(
        "harness.retrieval.registry", fromlist=["build_default_registry"]
    ).build_default_registry()
    monkeypatch.setattr(financial_router, "service", service)
    monkeypatch.setattr(deps, "service", service)
    app = FastAPI()
    app.include_router(financial_router.router)
    return TestClient(app)


def test_providers_route_lists_registry(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/financial/providers")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "OK"
    ids = {p["id"] for p in body["providers"]}
    assert {"JDDS", "LIVE_STRUCTURED", "SEC", "WEB", "CRYPTO"} <= ids
    # A declared provider is present but honestly not implemented.
    assert any(p["id"] == "POLYGON" and p["implemented"] is False for p in body["providers"])
    # No credential VALUE ever appears — only a reference.
    for p in body["providers"]:
        assert "apiKey" not in p
        assert "value" not in p


def test_providers_route_filters_by_capability(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    res = client.get("/financial/providers", params={"capability": "crypto_market_data"})
    assert res.status_code == 200
    body = res.json()
    assert body["capability"] == "crypto_market_data"
    assert all("crypto_market_data" in p["capabilities"] for p in body["providers"])
