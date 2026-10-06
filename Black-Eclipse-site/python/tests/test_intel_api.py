"""CIUE HTTP routes — read-only status + operator-gated index trigger.

Drives the REAL router against a REAL temp root. A read route reports the
process-wide runtime state; a mutation (index/servers) is operator-gated by
transport (loopback in the test client), exactly like the other code routes.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-ciue-"), "agent-memory.db"),
)

FIXTURES = Path(__file__).parent / "fixtures" / "intel"


@pytest.fixture()
def intel_app(tmp_path, monkeypatch):
    import harness.routers.code_intel as intel_router
    from harness.code.intel.runtime import build_code_intel_runtime

    root = tmp_path / "proj"
    shutil.copytree(FIXTURES / "typescript-project", root)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))

    class _StubService:
        pass

    stub = _StubService()
    stub.code_intel = build_code_intel_runtime()
    monkeypatch.setattr(intel_router, "service", stub, raising=False)

    app = FastAPI()
    app.include_router(intel_router.router)
    try:
        yield TestClient(app), root, stub
    finally:
        stub.code_intel.stop()


def test_status_route_reports_the_runtime(intel_app):
    client, _root, _stub = intel_app
    resp = client.get("/code/intel/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["enabled"] is True
    assert "config" in body


def test_project_route_detects_languages(intel_app):
    client, _root, _stub = intel_app
    resp = client.get("/code/intel/project")
    assert resp.status_code == 200
    body = resp.json()
    assert "typescript" in body["project"]["languages"]


def test_index_route_builds_the_index(intel_app):
    client, _root, _stub = intel_app
    resp = client.post("/code/intel/index")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["fileCount"] >= 1
    assert body["symbolCount"] >= 1


def test_index_route_is_operator_gated_off_loopback(intel_app, monkeypatch):
    # A non-loopback client with no operator secret is refused.
    import harness.deps as deps

    monkeypatch.setattr(deps, "_is_loopback", lambda request: False)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    import harness.routers.code_intel as intel_router

    app = FastAPI()
    app.include_router(intel_router.router)
    client = TestClient(app)
    resp = client.post("/code/intel/index")
    assert resp.status_code == 403
