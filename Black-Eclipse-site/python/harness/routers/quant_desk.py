"""Quant desk routes — reproducibility, research sessions, portfolio and stress.

Separate from `routers/quant.py` (size budget) and `quant_reports.py` (judging a
result). Every route is a thin adapter over the same functions the agent tools
call, so the UI and the agent cannot disagree.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from .quant import _http, _store

router = APIRouter(tags=["quant"])


# ── Reproducibility ──────────────────────────────────────────────────────────

@router.get("/quant/experiments/{experiment_id}/manifest")
async def get_manifest(experiment_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return {"manifest": _store().get_run_manifest(experiment_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/experiments/{experiment_id}/reproduce")
async def reproduce(experiment_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.desk_tools import reproduce_experiment  # noqa: PLC0415

        _, data = await reproduce_experiment({"experimentId": experiment_id}, service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Research sessions ────────────────────────────────────────────────────────

class SessionBody(BaseModel):
    title: str = Field(min_length=1)
    question: Optional[str] = None
    strategyId: Optional[str] = None


class HypothesisBody(BaseModel):
    statement: str = Field(min_length=1)
    universe: list[str] = Field(default_factory=list)
    period: dict[str, Any] = Field(default_factory=dict)
    metric: Optional[str] = None
    acceptance: Optional[str] = None


class TrialBody(BaseModel):
    kind: str = "backtest"
    hypothesisId: Optional[str] = None
    experimentId: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/sessions")
async def create_session(body: SessionBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().create_research_session(
            title=body.title, question=body.question, strategy_id=body.strategyId
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/sessions")
async def list_sessions(limit: int = 50, status: Optional[str] = None,
                        _: bool = Depends(require_operator)) -> dict:
    try:
        return {"sessions": _store().list_research_sessions(limit=limit, status=status)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/sessions/{session_id}")
async def get_session(session_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().get_research_session(session_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/sessions/{session_id}/journal")
async def get_journal(session_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().session_journal(session_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/sessions/{session_id}/hypotheses")
async def register_hypothesis(session_id: str, body: HypothesisBody,
                              _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().pre_register_hypothesis(
            session_id, statement=body.statement, universe=body.universe,
            period=body.period, metric=body.metric, acceptance=body.acceptance,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/sessions/{session_id}/trials")
async def record_trial(session_id: str, body: TrialBody,
                       _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().record_trial(
            session_id, kind=body.kind, hypothesis_id=body.hypothesisId,
            experiment_id=body.experimentId, parameters=body.parameters,
            metrics=body.metrics,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Portfolio & stress ───────────────────────────────────────────────────────

class PortfolioBody(BaseModel):
    weights: Optional[list[float]] = None
    covariance: Optional[list[list[float]]] = None
    returns: Optional[list[list[float]]] = None
    expectedReturns: Optional[list[float]] = None
    method: str = "min_variance"
    riskAversion: float = 1.0
    net: float = 1.0
    gross: Optional[float] = None
    minWeight: Optional[float] = None
    maxWeight: Optional[float] = None
    maxTurnover: Optional[float] = None
    currentWeights: Optional[list[float]] = None
    views: Optional[dict[str, Any]] = None
    annualize: bool = True
    interval: str = "1d"
    riskFreeRate: float = 0.0


@router.post("/quant/portfolio/optimize")
async def optimize_portfolio_route(body: PortfolioBody,
                                   _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.desk_tools import optimize_portfolio_tool  # noqa: PLC0415

        _, data = await optimize_portfolio_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/portfolio/risk")
async def portfolio_risk_route(body: PortfolioBody,
                               _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.desk_tools import analyze_portfolio_risk  # noqa: PLC0415

        if body.weights is None:
            raise HTTPException(422, detail={"code": "INVALID_INPUT", "message": "weights required"})
        _, data = await analyze_portfolio_risk(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class StressBody(PortfolioBody):
    scenarios: Optional[dict[str, Any]] = None
    symbols: Optional[list[str]] = None
    confidence: float = 0.95
    horizonDays: float = 1.0
    portfolioValue: float = 1.0


@router.post("/quant/stress")
async def stress_route(body: StressBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.desk_tools import stress_portfolio  # noqa: PLC0415

        if body.weights is None:
            raise HTTPException(422, detail={"code": "INVALID_INPUT", "message": "weights required"})
        _, data = await stress_portfolio(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Asset-class extensions ───────────────────────────────────────────────────

class OptionChainBody(BaseModel):
    snapshots: list[dict[str, Any]] = Field(min_length=2)
    initialCapital: float = 100_000.0
    commissionPerContract: Optional[float] = None


@router.post("/quant/options/backtest-chain")
async def option_chain_route(body: OptionChainBody,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.options_backtest import backtest_option_chain  # noqa: PLC0415
        return backtest_option_chain(
            body.snapshots, initial_capital=body.initialCapital,
            commission_per_contract=body.commissionPerContract,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class TermStructureBody(BaseModel):
    points: list[dict[str, Any]] = Field(min_length=1)
    spot: Optional[float] = None
    riskFree: float = 0.0
    storage: float = 0.0


@router.post("/quant/futures/term-structure")
async def term_structure_route(body: TermStructureBody,
                               _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.futures import term_structure  # noqa: PLC0415
        return term_structure(body.points, spot=body.spot, risk_free=body.riskFree,
                              storage=body.storage)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class RollCostBody(BaseModel):
    contracts: list[dict[str, Any]] = Field(min_length=1)
    rollDates: list[str] = Field(default_factory=list)
    adjustment: str = "difference"
    costBps: float = 0.0
    initialCapital: float = 100_000.0


@router.post("/quant/futures/roll-cost")
async def roll_cost_route(body: RollCostBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.futures import roll_cost  # noqa: PLC0415
        return roll_cost(body.contracts, body.rollDates, adjustment=body.adjustment,
                         cost_bps=body.costBps, initial_capital=body.initialCapital)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class BenchBody(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/benchmark")
async def benchmark_route(body: BenchBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant_bench.runner import run_benchmark  # noqa: PLC0415
        return run_benchmark(answers=body.answers)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ReportExportBody(BaseModel):
    format: str = "html"


@router.post("/quant/experiments/{experiment_id}/report/export")
async def export_report(experiment_id: str, body: ReportExportBody,
                        _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.report_export import export_experiment  # noqa: PLC0415
        return export_experiment(_store(), experiment_id, fmt=body.format)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Method discovery ─────────────────────────────────────────────────────────

class MethodScanBody(BaseModel):
    symbol: str
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    oosFraction: float = 0.3


class MethodSynthesizeBody(BaseModel):
    methodId: str
    symbol: str
    interval: str = "1d"
    params: dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = None


class MethodCombineBody(BaseModel):
    primaryMethodId: str
    filterMethodId: str
    symbol: str
    interval: str = "1d"
    primaryParams: dict[str, Any] = Field(default_factory=dict)
    filterParams: dict[str, Any] = Field(default_factory=dict)


class MethodMineBody(MethodScanBody):
    methodIds: Optional[list[str]] = None
    maxTrials: int = 24
    combinations: int = 0


class MethodRecommendBody(BaseModel):
    assetClass: Optional[str] = None
    horizon: Optional[str] = None
    riskTolerance: Optional[str] = None
    objective: Optional[str] = None
    capital: Optional[float] = None
    availableData: Optional[list[str]] = None
    allowShort: bool = True
    complexityMax: Optional[int] = None
    regime: Optional[str] = None
    symbol: Optional[str] = None
    interval: str = "1d"
    limit: int = 5


class DiscoveredMethodBody(BaseModel):
    name: str
    methodFamily: str = "custom"
    spec: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: str = "discovered"
    strategyId: Optional[str] = None


@router.get("/quant/methods")
async def list_methods(_: bool = Depends(require_operator),
                       category: Optional[str] = None,
                       assetClass: Optional[str] = None,
                       horizon: Optional[str] = None,
                       maxComplexity: Optional[int] = None) -> dict:
    try:
        from ..quant.discovery.library import list_method_families  # noqa: PLC0415
        return {"methods": list_method_families(
            category=category, asset_class=assetClass, horizon=horizon,
            max_complexity=maxComplexity,
        )}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/methods/{method_id}")
async def get_method(method_id: str, symbol: Optional[str] = None,
                     interval: str = "1d",
                     _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery.library import get_method_card  # noqa: PLC0415
        return get_method_card(method_id, symbol=symbol, interval=interval)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/recommend")
async def recommend(body: MethodRecommendBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery.library import recommend_methods  # noqa: PLC0415
        return recommend_methods(body.model_dump(), limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/scan-structure")
async def scan_structure(body: MethodScanBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery_tools import scan_market_structure_tool  # noqa: PLC0415
        _, data = await scan_market_structure_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/hypotheses")
async def method_hypotheses(body: MethodScanBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery_tools import generate_hypotheses_tool  # noqa: PLC0415
        _, data = await generate_hypotheses_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/synthesize")
async def synthesize(body: MethodSynthesizeBody,
                     _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery.synthesize import synthesize_method  # noqa: PLC0415
        return synthesize_method(body.methodId, symbol=body.symbol, interval=body.interval,
                                 params=body.params or None, name=body.name)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/combine")
async def combine(body: MethodCombineBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery.synthesize import build_combination  # noqa: PLC0415
        return {"spec": build_combination(
            body.primaryMethodId, body.filterMethodId, symbol=body.symbol,
            interval=body.interval, primary_params=body.primaryParams or None,
            filter_params=body.filterParams or None,
        )}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/mine")
async def mine(body: MethodMineBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery_tools import mine_methods_tool  # noqa: PLC0415
        _, data = await mine_methods_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class PlaybookBody(BaseModel):
    methodId: Optional[str] = None
    strategyId: Optional[str] = None
    version: Optional[str] = None
    symbol: Optional[str] = None
    interval: str = "1d"
    params: dict[str, Any] = Field(default_factory=dict)
    experimentId: Optional[str] = None
    spec: Optional[dict[str, Any]] = None


@router.post("/quant/methods/playbook")
async def trading_playbook(body: PlaybookBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery_tools import generate_trading_playbook_tool  # noqa: PLC0415
        _, data = await generate_trading_playbook_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/methods/setups")
async def current_setups(body: MethodScanBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.discovery_tools import scan_current_setups_tool  # noqa: PLC0415
        _, data = await scan_current_setups_tool(body.model_dump(), service)
        if data.get("status") == "ERROR":
            raise _http(Exception(str(data.get("error"))))
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/discovered-methods")
async def list_discovered(status: Optional[str] = None, limit: int = 50,
                          _: bool = Depends(require_operator)) -> dict:
    try:
        return {"methods": _store().list_methods(status=status, limit=limit)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/discovered-methods")
async def save_discovered(body: DiscoveredMethodBody,
                          _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().save_method(
            name=body.name, method_family=body.methodFamily, spec=body.spec,
            evidence=body.evidence, status=body.status, strategy_id=body.strategyId,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/discovered-methods/{method_id}/promote")
async def promote_discovered(method_id: str, status: str,
                             strategyId: Optional[str] = None,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().promote_method(method_id, status, strategy_id=strategyId)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


__all__ = ["router"]
