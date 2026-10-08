"""API tests — the `/observability/*` operator-gated route group."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub


class _StubService:
    def __init__(self, hub):
        self.observability = hub


@pytest.fixture
def client(monkeypatch):
    from harness.routers import observability as obs_router

    hub = ObservabilityHub(ObservabilityConfig(jsonl_dir=""), capture_inmemory=True, start_exporters=False)
    hub.emit("onRunStart", name="eclipse.run")
    with hub.span("eclipse.run", kind="server", attributes={"messages": 3}):
        with hub.span("eclipse.tool.web_search", kind="tool"):
            pass
    hub.emit("onLLMEnd", provider="openai", model="gpt-4o-mini", status="OK",
             duration_ms=120.0, tokens={"input": 100, "output": 50, "total": 150})
    hub.emit("onLLMError", provider="openai", model="gpt-4o-mini",
             error_type="Timeout", error_message="timed out")
    stub = _StubService(hub)
    monkeypatch.setattr(obs_router, "service", stub)

    app = FastAPI()
    app.include_router(obs_router.router)
    with TestClient(app) as test_client:
        yield test_client, hub


def test_status_and_config(client):
    http, _ = client
    status = http.get("/observability/status").json()
    assert status["success"] is True
    assert status["service"] == "eclipse-harness"
    config = http.get("/observability/config").json()
    assert config["captureMode"] == "SUMMARY"
    assert "problems" in config


def test_metrics_and_prometheus(client):
    http, _ = client
    metrics = http.get("/observability/metrics").json()
    assert "counters" in metrics
    prom = http.get("/observability/metrics/prometheus")
    assert prom.status_code == 200
    assert "eclipse_llm_cost_usd_total" in prom.text or "eclipse_llm_requests_total" in prom.text


def test_traces_and_trajectory(client):
    http, hub = client
    trace_ids = http.get("/observability/traces").json()["traceIds"]
    assert trace_ids
    trace_id = trace_ids[0]
    trace = http.get(f"/observability/traces/{trace_id}").json()
    assert len(trace["spans"]) >= 1
    trajectory = http.get(f"/observability/traces/{trace_id}/trajectory").json()
    assert trajectory["found"] is True
    assert trajectory["roots"][0]["name"] == "eclipse.run"


def test_errors_costs_health_slos(client):
    http, _ = client
    errors = http.get("/observability/errors").json()["errors"]
    assert errors and errors[0]["errorType"] == "Timeout"
    costs = http.get("/observability/costs").json()
    assert costs["total"]["requests"] >= 1
    health = http.get("/observability/health").json()
    assert "subsystems" in health
    slos = http.get("/observability/slos").json()
    assert "objectives" in slos


def test_diagnostics_and_missing_trace(client):
    http, _ = client
    diagnostics = http.get("/observability/diagnostics").json()
    assert "exporters" in diagnostics
    assert "observedHooks" in diagnostics
    missing = http.get("/observability/traces/deadbeef")
    assert missing.status_code == 404
