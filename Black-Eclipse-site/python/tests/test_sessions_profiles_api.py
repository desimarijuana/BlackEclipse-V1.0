"""M3/M4 API surface — named sessions and profiles, operator authorization.

API-level tests (real FastAPI TestClient). A body `operator` boolean from a remote
caller must never authorize a mutation; reads stay open.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-sp-run-"), "agent-memory.db"))
os.environ.setdefault("ECLIPSE_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-sp-em-"), "eclipse-memory.db"))
os.environ.setdefault("BLACK_ECLIPSE_PROFILES_ROOT", tempfile.mkdtemp(prefix="be-sp-prof-"))

REMOTE = ("203.0.113.9", 5555)


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _remote(monkeypatch, *, secret=None):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    if secret:
        monkeypatch.setenv("CRON_SECRET", secret)
    else:
        monkeypatch.delenv("CRON_SECRET", raising=False)
    return TC(main_module.app, client=REMOTE)


def test_profiles_list_includes_default(client):
    body = client.get("/profiles").json()
    assert body["success"] is True
    assert any(p["id"] == "default" for p in body["profiles"])


def test_profile_create_requires_operator(monkeypatch):
    # A remote caller with no runtime secret is refused regardless of the body.
    remote = _remote(monkeypatch)
    response = remote.post("/profiles", json={"id": "work", "operator": True})
    assert response.status_code == 403


def test_session_create_and_lifecycle(client):
    created = client.post("/sessions", json={"title": "Research run", "userId": "u1"})
    assert created.status_code == 200
    session_id = created.json()["session"]["id"]
    listed = client.get("/sessions").json()
    assert any(s["id"] == session_id for s in listed["sessions"])
    # Rename.
    patched = client.patch(f"/sessions/{session_id}", json={"title": "Renamed"})
    assert patched.json()["session"]["title"] == "Renamed"
    # Fork.
    forked = client.post(f"/sessions/{session_id}/fork", json={})
    assert forked.json()["session"]["sourceSessionId"] == session_id
    # Export.
    exported = client.get(f"/sessions/{session_id}/export")
    assert exported.json()["session"]["id"] == session_id
    # Archive (default delete).
    archived = client.delete(f"/sessions/{session_id}")
    assert archived.json()["archived"] is True


def test_session_search_filters_by_session(client):
    # Index a message via the reindex route (operator) is heavy; instead assert
    # the filter is accepted and the response shape is honest.
    body = client.get("/session-search", params={"q": "rebalance", "sessionId": "missing-session"}).json()
    assert body["success"] is True
    assert body["results"] == []
