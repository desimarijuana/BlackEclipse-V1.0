"""Memory/skill API authorization — a body boolean must NOT authorize.

These are API-LEVEL tests (real FastAPI TestClient) proving that the
memory/skill mutation endpoints require PROOF OF AUTHORIZATION by transport
(loopback) or the runtime secret, exactly like the MCP endpoints. A remote
caller that crafts `{"operator": true}` — or calls the Python service directly —
is refused before the body is considered.

This closes the bypass where the Next.js front door derived `operator` from
trusted auth but the Python endpoint trusted the body boolean, so a directly
reachable runtime (or a crafted proxied payload) could self-authorize.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Paths must be set BEFORE importing the app module (the service is created at
# import time).
os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-mem-auth-run-"), "agent-memory.db"))
os.environ.setdefault("ECLIPSE_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-mem-auth-em-"), "eclipse-memory.db"))

SECRET = "runtime-operator-secret-mem-xyz789"
REMOTE = ("203.0.113.9", 5555)


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _remote(monkeypatch, *, secret=None):
    """A TestClient whose peer address is NON-loopback (a remote caller)."""
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    if secret:
        monkeypatch.setenv("CRON_SECRET", secret)
    else:
        monkeypatch.delenv("CRON_SECRET", raising=False)
    return TC(main_module.app, client=REMOTE)


# ── The core bypass: body boolean from a remote caller ──────────────────────


def test_remote_body_operator_boolean_cannot_write_memory(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post(
            "/eclipse-memory/memories",
            json={"operator": True, "content": "x", "memoryType": "preference", "scope": "user", "scopeId": "u1"},
        )
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_accept_suggestion(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post("/eclipse-memory/suggestions/sugg_does_not_matter/accept", json={"operator": True})
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_dismiss_suggestion(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post("/eclipse-memory/suggestions/sugg_does_not_matter/dismiss", json={"operator": True})
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_change_policies(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.put("/eclipse-memory/policies", json={"operator": True, "policies": {"memory_mode": "off"}})
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_enable_skill(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post("/skills/research.planning/enable", json={"operator": True})
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_author_skill(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post(
            "/skills/author",
            json={"operator": True, "name": "X", "description": "d", "instructions": "i"},
        )
    assert res.status_code == 403, res.text


def test_remote_body_operator_boolean_cannot_analytze_run(monkeypatch):
    with _remote(monkeypatch) as c:
        res = c.post("/eclipse-memory/analyze/run_x", json={"operator": True})
    assert res.status_code == 403, res.text


def test_remote_execute_operator_flag_is_downgraded(monkeypatch):
    # Skill execution is allowed for non-operators, so it is not blanket-gated;
    # but a remote caller's body `operator: true` must NOT widen the actor beyond
    # the safe set. Capture the request the endpoint hands to `run_skill` and
    # assert the operator flag was cleared for a remote, token-less caller.
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    captured: dict = {}

    async def _fake_run_skill(request):
        captured["operator"] = request.operator
        from harness.skills.runtime import SkillExecutionResult

        return SkillExecutionResult(status="blocked", skillId=request.skillId)

    monkeypatch.setattr(main_module.service, "run_skill", _fake_run_skill)
    monkeypatch.delenv("CRON_SECRET", raising=False)

    with TC(main_module.app, client=REMOTE) as c:
        res = c.post("/skills/research.planning/execute", json={"operator": True, "input": {"objective": "x"}})
    assert res.status_code == 200, res.text
    assert captured["operator"] is False, "remote body operator must be downgraded"

    # With the runtime secret, the same body flag IS honoured.
    monkeypatch.setenv("CRON_SECRET", SECRET)
    with TC(main_module.app, client=REMOTE) as c:
        c.post(
            "/skills/research.planning/execute",
            json={"operator": True, "input": {"objective": "x"}},
            headers={"X-Harness-Operator": SECRET},
        )
    assert captured["operator"] is True


# ── Authorization succeeds via the trusted mechanisms ───────────────────────


def test_loopback_is_trusted(client):
    # Default TestClient host is loopback → zero-config local use keeps working.
    res = client.post(
        "/eclipse-memory/memories",
        json={"operator": True, "content": "loopback can save", "memoryType": "semantic", "scope": "general"},
    )
    assert res.status_code == 200, res.text


def test_runtime_secret_allows_remote(monkeypatch):
    with _remote(monkeypatch, secret=SECRET) as c:
        # No token → forbidden.
        assert c.put("/eclipse-memory/policies", json={"operator": True, "policies": {}}).status_code == 403
        # Wrong token → forbidden.
        bad = c.put(
            "/eclipse-memory/policies",
            json={"operator": True, "policies": {}},
            headers={"X-Harness-Operator": "nope"},
        )
        assert bad.status_code == 403
        # Correct token → allowed (empty policy update is a no-op success).
        ok = c.put(
            "/eclipse-memory/policies",
            json={"operator": True, "policies": {}},
            headers={"X-Harness-Operator": SECRET},
        )
        assert ok.status_code == 200, ok.text


def test_runtime_secret_bearer_allows_remote(monkeypatch):
    with _remote(monkeypatch, secret=SECRET) as c:
        ok = c.put(
            "/eclipse-memory/policies",
            json={"operator": True, "policies": {}},
            headers={"Authorization": f"Bearer {SECRET}"},
        )
        assert ok.status_code == 200, ok.text
