"""Quantitative research-data HTTP routes (operator-gated).

A REST surface over the SAME services the research tools use — the Market Data
Gateway (routing/quality/provenance), the verification engine, the transforms and
the immutable dataset store. The UI and external consumers reach research data
here without going through an agent; nothing is re-implemented, and a per-request
gateway is bound to the server bridge (the ONE read-only transport).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["research-data"])


class _Ctx:
    """A per-request tool context (the same shape the research tools receive)."""

    def __init__(self) -> None:
        from ..market.gateway import MarketDataGateway

        bridge = service.server_bridge()
        self.data_bridge = bridge
        self.run_id = "http"
        self.market_gateway = MarketDataGateway(
            bridge,
            cache=getattr(service, "market_cache", None),
            router=getattr(service, "market_router", None),
        )
        self.market_store = getattr(service, "market_store", None)
        self.dataset_store = getattr(service, "dataset_store", None)


def _ctx() -> _Ctx:
    return _Ctx()


def _dataset_store() -> Any:
    store = getattr(service, "dataset_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="the dataset store is unavailable in this runtime")
    return store


def _unwrap(result: tuple[str, Any]) -> dict[str, Any]:
    _, data = result
    return data


# ── Introspection ────────────────────────────────────────────────────────────

@router.get("/research-data/policies")
async def policies(_: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.verification import list_policies

    return {"available": True, "policies": list_policies()}


@router.get("/research-data/providers")
async def providers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..tools import ToolRegistry  # noqa: F401 - keeps import surface obvious
    from ..market.research_tools import list_providers

    return _unwrap(await list_providers({}, _ctx()))


@router.get("/research-data/health")
async def health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import get_provider_health

    return _unwrap(await get_provider_health({}, _ctx()))


@router.get("/research-data/calendar")
async def calendar(market: str = "us_equity", year: Optional[int] = None,
                   _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import get_trading_calendar

    return _unwrap(await get_trading_calendar({"market": market, "year": year}, _ctx()))


@router.get("/research-data/series")
async def series(limit: int = 200, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = getattr(service, "market_store", None)
    if store is None:
        return {"available": False}
    from ..market.series_store import SeriesStore

    listing = SeriesStore(store).list_series(limit)
    return {"available": True, "series": listing}


@router.get("/research-data/quality")
async def quality(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = getattr(service, "market_store", None)
    if store is None:
        return {"available": False}
    from ..market.series_store import SeriesStore

    return {"available": True, "events": store.recent_quality(limit),
            "storedSeries": SeriesStore(store).list_series()}


# ── Retrieval / verification / transforms ────────────────────────────────────

class ResolveBody(BaseModel):
    symbol: str
    market: Optional[str] = None


@router.post("/research-data/resolve")
async def resolve(body: ResolveBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import resolve_instrument

    return _unwrap(await resolve_instrument(body.model_dump(), _ctx()))


class MarketDataBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    start: Optional[str] = None
    end: Optional[str] = None
    interval: str = "1d"
    adjusted: bool = True
    verification_policy: str = "fresh_preferred"
    provider: Optional[str] = None
    max_bars: int = 500
    tolerance: float = 0.015


@router.post("/research-data/market-data")
async def market_data(body: MarketDataBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import get_market_data

    return _unwrap(await get_market_data(body.model_dump(), _ctx()))


class VerifyBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    policy: str = "cross_verified"
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    adjusted: bool = True
    tolerance: float = 0.015
    providers: Optional[list[str]] = None


@router.post("/research-data/verify")
async def verify(body: VerifyBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import verify_market_data

    return _unwrap(await verify_market_data(body.model_dump(), _ctx()))


class ResampleBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    target_interval: str
    interval: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    adjusted: bool = True
    provider: Optional[str] = None


@router.post("/research-data/resample")
async def resample(body: ResampleBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import resample_data

    return _unwrap(await resample_data(body.model_dump(), _ctx()))


class AlignBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    column: str = "close"
    join: str = "inner"
    fill: Optional[Any] = None
    max_points: int = 500


@router.post("/research-data/align")
async def align(body: AlignBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import align_timeseries

    return _unwrap(await align_timeseries(body.model_dump(), _ctx()))


# ── Datasets ─────────────────────────────────────────────────────────────────

@router.get("/research-data/datasets")
async def list_datasets(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": True, "datasets": _dataset_store().list_datasets(limit)}


@router.get("/research-data/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, version: Optional[str] = None,
                      _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"available": True, "manifest": _dataset_store().get_version(dataset_id, version)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"code": "DATASET_NOT_FOUND", "message": str(exc)}) from exc


@router.get("/research-data/datasets/{dataset_id}/versions")
async def dataset_versions(dataset_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _dataset_store()
    try:
        return {"available": True, "versions": store.list_versions(dataset_id),
                "latest": store.get_version(dataset_id)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"code": "DATASET_NOT_FOUND", "message": str(exc)}) from exc


class BuildBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    start: Optional[str] = None
    end: Optional[str] = None
    interval: str = "1d"
    adjusted: bool = True
    verification_policy: str = "fresh_preferred"
    name: Optional[str] = None
    dataset_id: Optional[str] = None
    force: bool = False
    tolerance: float = 0.015


@router.post("/research-data/datasets/build")
async def build_dataset(body: BuildBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import build_research_dataset

    return _unwrap(await build_research_dataset(body.model_dump(), _ctx()))


class RefreshBody(BaseModel):
    from_version: Optional[str] = None
    symbols: Optional[list[str]] = None
    interval: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    adjusted: Optional[bool] = None


@router.post("/research-data/datasets/{dataset_id}/refresh")
async def refresh_dataset(dataset_id: str, body: RefreshBody,
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import refresh_dataset as _refresh

    payload = body.model_dump()
    payload["dataset_id"] = dataset_id
    return _unwrap(await _refresh(payload, _ctx()))


class ExportBody(BaseModel):
    version: Optional[str] = None
    format: str = "csv"
    symbols: Optional[list[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    as_of: Optional[str] = None


@router.post("/research-data/datasets/{dataset_id}/export")
async def export_dataset(dataset_id: str, body: ExportBody,
                         _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import export_dataset as _export

    payload = body.model_dump()
    payload["dataset_id"] = dataset_id
    return _unwrap(await _export(payload, _ctx()))


class AnalyzeBody(BaseModel):
    version: Optional[str] = None
    symbols: Optional[list[str]] = None
    symbol: Optional[str] = None
    operations: list[str] = ["summary"]
    risk_free_rate: float = 0.0
    periods_per_year: int = 252


@router.post("/research-data/datasets/{dataset_id}/analyze")
async def analyze_dataset(dataset_id: str, body: AnalyzeBody,
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import analyze_dataset as _analyze

    payload = body.model_dump()
    payload["dataset_id"] = dataset_id
    return _unwrap(await _analyze(payload, _ctx()))


# ── Fundamentals / macro ─────────────────────────────────────────────────────

class SymbolBody(BaseModel):
    symbol: str


@router.post("/research-data/fundamentals")
async def fundamentals(body: SymbolBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    bridge = service.server_bridge()
    try:
        payload = await bridge.fetch("fundamentals", {"symbol": body.symbol.strip().upper()})
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "error": {"code": "DATA_NOT_AVAILABLE", "message": str(exc)}}
    if payload.get("status") != "OK":
        return {"status": "UNAVAILABLE", "error": {"code": "DATA_NOT_AVAILABLE",
                "message": payload.get("error") or "no fundamentals stored"}}
    return {"status": "OK", "fundamentals": payload}


class MacroBody(BaseModel):
    series_id: str
    quantity: Optional[int] = None


@router.post("/research-data/macro")
async def macro(body: MacroBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    bridge = service.server_bridge()
    params: dict[str, Any] = {"seriesId": body.series_id, "quantity": body.quantity}
    try:
        payload = await bridge.fetch("macro_series", params)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "error": {"code": "DATA_NOT_AVAILABLE", "message": str(exc)}}
    if payload.get("status") != "OK":
        return {"status": "UNAVAILABLE", "error": {"code": "DATA_NOT_AVAILABLE",
                "message": payload.get("error") or "macro series unavailable"}}
    return {"status": "OK", "macro": payload}


# ── Notebook (isolated execution) ────────────────────────────────────────────

class NotebookBody(BaseModel):
    code: str
    version: Optional[str] = None
    symbols: Optional[list[str]] = None
    timeout_seconds: int = 30


@router.post("/research-data/datasets/{dataset_id}/execute")
async def execute_dataset(dataset_id: str, body: NotebookBody,
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Run operator-supplied analytical code in the isolated sandbox against a
    read-only copy of the dataset version. Never in the FastAPI process, never
    with secrets/network."""
    import asyncio
    import tempfile

    from ..research.notebook import materialize_dataset, run_notebook

    store = _dataset_store()
    try:
        workdir = tempfile.mkdtemp(prefix="nb_in_")
        dataset_path, rows = materialize_dataset(store, dataset_id, body.version, workdir, body.symbols)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail={"code": "DATASET_NOT_FOUND", "message": str(exc)}) from exc
    result = await asyncio.to_thread(run_notebook, body.code, dataset_path=dataset_path,
                                     timeout_s=body.timeout_seconds)
    result["datasetId"] = dataset_id
    result["rows"] = rows
    return result


# ── Universes ────────────────────────────────────────────────────────────────

@router.get("/research-data/universes")
async def list_universes(_: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import list_universes as _list

    return _unwrap(await _list({}, _ctx()))


class RecordUniverseBody(BaseModel):
    universe_id: str
    name: Optional[str] = None
    effective_from: Optional[str] = None
    as_of: Optional[str] = None
    members: Optional[list[Any]] = None
    symbols: Optional[list[str]] = None


@router.post("/research-data/universes/record")
async def record_universe(body: RecordUniverseBody,
                          _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..market.research_tools import record_universe as _record

    return _unwrap(await _record(body.model_dump(), _ctx()))


__all__ = ["router"]
