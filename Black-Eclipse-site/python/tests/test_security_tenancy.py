"""Multi-tenant identity + authorization isolation."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-tenant-"), "agent-memory.db"),
)

from harness.security import (
    SecurityGateway,
    sign_identity,
    verify_identity_token,
)
from harness.security.identity import Identity, resolve_identity
from harness.security.secrets import SecretsManager, SecretGrant, StaticSecretProvider

SECRET = "test-secret-value-1234567890"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_SECRET", SECRET)
    monkeypatch.delenv("HARNESS_MULTI_TENANT", raising=False)
    yield


# ── identity token ───────────────────────────────────────────────────────────
def test_verify_valid_token():
    token = sign_identity({"sub": "u1", "tenant": "acme", "sid": "s1"}, secret=SECRET)
    claims = verify_identity_token(token, secret=SECRET)
    assert claims is not None
    assert claims["sub"] == "u1" and claims["tenant"] == "acme"


def test_verify_forged_token_is_none():
    token = sign_identity({"sub": "u1"}, secret=SECRET)
    parts = token.split(".")
    forged = f"{parts[0]}.{parts[1]}.{'A' * len(parts[2])}"
    assert verify_identity_token(forged, secret=SECRET) is None
    assert verify_identity_token(token, secret="a-different-secret-value-1234") is None


def test_verify_expired_token_is_none():
    # Beyond the clock-skew allowance (60s).
    token = sign_identity({"sub": "u1"}, secret=SECRET, ttl_s=-120)
    assert verify_identity_token(token, secret=SECRET) is None


def test_resolve_identity_precedence(monkeypatch):
    from starlette.requests import Request

    def make(headers=None, client=("127.0.0.1", 1)):
        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
        req = Request(scope)
        req.scope["client"] = client
        return req

    token = sign_identity({"sub": "u1", "tenant": "acme"}, secret=SECRET)
    session = resolve_identity(make({"x-harness-identity": token}, client=("203.0.113.9", 1)))
    assert session.verified and session.tenant_id == "acme" and session.method == "session"

    operator = resolve_identity(make(client=("127.0.0.1", 1)))
    assert operator.verified and operator.is_operator

    anonymous = resolve_identity(make(client=("203.0.113.9", 1)))
    assert not anonymous.verified


# ── require_identity dependency ──────────────────────────────────────────────
def _app(client=("testclient", 50000)):
    from harness.security.identity import require_identity

    app = FastAPI()

    @app.get("/whoami")
    def whoami(identity: Identity = Depends(require_identity)) -> dict:
        return identity.to_dict()

    return TestClient(app, client=client)


def test_require_identity_accepts_valid_token():
    client = _app()
    token = sign_identity({"sub": "u1", "tenant": "acme"}, secret=SECRET)
    resp = client.get("/whoami", headers={"X-Harness-Identity": token})
    assert resp.status_code == 200
    assert resp.json()["tenantId"] == "acme"


def test_require_identity_refuses_anonymous_when_multi_tenant(monkeypatch):
    monkeypatch.setenv("HARNESS_MULTI_TENANT", "1")
    client = _app(client=("203.0.113.9", 50000))
    resp = client.get("/whoami")
    assert resp.status_code == 401


def test_require_identity_loopback_is_operator_in_local_mode():
    client = _app()  # TestClient host is loopback
    resp = client.get("/whoami")
    assert resp.status_code == 200
    assert resp.json()["method"] == "operator"


# ── tenant isolation in the security plane ───────────────────────────────────
def _gateway(**kw):
    from harness.persistence import AgentMemoryStore
    from harness.security.models import PolicyProfile

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-sec-tenant-db-"), "agent-memory.db"))
    kw.setdefault("profile", PolicyProfile.DEVELOPER)
    return SecurityGateway(store=store, **kw)


def test_capability_is_tenant_scoped():
    gw = _gateway()
    gw.issue_capability(subject="agent", action="filesystem.write", resource="src/**",
                        tenant_id="acme", ttl_seconds=60)
    from harness.security.models import AuthorizationRequest

    acme = gw.authorize(AuthorizationRequest(action="filesystem.write", resource="src/x", actor="agent", tenant="acme"))
    other = gw.authorize(AuthorizationRequest(action="filesystem.write", resource="src/x", actor="agent", tenant="other"))
    assert acme.capability_id is not None
    assert other.capability_id is None


def test_secret_grant_is_tenant_scoped():
    manager = SecretsManager()
    manager.register_provider(StaticSecretProvider({"TOKEN": "value-value-value"}))
    manager.grant(SecretGrant(ref="secret://static/TOKEN", consumer="app", tenant_id="acme"))
    assert manager.resolve_optional("secret://static/TOKEN", consumer="app", tenant_id="acme") == "value-value-value"
    assert manager.resolve_optional("secret://static/TOKEN", consumer="app", tenant_id="other") is None
    assert manager.resolve_optional("secret://static/TOKEN", consumer="app") is None


def test_session_tenant_isolation(monkeypatch):
    from harness.security.context import IsolationViolation

    gw = _gateway()
    ctx = gw.open_session(session_id="s1", tenant_id="acme", workspace_id="ws")
    with pytest.raises(IsolationViolation):
        gw.sessions.assert_tenant(ctx, "other")


def test_multi_tenant_gateway_denies_untenanted(monkeypatch):
    from harness.security.models import AuthorizationRequest, Decision

    gw = _gateway()
    gw.multi_tenant = True
    denied = gw.authorize(AuthorizationRequest(action="filesystem.read", resource="a.py"))
    assert denied.decision is Decision.DENY
    allowed = gw.authorize(AuthorizationRequest(
        action="filesystem.read", resource="a.py",
        context={"operator": True},
    ))
    assert allowed.decision is Decision.ALLOW


def test_audit_is_tenant_filterable():
    from harness.security.models import AuthorizationRequest

    gw = _gateway()
    gw.authorize(AuthorizationRequest(action="filesystem.read", resource="a.py", tenant="acme"))
    gw.authorize(AuthorizationRequest(action="filesystem.read", resource="b.py", tenant="beta"))
    acme = gw.audit.list(tenant_id="acme")
    assert acme and all(e["tenantId"] == "acme" for e in acme)
    assert all(e["tenantId"] != "beta" for e in acme)
