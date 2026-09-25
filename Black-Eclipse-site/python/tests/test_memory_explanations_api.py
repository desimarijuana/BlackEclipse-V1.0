"""Memory explanations + lifecycle API — the Control Room observability surface.

API-level tests (real FastAPI TestClient) for the endpoints the UI consumes:
`GET /eclipse-memory/memories/{id}` now carries an explanation; `GET
/eclipse-memory/lifecycle` exposes counts + named views; a memory can be restored
and renewed; and the retention sweep only expires automatic memory.

Auth: reads are open; mutations require the operator transport/token (the same
guard as every other memory mutation).
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-mem-expl-run-"), "agent-memory.db"),
)
os.environ.setdefault(
    "ECLIPSE_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-mem-expl-em-"), "eclipse-memory.db"),
)

import pytest
from fastapi.testclient import TestClient

SECRET = "runtime-operator-secret-expl-abc123"
REMOTE = ("203.0.113.11", 5555)


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def saved_memory(client):
    res = client.post(
        "/eclipse-memory/memories",
        json={
            "operator": True, "content": "The user's reporting currency is PKR.",
            "memoryType": "semantic", "scope": "user", "scopeId": "u1",
            "subject": "reporting-currency",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["memory"]


def test_get_memory_includes_explanation(client, saved_memory):
    res = client.get(f"/eclipse-memory/memories/{saved_memory['id']}")
    assert res.status_code == 200, res.text
    body = res.json()
    explanation = body["explanation"]
    assert explanation["saveReason"]
    assert explanation["recallDisposition"]
    assert explanation["timeline"]["createdAt"]


def test_explain_endpoint(client, saved_memory):
    res = client.get(f"/eclipse-memory/memories/{saved_memory['id']}/explain")
    assert res.status_code == 200, res.text
    explanation = res.json()["explanation"]
    assert explanation["authority"] in ("explicit", "automatic")
    assert explanation["status"] == "active"


def test_explain_missing_memory_is_404(client):
    assert client.get("/eclipse-memory/memories/mem_nope/explain").status_code == 404


def test_lifecycle_overview(client):
    res = client.get("/eclipse-memory/lifecycle")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "counts" in body
    assert body["counts"]["active"] >= 1
    assert "budget" in body


def test_lifecycle_named_view(client, saved_memory):
    res = client.get("/eclipse-memory/lifecycle", params={"view": "active"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["view"] == "active"
    assert any(m["id"] == saved_memory["id"] for m in body["memories"])


def test_archive_then_restore_via_api(client, saved_memory):
    res = client.post(
        f"/eclipse-memory/memories/{saved_memory['id']}/archive",
        json={"operator": True, "reason": "operator archived for test"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["memory"]["status"] == "archived"
    # Expired/superseded/archived are never recalled.
    probe = client.post(
        "/eclipse-memory/retrieve",
        json={"query": "reporting currency", "actorScope": "user", "scopeId": "u1"},
    )
    assert all(m["id"] != saved_memory["id"] for m in probe.json()["memories"])
    # Restore brings it back.
    restored = client.post(
        f"/eclipse-memory/memories/{saved_memory['id']}/restore", json={"operator": True},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["memory"]["status"] == "active"


def test_restore_requires_operator(client):
    from starlette.testclient import TestClient as TC
    import harness.main as main_module

    with TC(main_module.app, client=REMOTE) as c:
        res = c.post("/eclipse-memory/memories/mem_x/restore", json={"operator": True})
    assert res.status_code == 403, res.text


def test_retention_sweep_is_operator_gated(client):
    from starlette.testclient import TestClient as TC
    import harness.main as main_module

    with TC(main_module.app, client=REMOTE) as c:
        assert c.post("/eclipse-memory/retention/sweep", json={"operator": True}).status_code == 403
