"""The quant REPORT routes ? the surfaces that judge a result.

Four routes live here rather than in `routers/quant.py` because that module is
at its size budget and these are a separate concern: they do not run a
backtest, they *judge* one.

  * `POST /quant/regime-monte-carlo` ? resample a strategy's trades in blocks
    of same-regime runs;
  * `POST /quant/edge-verdict`       ? grade the evidence behind an edge;
  * `POST /quant/prop-firm`          ? test a trade log against a firm's real
    evaluation rules, and estimate the pass probability;
  * `GET  /quant/prop-firm/firms`    ? the rule sets the engine knows, with
    their source and date;
  * `POST /quant/edge-report`        ? the grade, the evidence and the figures
    as one document.

Every route is a thin adapter over the same functions the agent tools use, so
the UI and the agent can never disagree.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..quant import StrategySpec
from ..quant.datasets import dataset_from_strategy
from ..quant.engine import BacktestConfig, run_backtest
from ..quant.montecarlo import MonteCarloConfig, MonteCarloEngine
from .quant import (
    ResearchBody,
    _dataset_for,
    _http,
    _load_strategy,
    _maybe_background,
    _save,
    _store,
)

router = APIRouter(tags=["quant"])


class RegimeMonteCarloBody(ResearchBody):
    regimeMix: str = "resample"
    regimeBlockLength: float = 1.0
    regimeConfig: dict[str, Any] = Field(default_factory=dict)


@router.post("/quant/regime-monte-carlo")
async def regime_monte_carlo_route(body: RegimeMonteCarloBody,
                                   _: bool = Depends(require_operator)) -> dict:
    try:
        store = _store()
        strategy = _load_strategy(store, body.strategyId, body.version)

        async def work(progress: Any) -> dict:
            dataset = await _dataset_for(strategy, body)
            result = MonteCarloEngine(strategy, dataset, MonteCarloConfig(
                method="regime_block_bootstrap",
                simulations=body.simulations, seed=body.seed,
                ruin_threshold=body.ruinThreshold,
                regime_mix=body.regimeMix,
                regime_block_length=body.regimeBlockLength,
                regime_config=body.regimeConfig,
                initial_capital=body.initialCapital, risk_free_rate=body.riskFreeRate,
            ), progress=progress).run()
            exp_id = _save(store, result, strategy, "monte_carlo", body.save)
            payload = result.to_dict()
            payload["experimentId"] = exp_id
            return payload

        return await _maybe_background(body, "regime_monte_carlo", work)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class EdgeVerdictBody(BaseModel):
    strategyId: Optional[str] = None
    version: Optional[str] = None
    experimentId: Optional[str] = None
    monteCarloExperimentId: Optional[str] = None
    symbols: Optional[list[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    initialCapital: float = 100_000.0
    riskFreeRate: float = 0.0
    seed: int = 42
    save: bool = True
    background: bool = False


@router.post("/quant/edge-verdict")
async def edge_verdict_route(body: EdgeVerdictBody,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.research import ResearchResult
        from ..quant.verdict import grade_edge

        store = _store()
        strategy: Optional[StrategySpec] = None
        if body.strategyId:
            strategy = _load_strategy(store, body.strategyId, body.version)

        async def work(progress: Any) -> dict:
            metrics: dict[str, Any] = {}
            trades: list[dict[str, Any]] = []
            equity: list[dict[str, Any]] = []
            symbols: list[str] = []
            interval = body.symbols and body.symbols[0] or None

            if body.experimentId:
                artifact = store.read_artifact(str(body.experimentId))
                metrics = artifact.get("metrics") or {}
                trades = artifact.get("trades") or []
                equity = artifact.get("equityCurve") or []
                symbols = (artifact.get("metadata") or {}).get("symbols") or []
                interval = (artifact.get("metadata") or {}).get("interval") or interval
            else:
                if strategy is None:
                    raise HTTPException(
                        status_code=422,
                        detail="provide `experimentId` or `strategyId`")
                dataset = await dataset_from_strategy(
                    _market_gateway(), strategy, start=body.start, end=body.end,
                    symbols=body.symbols)
                result = run_backtest(strategy, dataset, BacktestConfig(
                    initial_capital=body.initialCapital,
                    risk_free_rate=body.riskFreeRate, random_seed=body.seed),
                    symbols=body.symbols)
                metrics = result.metrics
                trades = result.trades
                equity = result.equity_curve
                symbols = result.metadata.get("symbols") or []
                interval = result.metadata.get("interval") or interval

            monte_carlo = (store.read_artifact(str(body.monteCarloExperimentId))
                           if body.monteCarloExperimentId else None)
            regimes = (monte_carlo or {}).get("regimeAttribution")

            verdict = grade_edge(metrics=metrics, trades=trades, equity_curve=equity,
                                 monte_carlo=monte_carlo, regimes=regimes)
            verdict["strategyId"] = body.strategyId
            verdict["experimentId"] = body.experimentId
            verdict["monteCarloExperimentId"] = body.monteCarloExperimentId

            stored = ResearchResult(
                kind="edge_verdict", status="OK",
                metadata={"symbols": symbols, "interval": interval,
                          "engineVersion": None},
                configuration={"start": body.start, "end": body.end,
                               "initialCapital": body.initialCapital,
                               "randomSeed": body.seed},
                metrics={"grade_score": verdict["score"],
                         "probability_of_loss": (monte_carlo or {}).get("probabilityOfLoss")},
                warnings=[{"code": f["code"], "message": f["message"]}
                          for f in verdict["flags"]],
                payload={"verdict": verdict})
            exp_id = None
            if body.save:
                exp_id = store.save_experiment(
                    stored,
                    strategy_id=strategy.id if strategy else None,
                    strategy_version=strategy.version if strategy else None,
                    kind="edge_verdict")
            payload = {"status": "OK", "verdict": verdict, "experimentId": exp_id}
            return payload

        return await _maybe_background(body, "edge_verdict", work)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


class PropFirmBody(BaseModel):
    firm: str
    size: str = "50k"
    trades: Optional[list[dict[str, Any]]] = None
    experimentId: Optional[str] = None
    simulations: int = 500
    seed: int = 42
    resample: str = "block"
    blockLength: float = 1.0
    feePerAttempt: float = 0.0
    resetFee: float = 0.0
    simulateFunded: bool = True


@router.post("/quant/prop-firm")
async def prop_firm_route(body: PropFirmBody,
                          _: bool = Depends(require_operator)) -> dict:
    try:
        from ..quant.propfirm import get_spec, list_firms
        from ..quant.propfirm_mc import PropFirmMonteCarloConfig, run_prop_firm_monte_carlo

        spec = get_spec(body.firm)
        size = spec.size(body.size)

        trades = body.trades
        if trades is None:
            if not body.experimentId:
                raise HTTPException(
                    status_code=422,
                    detail="provide `trades` or `experimentId`")
            store = _store()
            artifact = store.read_artifact(str(body.experimentId))
            trades = artifact.get("trades") or []

        report = run_prop_firm_monte_carlo(
            list(trades), spec, size,
            PropFirmMonteCarloConfig(
                simulations=body.simulations, seed=body.seed,
                resample=body.resample, block_length=body.blockLength,
                fee_per_attempt=body.feePerAttempt, reset_fee=body.resetFee,
                simulate_funded=body.simulateFunded))
        report["firms"] = [{"id": f["id"], "name": f["name"], "asOf": f["asOf"]}
                           for f in list_firms()]
        return report
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/prop-firm/firms")
async def prop_firm_firms_route(_: bool = Depends(require_operator)) -> dict:
    from ..quant.propfirm import list_firms

    return {"firms": list_firms()}


class TradeLogBody(BaseModel):
    trades: Optional[list[dict[str, Any]]] = None
    symbols: Optional[list[str]] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None


@router.post("/quant/trade-log")
async def trade_log_route(body: TradeLogBody,
                          _: bool = Depends(require_operator)) -> dict:
    """Read a closed-trade log against the conditions in which each entry happened."""
    from ..quant.trade_log import analyse_trade_log

    trades = list(body.trades or [])
    if not trades:
        raise HTTPException(status_code=422,
                            detail="provide `trades` (a closed-trade log)")
    symbols = list(body.symbols or []) or sorted(
        {str(t.get("symbol") or "") for t in trades if t.get("symbol")})
    if not symbols:
        raise HTTPException(status_code=422,
                            detail="the trades name no symbol, so no market can be "
                                   "read for them")

    from ..market.gateway import MarketDataGateway

    gateway = MarketDataGateway(
        service.server_bridge(),
        cache=getattr(service, "market_cache", None),
        router=getattr(service, "market_router", None),
    )
    series: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        try:
            bars = await gateway.get_historical_prices(
                symbol, None, start=body.start, end=body.end,
                interval=body.interval)
        except Exception:  # noqa: BLE001 - a symbol we cannot load is reported
            continue
        rows = getattr(bars, "bars", None)
        if rows is None and isinstance(bars, dict):
            rows = bars.get("bars")
        if not rows:
            continue
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append({"time": row.get("timestamp"), "o": row.get("open"),
                            "h": row.get("high"), "l": row.get("low"),
                            "c": row.get("close"), "v": row.get("volume")})
            else:
                out.append({"time": getattr(row, "timestamp", None),
                            "o": getattr(row, "open", None),
                            "h": getattr(row, "high", None),
                            "l": getattr(row, "low", None),
                            "c": getattr(row, "close", None),
                            "v": getattr(row, "volume", None)})
        series[symbol] = out
    if not series:
        raise HTTPException(status_code=422,
                            detail=f"no bars could be loaded for {', '.join(symbols)}")

    analysis = analyse_trade_log(trades, series)
    return {"status": "OK", **analysis.to_dict()}


class EdgeReportBody(BaseModel):
    experimentId: str
    monteCarloExperimentId: Optional[str] = None
    renderCharts: bool = True


@router.post("/quant/edge-report")
async def edge_report_route(body: EdgeReportBody,
                             _: bool = Depends(require_operator)) -> dict:
    try:
        from ..charts.render import ChartRenderError
        from ..charts.service import register_chart_artifact, render_spec
        from ..charts.spec import ChartSpec
        from ..quant.edge_report import build_edge_report

        store = _store()
        artifact = store.read_artifact(str(body.experimentId))
        monte_carlo = None
        if body.monteCarloExperimentId:
            monte_carlo = store.read_artifact(str(body.monteCarloExperimentId))

        report = build_edge_report(artifact, monte_carlo)
        payload: dict[str, Any] = {
            "status": "OK",
            "experimentId": body.experimentId,
            "monteCarloExperimentId": body.monteCarloExperimentId,
            "verdict": report.verdict,
            "markdown": report.markdown,
            "warnings": report.warnings,
            "charts": [],
        }

        if body.renderCharts:
            ctx = service
            for chart in report.charts:
                entry: dict[str, Any] = {"name": chart["name"], "title": chart["title"],
                                         "spec": chart["spec"]}
                try:
                    rendered = render_spec(ChartSpec.model_validate(chart["spec"]))
                except ChartRenderError as exc:
                    entry["error"] = {"code": exc.code, "reason": exc.reason}
                    payload["charts"].append(entry)
                    continue
                registered = register_chart_artifact(ctx, rendered,
                                                     source_tool="edge_report")
                entry["figure"] = rendered.to_dict()
                entry["artifactId"] = getattr(registered, "id", None)
                payload["charts"].append(entry)

        payload["summary"] = report.verdict.get("summary")
        return payload
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


# ── The Quant Figure Kit ─────────────────────────────────────────────────────


@router.get("/quant/experiments/{experiment_id}/figures")
async def list_quant_figures(experiment_id: str,
                             figures: Optional[str] = None,
                             theme: str = "eclipse-dark",
                             _: bool = Depends(require_operator)) -> dict:
    """List the figures available for one stored artifact.

    The default is the `core` preset. A figure whose input is absent is returned
    with `available: false` and the reason, never as an empty chart.
    """
    try:
        from ..quant.visuals import build_figures

        store = _store()
        artifact = store.read_artifact(experiment_id)
        requested = [part for part in (figures or "core").split(",") if part.strip()]
        built = build_figures(artifact, figures=requested, theme=theme)
        return {
            "status": "OK",
            "experimentId": experiment_id,
            "figures": [figure.to_dict() for figure in built],
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/quant/experiments/{experiment_id}/figures/{figure}")
async def get_quant_figure(experiment_id: str, figure: str,
                           theme: str = "eclipse-dark",
                           _: bool = Depends(require_operator)) -> dict:
    """One figure's chart-engine spec, or an honest `available: false`."""
    try:
        from ..quant.visuals import build_figure

        store = _store()
        artifact = store.read_artifact(experiment_id)
        built = build_figure(figure, artifact, theme=theme)
        return {
            "status": "OK",
            "experimentId": experiment_id,
            "figure": built.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


