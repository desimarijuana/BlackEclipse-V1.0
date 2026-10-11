"""Quant Engine HTTP routes (operator-gated).

Thin adapters over the SAME engine and store the agent tools use. The routes
reach shared runtime state only through `harness.deps.service`, so the UI and the
agent can never disagree. A backtest route builds a per-request market gateway
bound to the server bridge (the SAME read-only transport).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant import StrategySpec, parse_strategy, validate_strategy
from ..quant.bundle import bundle_to_bytes, export_bundle, import_bundle
from ..quant.compiler import compile_graph
from ..quant.datasets import dataset_from_strategy, resolve_dataset
from ..quant.sdk_runtime import run_strategy_source
from ..quant.nodes import REGISTRY
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
from ..quant.runner import get_runner
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


@router.get("/quant/strategies/{strategy_id}/export")
async def export_strategy_bundle(strategy_id: str, version: Optional[str] = None,
                                 format: str = "zip",
                                 _: bool = Depends(require_operator)):
    try:
        store = _store()
        record = store.get_strategy(strategy_id, version)
        spec = StrategySpec.model_validate(record["spec"])
        bundle = export_bundle(spec, provenance={
            "source": "black-eclipse", "strategyId": strategy_id,
            "version": record["version"], "contentHash": record.get("contentHash"),
        }, schema_version=record.get("schemaVersion"))
        if format == "json":
            return {"bundle": bundle}
        filename = f"{strategy_id}@{record['version']}.zip"
        return Response(
            content=bundle_to_bytes(bundle), media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class ImportBody(BaseModel):
    bundle: Optional[dict[str, Any]] = None
    bundleBase64: Optional[str] = None
    save: bool = False


@router.post("/quant/strategies/import")
async def import_strategy_bundle(body: ImportBody, _: bool = Depends(require_operator)) -> dict:
    try:
        import base64

        if body.bundleBase64:
            source: Any = base64.b64decode(body.bundleBase64)
        elif body.bundle is not None:
            source = body.bundle
        else:
            raise HTTPException(status_code=400, detail={
                "code": "INVALID_REQUEST", "message": "bundle or bundleBase64 required"})
        result = import_bundle(source)
        spec = result["spec"]
        errs = errors_only(result["issues"])
        payload: dict[str, Any] = {
            "valid": not errs,
            "strategy": spec.to_dict(),
            "manifest": result["manifest"],
            "issues": [i.to_dict() for i in result["issues"]],
            "warnings": result["warnings"],
            "contentHash": result["contentHash"],
        }
        if not errs and body.save:
            payload["saved"] = _store().save_strategy(spec)
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/strategies/{strategy_id}/diff")
async def diff_strategy_versions(strategy_id: str, a: str, b: str,
                                 _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().diff_versions(strategy_id, a, b)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/strategies/{strategy_id}/versions/{version}")
async def get_strategy_version_meta(strategy_id: str, version: str,
                                    _: bool = Depends(require_operator)) -> dict:
    try:
        return _store().version_meta(strategy_id, version)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Strategy graph (visual builder compiler) ─────────────────────────────────

@router.get("/quant/graph/nodes")
async def list_graph_nodes(_: bool = Depends(require_operator)) -> dict:
    return {"nodes": REGISTRY.describe_all()}


class GraphBody(BaseModel):
    graph: Optional[dict[str, Any]] = None
    graphJson: Optional[str] = None


def _graph_source(body: GraphBody) -> Any:
    if body.graph is not None:
        return body.graph
    if body.graphJson:
        return body.graphJson
    raise HTTPException(status_code=400, detail={
        "code": "INVALID_REQUEST", "message": "graph or graphJson required"})


@router.post("/quant/graph/compile")
async def compile_graph_route(body: GraphBody, _: bool = Depends(require_operator)) -> dict:
    try:
        result = compile_graph(_graph_source(body))
        return {
            "ok": result.ok,
            "spec": result.spec.to_dict() if result.spec else None,
            "diagnostics": [d.to_dict() for d in result.diagnostics],
            "sourceMap": result.source_map,
            "ordering": result.ordering,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/graph/validate")
async def validate_graph_route(body: GraphBody, _: bool = Depends(require_operator)) -> dict:
    try:
        result = compile_graph(_graph_source(body))
        return {
            "valid": result.ok,
            "diagnostics": [d.to_dict() for d in result.diagnostics],
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


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


# ── AI Strategy Copilot (deterministic plans, reports, signals) ──────────────

@router.post("/quant/strategies/{strategy_id}/research-plan")
async def research_plan_route(strategy_id: str, body: dict[str, Any],
                              _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.copilot import build_research_plan

        record = _store().get_strategy(strategy_id, body.get("version"))
        spec = StrategySpec.model_validate(record["spec"])
        plan = build_research_plan(
            spec, start=body.get("start"), end=body.get("end"),
            benchmark=body.get("benchmark"), train_bars=int(body.get("trainBars") or 250),
            test_bars=int(body.get("testBars") or 60),
            max_evaluations=int(body.get("maxEvaluations") or 60),
            objective=str(body.get("objective") or "sharpe"))
        return {"plan": plan}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/experiments/{experiment_id}/report")
async def experiment_report_route(experiment_id: str, artifact: bool = True,
                                  _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.copilot import build_report

        store = _store()
        experiment = store.get_experiment(experiment_id)
        art = store.read_artifact(experiment_id) if artifact else None
        return {"experimentId": experiment_id, "format": "markdown",
                "report": build_report(experiment, art)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/quant/signals")
async def signals_route(body: BacktestBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.copilot import calculate_signals

        store = _store()
        if body.strategyId:
            strategy = StrategySpec.model_validate(
                store.get_strategy(body.strategyId, body.version)["spec"])
        elif body.strategy is not None:
            strategy = parse_strategy(body.strategy)
        else:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST",
                                                         "message": "strategyId required"})
        dataset = await dataset_from_strategy(
            _market_gateway(), strategy, start=body.start, end=body.end, symbols=body.symbols)
        return calculate_signals(strategy, dataset, symbols=body.symbols)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Python Strategy Lab (isolated SDK runtime) ───────────────────────────────

class PythonRunBody(BaseModel):
    strategyCode: str
    className: Optional[str] = None
    symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    initialCapital: float = 100_000.0
    riskFreeRate: float = 0.0
    randomSeed: int = 42
    params: dict[str, Any] = Field(default_factory=dict)
    timeoutSeconds: float = 60.0
    save: bool = True
    background: bool = False


def _dataset_rows(dataset: Any) -> dict[str, list[dict[str, Any]]]:
    return {
        symbol: [
            {"timestamp": s.timestamps[i], "open": float(s.open[i]), "high": float(s.high[i]),
             "low": float(s.low[i]), "close": float(s.close[i]), "volume": float(s.volume[i])}
            for i in range(s.length)
        ]
        for symbol, s in dataset.series.items()
    }


@router.post("/quant/python/run")
async def python_run_route(body: PythonRunBody, _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        symbols = [s.upper() for s in body.symbols]
        if not symbols:
            raise HTTPException(status_code=400, detail={
                "code": "SDK_NO_SYMBOLS", "message": "symbols required"})
        dataset = await resolve_dataset(
            _market_gateway(), symbols, primary=body.interval, start=body.start, end=body.end)
        rows = _dataset_rows(dataset)
        timeout_s = min(300.0, max(1.0, body.timeoutSeconds))

        async def work(progress: Any) -> dict:
            import asyncio

            result, err = await asyncio.to_thread(
                run_strategy_source, body.strategyCode, rows,
                symbols=symbols, interval=body.interval,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
                random_seed=body.randomSeed, params=body.params, class_name=body.className,
                timeout_s=timeout_s,
            )
            if err is not None:
                return {"status": "ERROR", "error": err}
            assert result is not None
            exp_id = None
            if body.save:
                exp_id = store.save_experiment(
                    result, strategy_id=result.metadata.get("strategyId"),
                    strategy_version=result.metadata.get("strategyVersion"),
                    kind="python_backtest")
            payload = result.to_dict(include_series=True)
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "python_backtest", work)
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
    background: bool = False


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

        async def work(progress: Any) -> dict:
            dataset = await dataset_from_strategy(
                _market_gateway(), strategy, start=body.start, end=body.end, symbols=body.symbols
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

        return await _maybe_background(body, "backtest", work)
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
    background: bool = False


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

        async def work(progress: Any) -> dict:
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
                    strategy_version=",".join(s.version for s in strategies),
                    kind="portfolio_backtest")
            payload = result.to_dict(include_series=True)
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "portfolio_backtest", work)
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
    # Run the work off the request loop; returns a runId to poll.
    background: bool = False


async def _maybe_background(body: Any, kind: str, work: Any) -> dict:
    """Either await `work(progress)` or submit it to the background runner."""
    if getattr(body, "background", False):
        run_id = get_runner().submit(kind, work)
        return {"runId": run_id, "status": "queued", "kind": kind, "background": True}
    return await work(lambda *_a: None)


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

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = OptimizationEngine(
                strategy, dataset, ParamSpace.from_dict(body.paramSpace),
                OptimizationConfig(
                    method=body.method, objective=body.objective, objectives=body.objectives,
                    max_evaluations=body.maxEvaluations, seed=body.seed,
                    initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
                    start=body.start, end=body.end, symbols=body.symbols,
                ), progress=progress).run()
            exp_id = _save(store, result, strategy, "optimization", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "optimization", work)
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

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = WalkForwardEngine(strategy, dataset, WalkForwardConfig(
                train_bars=body.trainBars, test_bars=body.testBars, step_bars=body.stepBars,
                method=body.method, objective=body.objective, param_space=body.paramSpace,
                max_evaluations=body.maxEvaluations, seed=body.seed,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
                anchored=body.anchored,
            ), progress=progress).run()
            exp_id = _save(store, result, strategy, "walk_forward", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "walk_forward", work)
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

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = MonteCarloEngine(strategy, dataset, MonteCarloConfig(
                method=body.method, simulations=body.simulations, seed=body.seed,
                ruin_threshold=body.ruinThreshold, perturbation_pct=body.perturbationPct,
                perturbation=body.perturbation, execution_perturbation=body.executionPerturbation,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
            ), progress=progress).run()
            exp_id = _save(store, result, strategy, "monte_carlo", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "monte_carlo", work)
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

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = SensitivityEngine(strategy, dataset, SensitivityConfig(
                param_ranges=body.paramRanges, objective=body.objective, seed=body.seed,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
            )).run()
            exp_id = _save(store, result, strategy, "sensitivity", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "sensitivity", work)
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

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = RobustnessEngine(strategy, dataset, RobustnessConfig(
                param_ranges=body.paramRanges, objective=body.objective,
                cost_multipliers=body.costMultipliers, min_trades=body.minTrades, seed=body.seed,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
            ), progress=progress).run()
            exp_id = _save(store, result, strategy, "robustness", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "robustness", work)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Advanced engines (vectorized / costs / OOS / bootstrap / multiple-testing) ─

@router.post("/quant/vectorized-backtest")
async def vectorized_backtest_route(body: ResearchBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.vector_engine import run_vectorized_backtest, vector_capability

        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        cap = vector_capability(strategy, symbols=body.symbols)
        if not cap["supported"]:
            raise QuantError("strategy is not representable by the vectorized engine: "
                             + "; ".join(cap["reasons"]), detail=cap)

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = run_vectorized_backtest(strategy, dataset, BacktestConfig(
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
                random_seed=body.seed), symbols=body.symbols)
            exp_id = _save(store, result, strategy, "vectorized_backtest", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "vectorized_backtest", work)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class CostBody(BaseModel):
    orders: list[dict[str, Any]] = Field(default_factory=list)
    execution: Optional[dict[str, Any]] = None
    seed: Optional[int] = None


@router.post("/quant/costs")
async def costs_route(body: CostBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.costs import simulate_costs

        return {"simulations": {
            kind: simulate_costs(kind, body.orders, body.execution, seed=body.seed)
            for kind in ("transaction", "slippage", "spread", "impact")}}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class OutOfSampleBody(ResearchBody):
    oosFraction: Optional[float] = None
    oosStartIndex: Optional[int] = None


@router.post("/quant/out-of-sample")
async def out_of_sample_route(body: OutOfSampleBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.advanced_tools import _oos_contamination, run_out_of_sample

        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)
        report = await run_out_of_sample(strategy, _market_gateway(), {
            "start": body.start, "end": body.end, "symbols": body.symbols,
            "initialCapital": body.initialCapital, "riskFreeRate": body.riskFreeRate,
            "randomSeed": body.seed, "oosFraction": body.oosFraction,
            "oosStartIndex": body.oosStartIndex,
        })
        split = report["split"]
        evidence = _oos_contamination(store, strategy.id, split["oosStart"], split["oosEnd"])
        report["contaminated"] = bool(evidence)
        report["contaminationEvidence"] = evidence
        exp_id = _save(store, report["oosResult"], strategy, "out_of_sample", body.save)
        report["experimentId"] = exp_id
        return {k: v for k, v in report.items() if k != "oosResult"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class BootstrapBody(BaseModel):
    experimentId: Optional[str] = None
    returns: Optional[list[float]] = None
    method: str = "iid"
    statistic: str = "mean"
    iterations: int = 2000
    seed: int = 42
    confidence: float = 0.95
    blockSize: Optional[int] = None
    interval: str = "1d"


@router.post("/quant/bootstrap")
async def bootstrap_route(body: BootstrapBody, _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.advanced_tools import snapshot_return_series
        from ..quant.validation import bootstrap_ci

        returns, interval, source = body.returns, body.interval, "returns"
        if returns is None:
            if not body.experimentId:
                raise QuantError("provide `returns` or an `experimentId`",
                                 detail={"code": "BOOTSTRAP_INPUT_REQUIRED"})
            returns, interval = snapshot_return_series(
                _store().read_artifact(body.experimentId), body.interval)
            source = f"experiment:{body.experimentId}"
        result = bootstrap_ci(returns, method=body.method, statistic=body.statistic,
                              iterations=body.iterations, seed=body.seed,
                              confidence=body.confidence, block_size=body.blockSize,
                              interval=interval)
        result["source"] = source
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class MultipleTestingBody(ResearchBody):
    paramSpace: dict[str, Any] = Field(default_factory=dict)
    maxEvaluations: int = 20
    returns: Optional[list[float]] = None
    trialSharpes: Optional[list[float]] = None
    returnsMatrix: Optional[list[list[float]]] = None
    srVariance: Optional[float] = None
    trialCount: Optional[int] = None
    nSplits: int = 16


@router.post("/quant/multiple-testing")
async def multiple_testing_route(body: MultipleTestingBody,
                                 _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.advanced_tools import _sweep_trials
        from ..quant.multiple_testing import deflated_sharpe, pbo_cscv

        returns, trial_sharpes, matrix = body.returns, body.trialSharpes, body.returnsMatrix
        sweep: Optional[dict[str, Any]] = None
        has_dsr = returns is not None and (
            trial_sharpes is not None or (body.srVariance is not None and body.trialCount is not None))
        if matrix is None and not has_dsr:
            strategy = _load_strategy(_store(), body.strategyId, body.version)
            dataset = await _dataset_for(strategy, body)
            trials = _sweep_trials(strategy, dataset, {
                "paramSpace": body.paramSpace, "maxEvaluations": body.maxEvaluations,
                "seed": body.seed, "symbols": body.symbols,
                "initialCapital": body.initialCapital, "riskFreeRate": body.riskFreeRate})
            if len(trials) < 2:
                raise QuantError("the sweep produced fewer than 2 usable trials",
                                 detail={"code": "MULTIPLE_TESTING_TOO_FEW_TRIALS"})
            matrix = [tr["returns"] for tr in trials]
            trial_sharpes = [tr["sharpe"] for tr in trials]
            best = max(range(len(trials)), key=lambda i: trials[i]["sharpe"])
            returns = trials[best]["returns"]
            sweep = {"generatedFrom": "parameter_sweep", "trials": len(trials),
                     "bestSharpe": trial_sharpes[best], "bestParams": trials[best]["params"]}
        dsr = None
        if returns is not None:
            if trial_sharpes is not None:
                dsr = deflated_sharpe(returns, trial_sharpes=trial_sharpes)
            elif body.srVariance is not None and body.trialCount is not None:
                dsr = deflated_sharpe(returns, sr_variance=body.srVariance,
                                      trial_count=body.trialCount)
        pbo = pbo_cscv(matrix, n_splits=body.nSplits) if matrix is not None else None
        return {"deflatedSharpe": dsr, "pbo": pbo, "sweep": sweep}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── Background runs ──────────────────────────────────────────────────────────

@router.get("/quant/runs")
async def list_runs(_: bool = Depends(require_operator)) -> dict:
    return {"runs": get_runner().list()}


@router.get("/quant/runs/{run_id}")
async def get_run(run_id: str, result: bool = False, _: bool = Depends(require_operator)) -> dict:
    run = get_runner().get(run_id, include_result=result)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": run_id})
    return run


@router.post("/quant/runs/{run_id}/cancel")
async def cancel_run(run_id: str, _: bool = Depends(require_operator)) -> dict:
    return {"cancelled": get_runner().cancel(run_id), "runId": run_id}


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
        from ..quant.advanced_tools import _comparability_warnings

        comparison = _store().compare_experiments(body.experimentIds)
        comparison["comparability"] = _comparability_warnings(comparison["experiments"])
        return comparison
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# The Statistical Analysis Engine router owns its own `/stats/v1` prefix; it is
# mounted here so `main.py` stays under its non-ratcheted hard ceiling.
from .stats import router as _stats_router  # noqa: E402

router.include_router(_stats_router)


__all__ = ["router"]
