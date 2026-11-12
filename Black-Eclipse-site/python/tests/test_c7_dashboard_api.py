"""C7: release-report + SLO dashboard endpoints, and escaped rendering."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.dashboard import render_dashboard
from harness.observability.integration import RunEventProjector


class _StubService:
    def __init__(self, hub):
        self.observability = hub


@pytest.fixture()
def client(monkeypatch):
    from harness.routers import observability as obs_router

    hub = ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )
    projector = RunEventProjector(hub)
    base = 1000.0
    projector.handle({"type": "run.created", "runId": "r1", "at": base, "data": {}})
    projector.handle({"type": "step.started", "runId": "r1", "at": base,
                      "data": {"step": 1, "stepId": "r1:step:1"}})
    projector.handle({"type": "step.completed", "runId": "r1", "at": base + 0.1,
                      "data": {"step": 1, "stepId": "r1:step:1", "status": "ok"}})
    projector.handle({"type": "run.completed", "runId": "r1", "at": base + 0.2,
                      "data": {"steps": 1}})
    monkeypatch.setattr(obs_router, "service", _StubService(hub))

    app = FastAPI()
    app.include_router(obs_router.router)
    with TestClient(app) as test_client:
        yield test_client, hub


def test_release_report_exposes_the_gate_input(client):
    http, _ = client
    response = http.get("/observability/release-report")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["runs"]["created"] == 1
    assert body["runs"]["terminal"] == 1
    assert "slos" in body
    assert "failures" in body


def test_dashboard_renders_one_card_per_slo(client):
    http, hub = client
    response = http.get("/observability/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Observability — SLOs that bite" in body
    for name in ("terminal_correctness", "run_p95_latency", "orphan_rate"):
        assert name in body
    assert "error budget" in body


def test_dashboard_escapes_labels():
    report = {
        "generatedAt": "now",
        "runs": {"created": 1, "terminal": 1, "completed": 1, "failed": 0, "cancelled": 0,
                 "orphaned": 0, "active": 0},
        "latency": {"samples": 1, "p50": 1, "p95": 2, "p99": 3},
        "resume": {"samples": 0, "p95": None},
        "cost": {"samples": 0, "totalUsd": 0, "perTaskP50": None, "perTaskP95": None,
                 "unpricedRuns": 0},
        "tools": {"calls": 0, "errors": 0},
        "failures": {"<script>alert(1)</script>": 1},
        "slos": {"objectives": [{
            "name": "<img src=x onerror=alert(1)>", "kind": "ratio", "target": 0.99,
            "healthy": True, "compliance": 1.0, "total": 1, "good": 1,
            "errorBudgetRemaining": 1.0, "burnRate": 0.0, "description": "<b>x</b>",
        }]},
    }
    html = render_dashboard(report)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
