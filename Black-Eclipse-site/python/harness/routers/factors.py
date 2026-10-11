"""Factor & Alpha Research Lab HTTP routes (operator-gated).

A thin surface over the SAME registry, engine, store and market gateway the agent
tools use. Data endpoints fetch through the run gateway; compute endpoints accept
either explicit panels or a symbol list.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..factors import service as S
from ..factors import engine as E
from ..factors.tools import _fetch
from ..stats.base import StatsError

router = APIRouter(prefix="/factors/v1", tags=["factors"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, StatsError):
        return HTTPException(status_code=exc.http_status,
                             detail={"code": exc.code, "message": exc.message})
    return HTTPException(status_code=500, detail={"code": "FACTOR_ERROR", "message": str(exc)})


def _market_gateway() -> Any:
    from ..market.gateway import MarketDataGateway  # noqa: PLC0415

    return MarketDataGateway(service.server_bridge(), cache=getattr(service, "market_cache", None),
                             router=getattr(service, "market_router", None))


class FactorBody(BaseModel):
    factorId: Optional[str] = None
    name: str
    description: str = ""
    family: str = "custom"
    direction: Optional[str] = None
    frequency: str = "1d"
    assetClass: str = "equity"
    expression: str = ""
    inputs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    normalization: str = "cross_sectional_zscore"
    missingPolicy: str = "drop"
    lookback: int = 1
    tags: list[str] = Field(default_factory=list)
    pitSafe: bool = True
    bump: str = "minor"
    changelog: Optional[str] = None


class ComputeBody(BaseModel):
    expression: str
    symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    horizons: list[int] = Field(default_factory=lambda: [1, 5, 21])
    method: str = "pearson"
    minObs: int = 5
    expectedDirection: Optional[str] = None
    periodsPerYear: Optional[int] = None


class PortfolioBody(ComputeBody):
    quantiles: int = 5
    weighting: str = "equal"
    longShort: bool = True
    rebalance: int = 1
    costBps: float = 0.0
    riskFree: float = 0.0


class PromoteBody(BaseModel):
    factorId: str
    version: Optional[str] = None
    symbols: list[str]
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    quantiles: int = 5
    weighting: str = "equal"
    longShort: bool = True
    rebalance: int = 21
    costBps: float = 0.0
    actor: Optional[str] = None
    requestApproval: bool = True


class ComposeBody(BaseModel):
    factors: list[dict[str, Any]]
    symbols: list[str]
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    method: str = "equal_zscore"
    weights: Optional[list[float]] = None
    trainingRows: Optional[int] = None
    horizon: int = 1


async def _series(body: ComputeBody):
    if not body.symbols:
        raise StatsError("INVALID_INPUT", "symbols are required")
    return await _fetch(_market_gateway(), body.symbols, body.interval, body.start, body.end)


@router.get("/capabilities")
async def factor_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": S.get_factor_store() is not None, "engineVersion": E.FACTOR_ENGINE_VERSION}


@router.get("/library")
async def factor_library(availableOnly: bool = False, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"library": S.list_library(available_only=availableOnly)}


@router.get("/factors")
async def factor_list(family: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"factors": S.list_factors(family=family)}


@router.post("/factors")
async def factor_create(body: FactorBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..factors.models import FactorDefinition  # noqa: PLC0415

    try:
        defn = FactorDefinition(
            name=body.name, description=body.description, family=body.family, direction=body.direction,
            frequency=body.frequency, asset_class=body.assetClass, expression=body.expression,
            inputs=body.inputs, parameters=body.parameters, normalization=body.normalization,
            missing_policy=body.missingPolicy, lookback=body.lookback, tags=body.tags,
            pit_safe=body.pitSafe, factor_id=body.factorId,
        )
        return S.save_factor(defn, bump=body.bump, changelog=body.changelog)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/factors/{factor_id}")
async def factor_get(factor_id: str, includeVersions: bool = False,
                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    factor = S.get_factor(factor_id, include_versions=includeVersions)
    if factor is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "unknown factor"})
    return factor


@router.get("/factors/{factor_id}/versions")
async def factor_versions(factor_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = S.get_factor_store()
    return {"versions": store.list_versions(factor_id) if store else []}


@router.post("/validate")
async def factor_validate(body: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    return S.validate_expression(str(body.get("expression") or ""), sample=body.get("sample"))


@router.post("/evaluate")
async def factor_evaluate(body: ComputeBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        syms, dates, series = await _series(body)
        result = S.evaluate(body.expression, series, syms, horizons=body.horizons, method=body.method,
                            min_obs=body.minObs, periods_per_year=body.periodsPerYear,
                            expected_direction=body.expectedDirection)
        result["symbols"] = syms
        result["dates"] = dates
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/portfolio")
async def factor_portfolio(body: PortfolioBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        syms, dates, series = await _series(body)
        result = S.quantile_portfolio(body.expression, series, syms, quantiles=body.quantiles,
                                      weighting=body.weighting, long_short=body.longShort,
                                      rebalance=body.rebalance, cost_bps=body.costBps,
                                      min_obs=body.minObs)
        result["dates"] = dates
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/compose")
async def factor_compose(body: ComposeBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        syms, _, series = await _fetch(_market_gateway(), body.symbols, body.interval, body.start, body.end)
        panels = [S.build_factor_panel(str(f.get("expression")), series, syms)[0] for f in body.factors]
        prices = S.series_panel(series, syms, "close")
        T = min(p.shape[0] for p in panels)
        fwd = E.forward_returns(prices[:T], body.horizon)
        return S.compose([p[:T] for p in panels], method=body.method, weights=body.weights,
                         forward=fwd, training_rows=body.trainingRows)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/experiments")
async def factor_experiments(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = S.get_factor_store()
    return {"experiments": store.list_experiments(limit=limit) if store else []}


@router.post("/promote")
async def factor_promote(body: PromoteBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..factors.promotion import promote_to_strategy  # noqa: PLC0415

    quant_store = getattr(service, "quant_store", None)
    if quant_store is None:
        raise HTTPException(status_code=503, detail={"code": "UNAVAILABLE",
                                                     "message": "the quant store is unavailable"})
    try:
        syms, _, series = await _fetch(_market_gateway(), body.symbols, body.interval, body.start, body.end)
        config = {
            "interval": body.interval, "quantiles": body.quantiles, "longShort": body.longShort,
            "rebalance": body.rebalance, "costBps": body.costBps, "weighting": body.weighting,
        }
        return promote_to_strategy(factor_id=body.factorId, version=body.version, config=config,
                                   symbols=syms, series_by_symbol=series, quant_store=quant_store,
                                   actor=body.actor, request_approval=body.requestApproval)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/lineage")
async def factor_lineage(childType: str, childId: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = S.get_factor_store()
    return {"lineage": store.lineage_for(childType, childId) if store else []}
