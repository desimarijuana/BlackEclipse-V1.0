"""Memory-expansion API surface (M1–M4) — endpoints, honest states, isolation.

API-level tests (real FastAPI TestClient) for the new capabilities:
  * compact profile (get / preview / rebuild operator-gated);
  * session-history search (search, open, health, reindex operator-gated,
    delete operator-gated);
  * learning review (health, list, run operator-gated, decide operator-gated);
  * the file projection routes are TS-only and covered by vitest.

A body `operator` boolean from a remote caller must never authorize a mutation.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Paths must be set BEFORE importing the app module (the service is created at
# import time).
os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-exp-run-"), "agent-memory.db"))
os.environ.setdefault("ECLIPSE_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-exp-em-"), "eclipse-memory.db"))

SECRET = "runtime-operator-secret-exp-abc123"
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


# ── Profile (M1) ────────────────────────────────────────────────────────────


def test_profile_get_and_preview(client):
    res = client.get("/eclipse-memory/profile")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "snapshot" in body
    assert "prompt" in body
    preview = client.get("/eclipse-memory/profile/preview")
    assert preview.status_code == 200
    assert "snapshot" in preview.json()


def test_profile_rebuild_requires_operator(client, monkeypatch):
    # Loopback but no operator body flag → refused.
    res = client.post("/eclipse-memory/profile/rebuild", json={})
    assert res.status_code == 403
    # Remote caller with a spoofed body boolean → still refused.
    remote = _remote(monkeypatch)
    res = remote.post("/eclipse-memory/profile/rebuild", json={"operator": True})
    assert res.status_code == 403


def test_profile_rebuild_with_token(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    remote = _remote(monkeypatch, secret=SECRET)
    res = remote.post(
        "/eclipse-memory/profile/rebuild",
        json={"operator": True},
        headers={"X-Harness-Operator": SECRET},
    )
    assert res.status_code == 200, res.text
    assert res.json().get("rebuilt") is True


# ── Session history (M2) ────────────────────────────────────────────────────


def test_session_search_health_and_empty(client):
    health = client.get("/session-search/health")
    assert health.status_code == 200
    body = health.json()
    assert "fts5" in body and "indexed" in body
    res = client.get("/session-search", params={"q": "nothing here"})
    assert res.status_code == 200
    assert res.json()["results"] == []


def test_session_search_requires_query(client):
    res = client.get("/session-search")
    assert res.status_code == 422  # required q


def test_session_reindex_requires_operator(client, monkeypatch):
    res = client.post("/session-search/reindex", json={})
    assert res.status_code == 403
    remote = _remote(monkeypatch)
    res = remote.post("/session-search/reindex", json={"operator": True})
    assert res.status_code == 403


def test_session_delete_requires_operator(client, monkeypatch):
    res = client.post("/session-search/delete/run_x", json={})
    assert res.status_code == 403


# ── Learning review (M3) ────────────────────────────────────────────────────


def test_learning_review_health_and_list(client):
    health = client.get("/learning-review/health")
    assert health.status_code == 200
    body = health.json()
    assert "queue" in body and "byStatus" in body
    listing = client.get("/learning-review")
    assert listing.status_code == 200
    assert isinstance(listing.json()["reviews"], list)


def test_learning_review_run_requires_operator(client, monkeypatch):
    res = client.post("/learning-review/run", json={"runId": "run_x"})
    assert res.status_code == 403
    remote = _remote(monkeypatch)
    res = remote.post("/learning-review/run", json={"operator": True, "runId": "run_x"})
    assert res.status_code == 403


def test_learning_review_run_with_token_on_missing_run(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    remote = _remote(monkeypatch, secret=SECRET)
    res = remote.post(
        "/learning-review/run",
        json={"operator": True, "runId": "run_does_not_exist"},
        headers={"X-Harness-Operator": SECRET},
    )
    assert res.status_code == 200, res.text
    review = res.json()["review"]
    assert review["runId"] == "run_does_not_exist"
    assert review["status"] == "completed"


def test_learning_review_decide_requires_operator(client, monkeypatch):
    res = client.post("/learning-review/decide", json={"reviewId": "x", "action": "accept"})
    assert res.status_code == 403
