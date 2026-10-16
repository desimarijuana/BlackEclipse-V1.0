"""Security routes — the operator surface for the Security subsystem.

Read-only inspection plus the administrator actions (policy reload, capability
issue/revoke, approval decide). Every mutation is operator-gated by
`require_operator` (transport/token, never a body flag).

The routes never expose a secret value: `resolve` is not offered here. They do
offer `check` (evaluate a request and return the decision) and `network/check`
(evaluate an outbound URL) so an operator can see exactly what the gateway would
do without performing the action.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import identity_for, require_operator, service
from ..security.models import (
    AuthorizationRequest,
    Environment,
    Permission,
    PolicyProfile,
)
from ..security.ratelimit import default_limiter

log = logging.getLogger("harness")

router = APIRouter(tags=["security"])


def rate_limit(request: Request) -> None:
    """Per-tenant (or per-host) abuse control for the security endpoints."""
    identity = identity_for(request)
    key = identity.tenant_id or identity.user_id or (
        request.client.host if request.client else "unknown"
    )
    bucket = f"security:{key}"
    if not default_limiter().allow(bucket):
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(int(default_limiter().retry_after(bucket)) + 1)},
        )


def _gateway():
    gateway = getattr(service, "security", None)
    if gateway is None:
        raise HTTPException(status_code=503, detail="security subsystem unavailable")
    return gateway


def security_health_safe() -> dict[str, Any]:
    """Liveness-safe security health for `/health`: never raises.

    `/health` is the front door's liveness probe; a 500 there makes it treat a
    live runtime as down and restart it (orphaning in-flight runs). A fault in
    the security subsystem must degrade to an honest failure, not the endpoint.
    """
    gateway = getattr(service, "security", None)
    if gateway is None:
        return {"ok": False, "available": False}
    try:
        return gateway.health()
    except Exception:  # noqa: BLE001 - a health fault is reported, never fatal
        log.exception("security health failed")
        return {"ok": False, "available": True, "error": "health check failed"}


def _build_request(payload: dict[str, Any]) -> AuthorizationRequest:
    permission: Optional[Permission] = None
    if payload.get("permission"):
        try:
            permission = Permission(str(payload["permission"]).lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="unknown permission") from None
    return AuthorizationRequest(
        action=str(payload.get("action") or ""),
        resource=str(payload.get("resource") or ""),
        permission=permission,
        actor=str(payload.get("actor") or "operator"),
        user=payload.get("user"),
        agent=payload.get("agent"),
        session=payload.get("session"),
        task=payload.get("task"),
        tool=payload.get("tool"),
        environment=Environment.parse(payload.get("environment")),
        workspace=payload.get("workspace"),
        context=payload.get("context") or {},
    )


@router.get("/security/status")
def security_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_gateway().status()}


@router.get("/security/health")
def security_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_gateway().health()}


@router.get("/security/metrics")
def security_metrics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **service.security.audit.summary(), "health": service.security.health()}


@router.get("/security/policy")
def get_policy(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "policy": _gateway().get_policy()}


@router.post("/security/policy/reload")
def reload_policy(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    gateway = _gateway()
    documents = payload.get("policy") if isinstance(payload.get("policy"), dict) else payload.get("layers")
    if not isinstance(documents, dict):
        raise HTTPException(status_code=400, detail="body must contain a policy mapping")
    profile = payload.get("profile")
    if profile is not None and str(profile).lower() not in PolicyProfile._value2member_map_:
        raise HTTPException(status_code=400, detail="unknown profile")
    try:
        record = gateway.reload_policy(documents, profile=profile, actor="operator")
    except Exception as exc:  # noqa: BLE001 - a bad policy is a 400, never a swap
        raise HTTPException(status_code=400, detail=f"policy rejected: {exc}") from exc
    return {"success": True, **record}


@router.get("/security/audit")
def list_audit(
    category: Optional[str] = None,
    session_id: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {
        "success": True,
        "events": _gateway().audit.list(
            category=category, session_id=session_id, decision=decision, limit=limit,
        ),
    }


@router.get("/security/audit/verify")
def verify_audit(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_gateway().audit.verify()}


@router.get("/security/capabilities")
def list_capabilities(subject: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "capabilities": _gateway().capabilities.snapshot()}


@router.post("/security/capabilities")
def issue_capability(payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    gateway = _gateway()
    action = str(payload.get("action") or "")
    subject = str(payload.get("subject") or "")
    if not action or not subject:
        raise HTTPException(status_code=400, detail="subject and action are required")
    cap = gateway.issue_capability(
        subject=subject,
        action=action,
        resource=str(payload.get("resource") or "**"),
        scope=str(payload.get("scope") or ""),
        constraints=tuple(payload.get("constraints") or ()),
        ttl_seconds=payload.get("ttlSeconds"),
        session_id=payload.get("session"),
        task_id=payload.get("task"),
        issuer="operator",
    )
    return {"success": True, "capability": cap.to_dict()}


@router.post("/security/capabilities/{capability_id}/revoke")
def revoke_capability(capability_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ok = _gateway().revoke_capability(capability_id)
    if not ok:
        raise HTTPException(status_code=404, detail="capability not found")
    return {"success": True, "revoked": capability_id}


@router.get("/security/approvals")
def list_approvals(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "approvals": _gateway().approvals.list_pending(limit)}


@router.post("/security/approvals/{approval_id}/decide")
def decide_approval(approval_id: str, payload: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    approve = bool(payload.get("approve"))
    record = _gateway().approvals.decide(
        approval_id, approve=approve,
        decided_by=str(payload.get("decidedBy") or "operator"),
        reason=str(payload.get("reason") or ""),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if approve and bool(payload.get("remember")):
        _gateway().approvals.remember(approval_id)
    return {"success": True, "approval": record}


@router.post("/security/check")
def check_request(payload: dict[str, Any], _: bool = Depends(require_operator), __: None = Depends(rate_limit)) -> dict[str, Any]:
    """Evaluate a request WITHOUT performing it (dry-run decision)."""
    gateway = _gateway()
    request = _build_request(payload)
    decision = gateway.authorize(request, claim_approval=False)
    return {"success": True, "decision": decision.to_dict(), "request": request.to_dict()}


@router.post("/security/network/check")
def check_network(payload: dict[str, Any], _: bool = Depends(require_operator), __: None = Depends(rate_limit)) -> dict[str, Any]:
    url = str(payload.get("url") or "")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    decision = _gateway().check_network(url, direction=str(payload.get("direction") or "egress"))
    return {"success": True, "decision": decision.to_dict()}


__all__ = ["router"]
