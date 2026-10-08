"""The orchestration HTTP router — transport seam + an end-to-end round trip."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.events import EventBus
from harness.orchestration.bootstrap import install_orchestration_layer
from harness.tools import ToolRegistry

from orchestration_helpers import make_store


class StubService:
    def __init__(self, store) -> None:
        self.store = store
        self.registry = ToolRegistry()
        self.bus = EventBus()

    def build_bridge(self, base_url, token):  # noqa: D401 - test stub
        return None


@pytest.fixture()
def app(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    stub = StubService(store)
    install_orchestration_layer(stub)

    from harness.routers import orchestration as orchestration_router

    monkeypatch.setattr(orchestration_router, "service", stub, raising=False)
    application = FastAPI()
    application.include_router(orchestration_router.router)
    yield application, store
    store.close()


def test_round_trip(app):
    application, _ = app
    with TestClient(application) as client:
        response = client.post("/orchestration/executions", json={
            "tasks": [
                {"id": "a", "kind": "noop", "input": {"value": 1}},
                {"id": "b", "kind": "noop", "input": {"value": 2}, "dependsOn": ["a"]},
            ],
        })
        body = response.json()
        assert body["success"]
        result = body["result"]
        assert result["status"] == "COMPLETED"
        assert result["successfulTasks"] == 2
        execution_id = result["executionId"]

        status = client.get(f"/orchestration/executions/{execution_id}").json()
        assert status["success"]
        graph = client.get(f"/orchestration/executions/{execution_id}/graph").json()
        assert graph["success"] and len(graph["graph"]["nodes"]) == 2
        listed = client.get("/orchestration/list").json()
        assert listed["success"] and listed["executions"]
        resources = client.get("/orchestration/resources").json()
        assert resources["success"] and "realms" not in resources
        assert resources["resources"]["limits"]


def test_unknown_execution_is_404(app):
    application, _ = app
    with TestClient(application) as client:
        assert client.get("/orchestration/executions/missing").status_code == 404
        assert client.get("/orchestration/executions/missing/graph").status_code == 404


def test_recover_route_re_drives_interrupted_execution(app):
    application, _ = app
    from harness.orchestration.models import ExecutionStatus, NodeKind
    from harness.routers import orchestration as orchestration_router

    layer = orchestration_router.service.orchestration
    graph = layer.primary.create_execution(execution_id="recover_me")
    layer.primary.create_task(graph.id, kind=NodeKind.NOOP, input={"value": 1}, node_id="n")
    stored = layer.primary.build_graph("recover_me")
    stored.status = ExecutionStatus.RUNNING
    layer.primary.store.save_execution(stored)

    with TestClient(application) as client:
        body = client.post("/orchestration/recover").json()
    assert body["success"]
    assert "recover_me" in body["recovered"]
    assert layer.primary.get_result("recover_me").status.value == "COMPLETED"


def test_invalid_failure_policy_is_400(app):
    application, _ = app
    with TestClient(application) as client:
        response = client.post("/orchestration/executions", json={
            "tasks": [{"id": "a", "kind": "noop", "input": {"value": 1}}],
            "failurePolicy": "NOT_A_POLICY",
        })
        assert response.status_code == 400
