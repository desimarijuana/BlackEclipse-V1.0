"""Standing-grant routes — list and revoke "always allow" permissions.

A standing grant is an explicit, operator-only permission (see `harness/grants.py`)
that removes the approval *prompt* for one program/tool in one workspace. It never
bypasses the effect classification: a `deny`-classified command is still refused,
and a grant is inert for a different digest. This router is the read/revoke surface
the Permissions screen uses; grants are CREATED only through a "always allow"
decision on a real pending approval, so a caller can never mint trust by hand.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_operator, service

router = APIRouter(tags=["grants"])


@router.get("/grants")
def list_grants(scope: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Every standing grant, newest first. `scope` narrows to one workspace."""
    approvals = service.approvals
    if approvals is None:
        return {"success": True, "grants": [], "unavailable": True}
    return {"success": True, "grants": approvals.grants.list(scope)}


@router.post("/grants/{grant_id}/revoke")
def revoke_grant(grant_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Revoke one standing grant. Idempotent: an unknown id reports not found."""
    approvals = service.approvals
    if approvals is None:
        raise HTTPException(status_code=503, detail="grants unavailable")
    removed = approvals.grants.revoke(grant_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Grant not found")
    return {"success": True, "revoked": grant_id}


__all__ = ["router"]
