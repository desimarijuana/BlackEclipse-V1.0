"""The execution HTTP router — transport seam + a real end-to-end round trip."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.execution.service import ExecutionService
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def app(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(project))
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    layer = ExecutionService(store=store, terminal=None)

    from harness.routers import execution as execution_router

    class _Stub:
        execution = layer

    monkeypatch.setattr(execution_router, "service", _Stub(), raising=False)
    application = FastAPI()
    application.include_router(execution_router.router)
    yield application, layer
    layer.stop()
    store.close()


def test_status_is_reachable(app):
    application, _ = app
    with TestClient(application) as client:
        body = client.get("/execution/status").json()
        assert body["success"]
        assert "runtimes" in body and body["runtimes"]
        assert body["maxConcurrency"] >= 1


def test_run_python_round_trip(app):
    application, layer = app
    if not layer.registry.get("python").available():
        pytest.skip("python runtime not available")
    with TestClient(application) as client:
        response = client.post("/execution/run", json={"language": "python", "code": "print('via-http')"})
        body = response.json()
        assert body["success"]
        result = body["result"]
        assert result["status"] == "COMPLETED"
        assert "via-http" in result["stdout"]

        execution_id = result["executionId"]
        fetched = client.get(f"/execution/{execution_id}").json()
        assert fetched["success"]
        logs = client.get(f"/execution/{execution_id}/logs").json()
        assert logs["success"] and "via-http" in logs["stdout"]


def test_list_executions(app):
    application, _ = app
    with TestClient(application) as client:
        body = client.get("/execution/list").json()
        assert body["success"] and isinstance(body["executions"], list)


def test_unknown_execution_is_404(app):
    application, _ = app
    with TestClient(application) as client:
        assert client.get("/execution/exec_does_not_exist").status_code == 404
