"""Recovery routes — the operator surface for the failure-intelligence engine.

Read-only inspection of the recorded failure incidents, their classification, the
recovery decision taken and the attempt history; plus one operator-gated action
to record an attempt's outcome. Every mutation is gated by `require_operator`
(transport/token, never a body flag).

No route exposes a secret: incidents carry only the already-sanitized code,
message and metadata the emitting subsystem supplied.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_operator, service

router = APIRouter(tags=["recovery"])


def _engine():
    engine = getattr(service, "recovery", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="recovery engine unavailable")
    return engine


@router.get("/recovery/health")
def recovery_health() -> dict[str, Any]:
    return _engine().health()


@router.get("/recovery/summary")
def recovery_summary() -> dict[str, Any]:
    return _engine().summary()


@router.get("/recovery/incidents")
def list_incidents(
    status: Optional[str] = Query(default=None),
    task_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    incidents = _engine().list_incidents(status=status, task_id=task_id, limit=limit)
    return {"incidents": incidents, "count": len(incidents)}


@router.get("/recovery/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict[str, Any]:
    engine = _engine()
    incident = engine.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"incident": incident, "attempts": engine.incident_attempts(incident_id)}


@router.get("/recovery/discover")
def discover(query: str = Query(..., min_length=1), limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
    engine = _engine()
    matches = engine.discover(query, limit=limit)
    return {"query": query, "matches": matches, "plan": engine.plan_acquisition(query)}


@router.get("/recovery/envelope")
def get_envelope() -> dict[str, Any]:
    return {"envelope": _engine().envelope_view()}


@router.put("/recovery/envelope")
def set_envelope(
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    from ..recovery.envelope import from_dict  # noqa: PLC0415

    envelope = from_dict(payload or {}, source="operator")
    return {"envelope": _engine().set_envelope(envelope)}


@router.get("/recovery/operations")
def list_operations(
    incident_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    ledger = _engine().operations
    if incident_id:
        operations = ledger.list_by_incident(incident_id, limit=limit)
    else:
        operations = ledger.pending_compensations(limit=limit)
    return {"operations": operations, "count": len(operations)}


@router.get("/recovery/incidents/{incident_id}/approvals")
def list_approvals(incident_id: str) -> dict[str, Any]:
    return {"approvals": _engine().approvals(incident_id)}


@router.post("/recovery/incidents/{incident_id}/approve")
def approve(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    strategy = str(payload.get("strategy") or "").strip()
    if not strategy:
        raise HTTPException(status_code=400, detail="strategy is required")
    approval = _engine().approve(
        incident_id, strategy, approved_by=payload.get("approvedBy") or "operator"
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"approval": approval}


@router.post("/recovery/incidents/{incident_id}/diagnose")
def diagnose(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    diagnosis = _engine().diagnose_incident(incident_id, evidence=payload or {})
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"diagnosis": diagnosis}


@router.post("/recovery/promote")
def promote(
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    engine = _engine()
    min_occurrences = int(payload.get("minOccurrences", 2))
    result = engine.promote_incidents(
        min_occurrences=max(2, min_occurrences),
        limit=int(payload.get("limit", 50)),
    )
    return result


@router.post("/recovery/incidents/{incident_id}/outcome")
def record_outcome(
    incident_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    engine = _engine()
    outcome = str(payload.get("outcome") or "").strip()
    if outcome not in ("succeeded", "resolved", "failed", "exhausted"):
        raise HTTPException(status_code=400, detail="unknown outcome")
    attempt = engine.record_outcome(incident_id, outcome=outcome, detail=payload.get("detail"))
    if attempt is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"attempt": attempt}
