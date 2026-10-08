"""Native Automation Engine API — operator gating + full CRUD/lifecycle cycle.

Mirrors the jobs API convention: a directly reachable runtime must not expose
automation control without proof; the legacy `/jobs` surface is the SAME store.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-auto-api-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-auto-cfg-"), "mcp-servers.json")
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


OPERATOR_ROUTES = [
    ("GET", "/automations", None),
    ("GET", "/automations/metrics", None),
    ("POST", "/automations", {"name": "x", "trigger": {"type": "manual"}, "action": {"type": "run_agent", "objective": "x"}}),
    ("GET", "/automations/nope", None),
    ("PATCH", "/automations/nope", {"name": "x"}),
    ("DELETE", "/automations/nope", None),
    ("POST", "/automations/nope/enable", None),
    ("POST", "/automations/nope/pause", None),
    ("POST", "/automations/nope/run", None),
    ("POST", "/automations/nope/dry-run", None),
    ("POST", "/automations/nope/test", None),
    ("GET", "/automations/nope/status", None),
    ("GET", "/automations/nope/history", None),
    ("GET", "/automations/nope/versions", None),
    ("GET", "/automations/executions/nope", None),
]


@pytest.mark.parametrize("method,path,body", OPERATOR_ROUTES)
def test_every_operator_route_refuses_a_non_operator(monkeypatch, method, path, body):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        res = remote.request(method, path, json=body)
        assert res.status_code == 403, f"{method} {path}: {res.text}"


@pytest.mark.parametrize("method,path,body", OPERATOR_ROUTES)
def test_every_operator_route_allows_loopback(client, method, path, body):
    res = client.request(method, path, json=body)
    assert res.status_code != 403, f"{method} {path}: {res.text}"


def test_create_validate_dry_run_and_history(client):
    created = client.post("/automations", json={
        "name": "Morning brief",
        "state": "draft",
        "trigger": {"type": "cron", "cron": "0 8 * * *", "timezone": "UTC"},
        "action": {"type": "run_agent", "objective": "brief me"},
        "delivery": {"adapter": "in_app"},
    }).json()["automation"]
    automation_id = created["id"]
    assert created["state"] == "draft"
    assert created["trigger"]["cron"] == "0 8 * * *"

    listing = client.get("/automations").json()["automations"]
    assert any(a["id"] == automation_id for a in listing)

    assert client.post(f"/automations/{automation_id}/validate").json()["valid"] is True

    preview = client.post(f"/automations/{automation_id}/dry-run").json()["dryRun"]
    assert any("run agent" in step for step in preview["plannedActions"])

    # Activate -> next run is computed.
    enabled = client.post(f"/automations/{automation_id}/enable").json()["automation"]
    assert enabled["state"] == "active"
    status = client.get(f"/automations/{automation_id}/status").json()["status"]
    assert status["nextRunAt"] is not None

    # Pause does not delete; resume restores.
    assert client.post(f"/automations/{automation_id}/pause").json()["automation"]["state"] == "paused"
    assert client.post(f"/automations/{automation_id}/resume").json()["automation"]["state"] == "active"

    assert client.get(f"/automations/{automation_id}/history").json()["success"] is True
    assert client.get(f"/automations/{automation_id}/versions").json()["success"] is True

    assert client.delete(f"/automations/{automation_id}").json()["deleted"] == automation_id
    assert client.get(f"/automations/{automation_id}").status_code == 404


def test_invalid_cron_is_refused(client):
    res = client.post("/automations", json={
        "name": "Bad",
        "trigger": {"type": "cron", "cron": "not a cron", "timezone": "UTC"},
        "action": {"type": "run_agent", "objective": "x"},
    })
    assert res.status_code == 400


def test_unknown_timezone_is_refused(client):
    res = client.post("/automations", json={
        "name": "Bad tz",
        "trigger": {"type": "cron", "cron": "0 8 * * *", "timezone": "Mars/Olympus"},
        "action": {"type": "run_agent", "objective": "x"},
    })
    assert res.status_code == 400


def test_invalid_transition_is_refused(client):
    created = client.post("/automations", json={
        "name": "Lifecycle", "state": "draft",
        "trigger": {"type": "manual"}, "action": {"type": "run_agent", "objective": "x"},
    }).json()["automation"]
    aid = created["id"]
    client.post(f"/automations/{aid}/archive")
    res = client.post(f"/automations/{aid}/resume")
    assert res.status_code == 400
    client.delete(f"/automations/{aid}")


def test_legacy_jobs_are_the_same_automations(client):
    """A job created through /jobs is an automation in /automations (one store)."""
    job = client.post("/jobs", json={
        "name": "Shared", "kind": "manual",
        "target": {"kind": "objective", "objective": "x"},
    }).json()["job"]
    automation = client.get(f"/automations/{job['id']}")
    assert automation.status_code == 200
    assert automation.json()["automation"]["id"] == job["id"]
    client.delete(f"/jobs/{job['id']}")
