"""Advisory Ledger HTTP routes.

Thin adapters over the SAME `AdvisoryService` the agent tools use (reached
through `harness.deps.service`). All routes are operator-gated (loopback or
runtime token), matching every other runtime surface.

Read-only: the ledger is written by the runtime at the answer seam, never by a
route. An optional actor identity (`X-Harness-User` or `actorId`) filters by
owner.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from ..deps import require_operator, service

router = APIRouter(tags=["advisory"])


def _ledger() -> Any:
    ledger = getattr(service, "advisory", None)
    if ledger is None:
        raise HTTPException(status_code=503, detail="the advisory ledger is unavailable")
    return ledger


def _actor(request: Request, body: Optional[dict[str, Any]] = None,
           query_actor: Optional[str] = None) -> Optional[str]:
    return (
        request.headers.get("x-harness-user")
        or (body or {}).get("actorId")
        or query_actor
    )


@router.get("/advisory/decisions")
async def advisory_decisions(request: Request, portfolio_id: Optional[str] = None,
                             status: Optional[str] = None, limit: int = 100,
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": True, "decisions": _ledger().list_decisions(
        portfolio_id=portfolio_id, owner_id=_actor(request), status=status, limit=limit,
    )}


@router.get("/advisory/decisions/{decision_id}")
async def advisory_decision(decision_id: str,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    record = _ledger().get_decision(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such recommendation")
    return record


@router.get("/advisory/scorecard")
async def advisory_scorecard(request: Request, portfolio_id: Optional[str] = None,
                             _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _ledger().scorecard(portfolio_id=portfolio_id, owner_id=_actor(request))


@router.post("/advisory/decisions/{decision_id}/outcome")
async def advisory_record_outcome(decision_id: str, request: Request,
                                  body: dict[str, Any] = Body(...),
                                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    if "realizedReturn" not in body:
        raise HTTPException(status_code=400, detail="`realizedReturn` is required")
    result = _ledger().record_outcome(
        decision_id,
        realized_return=float(body["realizedReturn"]),
        benchmark_return=(float(body["benchmarkReturn"]) if body.get("benchmarkReturn") is not None else None),
        horizon=body.get("horizon"), note=body.get("note"),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="no such recommendation")
    return result


@router.post("/advisory/evaluate")
async def advisory_evaluate(body: dict[str, Any] = Body(...),
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Evaluate open decisions against caller-supplied marks (closes the loop).

    `marks` maps a symbol to its current price. Only decisions with a captured
    entry price AND a matching mark are evaluated; the rest are skipped, never
    invented.
    """
    marks = body.get("marks")
    if not isinstance(marks, dict) or not marks:
        raise HTTPException(status_code=400, detail="`marks` (symbol → price) is required")
    outcomes = _ledger().evaluate_decisions(
        {str(k): float(v) for k, v in marks.items()},
        benchmark_return=(float(body["benchmarkReturn"]) if body.get("benchmarkReturn") is not None else None),
        horizon=body.get("horizon"),
    )
    return {"success": True, "evaluated": len(outcomes), "outcomes": outcomes}
