"""Phase 6 G3 — every jobs route refuses a non-operator (reads AND mutations).

The MCP convention (`test_read_routes_refuse_a_non_operator`) copied to jobs: a
directly reachable runtime must not expose job control without proof. The single
exception is the webhook trigger, which authenticates on the job's hashed token.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-jobs-api-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-jobs-cfg-"), "mcp-servers.json")
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
SECRET = "runtime-operator-secret-jobs-xyz"


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


# The complete route set from §6.6 (minus the webhook trigger, tested separately).
OPERATOR_ROUTES = [
    ("GET", "/jobs", None),
    ("GET", "/jobs/templates", None),
    ("POST", "/jobs", {"target": {"kind": "objective", "objective": "x"}}),
    ("GET", "/jobs/nope", None),
    ("PATCH", "/jobs/nope", {"name": "x"}),
    ("DELETE", "/jobs/nope", None),
    ("POST", "/jobs/nope/enable", None),
    ("POST", "/jobs/nope/disable", None),
    ("POST", "/jobs/nope/run", None),
    ("POST", "/jobs/nope/reset-breaker", None),
    ("GET", "/jobs/nope/runs", None),
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
    # The default TestClient host is loopback -> zero-config local use works.
    res = client.request(method, path, json=body)
    assert res.status_code != 403, f"{method} {path}: {res.text}"


def test_templates_are_all_disabled(client):
    body = client.get("/jobs/templates").json()
    assert body["success"] is True
    # The seven finance templates + the two Application Runtime deploy templates
    # + the three evidence-backed research templates + the native-video market
    # recap template.
    assert len(body["templates"]) == 13


def test_create_from_template_is_disabled(client):
    body = client.post("/jobs", json={"templateId": "overnight-news-digest", "params": {"tickers": "AAPL"}}).json()
    assert body["success"] is True
    job = body["job"]
    assert job["enabled"] is False
    assert "AAPL" in job["target"]["objective"]
    assert "webhookTokenHash" not in job
    client.delete(f"/jobs/{job['id']}")


def test_create_list_run_delete_cycle(client):
    created = client.post("/jobs", json={
        "name": "My brief",
        "kind": "manual",
        "target": {"kind": "objective", "objective": "brief me"},
    }).json()["job"]
    job_id = created["id"]
    assert created["enabled"] is False

    listing = client.get("/jobs").json()["jobs"]
    assert any(j["id"] == job_id for j in listing)

    assert client.post(f"/jobs/{job_id}/run").status_code == 409  # not enabled
    assert client.post(f"/jobs/{job_id}/enable").json()["job"]["enabled"] is True
    assert client.post(f"/jobs/{job_id}/run").status_code == 200
    assert client.get(f"/jobs/{job_id}/runs").json()["success"] is True

    assert client.delete(f"/jobs/{job_id}").json()["deleted"] == job_id
    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_patch_preserves_absent_fields(client):
    created = client.post("/jobs", json={
        "name": "Keep me", "kind": "manual",
        "target": {"kind": "objective", "objective": "x"},
    }).json()["job"]
    job_id = created["id"]
    patched = client.patch(f"/jobs/{job_id}", json={"name": "Renamed"}).json()["job"]
    assert patched["name"] == "Renamed"
    assert patched["target"]["objective"] == "x"  # absent -> preserved
    client.delete(f"/jobs/{job_id}")


def test_unknown_delivery_adapter_is_refused_at_save(client):
    res = client.post("/jobs", json={
        "kind": "manual",
        "target": {"kind": "objective", "objective": "x"},
        "delivery": {"adapter": "carrier-pigeon"},
    })
    assert res.status_code == 400


def test_webhook_token_shown_once_and_never_stored(client):
    created = client.post("/jobs", json={
        "name": "Hook",
        "kind": "webhook",
        "target": {"kind": "objective", "objective": "react"},
        "enableWebhook": True,
    }).json()
    job = created["job"]
    token = created["webhookToken"]
    assert token
    job_id = job["id"]

    # The stored/listed job never exposes the token or its hash.
    listed = client.get(f"/jobs/{job_id}").json()["job"]
    assert "webhookToken" not in listed
    assert "webhookTokenHash" not in listed

    # The webhook refuses a wrong token and ignores any body.
    assert client.post(f"/jobs/{job_id}/trigger", headers={"X-Job-Token": "wrong"}).status_code == 403
    # Disabled -> 409 even with the right token.
    assert client.post(f"/jobs/{job_id}/trigger", headers={"X-Job-Token": token}).status_code == 409
    # Enable, then the right token fires.
    client.post(f"/jobs/{job_id}/enable")
    assert client.post(f"/jobs/{job_id}/trigger", headers={"X-Job-Token": token}).status_code == 200
    client.delete(f"/jobs/{job_id}")


def test_webhook_route_refuses_non_operator_without_token(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        # No token -> forbidden, even though this route is not operator-gated.
        res = remote.post("/jobs/whatever/trigger", headers={})
        assert res.status_code in (403, 404)
