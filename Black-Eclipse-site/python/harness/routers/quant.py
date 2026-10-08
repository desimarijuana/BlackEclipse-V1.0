"""Quant Engine HTTP routes (operator-gated).

Thin adapters over the SAME engine and store the agent tools use. The routes
reach shared runtime state only through `harness.deps.service`, so the UI and the
agent can never disagree. A backtest route builds a per-request market gateway
bound to the server bridge (the SAME read-only transport).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant import StrategySpec, parse_strategy, validate_strategy
from ..quant.datasets import dataset_from_strategy, resolve_dataset
from ..quant.engine import BacktestConfig, run_backtest, run_portfolio_backtest
from ..quant.errors import QuantError
from ..quant.montecarlo import MonteCarloConfig, MonteCarloEngine
from ..quant.optimize import OptimizationConfig, OptimizationEngine
from ..quant.params import ParamSpace
from ..quant.robustness import (
    RobustnessConfig,
    RobustnessEngine,
    SensitivityConfig,
    SensitivityEngine,
)
from ..quant.strategy import errors_only
from ..quant.tools import _CAPABILITY
from ..quant.walkforward import WalkForwardConfig, WalkForwardEngine

router = APIRouter(tags=["quant"])


def _store() -> Any:
    store = getattr(service, "quant_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="the quant engine is unavailable in this runtime")
    return store


def _market_gateway() -> Any:
    from ..market.gateway import MarketDataGateway

    return MarketDataGateway(
        service.server_bridge(),
        cache=getattr(service, "market_cache", None),
        router=getattr(service, "market_router", None),
    )


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, QuantError):
        return HTTPException(status_code=exc.http_status, detail=exc.to_dict())
    return HTTPException(status_code=500, detail={"code": "QUANT_ERROR", "message": str(exc)})


# ── Capabilities & strategies ────────────────────────────────────────────────

@router.get("/quant/capabilities")
async def quant_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"available": getattr(service, "quant_store", None) is not None, "capability": _CAPABILITY}


class StrategyBody(BaseModel):
    strategy: Optional[dict[str, Any]] = None
    strategyYaml: Optional[str] = None
    description: Optional[str] = None


def _parse_body(body: StrategyBody) -> StrategySpec:
    if body.strategy is not None:
        return parse_strategy(body.strategy)
    if body.strategyYaml:
        return parse_strategy(body.strategyYaml)
    raise HTTPException(status_code=400, detail={"code": "INVALID_STRATEGY",
                                                 "message": "strategy or strategyYaml required"})


@router.get("/quant/strategies")
async def list_strategies(includeArchived: bool = False, _: bool = Depends(require_operator)) -> dict:
    return {"strategies": _store().list_strategies(include_archived=includeArchived)}


@router.post("/quant/strategies")
async def create_strategy(body: StrategyBody, _: bool = Depends(require_operator)) -> dict:
    try:
        spec = _parse_body(body)
        issues = validate_strategy(spec)
        errs = errors_only(issues)
        if errs:
            raise HTTPException(status_code=422, detail={
                "code": "STRATEGY_VALIDATION_FAILED", "message": "strategy is invalid",
                "issues": [i.to_dict() for i in issues],
            })
        record = _store().save_strategy(spec, description=body.description)
        return {"strategy": record, "issues": [i.to_dict() for i in issues]}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/strategies/{strategy_id}")
async def get_strategy(strategy_id: str, version: Optional[str] = None,
                       _: bool = Depends(require_operator)) -> dict:
    try:
        return {"strategy": _store().get_strategy(strategy_id, version)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.patch("/quant/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, body: dict[str, Any],
                          _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.strategy import bump_version

        store = _store()
        current = store.get_strategy(strategy_id)
        merged = dict(current["spec"])
        merged.update(body.get("updates") or {})
        if body.get("bumpVersion", True):
            merged["version"] = bump_version(current["version"], body.get("bumpPart") or "patch")
        spec = StrategySpec.model_validate(merged)
        errs = errors_only(validate_strategy(spec))
        if errs:
            raise HTTPException(status_code=422, detail={
                "code": "STRATEGY_VALIDATION_FAILED", "message": "updated strategy is invalid",
                "issues": [i.to_dict() for i in errs],
            })
        return {"strategy": store.save_strategy(spec)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.delete("/quant/strategies/{strategy_id}")
async def archive_strategy(strategy_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        _store().archive_strategy(strategy_id, True)
        return {"archived": True, "strategyId": strategy_id}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/strategies/{strategy_id}/versions")
async def list_versions(strategy_id: str, _: bool = Depends(require_operator)) -> dict:
    return {"versions": _store().list_versions(strategy_id)}


@router.post("/quant/validate")
async def validate(body: StrategyBody, _: bool = Depends(require_operator)) -> dict:
    try:
        spec = _parse_body(body)
        issues = validate_strategy(spec)
        return {"valid": not errors_only(issues), "issues": [i.to_dict() for i in issues]}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Backtests ────────────────────────────────────────────────────────────────

class BacktestBody(BaseModel):
    strategyId: Optional[str] = None
    version: Optional[str] = None
    strategy: Optional[dict[str, Any]] = None
    strategyYaml: Optional[str] = None
    symbols: Optional[list[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    initialCapital: float = 100_000.0
    riskFreeRate: float = 0.0
    randomSeed: int = 42
    save: bool = True


@router.post("/quant/backtest")
async def run_backtest_route(body: BacktestBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        if body.strategyId:
            strategy = StrategySpec.model_validate(store.get_strategy(body.strategyId, body.version)["spec"])
        elif body.strategy is not None:
            strategy = parse_strategy(body.strategy)
        elif body.strategyYaml:
            strategy = parse_strategy(body.strategyYaml)
        else:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST",
                                                         "message": "strategyId or strategy required"})
        errs = errors_only(validate_strategy(strategy))
        if errs:
            raise HTTPException(status_code=422, detail={
                "code": "STRATEGY_VALIDATION_FAILED", "message": "strategy is invalid",
                "issues": [i.to_dict() for i in errs],
            })
        gateway = _market_gateway()
        dataset = await dataset_from_strategy(
            gateway, strategy, start=body.start, end=body.end, symbols=body.symbols
        )
        result = run_backtest(strategy, dataset, BacktestConfig(
            initial_capital=body.initialCapital, start=body.start, end=body.end,
            risk_free_rate=body.riskFreeRate, random_seed=body.randomSeed,
        ))
        exp_id = None
        if body.save:
            exp_id = store.save_experiment(
                result, strategy_id=strategy.id, strategy_version=strategy.version, kind="backtest"
            )
        payload = result.to_dict(include_series=True)
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class PortfolioBacktestBody(BaseModel):
    strategyIds: list[str]
    start: Optional[str] = None
    end: Optional[str] = None
    initialCapital: float = 100_000.0
    riskFreeRate: float = 0.0
    randomSeed: int = 42
    save: bool = True


@router.post("/quant/portfolio-backtest")
async def portfolio_backtest_route(body: PortfolioBacktestBody,
                                   _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategies = [StrategySpec.model_validate(store.get_strategy(sid)["spec"])
                      for sid in body.strategyIds]
        if not strategies:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST",
                                                         "message": "strategyIds required"})
        primaries = {s.timeframes.primary for s in strategies}
        if len(primaries) != 1:
            raise HTTPException(status_code=422, detail={
                "code": "TIMEFRAME_MISMATCH", "message": "all strategies must share one primary timeframe"})
        symbols = sorted({sym for s in strategies for sym in s.universe.symbols})
        confirmation = sorted({tf for s in strategies for tf in s.timeframes.confirmation})
        dataset = await resolve_dataset(
            _market_gateway(), symbols, primary=next(iter(primaries)),
            confirmation=confirmation, start=body.start, end=body.end,
        )
        result = run_portfolio_backtest(strategies, dataset, BacktestConfig(
            initial_capital=body.initialCapital, start=body.start, end=body.end,
            risk_free_rate=body.riskFreeRate, random_seed=body.randomSeed,
        ))
        exp_id = None
        if body.save:
            exp_id = store.save_experiment(
                result, strategy_id=None,
                strategy_version=",".join(s.version for s in strategies), kind="portfolio_backtest")
        payload = result.to_dict(include_series=True)
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Research (optimization / walk-forward / Monte-Carlo / robustness) ────────

class ResearchBody(BaseModel):
    strategyId: str
    version: Optional[str] = None
    symbols: Optional[list[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    initialCapital: float = 100_000.0
    riskFreeRate: float = 0.0
    seed: int = 42
    save: bool = True


def _load_strategy(store: Any, strategy_id: str, version: Optional[str]) -> StrategySpec:
    return StrategySpec.model_validate(store.get_strategy(strategy_id, version)["spec"])


async def _dataset_for(strategy: StrategySpec, body: ResearchBody) -> Any:
    return await dataset_from_strategy(
        _market_gateway(), strategy, start=body.start, end=body.end, symbols=body.symbols)


def _save(store: Any, result: Any, strategy: StrategySpec, kind: str, save: bool) -> Optional[str]:
    if not save:
        return None
    return store.save_experiment(
        result, strategy_id=strategy.id, strategy_version=strategy.version, kind=kind)


class OptimizeBody(ResearchBody):
    paramSpace: dict[str, Any] = Field(default_factory=dict)
    method: str = "random"
    objective: str = "sharpe"
    objectives: list[str] = Field(default_factory=list)
    maxEvaluations: int = 60


@router.post("/quant/optimize")
async def optimize_route(body: OptimizeBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        dataset = await _dataset_for(strategy, body)
        result = OptimizationEngine(strategy, dataset, ParamSpace.from_dict(body.paramSpace),
                                    OptimizationConfig(
                                        method=body.method, objective=body.objective,
                                        objectives=body.objectives,
                                        max_evaluations=body.maxEvaluations, seed=body.seed,
                                        initial_capital=body.initialCapital,
                                        risk_free_rate=body.riskFreeRate,
                                        start=body.start, end=body.end, symbols=body.symbols,
                                    )).run()
        exp_id = _save(store, result, strategy, "optimization", body.save)
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class WalkForwardBody(ResearchBody):
    paramSpace: dict[str, Any] = Field(default_factory=dict)
    trainBars: int = 250
    testBars: int = 60
    stepBars: Optional[int] = None
    method: str = "random"
    objective: str = "sharpe"
    maxEvaluations: int = 40
    anchored: bool = False


@router.post("/quant/walk-forward")
async def walk_forward_route(body: WalkForwardBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        dataset = await _dataset_for(strategy, body)
        result = WalkForwardEngine(strategy, dataset, WalkForwardConfig(
            train_bars=body.trainBars, test_bars=body.testBars, step_bars=body.stepBars,
            method=body.method, objective=body.objective, param_space=body.paramSpace,
            max_evaluations=body.maxEvaluations, seed=body.seed,
            initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
            anchored=body.anchored,
        )).run()
        exp_id = _save(store, result, strategy, "walk_forward", body.save)
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class MonteCarloBody(ResearchBody):
    method: str = "trade_reshuffle"
    simulations: int = 1000
    ruinThreshold: float = 0.5
    perturbationPct: float = 0.10
    perturbation: dict[str, float] = Field(default_factory=dict)
    executionPerturbation: dict[str, float] = Field(default_factory=dict)


@router.post("/quant/monte-carlo")
async def monte_carlo_route(body: MonteCarloBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        dataset = await _dataset_for(strategy, body)
        result = MonteCarloEngine(strategy, dataset, MonteCarloConfig(
            method=body.method, simulations=body.simulations, seed=body.seed,
            ruin_threshold=body.ruinThreshold, perturbation_pct=body.perturbationPct,
            perturbation=body.perturbation, execution_perturbation=body.executionPerturbation,
            initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
        )).run()
        exp_id = _save(store, result, strategy, "monte_carlo", body.save)
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class SensitivityBody(ResearchBody):
    paramRanges: dict[str, Any] = Field(default_factory=dict)
    objective: str = "sharpe"


@router.post("/quant/sensitivity")
async def sensitivity_route(body: SensitivityBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        dataset = await _dataset_for(strategy, body)
        result = SensitivityEngine(strategy, dataset, SensitivityConfig(
            param_ranges=body.paramRanges, objective=body.objective, seed=body.seed,
            initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
        )).run()
        exp_id = _save(store, result, strategy, "sensitivity", body.save)
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class RobustnessBody(ResearchBody):
    paramRanges: dict[str, Any] = Field(default_factory=dict)
    objective: str = "sharpe"
    costMultipliers: list[float] = Field(default_factory=lambda: [1.0, 2.0, 5.0])
    minTrades: int = 30


@router.post("/quant/robustness")
async def robustness_route(body: RobustnessBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        dataset = await _dataset_for(strategy, body)
        result = RobustnessEngine(strategy, dataset, RobustnessConfig(
            param_ranges=body.paramRanges, objective=body.objective,
            cost_multipliers=body.costMultipliers, min_trades=body.minTrades, seed=body.seed,
            initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
        )).run()
        exp_id = _save(store, result, strategy, "robustness", body.save)
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Experiments ──────────────────────────────────────────────────────────────

@router.get("/quant/experiments")
async def list_experiments(strategyId: Optional[str] = None, limit: int = 50,
                           _: bool = Depends(require_operator)) -> dict:
    return {"experiments": _store().list_experiments(strategy_id=strategyId, limit=limit)}


@router.get("/quant/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, artifact: bool = False,
                         _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().get_experiment(experiment_id, with_artifact=artifact)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/experiments/{experiment_id}/artifact")
async def get_artifact(experiment_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().read_artifact(experiment_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.delete("/quant/experiments/{experiment_id}")
async def delete_experiment(experiment_id: str, _: bool = Depends(require_operator)) -> dict:
    try:
        _store().delete_experiment(experiment_id)
        return {"deleted": True, "experimentId": experiment_id}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class CompareBody(BaseModel):
    experimentIds: list[str] = Field(default_factory=list)


@router.post("/quant/compare")
async def compare(body: CompareBody, _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().compare_experiments(body.experimentIds)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


__all__ = ["router"]
