"""Engineering hardening Phase 3 — the FastAPI router transport seam.

`python/tests/` had zero references to `harness/routers/`. Service-level behavior
is covered elsewhere; these tests cover the TRANSPORT seam: the operator
authorization dependency (`require_operator` / `require_mcp_operator`) accept/
reject by loopback vs remote+token, and the 404/400/403 status mapping at the
router boundary. The service is stubbed so the test is about the seam, not the
domain logic.

The app is built the same way `harness.main` builds it: a fresh FastAPI that
includes the real routers. Each router imports `service` from `harness.deps`, so
the stub is patched onto the router MODULE attribute (the name each handler
actually looks up).
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-router-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-router-cfg-"), "mcp-servers.json")

SECRET = "router-seam-operator-secret-xyz"


class _StubMemoryStore:
    def get_memory(self, memory_id: str):
        return None

    def list_memories(self, **_kwargs):
        return []


class _StubMemory:
    def health(self):
        return {"ok": True}

    def usage_report(self, window_days: int = 30):
        return {"windowDays": window_days, "writes": 0}

    def lifecycle_overview(self):
        return {}


class _StubStore:
    def create_chat_session(self, session_id, **_kwargs):
        return {"id": session_id, "title": _kwargs.get("title")}


class _StubService:
    """A minimal service stand-in: only the attributes the tested routes touch."""

    memory_store = _StubMemoryStore()
    memory = _StubMemory()
    store = _StubStore()
    mcp = None
    approvals = None


@pytest.fixture()
def routers_app(monkeypatch):
    """A FastAPI app with the real routers and a stubbed service bound per module."""
    from harness.routers import mcp as mcp_router
    from harness.routers import memory as memory_router
    from harness.routers import sessions as sessions_router
    from harness.routers import skills as skills_router

    stub = _StubService()
    for module in (mcp_router, memory_router, sessions_router, skills_router):
        monkeypatch.setattr(module, "service", stub, raising=False)

    app = FastAPI()
    app.include_router(mcp_router.router)
    app.include_router(memory_router.router)
    app.include_router(sessions_router.router)
    app.include_router(skills_router.router)
    return app


def _remote(app):
    """A non-loopback TestClient (the default host is loopback)."""
    return TestClient(app, client=("203.0.113.9", 5555))


def _loopback(app):
    return TestClient(app)


# ── authorization: a remote caller without the secret is refused ────────────


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/mcp/servers", {"server": {"id": "x", "command": "python"}}),
        ("post", "/eclipse-memory/memories", {"content": "hi", "memoryType": "fact", "operator": True}),
        ("post", "/sessions", {"title": "x"}),
        ("post", "/skills/project/approve", {"operator": True}),
    ],
)
def test_remote_without_token_is_refused_on_every_router(routers_app, monkeypatch, method, path, body):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with _remote(routers_app) as c:
        res = getattr(c, method)(path, json=body)
        assert res.status_code == 403, res.text


def test_body_operator_boolean_never_authorizes(routers_app, monkeypatch):
    # The transport gate runs BEFORE the body is read, so {"operator": true}
    # cannot authorize a remote caller.
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with _remote(routers_app) as c:
        res = c.post("/eclipse-memory/memories", json={"operator": True, "content": "x"})
        assert res.status_code == 403


def test_runtime_secret_token_authorizes_remote(routers_app, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    with _remote(routers_app) as c:
        assert c.post("/sessions", json={"title": "x"}).status_code == 403
        ok = c.post("/sessions", json={"title": "x"}, headers={"X-Harness-Operator": SECRET})
        assert ok.status_code == 200, ok.text


def test_wrong_token_is_refused(routers_app, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    with _remote(routers_app) as c:
        res = c.post("/sessions", json={"title": "x"}, headers={"X-Harness-Operator": "wrong"})
        assert res.status_code == 403


def test_loopback_is_allowed_zero_config(routers_app, monkeypatch):
    # No secret configured: a loopback caller (the Next.js front door) is allowed
    # so `npm run dev` keeps working with zero setup.
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with _loopback(routers_app) as c:
        res = c.post("/sessions", json={"title": "x"})
        assert res.status_code != 403, res.text


# ── error mapping at the router boundary ────────────────────────────────────


def test_missing_resource_maps_to_404(routers_app):
    # GET /eclipse-memory/memories/{id} is a READ (no operator gate) and maps a
    # missing memory to 404, never a fabricated 200.
    with _loopback(routers_app) as c:
        res = c.get("/eclipse-memory/memories/does-not-exist")
        assert res.status_code == 404


def test_mcp_unavailable_is_honest(routers_app):
    # With `service.mcp is None`, the MCP list route reports unavailable rather
    # than fabricating a catalog.
    with _loopback(routers_app) as c:
        body = c.get("/mcp/servers").json()
        assert body["success"] is False
        assert body.get("unavailable") is True
