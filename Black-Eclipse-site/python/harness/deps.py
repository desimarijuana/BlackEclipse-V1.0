"""Shared runtime state and authorization for the FastAPI front door.

This module owns the ONE process-wide `AgenticService`, the operator
authorization dependencies, and the identity/tenancy boundary helpers. It is
imported by `main.py` (which re-exports the public names) and by the route
routers, so a router never has to import `main` (which would be circular).

Nothing here is agentic logic: it is the transport/authorization seam.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request

from .service import AgenticService

# The single, process-wide runtime service. Every route and router reaches the
# same instance. Import-time construction means env vars (DB paths, MCP config)
# must be set before importing this module — the same contract `main` had.
service = AgenticService()

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# ── Identity / tenancy boundary ──────────────────────────────────────────────
# Black Eclipse is a SINGLE-USER LOCAL application. This block names the four
# concepts that must never be conflated, so a caller cannot mistake a
# caller-supplied label for authorization:
#
#   * AUTHENTICATION — NOT implemented. There are no accounts and no login.
#   * TENANCY ISOLATION — NOT implemented. `userId`/`scopeId` are scope FILTER
#     labels, not security identities; they are self-asserted by the caller.
#   * OPERATOR AUTHORIZATION — transport/token only (loopback or the runtime
#     secret), enforced by `require_operator`; never a request-body flag.
#   * SCOPE FILTERING — enforced as filters in retrieval/listing, but because the
#     labels are caller-supplied they are a correctness boundary, not a trust
#     boundary.
#
# The app must therefore NEVER be presented as multi-user secure. A non-loopback
# bind without a configured operator secret is flagged loudly at startup and in
# `/health`.
IDENTITY_BOUNDARY: dict[str, str] = {
    "authentication": "not implemented — no accounts, no login",
    "tenancyIsolation": (
        "not implemented — single local operator; userId/scopeId are self-asserted "
        "scope labels, never identities"
    ),
    "operatorAuthorization": (
        "transport/token only (loopback or the runtime secret); never a request-body flag"
    ),
    "scopeFiltering": (
        "enforced as filters for retrieval/listing, but caller-supplied and therefore "
        "not a trust boundary"
    ),
}

_OPERATOR_SECRET_PLACEHOLDER = "change-me-to-a-random-secret"


def _is_loopback(request: Request) -> bool:
    client = request.client
    host = (client.host if client else "") or ""
    return host in _LOOPBACK_HOSTS


def _operator_secret_configured() -> bool:
    import os

    secret = os.environ.get("CRON_SECRET")
    return bool(secret) and secret != _OPERATOR_SECRET_PLACEHOLDER


def deployment_exposure(host: Optional[str] = None) -> dict[str, Any]:
    """Describe the runtime's network exposure honestly.

    `exposed` is True when the runtime is bound beyond loopback without a
    configured operator secret — i.e. reachable by another machine while every
    mutation still authenticates only by transport/token. That configuration is
    NOT multi-user safe and must be flagged, never presented as secure.
    """
    bind_host = (host if host is not None else __import__("os").environ.get("HARNESS_PY_HOST") or "").strip()
    public_bind = bool(bind_host) and bind_host not in _LOOPBACK_HOSTS
    has_secret = _operator_secret_configured()
    exposed = public_bind and not has_secret
    warning: Optional[str] = None
    if exposed:
        warning = (
            f"Runtime bound to non-loopback host {bind_host!r} without a configured "
            "CRON_SECRET. This app is single-user local and has NO authentication or "
            "tenancy isolation — userId/scopeId are self-asserted labels. Do not expose "
            "it to a network. Set CRON_SECRET and place it behind an authenticated, "
            "single-operator boundary, or bind loopback."
        )
    elif public_bind:
        warning = (
            f"Runtime bound to non-loopback host {bind_host!r}. Mutations require the "
            "operator secret, but this app still has NO authentication and NO tenancy "
            "isolation: userId/scopeId are self-asserted labels and reads are not "
            "identity-scoped. It must remain a single-operator deployment behind an "
            "authenticated boundary."
        )
    return {
        "host": bind_host or None,
        "loopback": not public_bind,
        "operatorSecretConfigured": has_secret,
        "multiUserSafe": False,
        "exposed": exposed,
        "warning": warning,
    }


def identity_boundary(host: Optional[str] = None) -> dict[str, Any]:
    """A machine-readable statement of what is and is not protected.

    Returned in `/health` so a deployment can observe, without reading the docs,
    that there is no authentication and no tenancy isolation.
    """
    boundary: dict[str, Any] = {
        "authentication": False,
        "operatorAuthorization": "transport/token",
        "tenancy": "single-user-local",
        "scopeFiltering": "caller-supplied-labels",
        "multiUserSafe": False,
        "notes": IDENTITY_BOUNDARY,
    }
    boundary["exposure"] = deployment_exposure(host)
    return boundary


def _valid_operator_token(request: Request) -> bool:
    """Validate the runtime secret WITHOUT ever logging or echoing it."""
    import hmac
    import os

    secret = os.environ.get("CRON_SECRET")
    if not secret or secret == _OPERATOR_SECRET_PLACEHOLDER:
        return False
    provided = request.headers.get("x-harness-operator") or ""
    auth = request.headers.get("authorization") or ""
    bearer = auth[7:] if auth.startswith("Bearer ") else ""
    for candidate in (provided, bearer):
        if candidate and hmac.compare_digest(candidate, secret):
            return True
    return False


def require_operator(request: Request) -> bool:
    """FastAPI dependency: prove the caller MAY set the operator flag.

    Proof is transport/token only — NEVER a caller-supplied JSON boolean:
    the request must originate from the loopback interface (the Next.js front
    door or a local operator) OR present the runtime secret in
    `X-Harness-Operator` / a Bearer token.

    A memory/skill mutation endpoint reads the body `operator` flag only AFTER
    this dependency passes, so a directly reachable Python runtime cannot be
    handed an operator decision by spoofing `{"operator": true}`; a remote
    caller without the secret is refused before the body is considered.
    """
    if _is_loopback(request) or _valid_operator_token(request):
        return True
    raise HTTPException(
        status_code=403,
        detail="this operation requires an authorized operator (loopback or runtime secret)",
    )


def require_mcp_operator(request: Request) -> None:
    """FastAPI dependency: authorize an MCP mutation by transport or token.

    Loopback is trusted (zero-config local use keeps working). A remote caller
    must present the runtime secret as `X-Harness-Operator` (or a Bearer token).
    The body is never consulted, so `{"operator": true}` cannot authorize.
    """
    if _is_loopback(request) or _valid_operator_token(request):
        return
    raise HTTPException(
        status_code=403,
        detail="MCP configuration requires an authorized operator (loopback or runtime secret)",
    )


__all__ = [
    "IDENTITY_BOUNDARY",
    "deployment_exposure",
    "identity_boundary",
    "require_mcp_operator",
    "require_operator",
    "service",
]
