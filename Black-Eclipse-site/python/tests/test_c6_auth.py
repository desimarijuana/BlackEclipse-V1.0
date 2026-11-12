"""C6: auth is required by default outside loopback, never for zero-config local.

The precedence is the documented one in `docs/harness/authentication.md`:
explicit `HARNESS_AUTH`, else auto-on for a non-loopback bind or a production
build, else off. These tests pin both halves of the promise: a public bind can
never be anonymous, and `npm run dev` on loopback still needs no setup.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from harness.security.identity import (
    ANONYMOUS,
    front_door_requires_auth,
    resolve_identity,
    sign_identity,
)


def _request(host: str, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    })


def test_zero_config_loopback_dev_needs_no_auth(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setenv("NODE_ENV", "development")
    assert front_door_requires_auth() is False
    identity = resolve_identity(_request("127.0.0.1"))
    assert identity.method == "operator"
    assert identity.is_authenticated


def test_a_non_loopback_bind_requires_auth_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH", raising=False)
    monkeypatch.setenv("HOST", "0.0.0.0")
    assert front_door_requires_auth() is True


def test_a_production_build_requires_auth_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setenv("NODE_ENV", "production")
    assert front_door_requires_auth() is True


def test_explicit_auth_off_is_honored_even_public(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH", "off")
    monkeypatch.setenv("HOST", "0.0.0.0")
    assert front_door_requires_auth() is False


def test_a_non_loopback_request_without_a_token_is_anonymous(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_SECRET", "a-secret-long-enough-to-sign")
    assert resolve_identity(_request("10.0.0.5")) is ANONYMOUS


def test_a_signed_identity_verifies_and_binds_the_tenant(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_SECRET", "a-secret-long-enough-to-sign")
    token = sign_identity({"sub": "user_1", "tenant": "tenant_a", "roles": ["analyst"]})
    identity = resolve_identity(_request("10.0.0.5", {"x-harness-identity": token}))
    assert identity.verified
    assert identity.user_id == "user_1"
    assert identity.tenant_id == "tenant_a"
    assert identity.method == "session"


def test_a_forged_token_is_not_trusted(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_SECRET", "a-secret-long-enough-to-sign")
    assert resolve_identity(
        _request("10.0.0.5", {"x-harness-identity": "a.b.c"})
    ) is ANONYMOUS
