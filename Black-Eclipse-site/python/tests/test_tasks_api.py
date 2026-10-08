"""The task/plan API routes: operator-gated, and they drive the real manager."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-tasks-api-"), "agent-memory.db"),
)
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_non_operator_is_refused(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.get("/tasks").status_code == 403
        assert remote.post("/plans", json={"name": "x"}).status_code == 403


def test_plan_and_task_lifecycle_over_http(client):
    plan = client.post("/plans", json={"name": "Compare NVDA/AMD"}).json()["plan"]
    plan_id = plan["id"]
    assert plan["status"] == "PLANNING"

    task = client.post("/tasks", json={
        "title": "Research NVDA", "planId": plan_id,
        "acceptanceCriteria": [{"text": "10-K obtained"}],
    }).json()["task"]
    task_id = task["id"]

    # Complete is refused until the criterion passes (400 + structured code).
    res = client.post(f"/tasks/{task_id}/complete", json={})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "COMPLETION_REJECTED"

    crit = client.post(f"/tasks/{task_id}/criteria",
                       json={"text": "extra"}).json()["criterion"]
    client.patch(f"/criteria/{crit['id']}", json={"state": "PASSED"})
    # The original criterion still pending -> still refused.
    assert client.post(f"/tasks/{task_id}/complete", json={}).status_code == 400

    # Read views work regardless.
    assert client.get(f"/tasks/{task_id}/tree").status_code == 200
    assert client.get(f"/tasks/{task_id}/events").status_code == 200
    assert client.get(f"/tasks/{task_id}/dependencies").status_code == 200
    assert client.get(f"/plans/{plan_id}").status_code == 200
    assert client.get(f"/plans/{plan_id}/tasks").status_code == 200

    # Force completes (recorded override), then the plan start route works.
    assert client.post(f"/tasks/{task_id}/complete", json={"force": True}).status_code == 200
    assert client.post(f"/plans/{plan_id}/start").json()["plan"]["status"] == "RUNNING"


def test_404_for_missing(client):
    assert client.get("/tasks/task_nope").status_code == 404
    assert client.get("/plans/plan_nope").status_code == 404
