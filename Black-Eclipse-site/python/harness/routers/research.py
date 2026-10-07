"""Web research engine HTTP routes.

Thin, operator-gated adapters over the SAME engine the agent tools use. The
routes reach shared runtime state only through `harness.deps.service`, so UI and
agent can never disagree, and a second engine is never constructed.

Mutations (create/run/cancel/continue/update) require an operator; reads
(list/get/status) are operator-gated too, because the research surface carries
retrieved evidence.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["research"])


class ResearchRunBody(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    depth: Optional[str] = None
    freshness: Optional[str] = None
    pointInTime: Optional[str] = None  # noqa: N815
    sourceTypes: list[str] = Field(default_factory=list)  # noqa: N815
    minSources: int = Field(default=3, ge=1, le=50)  # noqa: N815
    maxSources: int = Field(default=12, ge=1, le=100)  # noqa: N815
    maxQueries: int = Field(default=12, ge=1, le=100)  # noqa: N815
    maxTimeSeconds: float = Field(default=120.0, ge=1.0, le=1800.0)  # noqa: N815
    citationsRequired: bool = True  # noqa: N815
    crossValidationRequired: bool = False  # noqa: N815
    primarySourcesRequired: bool = False  # noqa: N815


def _store():
    store = getattr(service, "evidence_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="the web research engine is unavailable")
    return store


def _bridge():
    """Build a bridge to the front door for this request (the same transport tools use)."""
    from ..service import _default_callback_base_url

    try:
        return service.build_bridge(_default_callback_base_url(), None)
    except Exception:  # noqa: BLE001 - a bridge failure is an unavailable route, not a crash
        return None


def _new_engine():
    from ..research.web_engine import ResearchEngine

    return ResearchEngine(bridge=_bridge(), store=getattr(service, "evidence_store", None))


def _request(body: ResearchRunBody):
    from ..research.web_contracts import ResearchDepth, ResearchRequest, SourceType

    try:
        depth = ResearchDepth(body.depth) if body.depth else ResearchDepth.STANDARD
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown depth {body.depth!r}") from None
    source_types = []
    for value in body.sourceTypes:
        try:
            source_types.append(SourceType(value))
        except ValueError:
            continue
    return ResearchRequest(
        question=body.question,
        depth=depth,
        freshness=body.freshness,
        pointInTime=body.pointInTime,
        sourceTypes=source_types,
        minSources=body.minSources,
        maxSources=body.maxSources,
        maxQueries=body.maxQueries,
        maxTimeSeconds=body.maxTimeSeconds,
        citationsRequired=body.citationsRequired,
        crossValidationRequired=body.crossValidationRequired,
        primarySourcesRequired=body.primarySourcesRequired,
    )


@router.post("/research/web/run")
async def run_web_research(body: ResearchRunBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _new_engine()
    result = await engine.run(_request(body))
    return {"success": True, "result": result.to_dict()}


@router.post("/research/web/plan")
async def plan_web_research(body: ResearchRunBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _new_engine()
    mandate, plan = await engine.create_research(_request(body))
    return {"success": True, "researchId": mandate.researchId, "mandate": mandate.model_dump(), "plan": plan.model_dump()}


@router.get("/research/web/list")
def list_web_research(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "runs": _store().list_runs(limit=limit)}


@router.get("/research/web/{research_id}")
def get_web_research(research_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _store()
    run = store.get_run(research_id)
    if run is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return {
        "success": True,
        "run": run,
        "evidence": [_bound_evidence(e) for e in store.list_evidence(research_id)],
        "sources": store.list_sources(research_id),
        "claims": store.list_claims(research_id),
        "citations": store.list_citations(research_id),
        "conflicts": store.list_conflicts(research_id),
        "snapshots": _bound_snapshots(store.list_snapshots(research_id)),
    }


# The stored record keeps the full raw text; the API payload is bounded so a deep
# run cannot return a multi-megabyte response.
_MAX_API_RAW_CHARS = 8_000


def _bound_evidence(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("rawText") or ""
    if isinstance(raw, str) and len(raw) > _MAX_API_RAW_CHARS:
        row = {**row, "rawText": raw[:_MAX_API_RAW_CHARS], "rawTextTruncated": True, "rawTextChars": len(raw)}
    return row


def _bound_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for snap in snapshots:
        payload = snap.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("evidence"), list):
            payload = {**payload, "evidence": [_bound_evidence(e) for e in payload["evidence"]]}
        out.append({**snap, "payload": payload})
    return out


@router.get("/research/web/{research_id}/status")
def web_research_status(research_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..research.web_engine import run_status

    status = run_status(research_id)
    if status is not None:
        return {"success": True, "status": status.model_dump()}
    row = _store().get_run(research_id)
    if row is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return {"success": True, "status": {"researchId": research_id, "state": row.get("state"), "stopReason": row.get("status")}}


@router.post("/research/web/{research_id}/cancel")
def cancel_web_research(research_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..research.web_engine import request_cancel

    return {"success": request_cancel(research_id)}


@router.post("/research/web/{research_id}/continue")
async def continue_web_research(research_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _new_engine()
    result = await engine.continue_research(research_id)
    if result is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return {"success": True, "result": result.to_dict()}


@router.post("/research/web/{research_id}/update")
async def update_web_research(research_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    engine = _new_engine()
    result = await engine.update_research(research_id)
    if result is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return {"success": True, "result": result.to_dict()}


__all__ = ["router"]
