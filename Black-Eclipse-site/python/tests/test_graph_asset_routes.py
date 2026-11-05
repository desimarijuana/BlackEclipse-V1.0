"""Graph asset upload boundary: owner resolution and rate limiting."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from harness.routers import graph_assets
from harness.security import ratelimit
from harness.security.identity import sign_identity


def _request(headers: dict | None = None, host: str = "127.0.0.1"):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=host),
    )


def test_owner_comes_from_the_verified_identity_not_the_query(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_SECRET", "x" * 32)
    token = sign_identity({"sub": "user-1", "tenant": "tenant-1"})
    request = _request({"x-harness-identity": token}, host="203.0.113.5")
    assert graph_assets._owner(request, "spoofed-owner") == "user-1"


def test_local_operator_keeps_the_local_owner(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH_SECRET", raising=False)
    request = _request({}, host="127.0.0.1")
    assert graph_assets._owner(request, "") == "local"
    assert graph_assets._owner(request, "workspace") == "workspace"


def test_upload_rate_limit_is_per_owner(monkeypatch):
    monkeypatch.setattr(
        ratelimit, "_DEFAULT", ratelimit.RateLimiter(rate_per_minute=1, burst=1),
    )
    request = _request()
    graph_assets._rate_limit(request, "alice")
    with pytest.raises(HTTPException) as exc:
        graph_assets._rate_limit(request, "alice")
    assert exc.value.status_code == 429
    # A different owner has its own bucket.
    graph_assets._rate_limit(request, "bob")
