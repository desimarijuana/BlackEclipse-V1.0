"""Statistical Analysis Engine HTTP routes (operator-gated).

A thin surface over the SAME deterministic engine, registry, cache and store the
agent tools use. Reaches shared runtime state only through `harness.deps`. The
feature/formula/analysis/job routes are declared before the `/{tool}` catch-all
so they are matched first.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..stats import StatsError, TOOLS, TOOL_NAMES, run_tool
from ..stats.feature_registry import FeatureDefinition, FeatureRegistry
from ..stats.runner import get_runner
from ..stats.service import (
    execute,
    execute_formula,
    execute_with_data,
    get_stats_store,
    validate_formula,
)

router = APIRouter(prefix="/stats/v1", tags=["stats"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, StatsError):
        return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.message})
    return HTTPException(status_code=500, detail={"code": "STATS_ERROR", "message": str(exc)})


def _store() -> Any:
    store = get_stats_store()
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "UNAVAILABLE",
                                                     "message": "the statistical store is unavailable"})
    return store


def _market_gateway() -> Any:
    from ..market.gateway import MarketDataGateway  # noqa: PLC0415

    return MarketDataGateway(
        service.server_bridge(),
        cache=getattr(service, "market_cache", None),
        router=getattr(service, "market_router", None),
    )


# ── capabilities / tools ─────────────────────────────────────────────────────

@router.get("/capabilities")
async def stats_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": bool(get_stats_store()), "tools": list(TOOL_NAMES)}


@router.get("/tools")
async def stats_tools(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"tools": [
        {"name": name, "category": spec.category, "description": spec.description,
         "inputSchema": spec.input_schema}
        for name, spec in TOOLS.items()
    ]}


# ── datasets ─────────────────────────────────────────────────────────────────

@router.get("/datasets/series")
async def stats_dataset_series(symbol: str, interval: str = "1d", start: Optional[str] = None,
                               end: Optional[str] = None, field: str = "close",
                               _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..stats.datasets import resolve_series  # noqa: PLC0415

    try:
        return await resolve_series(_market_gateway(), symbol, interval=interval, start=start,
                                    end=end, field=field)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── analyses ─────────────────────────────────────────────────────────────────

class AnalysisBody(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    useCache: bool = True


@router.post("/analyses")
async def stats_create_analysis(body: AnalysisBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return execute(body.tool, body.arguments, use_cache=body.useCache)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/analyses")
async def stats_list_analyses(tool: Optional[str] = None, limit: int = 50,
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"analyses": _store().list_analyses(tool=tool, limit=limit)}


@router.get("/analyses/{analysis_id}")
async def stats_get_analysis(analysis_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    record = _store().get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown analysis"})
    return record


class DataAnalysisBody(BaseModel):
    tool: str
    symbols: list[str]
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    field: str = "close"
    arguments: dict[str, Any] = Field(default_factory=dict)


def _data_analysis_runner(body: DataAnalysisBody):
    gateway = _market_gateway()

    async def factory(progress):
        progress("running", 0, len(body.symbols))
        envelope = await execute_with_data(
            body.tool, gateway, body.symbols, interval=body.interval, start=body.start,
            end=body.end, field=body.field, tool_args=body.arguments)
        progress("done", len(body.symbols), len(body.symbols))
        return envelope

    return factory


@router.post("/analyses/run")
async def stats_run_data_analysis(body: DataAnalysisBody,
                                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return await execute_with_data(
            body.tool, _market_gateway(), body.symbols, interval=body.interval, start=body.start,
            end=body.end, field=body.field, tool_args=body.arguments)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/analyses/submit")
async def stats_submit_data_analysis(body: DataAnalysisBody,
                                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        run_id = get_runner().submit("analysis", _data_analysis_runner(body),
                                     message=f"{body.tool} {body.symbols}")
        return {"runId": run_id}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── jobs ─────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def stats_jobs(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"jobs": get_runner().list()}


@router.get("/jobs/{run_id}")
async def stats_job(run_id: str, includeResult: bool = False,
                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    run = get_runner().get(run_id, include_result=includeResult)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown run"})
    return run


@router.post("/jobs/{run_id}/cancel")
async def stats_cancel_job(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"cancelled": get_runner().cancel(run_id)}


# ── formulas ─────────────────────────────────────────────────────────────────

class FormulaBody(BaseModel):
    expression: str
    sample: dict[str, Any] = Field(default_factory=dict)


@router.post("/formulas/validate")
async def stats_validate_formula(body: FormulaBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return validate_formula(body.expression)


@router.post("/formulas/execute")
async def stats_execute_formula(body: FormulaBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return execute_formula(body.expression, body.sample)


# ── feature registry ─────────────────────────────────────────────────────────

class FeatureBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    expression: Optional[str] = None
    pipeline: Optional[list[dict[str, Any]]] = None
    paramSchema: Optional[dict[str, Any]] = None
    inputSchema: Optional[dict[str, Any]] = None
    outputSchema: Optional[dict[str, Any]] = None
    changelog: Optional[str] = None
    owner: Optional[str] = None
    visibility: str = "personal"
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    sample: Optional[dict[str, Any]] = None


def _definition(body: FeatureBody) -> FeatureDefinition:
    return FeatureDefinition(
        expression=body.expression, pipeline=body.pipeline,
        param_schema=body.paramSchema or {}, input_schema=body.inputSchema or {},
        output_schema=body.outputSchema or {}, changelog=body.changelog,
    )


@router.get("/features")
async def stats_list_features(owner: Optional[str] = None, category: Optional[str] = None,
                              includeArchived: bool = False,
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"features": FeatureRegistry(_store()).list(
        owner=owner, category=category, include_archived=includeArchived)}


@router.post("/features")
async def stats_save_feature(body: FeatureBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        registry = FeatureRegistry(_store())
        feature = registry.save(
            name=body.name or "", definition=_definition(body), description=body.description,
            owner=body.owner, visibility=body.visibility, category=body.category, tags=body.tags)
        return {"feature": feature}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/features/{feature_id}")
async def stats_get_feature(feature_id: str, version: Optional[str] = None,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return FeatureRegistry(_store()).get(feature_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/features/{feature_id}/versions")
async def stats_feature_versions(feature_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"versions": FeatureRegistry(_store()).versions(feature_id)}


@router.post("/features/{feature_id}/versions")
async def stats_new_feature_version(feature_id: str, body: FeatureBody, part: str = "patch",
                                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        registry = FeatureRegistry(_store())
        src = registry.get(feature_id)["version"]
        definition = _definition(body) if (body.expression or body.pipeline) else FeatureDefinition(
            expression=src["expression"], pipeline=src["pipeline"])
        feature = registry.save(
            name=body.name or registry.get(feature_id)["feature"]["name"], definition=definition,
            description=body.description, owner=body.owner, visibility=body.visibility,
            category=body.category, tags=body.tags, feature_id=feature_id, bump=part)
        return {"feature": feature}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/features/{feature_id}/validate")
async def stats_validate_feature(feature_id: str, body: FeatureBody,
                                 _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return FeatureRegistry(_store()).validate(feature_id=feature_id, sample=body.sample)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/features/{feature_id}/preview")
async def stats_preview_feature(feature_id: str, body: FeatureBody,
                                _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return FeatureRegistry(_store()).preview(feature_id=feature_id, sample=body.sample)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/features/{feature_id}/rollback")
async def stats_rollback_feature(feature_id: str, version: str,
                                 _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"feature": FeatureRegistry(_store()).rollback(feature_id, version)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/features/{feature_id}/dependencies")
async def stats_feature_dependencies(feature_id: str, version: Optional[str] = None,
                                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return FeatureRegistry(_store()).dependencies(feature_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── artifacts / audit ────────────────────────────────────────────────────────

@router.get("/artifacts/{artifact_id}")
async def stats_artifact(artifact_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    record = _store().get_artifact(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown artifact"})
    return record


@router.get("/audit")
async def stats_audit(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"events": _store().list_audit(limit)}


# ── generic execution (declared last so specific routes win) ─────────────────

class ExecuteBody(BaseModel):
    tool: str = Field(description="One of the statistical tool names.")
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/execute")
async def stats_execute(body: ExecuteBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return run_tool(body.tool, body.arguments)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/{tool}")
async def stats_run(tool: str, arguments: dict[str, Any] | None = None,
                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return run_tool(tool, arguments or {})
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


__all__ = ["router"]
