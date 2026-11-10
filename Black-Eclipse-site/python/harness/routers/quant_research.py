"""HTTP routes for Quant Research Intelligence.

Thin adapters over the same functions the agent tools call, so the UI and the
agent cannot disagree. Every route is operator-gated. No route computes a
statistic; the deterministic engine and the reproduction harness do.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant.research_intel.dossier import build_dossier
from ..quant.research_intel.repro import reproduce_method, validate_reproduction
from ..quant.research_intel.schema import normalize_spec, validate_method_spec
from ..quant.research_intel.store import ResearchStore
from ..quant.research_intel.tools import (
    quant_attach_implementation_tool,
    research_compare_methods_tool,
    research_extract_method_tool,
    research_get_citations_tool,
    research_get_paper_tool,
    research_method_matrix_tool,
    research_search_papers_tool,
    research_visualize_tool,
)
from .quant import _http, _store

router = APIRouter(tags=["quant"])


def _research_store() -> ResearchStore:
    return ResearchStore(_store())


def _ctx() -> Any:
    try:
        bridge = service.server_bridge()
    except Exception:  # noqa: BLE001 - a route can still work without a bridge
        bridge = None
    return SimpleNamespace(
        quant_store=getattr(service, "quant_store", None),
        data_bridge=bridge,
        artifact_service=getattr(service, "artifacts", None),
        run_id="http-route",
    )


def _ok(data: Any) -> Any:
    if isinstance(data, dict) and data.get("status") == "ERROR":
        detail = data.get("error") or {}
        raise HTTPException(status_code=400, detail=detail)
    return data


# ── external research ────────────────────────────────────────────────────────

class SearchBody(BaseModel):
    objective: Optional[str] = None
    problem: Optional[str] = None
    query: Optional[str] = None
    instrument: str = ""
    timeframe: str = ""
    sources: list[str] = Field(default_factory=list)
    limit: int = 8
    maxQueries: int = 8
    researchId: Optional[str] = None


@router.post("/quant/research/search")
async def research_search(body: SearchBody, _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_search_papers_tool(body.model_dump(), _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class PaperBody(BaseModel):
    literatureId: str
    url: Optional[str] = None
    text: Optional[str] = None


@router.post("/quant/research/paper")
async def research_paper(body: PaperBody, _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_get_paper_tool(body.model_dump(), _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/research/citations/{literature_id}")
async def research_citations(literature_id: str, direction: str = "both",
                             depth: int = 1,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_get_citations_tool(
            {"literatureId": literature_id, "direction": direction, "depth": depth}, _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ExtractBody(BaseModel):
    literatureId: str
    text: Optional[str] = None
    url: Optional[str] = None
    methodHint: Optional[str] = None
    structured: Optional[dict[str, Any]] = None
    proposal: Optional[dict[str, Any]] = None
    persist: bool = True


@router.post("/quant/research/extract")
async def research_extract(body: ExtractBody, _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_extract_method_tool(body.model_dump(), _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class CompareBody(BaseModel):
    methodIds: list[str] = Field(default_factory=list)
    objective: Optional[str] = None
    query: Optional[str] = None
    instrument: str = ""
    timeframe: str = ""
    availableData: list[str] = Field(default_factory=list)
    complexityMax: Optional[int] = None
    constraints: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/research/compare")
async def research_compare(body: CompareBody, _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_compare_methods_tool(body.model_dump(), _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/research/evidence/{method_id}")
async def research_evidence(method_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _research_store()
        store.seed_catalog()
        record = store.get_method_spec(method_id)
        papers = store.list_papers(method_id)
        literature = []
        for link in papers:
            try:
                literature.append(store.get_literature(link["literatureId"]))
            except Exception:  # noqa: BLE001
                continue
        return {
            "status": "OK",
            "method": record,
            "papers": papers,
            "literature": literature,
            "relationships": store.list_relationships(method_id),
            "reproductions": store.list_reproductions(method_id),
            "implementations": store.list_implementations(method_id),
        }
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/research/matrix")
async def research_matrix(family: Optional[str] = None,
                          _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_method_matrix_tool({"family": family}, _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class VisualizeBody(BaseModel):
    methodIds: list[str] = Field(default_factory=list)
    objective: Optional[str] = None
    instrument: Optional[str] = None
    horizon: Optional[str] = None
    availableData: list[str] = Field(default_factory=list)
    symbol: Optional[str] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    series: Optional[list[dict[str, Any]]] = None
    reproductionId: Optional[str] = None
    loadData: bool = True


@router.post("/quant/research/visualize")
async def research_visualize(body: VisualizeBody,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await research_visualize_tool(body.model_dump(), _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── knowledge base ───────────────────────────────────────────────────────────

class SpecifyBody(BaseModel):
    spec: dict[str, Any]
    persist: bool = True


@router.post("/quant/methods/specify")
async def specify_method(body: SpecifyBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _research_store()
        spec = normalize_spec(body.spec)
        issues = validate_method_spec(spec)
        if issues:
            return {"status": "INCOMPLETE", "issues": issues, "spec": spec}
        if body.persist:
            spec["lifecycleStatus"] = spec.get("lifecycleStatus") or "specified"
            store.save_method_spec(spec, status="discovered")
            for lit in (spec.get("provenance") or {}).get("literatureIds") or []:
                store.link_paper(spec["methodId"], lit)
        return {"status": "OK", "spec": spec}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ReproduceBody(BaseModel):
    symbol: Optional[str] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    series: Optional[list[dict[str, Any]]] = None
    publishedBenchmark: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    datasetId: Optional[str] = None
    datasetVersion: Optional[str] = None
    tolerance: float = 0.25


@router.post("/quant/methods/{method_id}/reproduce")
async def reproduce_method_route(method_id: str, body: ReproduceBody,
                                 _: bool = Depends(require_operator)) -> dict:
    try:
        store = _research_store()
        store.seed_catalog()
        series = body.series
        if series is None:
            if not body.symbol:
                raise HTTPException(status_code=400,
                                    detail="pass `series` or `symbol`")
            from ..quant.research_intel.repro import load_series

            series = await load_series(_ctx(), symbol=body.symbol, interval=body.interval,
                                       start=body.start, end=body.end)
        record = reproduce_method(
            store, method_id=method_id, series=series,
            published_benchmark=body.publishedBenchmark or None,
            params=body.params or None,
            dataset_id=body.datasetId, dataset_version=body.datasetVersion,
            tolerance=body.tolerance,
        )
        return {"status": "OK", "reproduction": record}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ImplementationBody(BaseModel):
    source: str
    series: Optional[list[dict[str, Any]]] = None
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/methods/{method_id}/implementation")
async def attach_implementation(method_id: str, body: ImplementationBody,
                                _: bool = Depends(require_operator)) -> dict:
    try:
        _, data = await quant_attach_implementation_tool({
            "methodId": method_id, "source": body.source,
            "series": body.series, "params": body.params,
        }, _ctx())
        return _ok(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/reproductions/{reproduction_id}/validate")
async def validate_method_route(reproduction_id: str,
                                _: bool = Depends(require_operator)) -> dict:
    try:
        return {"status": "OK", **validate_reproduction(_research_store(), reproduction_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── dossiers ─────────────────────────────────────────────────────────────────

class DossierBody(BaseModel):
    title: str = "Quant research dossier"
    question: str
    sessionId: Optional[str] = None
    researchId: Optional[str] = None
    methodIds: list[str] = Field(default_factory=list)
    literatureIds: list[str] = Field(default_factory=list)
    reproductionIds: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    series: Optional[list[dict[str, Any]]] = None
    symbol: Optional[str] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None


@router.post("/quant/dossiers")
async def create_dossier(body: DossierBody, _: bool = Depends(require_operator)) -> dict:
    try:
        series = body.series
        if series is None and body.symbol:
            from ..quant.research_intel.repro import load_series

            series = await load_series(_ctx(), symbol=body.symbol,
                                       interval=body.interval, start=body.start,
                                       end=body.end)
        result = build_dossier(
            _research_store(),
            title=body.title, question=body.question,
            artifact_service=getattr(service, "artifacts", None),
            session_id=body.sessionId, research_id=body.researchId,
            method_ids=body.methodIds, literature_ids=body.literatureIds,
            reproduction_ids=body.reproductionIds,
            constraints=body.constraints or None, summary=body.summary,
            run_id="http-route", series=series, symbol=body.symbol or "",
        )
        return {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/dossiers")
async def list_dossiers(sessionId: Optional[str] = None, limit: int = 50,
                        _: bool = Depends(require_operator)) -> dict:
    try:
        rows = _research_store().list_dossiers(session_id=sessionId, limit=limit)
        return {"dossiers": rows}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/dossiers/{dossier_id}")
async def get_dossier(dossier_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"dossier": _research_store().get_dossier(dossier_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── register (explicit) ──────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    spec: dict[str, Any]
    lifecycleStatus: str = "specified"
    reproductionIds: list[str] = Field(default_factory=list)


@router.post("/quant/methods/register")
async def register_method(body: RegisterBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _research_store()
        spec = normalize_spec(body.spec)
        issues = validate_method_spec(spec)
        if issues:
            return {"status": "INCOMPLETE", "issues": issues}
        if body.lifecycleStatus in ("validated", "evaluated"):
            passing = []
            for rep_id in body.reproductionIds:
                try:
                    rep = store.get_reproduction(rep_id)
                except Exception:  # noqa: BLE001
                    continue
                if (rep.get("validation") or {}).get("status") == "pass":
                    passing.append(rep_id)
            if not passing:
                raise HTTPException(
                    status_code=400,
                    detail="a validated lifecycle requires a reproduction whose "
                           "validation status is 'pass'",
                )
        spec["lifecycleStatus"] = body.lifecycleStatus
        saved = store.save_method_spec(spec, status="discovered")
        for lit in (spec.get("provenance") or {}).get("literatureIds") or []:
            store.link_paper(spec["methodId"], lit)
        return {"status": "OK", "method": saved}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
