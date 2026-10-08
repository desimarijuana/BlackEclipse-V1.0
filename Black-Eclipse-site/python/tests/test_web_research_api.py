"""HTTP route tests for the web research engine.

Exercises the operator-gated router with the shared `deps.service` patched to a
tmp evidence store, and the engine bridge faked. No network.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeBridge:
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "web_search":
            return {
                "status": "OK",
                "provider": "fake",
                "results": [{"title": "Paris", "url": "https://en.wikipedia.org/wiki/Paris", "snippet": "capital"}],
            }
        if capability == "web_fetch":
            return {
                "status": "OK",
                "url": params.get("url"),
                "title": "Paris",
                "text": "Paris is the capital and largest city of France, a major European cultural centre with a long history.",
            }
        return {"status": "UNAVAILABLE"}


@pytest.fixture
def client(tmp_workspace, monkeypatch):
    from harness import deps
    from harness.persistence import AgentMemoryStore
    from harness.routers import research as research_router
    from harness.service import AgenticService

    service = AgenticService(AgentMemoryStore(os.path.join(tmp_workspace, "agent-memory.db")))
    service.build_bridge = lambda *a, **k: FakeBridge()  # type: ignore[method-assign]
    # The router did `from ..deps import service`, so it holds its own reference;
    # patch the router module's global AND deps so both agree.
    monkeypatch.setattr(research_router, "service", service)
    monkeypatch.setattr(deps, "service", service)

    app = FastAPI()
    app.include_router(research_router.router)
    return TestClient(app)


def test_run_and_get_route(client):
    response = client.post("/research/web/run", json={"question": "What is the capital of France?", "minSources": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    research_id = body["result"]["researchId"]
    assert body["result"]["evidence"]

    got = client.get(f"/research/web/{research_id}")
    assert got.status_code == 200
    assert got.json()["evidence"]

    status = client.get(f"/research/web/{research_id}/status")
    assert status.status_code == 200
    assert status.json()["status"]["state"] in ("COMPLETED", "PARTIAL")


def test_plan_route(client):
    response = client.post("/research/web/plan", json={"question": "Analyze NVIDIA valuation"})
    assert response.status_code == 200
    body = response.json()
    assert body["result"] if "result" in body else body["researchId"]
    assert body["plan"]["queries"]


def test_background_start_route(client, tmp_workspace):
    response = client.post("/research/web/start", json={"question": "What is the capital of France?", "minSources": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["mode"] == "background"
    research_id = body["researchId"]

    # The mandate is persisted synchronously before the task is scheduled, so the
    # run is observable IMMEDIATELY — even though the background task itself is
    # driven by the server event loop (not by this per-request test client).
    got = client.get(f"/research/web/{research_id}")
    assert got.status_code == 200
    assert got.json()["run"]["state"] in ("PLANNING", "SEARCHING", "EXTRACTING", "NORMALIZING",
                                          "VALIDATING", "COMPARING", "VERIFYING", "SYNTHESIZING",
                                          "COMPLETED", "PARTIAL", "FAILED")


def test_unknown_run_is_404(client):
    assert client.get("/research/web/nope").status_code == 404
