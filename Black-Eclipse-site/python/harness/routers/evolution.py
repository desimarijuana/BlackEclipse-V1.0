"""Self-improvement (evolution) route group (Phase 10).

Registered by `main.py` via `app.include_router`. Shared state comes from
`deps.py` — never by importing `main`.

EVERY route carries `require_operator` — reads AND mutations — exactly as the MCP
route group was hardened to do (ADR-H48). A candidate proposes a change to the
app's own code, so none of it is reachable without operator proof, and a body flag
never authorizes.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..code import evolution as evo
from ..code.evolution_service import activate, evaluate, rollback
from ..code.evolution_store import EvolutionStore
from ..deps import require_operator, service

router = APIRouter(tags=["evolution"])


def _store() -> EvolutionStore:
    return service.evolution_store()


class EvaluateRequest(BaseModel):
    runId: Optional[str] = None  # noqa: N815


class DecisionRequest(BaseModel):
    reason: str = ""
    canary: bool = False


@router.get("/evolution/candidates")
def list_candidates(status: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "candidates": _store().list_candidates(status=status, limit=100)}


@router.get("/evolution/candidates/{candidate_id}")
def get_candidate(candidate_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    candidate = _store().get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"success": True, "candidate": candidate}


@router.get("/evolution/candidates/{candidate_id}/attempts")
def list_attempts(candidate_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if _store().get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"success": True, "attempts": _store().list_attempts(candidate_id, limit=100)}


@router.post("/evolution/candidates/{candidate_id}/evaluate")
def evaluate_candidate_route(
    candidate_id: str, body: EvaluateRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    ctx = service.evolution_context(run_id=body.runId or f"evolution_{candidate_id}")
    result = evaluate(service.store, candidate_id, ctx=ctx, actor=service.operator_actor())
    if not result.get("ok") and not result.get("refused"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "evaluation failed"))
    return {"success": bool(result.get("ok")), **result}


@router.post("/evolution/candidates/{candidate_id}/activate")
def activate_candidate_route(
    candidate_id: str, body: DecisionRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    result = activate(
        service.store, candidate_id, registry=service.skill_registry,
        actor=service.operator_actor(), canary=body.canary,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "activation failed"))
    return {"success": True, **result}


@router.post("/evolution/candidates/{candidate_id}/rollback")
def rollback_candidate_route(
    candidate_id: str, body: DecisionRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    result = rollback(
        service.store, candidate_id, registry=service.skill_registry,
        actor=service.operator_actor(), reason=body.reason,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "rollback failed"))
    return {"success": True, **result}


@router.post("/evolution/candidates/{candidate_id}/dismiss")
def dismiss_candidate_route(candidate_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if _store().get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = _store().update_candidate(candidate_id, status="dismissed")
    return {"success": True, "candidate": candidate}


@router.get("/evolution/metrics")
def evolution_metrics(windowDays: int = 90, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **evo.archive_metrics(service.store, window_days=windowDays)}


__all__ = ["router"]
