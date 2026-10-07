"""HTTP route tests for browser observability (Phase 8).

Exercises the operator-gated `/browser/telemetry`, `/browser/cost`,
`/browser/logs` and `/browser/traces/{id}/replay` routes against a stub manager
(no browser, no database). The routes are thin adapters, so a stub is enough to
pin their contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.browser.telemetry import BrowserTelemetry


class _StubStore:
    def __init__(self, trace: dict[str, Any] | None) -> None:
        self._trace = trace

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        if self._trace and self._trace.get("id") == trace_id:
            return self._trace
        return None

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        return []


class _StubManager:
    def __init__(self, telemetry: BrowserTelemetry, trace: dict[str, Any] | None = None) -> None:
        self._telemetry = telemetry
        self.store = _StubStore(trace)

    def telemetry_snapshot(self) -> dict[str, Any]:
        return self._telemetry.snapshot()

    def telemetry_cost(self) -> dict[str, Any]:
        return self._telemetry.cost()

    def recent_logs(self, **filters: Any) -> list[dict[str, Any]]:
        return self._telemetry.logs(**filters)

    def active_count(self) -> int:
        return 0

    def capabilities(self) -> dict[str, Any]:
        return {"enabled": True, "defaultProvider": "local_chromium", "providers": []}

    def list_sessions(self) -> list[dict[str, Any]]:
        return []


class _StubRegistry:
    def names(self) -> list[str]:
        return ["browser_replay"]


class _StubService:
    def __init__(self, manager: _StubManager) -> None:
        self.browser = manager
        self.registry = _StubRegistry()


@pytest.fixture
def client(monkeypatch):
    from harness.routers import browser as browser_router

    telemetry = BrowserTelemetry()
    telemetry.session_opened("local_chromium", session_id="s1")
    telemetry.record_action("navigate", provider="local_chromium", duration_ms=50, ok=True)
    telemetry.record_action("click", provider="local_chromium", duration_ms=50, ok=False, error_code="BROWSER_TIMEOUT")
    trace = {
        "id": "btrace_x", "sessionId": "s1", "provider": "local_chromium", "status": "completed",
        "summary": {"stepCount": 1},
        "steps": [{"index": 0, "action": "click", "provider": "local_chromium", "durationMs": 10,
                   "params": {}, "observation": {}, "verification": {},
                   "error": {"code": "BROWSER_TIMEOUT", "message": "t"}}],
    }
    service = _StubService(_StubManager(telemetry, trace))
    monkeypatch.setattr(browser_router, "service", service)

    app = FastAPI()
    app.include_router(browser_router.router)
    return TestClient(app), browser_router


def test_telemetry_route_reports_aggregates(client):
    c, _ = client
    response = c.get("/browser/telemetry")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["sessions"]["created"] == 1
    assert body["actions"]["calls"] == 2
    assert body["actions"]["timeouts"] == 1


def test_cost_route_is_measurement_first(client):
    c, _ = client
    body = c.get("/browser/cost").json()
    assert body["success"] is True
    assert body["ratesConfigured"] is False
    assert body["estimatedMicros"] is None
    assert "measurements" in body


def test_logs_route_filters_by_code(client):
    c, _ = client
    body = c.get("/browser/logs", params={"code": "TIMEOUT"}).json()
    assert body["success"] is True
    assert all("TIMEOUT" in entry["code"] for entry in body["logs"])


def test_replay_route_renders_a_timeline(client):
    c, _ = client
    body = c.get("/browser/traces/btrace_x/replay").json()
    assert body["success"] is True
    assert body["replay"]["failureAnalysis"]["stepIndex"] == 0
    assert "btrace_x" in body["text"]


def test_replay_route_404s_for_unknown_trace(client):
    c, _ = client
    assert c.get("/browser/traces/nope/replay").status_code == 404


def test_health_block_includes_telemetry_summary(client):
    c, browser_router = client
    health = browser_router.browser_health()
    assert health["available"] is True
    assert health["telemetry"]["actionCalls"] == 2
    assert health["telemetry"]["timeouts"] == 1
