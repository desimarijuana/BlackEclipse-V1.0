"""W4 autonomy API: goals, verdicts, loops are operator-gated and durable."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-w4-api-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


@pytest.fixture(autouse=True)
def _goal_engine_on(monkeypatch):
    """These are the goal API tests; the off-engine refusal has its own case."""
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_remote_caller_is_refused(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.get("/goals").status_code == 403
        assert remote.post("/goals", json={"objective": "x"}).status_code == 403
        assert remote.get("/loops").status_code == 403


def test_goal_lifecycle_over_http(client):
    created = client.post("/goals", json={
        "objective": "ship a small widget", "maxTurns": 5, "start": False,
        "acceptance": ["the produced files exist"],
    })
    assert created.status_code == 200, created.text
    goal = created.json()["goal"]
    goal_id = goal["id"]
    assert goal["status"] == "active"
    assert goal["maxTurns"] == 5
    assert goal["usedTurns"] == 0

    listed = client.get("/goals", params={"sessionId": "s-none"}).json()
    assert listed["success"] is True

    assert client.get(f"/goals/{goal_id}").json()["goal"]["id"] == goal_id
    verdicts = client.get(f"/goals/{goal_id}/verdicts").json()
    assert verdicts["verdicts"] == []

    paused = client.post(f"/goals/{goal_id}/pause", json={"reason": "test"}).json()
    assert paused["goal"]["status"] == "paused"

    resumed = client.post(f"/goals/{goal_id}/resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["goal"]["status"] == "active"
    assert resumed.json()["goal"]["usedTurns"] == 1

    cancelled = client.post(f"/goals/{goal_id}/cancel").json()
    assert cancelled["goal"]["status"] == "cancelled"


def test_missing_goal_is_404(client):
    assert client.get("/goals/goal_missing").status_code == 404
    assert client.post("/goals/goal_missing/cancel").status_code == 404


def test_gates_require_a_workspace(client):
    res = client.post("/goals", json={
        "objective": "ship it", "start": False,
        "gates": [{"id": "g", "check": "unit_test"}],
    })
    assert res.status_code == 422


def test_an_off_engine_refuses_to_create_a_zombie_goal(client, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "off")
    res = client.post("/goals", json={"objective": "do the thing", "start": False})
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "GOAL_ENGINE_OFF"
    assert "HARNESS_GOAL_LOOP" in detail["message"]


def test_extend_grants_bounded_turns(client):
    created = client.post("/goals", json={
        "objective": "needs more room", "maxTurns": 1, "start": False,
    }).json()["goal"]
    extended = client.post(f"/goals/{created['id']}/extend", json={"turns": 4})
    assert extended.status_code == 200, extended.text
    goal = extended.json()["goal"]
    assert goal["maxTurns"] == 5
    assert goal["status"] == "active"


def test_loop_lifecycle_over_http(client):
    created = client.post("/loops", json={
        "sessionId": "session_w4", "kind": "loop", "prompt": "check the build",
        "intervalSeconds": 300, "maxTicks": 3,
    })
    assert created.status_code == 200, created.text
    loop = created.json()["loop"]
    loop_id = loop["id"]
    assert loop["status"] == "active"
    assert loop["intervalSeconds"] == 300

    assert client.get("/loops", params={"sessionId": "session_w4"}).json()["loops"][0]["id"] == loop_id
    assert client.post(f"/loops/{loop_id}/pause").json()["loop"]["status"] == "paused"
    assert client.post(f"/loops/{loop_id}/resume").json()["loop"]["status"] == "active"
    assert client.post(f"/loops/{loop_id}/cancel").json()["loop"]["status"] == "cancelled"


def test_health_reports_the_engine_mode(client):
    health = client.get("/autonomy/health").json()["health"]
    assert health["mode"] in ("off", "shadow", "on")
    assert "goals" in health and "loops" in health
