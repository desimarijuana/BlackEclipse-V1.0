"""Phase 1 — identity and tenancy boundary.

These tests prove the boundary is stated and enforced honestly:

  * `userId`/`scopeId` are scope FILTER labels, never authentication;
  * a request-body `userId` is never sufficient authorization for a mutation;
  * the app never claims multi-user safety;
  * a non-loopback bind without an operator secret is flagged;
  * `main()` refuses an insecure non-loopback bind unless explicitly
    acknowledged;
  * the front-door guard no longer treats the `0.0.0.0` wildcard as local.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

SECRET = "phase1-operator-secret-abc123"


def _main():
    """Import the harness app lazily.

    `harness.main` reads `AGENT_MEMORY_DB_PATH` at import time, so importing it
    at module scope would bind the default database before sibling test modules
    (e.g. `test_mcp_api.py`) can point it at a temp path. Import inside each test.
    """
    from harness import main as main_module

    return main_module


def _identity_boundary():
    return _main().identity_boundary()


def _deployment_exposure(host):
    return _main().deployment_exposure(host)


def _app():
    return _main().app


def _identity_boundary_constants():
    return _main().IDENTITY_BOUNDARY


def test_identity_boundary_never_claims_multi_user_safety():
    boundary = _identity_boundary()
    assert boundary["authentication"] is False
    assert boundary["multiUserSafe"] is False
    assert boundary["tenancy"] == "single-user-local"
    assert boundary["scopeFiltering"] == "caller-supplied-labels"
    # The four concepts are named distinctly and never conflated.
    identity_boundary = _identity_boundary_constants()
    assert set(identity_boundary) == {
        "authentication", "tenancyIsolation", "operatorAuthorization", "scopeFiltering",
    }
    assert "not implemented" in identity_boundary["authentication"].lower()
    assert "not implemented" in identity_boundary["tenancyIsolation"].lower()


def test_health_reports_the_identity_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", str(tmp_path / "agent-memory.db"))
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    with TestClient(_app()) as c:
        body = c.get("/health").json()
    assert body["identity"]["authentication"] is False
    assert body["identity"]["multiUserSafe"] is False
    assert "exposure" in body["identity"]


def test_loopback_bind_is_not_exposed():
    exposure = _deployment_exposure("127.0.0.1")
    assert exposure["loopback"] is True
    assert exposure["exposed"] is False
    assert exposure["multiUserSafe"] is False


def test_non_loopback_bind_without_secret_is_flagged(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    exposure = _deployment_exposure("0.0.0.0")
    assert exposure["loopback"] is False
    assert exposure["exposed"] is True
    assert exposure["multiUserSafe"] is False
    assert exposure["warning"]


def test_non_loopback_bind_with_secret_is_still_not_multi_user_safe(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    exposure = _deployment_exposure("0.0.0.0")
    # A secret protects mutations, but reads are not identity-scoped and there is
    # no authentication/tenancy: multi-user safety is still never claimed.
    assert exposure["exposed"] is False
    assert exposure["multiUserSafe"] is False
    assert exposure["operatorSecretConfigured"] is True
    # A public bind is still warned about even with a secret.
    assert exposure["warning"]


def test_main_refuses_insecure_non_loopback_bind(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("BLACK_ECLIPSE_ALLOW_INSECURE_BIND", raising=False)
    with pytest.raises(SystemExit):
        _main().main(host="0.0.0.0", port=0)


def test_main_allows_explicit_insecure_acknowledgement(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setenv("BLACK_ECLIPSE_ALLOW_INSECURE_BIND", "1")

    seen: dict[str, object] = {}

    def fake_run(app, host, port, log_level):  # noqa: ANN001 - uvicorn shim
        seen.update({"host": host, "port": port})

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    _main().main(host="0.0.0.0", port=8765)
    assert seen["host"] == "0.0.0.0"


def test_remote_body_user_id_is_not_authorization(monkeypatch, tmp_path):
    # A remote caller that supplies a userId in the body still cannot perform a
    # mutation: authorization is transport/token only.
    from starlette.testclient import TestClient as TC

    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", str(tmp_path / "agent-memory.db"))
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with TC(_app(), client=("203.0.113.9", 5555)) as c:
        res = c.post(
            "/eclipse-memory/memories",
            json={
                "operator": True, "userId": "admin", "scopeId": "admin",
                "content": "should not be written", "memoryType": "preference",
                "scope": "user",
            },
        )
    assert res.status_code == 403


def test_operator_secret_placeholder_is_not_configured(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "change-me-to-a-random-secret")
    assert _deployment_exposure("0.0.0.0")["operatorSecretConfigured"] is False
    assert _deployment_exposure("0.0.0.0")["exposed"] is True
