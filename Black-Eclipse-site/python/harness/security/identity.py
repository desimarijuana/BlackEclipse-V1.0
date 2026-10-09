"""Verified identity for the Python runtime — the trust boundary for multi-tenancy.

The Next.js front door authenticates the user and mints a short-lived, HS256-signed
identity token. This module verifies that token with the SAME secret
(`HARNESS_AUTH_SECRET`) using stdlib only (no new dependency) and turns it into an
`Identity`. The runtime never trusts a caller-supplied `userId`/`tenantId` again:
those come from the verified token.

Precedence:
  1. a valid `X-Harness-Identity` JWT → the verified user/tenant identity;
  2. otherwise loopback or the operator secret → an operator identity (zero-config
     local use keeps working, and the front door itself is loopback);
  3. otherwise → an ANONYMOUS, unverified identity.

In multi-tenant mode (`HARNESS_MULTI_TENANT=1`, or auto-on when the front door
requires auth), an anonymous request to a tenant-scoped surface is refused.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import HTTPException, Request

IDENTITY_HEADER = "x-harness-identity"
PLACEHOLDER_SECRET = "change-me-to-a-random-secret"
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_CLOCK_SKEW_S = 60


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def auth_secret() -> Optional[str]:
    secret = os.environ.get("HARNESS_AUTH_SECRET")
    if not secret or secret == PLACEHOLDER_SECRET or len(secret) < 16:
        return None
    return secret


def sign_identity(claims: dict[str, Any], *, secret: Optional[str] = None, ttl_s: int = 300) -> str:
    """Test/tooling helper: mint an HS256 identity token. Mirrors the front door."""
    key = secret or auth_secret()
    if not key:
        raise ValueError("no HARNESS_AUTH_SECRET configured")
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + int(ttl_s)}
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}." \
                    f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def verify_identity_token(token: str, *, secret: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Verify an HS256 JWT and return its claims, or None (forged/expired/absent)."""
    key = secret or auth_secret()
    if not key:
        return None
    parts = str(token or "").split(".")
    if len(parts) != 3:
        return None
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception:  # noqa: BLE001 - malformed token
        return None
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        return None
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        return None
    now = time.time()
    if "exp" in payload and float(payload["exp"]) < now - _CLOCK_SKEW_S:
        return None
    if "nbf" in payload and float(payload["nbf"]) > now + _CLOCK_SKEW_S:
        return None
    return payload if isinstance(payload, dict) else None


@dataclass(frozen=True)
class Identity:
    """A verified caller identity."""

    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: tuple[str, ...] = ()
    session_id: Optional[str] = None
    method: str = "anonymous"  # session | operator | anonymous
    verified: bool = False

    @property
    def is_operator(self) -> bool:
        return self.method == "operator" or "operator" in self.roles or "admin" in self.roles

    @property
    def is_authenticated(self) -> bool:
        return self.verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "tenantId": self.tenant_id,
            "roles": list(self.roles),
            "sessionId": self.session_id,
            "method": self.method,
            "verified": self.verified,
        }


ANONYMOUS = Identity()


def _is_loopback(request: Request) -> bool:
    client = request.client
    host = (client.host if client else "") or ""
    return host in _LOOPBACK_HOSTS


def _valid_operator_token(request: Request) -> bool:
    secret = os.environ.get("CRON_SECRET")
    if not secret or secret == PLACEHOLDER_SECRET:
        return False
    provided = request.headers.get("x-harness-operator") or ""
    auth = request.headers.get("authorization") or ""
    bearer = auth[7:] if auth.startswith("Bearer ") else ""
    for candidate in (provided, bearer):
        if candidate and hmac.compare_digest(candidate, secret):
            return True
    return False


def multi_tenant_required() -> bool:
    """Whether tenant identity is mandatory.

    Explicit `HARNESS_MULTI_TENANT`; otherwise auto-on when the front door
    requires auth (public bind / production), mirroring `src/lib/auth/config.ts`.
    """
    explicit = os.environ.get("HARNESS_MULTI_TENANT")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on", "enabled")
    host = (os.environ.get("HOST") or "").strip().lower()
    public_bind = bool(host) and host not in _LOOPBACK_HOSTS
    production = (os.environ.get("NODE_ENV") or "").strip().lower() == "production"
    return public_bind or production


def resolve_identity(request: Request) -> Identity:
    """Resolve the caller's verified identity from the request. Never raises."""
    token = request.headers.get(IDENTITY_HEADER)
    if token:
        claims = verify_identity_token(token)
        if claims is not None:
            tenant = claims.get("tenant") or claims.get("tenantId") or claims.get("scope")
            roles = claims.get("roles") or claims.get("role") or ()
            if isinstance(roles, str):
                roles = (roles,)
            return Identity(
                user_id=str(claims["sub"]) if claims.get("sub") else None,
                tenant_id=str(tenant) if tenant else None,
                roles=tuple(str(r) for r in roles),
                session_id=str(claims["sid"]) if claims.get("sid") else None,
                method="session",
                verified=True,
            )
    if _is_loopback(request) or _valid_operator_token(request):
        return Identity(
            tenant_id=os.environ.get("BLACK_ECLIPSE_DEFAULT_TENANT") or None,
            roles=("operator",),
            method="operator",
            verified=True,
        )
    return ANONYMOUS


def require_identity(request: Request) -> Identity:
    """FastAPI dependency: return a verified identity, or refuse.

    In multi-tenant mode an anonymous caller is refused (401). In single-tenant
    local mode the legacy loopback/operator behavior is preserved.
    """
    identity = resolve_identity(request)
    if identity.is_authenticated:
        return identity
    if multi_tenant_required():
        raise HTTPException(status_code=401, detail="authentication required")
    # Single-tenant local: the app has always been loopback/operator gated; a
    # non-loopback, non-operator caller without a token is still refused for
    # privileged surfaces by `require_operator`.
    raise HTTPException(status_code=403, detail="identity required")


def require_tenant(request: Request) -> Identity:
    """FastAPI dependency: require a verified identity bound to a tenant."""
    identity = require_identity(request)
    if identity.is_operator and not identity.tenant_id:
        raise HTTPException(status_code=403, detail="operator identity is not tenant-scoped")
    if not identity.tenant_id:
        raise HTTPException(status_code=403, detail="tenant context required")
    return identity


__all__ = [
    "ANONYMOUS",
    "IDENTITY_HEADER",
    "Identity",
    "auth_secret",
    "multi_tenant_required",
    "require_identity",
    "require_tenant",
    "resolve_identity",
    "sign_identity",
    "verify_identity_token",
]
