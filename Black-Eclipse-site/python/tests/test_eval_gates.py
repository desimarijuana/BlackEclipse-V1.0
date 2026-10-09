"""Eval gates: the offline closeout gates run and pass, and the route is wired.

`harness/eval_gates/` was previously reachable only from the offline eval CLI.
These tests pin the Python gates (deterministic, offline) and the operator route
that runs them on demand.

The route test mounts ONLY the eval-gates router on a minimal app and overrides
the operator dependency, so it never constructs an `AgenticService` (which would
install process-wide services and leak into other test modules).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.deps import require_operator
from harness.routers.eval_gates import router as eval_gates_router


def test_python_eval_gates_pass():
    from harness.eval_gates import resume, route_health, workflow

    # Each gate raises AssertionError/Exception on failure; running them is the
    # assertion (the offline fixtures are deterministic).
    route_health.run_gate()
    workflow.run_gate()
    resume.run_gate()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(eval_gates_router)
    app.dependency_overrides[require_operator] = lambda: True
    return TestClient(app)


def test_eval_gates_route_runs_gates(client, monkeypatch):
    import harness.eval_gates as eg

    calls = {"n": 0}

    def _fake():
        calls["n"] += 1
        return [
            {"name": "route_health", "passed": True, "failures": []},
            {"name": "workflow", "passed": True, "failures": []},
        ]

    monkeypatch.setattr(eg, "run_gates", _fake)
    response = client.get("/eval/gates")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["total"] == 2
    assert calls["n"] == 1


def test_eval_gates_route_reports_failure(client, monkeypatch):
    import harness.eval_gates as eg

    monkeypatch.setattr(eg, "run_gates", lambda: [
        {"name": "workflow", "passed": False, "failures": ["boom"]},
    ])
    body = client.get("/eval/gates").json()
    assert body["success"] is False
    assert body["gates"][0]["failures"] == ["boom"]
