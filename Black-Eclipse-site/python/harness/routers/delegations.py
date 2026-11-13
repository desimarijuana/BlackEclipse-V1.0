"""W7 delegation lifecycle routes.

Reads are operator-gated like every code read; cancel/steer are the same. The
runtime owns narrowing and approval; this router only exposes the durable
delegation records the Fabric worker already wrote.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..delegation_lifecycle import cancel, get_status
from ..delegation_store import DelegationStore
from ..deps import require_operator, service

router = APIRouter(tags=["delegations"])


class SteerRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("/delegations")
def list_delegations(
    parentRunId: Optional[str] = None,  # noqa: N803
    limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = getattr(service, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "RUNTIME_UNAVAILABLE"})
    if parentRunId:
        batches = DelegationStore(store).list_for_parent(parentRunId, limit=limit)
    else:
        batches = []
    return {"success": True, "delegations": batches}


@router.get("/delegations/{delegation_id}")
def get_delegation(
    delegation_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    batch = get_status(service.store, delegation_id=delegation_id)
    if not batch.get("found"):
        raise HTTPException(status_code=404, detail={"code": "DELEGATION_NOT_FOUND"})
    return {"success": True, **batch}


@router.post("/delegations/{delegation_id}/cancel")
async def cancel_delegation(
    delegation_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    result = await cancel(service.store, delegation_id=delegation_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail={"code": "DELEGATION_NOT_FOUND"})
    return {"success": True, **result}


@router.post("/delegations/{delegation_id}/steer")
def steer_delegation(
    delegation_id: str, body: SteerRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    db = DelegationStore(service.store)
    batch = db.get(delegation_id)
    if not batch.get("found"):
        raise HTTPException(status_code=404, detail={"code": "DELEGATION_NOT_FOUND"})
    if batch.get("status") in ("completed", "failed", "cancelled", "refused"):
        raise HTTPException(status_code=409, detail={"code": "DELEGATION_FINISHED"})
    try:
        from ..config.flags import get_int  # noqa: PLC0415

        seq = db.append_steer(
            delegation_id, body.message,
            max_pending=max(1, get_int("HARNESS_DELEGATION_STEER_MAX")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "DELEGATION_STEER_LIMIT", "message": str(exc),
        }) from exc
    return {"success": True, "delegationId": delegation_id, "seq": seq}


__all__ = ["router"]
