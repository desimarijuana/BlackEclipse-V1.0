"""The `/security/*` operator route seam."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-api-"), "agent-memory.db"),
)

from harness.security.gateway import SecurityGateway
from harness.security.models import PolicyProfile


class _StubService:
    def __init__(self):
        from harness.persistence import AgentMemoryStore
        from harness.mcp.approvals import ApprovalStore

        store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-sec-api-db-"), "agent-memory.db"))
        self.store = store
        self.approvals = ApprovalStore(store)
        self.security = SecurityGateway(store=store, approvals=self.approvals, profile=PolicyProfile.DEVELOPER)


@pytest.fixture()
def client(monkeypatch):
    from harness.routers import security as security_router

    stub = _StubService()
    monkeypatch.setattr(security_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(security_router.router)
    return TestClient(app), stub


def test_status(client):
    c, _ = client
    resp = c.get("/security/status")
    assert resp.status_code == 200
    assert resp.json()["profile"] == "developer"


def test_check_request_dry_run(client):
    c, _ = client
    resp = c.post("/security/check", json={"action": "filesystem.read", "resource": "a.py"})
    assert resp.status_code == 200
    assert resp.json()["decision"]["decision"] == "allow"


def test_check_hard_deny(client):
    c, _ = client
    resp = c.post("/security/check", json={"action": "filesystem.read", "resource": "/root/.ssh/id_rsa"})
    assert resp.json()["decision"]["decision"] == "deny"


def test_network_check(client):
    c, _ = client
    assert c.post("/security/network/check", json={"url": "https://api.github.com/x"}).json()["decision"]["decision"] == "allow"
    assert c.post("/security/network/check", json={"url": "http://169.254.169.254/"}).json()["decision"]["decision"] == "deny"


def test_capability_issue_and_revoke(client):
    c, _ = client
    resp = c.post("/security/capabilities", json={
        "subject": "agent", "action": "filesystem.delete", "resource": "build/**", "ttlSeconds": 60,
    })
    assert resp.status_code == 200
    cap_id = resp.json()["capability"]["id"]
    assert c.get("/security/capabilities").json()["capabilities"]
    assert c.post(f"/security/capabilities/{cap_id}/revoke").status_code == 200
    assert c.post("/security/capabilities/nope/revoke").status_code == 404


def test_policy_reload_valid_and_invalid(client):
    c, _ = client
    good = c.post("/security/policy/reload", json={"policy": {"project": {"defaults": {"filesystem": "deny"}}}})
    assert good.status_code == 200
    bad = c.post("/security/policy/reload", json={"policy": {"project": {"rules": [{"action": "x", "verdict": "bogus"}]}}})
    assert bad.status_code == 400


def test_approval_flow_via_api(client):
    c, stub = client
    # Trigger an approval-required decision then decide it through the route.
    decision = stub.security.authorize(
        __import__("harness.security.models", fromlist=["AuthorizationRequest"]).AuthorizationRequest(
            action="filesystem.delete", resource="src/a.py",
        )
    )
    assert decision.decision.value == "approval_required"
    listed = c.get("/security/approvals").json()["approvals"]
    assert any(a["id"] == decision.approval_id for a in listed)
    resp = c.post(f"/security/approvals/{decision.approval_id}/decide", json={"approve": True})
    assert resp.status_code == 200


def test_audit_and_verify(client):
    c, stub = client
    stub.security.authorize(
        __import__("harness.security.models", fromlist=["AuthorizationRequest"]).AuthorizationRequest(
            action="filesystem.read", resource="a.py",
        )
    )
    audit = c.get("/security/audit").json()["events"]
    assert audit
    verify = c.get("/security/audit/verify").json()
    assert verify["valid"] is True
