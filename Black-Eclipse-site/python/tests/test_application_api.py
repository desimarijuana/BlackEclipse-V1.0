"""The application-runtime HTTP router — transport seam + a real round trip.

Mirrors `test_execution_api.py`: the runtime is stubbed into the router so the
routes and the agent tools share one manager. Everything is operator-gated.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.execution.application.manager import ApplicationRuntimeManager, build_runtime_registry
from harness.execution.application.store import ApplicationRuntimeStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def app(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"name":"x","scripts":{"dev":"node x.js"}}', encoding="utf-8")
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(project))
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    manager = ApplicationRuntimeManager(
        registry=build_runtime_registry(), terminal=None, store=ApplicationRuntimeStore(store),
    )

    from harness.routers import application as app_router

    class _Stub:
        application_runtime = manager

    monkeypatch.setattr(app_router, "service", _Stub(), raising=False)
    application = FastAPI()
    application.include_router(app_router.router)
    yield application, manager
    store.close()


def test_status_is_reachable(app):
    application, _ = app
    with TestClient(application) as client:
        body = client.get("/runtime/status").json()
        assert body["success"]
        assert "runtimes" in body


def test_detect_and_list(app):
    application, _ = app
    with TestClient(application) as client:
        detect = client.get("/runtime/detect").json()
        assert detect["success"] and "tools" in detect
        listing = client.get("/runtime/list").json()
        assert listing["success"] and isinstance(listing["runtimes"], list)


def test_inspect_uses_the_workspace_root(app, monkeypatch):
    application, _ = app
    with TestClient(application) as client:
        body = client.get("/runtime/inspect").json()
        assert body["success"]
        assert body["descriptor"]["name"] == "project"


def test_unknown_runtime_is_404(app):
    application, _ = app
    with TestClient(application) as client:
        assert client.get("/runtime/rt_missing").status_code == 404


def test_ports_list(app):
    application, _ = app
    with TestClient(application) as client:
        body = client.get("/runtime/ports/list").json()
        assert body["success"] and "listening" in body
