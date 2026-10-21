"""Advanced quant agent tools: engine selection, standalone execution-cost
diagnostics, out-of-sample testing, bootstrap confidence intervals and
backtest comparison.

Every handler delegates to a real, deterministic implementation — the cost tools
share the engine's `ExecutionSimulator`, the vectorized tool uses the restricted
`vector_engine`, out-of-sample runs the real event engine on disjoint slices, and
the bootstrap uses `validation.bootstrap_ci`. None of them fabricate a result or
run a second, incompatible accounting path.
"""

from __future__ import annotations

from typing import Any, Optional


import numpy as np

from .costs import simulate_costs
from .engine import BacktestConfig, run_backtest
from .errors import QuantError
from .multiple_testing import deflated_sharpe, pbo_cscv
from .params import ParamSpace, apply_params
from .strategy import StrategySpec
from .validation import bootstrap_ci, returns_from_equity, split_index
from .vector_engine import VectorUnsupported, run_vectorized_backtest, vector_capability


def _t():
    from . import tools

    return tools


def snapshot_return_series(artifact: dict[str, Any], default_interval: str) -> tuple[list[float], str]:
    """Extract a per-period return series from a stored experiment artifact."""
    equity = [float(p["equity"]) for p in artifact.get("equityCurve", []) if "equity" in p]
    if len(equity) < 3:
        raise QuantError(
            "the experiment has too few equity points to bootstrap",
            detail={"equityPoints": len(equity)},
        )
    interval = str((artifact.get("configuration") or {}).get("interval") or default_interval)
    return returns_from_equity(equity), interval


async def run_out_of_sample(strategy: Any, gateway: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Run IS and OOS backtests on disjoint chronological slices of real data."""
    from .datasets import dataset_from_strategy

    full = await dataset_from_strategy(
        gateway, strategy, start=args.get("start"), end=args.get("end"),
        symbols=args.get("symbols"))
    timeline = full.timeline()
    if len(timeline) < 4:
        raise QuantError(
            "need at least 4 bars for an in-sample / out-of-sample split",
            detail={"bars": len(timeline)},
        )
    is_end, oos_start = split_index(
        len(timeline),
        oos_fraction=(float(args["oosFraction"]) if args.get("oosFraction") is not None else None),
        oos_start_index=(int(args["oosStartIndex"]) if args.get("oosStartIndex") is not None else None),
    )
    is_ds = full.slice_by_timestamps(timeline[0], timeline[is_end - 1])
    oos_ds = full.slice_by_timestamps(timeline[oos_start], timeline[-1])
    cfg = BacktestConfig(
        initial_capital=float(args.get("initialCapital") or 100_000.0),
        risk_free_rate=float(args.get("riskFreeRate") or 0.0),
        random_seed=int(args.get("randomSeed") or 42),
    )
    is_result = run_backtest(strategy, is_ds, cfg, symbols=args.get("symbols"))
    oos_result = run_backtest(strategy, oos_ds, cfg, symbols=args.get("symbols"))

    warnings: list[dict[str, Any]] = []
    warnings.append({
        "code": "OOS_PARAMETERS_MUST_BE_FROZEN",
        "message": "out-of-sample validity requires the strategy version and its parameters were "
                   "frozen before this window was observed; the engine cannot verify that itself",
    })
    return {
        "status": "OK",
        "strategy": {"id": strategy.id, "version": strategy.version},
        "split": {
            "isBars": is_end,
            "oosBars": len(timeline) - oos_start,
            "overlapBars": 0,
            "isStart": timeline[0],
            "isEnd": timeline[is_end - 1],
            "oosStart": timeline[oos_start],
            "oosEnd": timeline[-1],
        },
        "inSample": {"metrics": is_result.metrics, "bars": is_result.metadata.get("bars")},
        "outOfSample": {"metrics": oos_result.metrics, "bars": oos_result.metadata.get("bars")},
        "warnings": warnings,
        "contaminated": False,
        "extraFiles": {},
        "oosResult": oos_result,
    }


# ── Engine-selected backtests ────────────────────────────────────────────────

async def run_event_driven_backtest_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        store = t._store(ctx)
        strategy = await t._load_strategy(store, args)
        result = await t._run_one(strategy, t._gateway(ctx), args)
        exp_id = await t._persist(result, strategy, store, "event_driven_backtest") \
            if t._flag(args, "save", True) else None
        return (t._render_result(result, exp_id), t._result_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def run_vectorized_backtest_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        from .datasets import dataset_from_strategy

        store = t._store(ctx)
        strategy = await t._load_strategy(store, args)
        symbols = args.get("symbols") or strategy.universe.symbols
        cap = vector_capability(strategy, symbols=symbols)
        if not cap["supported"]:
            return (f"ERROR — VECTOR_UNSUPPORTED: {'; '.join(cap['reasons'])}",
                    {"status": "ERROR", "error": {"code": "VECTOR_UNSUPPORTED",
                                                  "message": "; ".join(cap["reasons"]),
                                                  "detail": cap}})
        dataset = await dataset_from_strategy(
            t._gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=symbols)
        cfg = BacktestConfig(
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            start=args.get("start"), end=args.get("end"),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            random_seed=int(args.get("randomSeed") or 42),
        )
        result = run_vectorized_backtest(strategy, dataset, cfg, symbols=symbols)
        exp_id = await t._persist(result, strategy, store, "vectorized_backtest") \
            if t._flag(args, "save", True) else None
        return (t._render_result(result, exp_id), t._result_data(result, exp_id))
    except VectorUnsupported as exc:
        return t._err(exc)
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── Standalone execution-cost diagnostics ────────────────────────────────────

def _cost_handler(kind: str):
    async def handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
        t = _t()
        try:
            result = simulate_costs(
                kind, args.get("orders") or [], args.get("execution"),
                seed=(int(args["seed"]) if args.get("seed") is not None else None))
            text = (f"{kind} simulation: {result['orderCount']} order(s), total "
                    f"{result['total']}"
                    + (" (frictionless model)" if result["frictionless"] else "")
                    + (f"; {len(result['warnings'])} warning(s)" if result["warnings"] else ""))
            return (text, {"status": "OK", "simulation": result})
        except Exception as exc:  # noqa: BLE001
            return t._err(exc)

    return handler


# ── Options & futures analytics ──────────────────────────────────────────────

def _risk_free(args: dict[str, Any]) -> float:
    from ..market.greeks import DEFAULT_RISK_FREE

    value = args.get("riskFree")
    return float(value) if value is not None else DEFAULT_RISK_FREE


async def price_option_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        from .options import price_option

        result = price_option(
            option_type=str(args.get("type") or args.get("optionType") or ""),
            spot=float(args.get("spot") or 0), strike=float(args.get("strike") or 0),
            time_to_expiry=float(args.get("timeToExpiry") or 0),
            iv=float(args.get("iv") or 0), risk_free=_risk_free(args),
            dividend_yield=float(args.get("dividendYield") or 0))
        if not result.get("available"):
            return (f"Option price unavailable: {result.get('reason')}",
                    {"status": "OK", "option": result})
        return (f"{result['optionType']} K={result['strike']}: price={result['price']:.4f}, "
                f"delta={result['delta']:.4f}, vega={result['vega']:.4f}.",
                {"status": "OK", "option": result})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def implied_volatility_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        from .options import implied_volatility

        result = implied_volatility(
            float(args.get("marketPrice") or 0),
            option_type=str(args.get("type") or args.get("optionType") or ""),
            spot=float(args.get("spot") or 0), strike=float(args.get("strike") or 0),
            time_to_expiry=float(args.get("timeToExpiry") or 0), risk_free=_risk_free(args),
            dividend_yield=float(args.get("dividendYield") or 0))
        if not result.get("available"):
            return (f"Implied vol unavailable: {result.get('reason')}",
                    {"status": "OK", "iv": result})
        return (f"Implied volatility = {result['impliedVolatility']:.4f}.",
                {"status": "OK", "iv": result})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def analyze_option_strategy_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        from .options import analyze_option_strategy

        result = analyze_option_strategy(
            args.get("legs") or [],
            spot_min=float(args.get("spotMin") or 0), spot_max=float(args.get("spotMax") or 0),
            points=int(args.get("points") or 201),
            valuation_spot=(float(args["valuationSpot"]) if args.get("valuationSpot") is not None else None),
            time_to_expiry=(float(args["timeToExpiry"]) if args.get("timeToExpiry") is not None else None),
            iv=(float(args["iv"]) if args.get("iv") is not None else None),
            risk_free=_risk_free(args))
        mp = result["maxProfit"]
        ml = result["maxLoss"]
        return (f"Strategy ({result['strategyType']}): break-evens={result['breakEvens']}, "
                f"maxProfit={mp}, maxLoss={ml}, bounded={result['bounded']}.",
                {"status": "OK", "strategy": result})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


def _rows_from_series(series: Any) -> list[dict[str, Any]]:
    return [{"timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
             "low": bar.low, "close": bar.close, "volume": getattr(bar, "volume", 0.0)}
            for bar in series.bars]


async def build_continuous_contract_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        from .futures import splice_continuous

        roll_dates = [str(x) for x in (args.get("rollDates") or [])]
        contracts = args.get("contracts")
        if not contracts:
            symbols = [str(s) for s in (args.get("symbols") or [])]
            if not symbols:
                return ("ERROR — provide `contracts` or `symbols`.",
                        {"status": "ERROR", "error": {"code": "FUTURES_INPUT_REQUIRED"}})
            gateway = t._gateway(ctx)
            contracts = []
            for sym in symbols:
                series = await gateway.get_historical_prices(
                    sym, None, start=args.get("start"), end=args.get("end"),
                    interval=str(args.get("interval") or "1d"))
                contracts.append({"symbol": sym, "rows": _rows_from_series(series)})
        result = splice_continuous(contracts, roll_dates,
                                   adjustment=str(args.get("adjustment") or "difference"))
        return (f"Continuous contract: {result['barCount']} bars, {len(result['rolls'])} roll(s), "
                f"adjustment={result['adjustment']}.",
                {"status": "OK",
                 **{k: v for k, v in result.items() if k != "bars"},
                 "bars": result["bars"]})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── Statistical validation ───────────────────────────────────────────────────

async def run_out_of_sample_test(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        store = t._store(ctx)
        strategy = await t._load_strategy(store, args)
        report = await run_out_of_sample(strategy, t._gateway(ctx), args)
        split = report["split"]
        contaminating = _oos_contamination(
            store, strategy.id, split["oosStart"], split["oosEnd"])
        report["contaminated"] = bool(contaminating)
        report["contaminationEvidence"] = contaminating
        if contaminating:
            report["warnings"].append({
                "code": "OOS_WINDOW_CONTAMINATED",
                "message": "the out-of-sample window overlaps an earlier optimization/"
                           "selection experiment for this strategy; this cannot be "
                           "certified as untouched",
                "detail": {"experiments": [e["id"] for e in contaminating]},
            })
        exp_id = None
        if t._flag(args, "save", True):
            exp_id = store.save_experiment(
                report["oosResult"], strategy_id=strategy.id,
                strategy_version=strategy.version, kind="out_of_sample")
        report["experimentId"] = exp_id
        data = {k: v for k, v in report.items() if k != "oosResult"}
        return (f"Out-of-sample {strategy.id} v{strategy.version}: "
                f"IS return={report['inSample']['metrics'].get('total_return')}, "
                f"OOS return={report['outOfSample']['metrics'].get('total_return')} "
                f"(OOS bars={split['oosBars']}, overlap=0, "
                f"contaminated={report['contaminated']}).", data)
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


def _oos_contamination(store: Any, strategy_id: str, oos_start: str, oos_end: str) -> list[dict]:
    """Prior selection experiments whose window overlaps [oos_start, oos_end]."""
    selecting = {"optimization", "walk_forward", "sensitivity", "robustness"}
    out: list[dict] = []
    for exp in store.list_experiments(strategy_id=strategy_id, limit=200):
        if exp.get("kind") not in selecting:
            continue
        start, end = exp.get("start"), exp.get("end")
        if not start or not end:
            continue
        if start <= oos_end and end >= oos_start:
            out.append({"id": exp["id"], "kind": exp["kind"], "start": start, "end": end})
    return out


async def run_bootstrap_test(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        returns = args.get("returns")
        interval = str(args.get("interval") or "1d")
        source = "returns"
        if returns is None:
            store = t._store(ctx)
            exp_id = str(args.get("experimentId") or "")
            if not exp_id:
                return ("ERROR — provide `returns` or an `experimentId`.",
                        {"status": "ERROR", "error": {"code": "BOOTSTRAP_INPUT_REQUIRED"}})
            artifact = store.read_artifact(exp_id)
            returns, interval = snapshot_return_series(artifact, interval)
            source = f"experiment:{exp_id}"
        result = bootstrap_ci(
            [float(x) for x in returns],
            method=str(args.get("method") or "iid"),
            statistic=str(args.get("statistic") or "mean"),
            iterations=int(args.get("iterations") or 2000),
            seed=int(args.get("seed") or 42),
            confidence=float(args.get("confidence") or 0.95),
            block_size=(int(args["blockSize"]) if args.get("blockSize") is not None else None),
            interval=interval,
        )
        result["source"] = source
        if not result.get("available", True):
            return (f"Bootstrap unavailable: {result.get('reason')}",
                    {"status": "OK", "bootstrap": result})
        return (f"Bootstrap {result['statistic']} ({result['method']}): "
                f"estimate={result['estimate']}, "
                f"{result['confidence'] * 100:.0f}% CI "
                f"[{result['ciLower']}, {result['ciUpper']}] over {result['successful']} "
                f"replicates.", {"status": "OK", "bootstrap": result})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── Multiple-testing / overfitting diagnostics ───────────────────────────────

def _per_period_sharpe(returns: list[float]) -> float:
    arr = np.asarray(returns, dtype=float)
    if arr.size < 2:
        return 0.0
    sd = float(np.std(arr, ddof=1))
    return float(np.mean(arr) / sd) if sd > 0 else 0.0


def _sweep_trials(strategy: StrategySpec, dataset: Any, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Run a bounded real parameter sweep, collecting each trial's returns."""
    space = ParamSpace.from_dict(args.get("paramSpace") or {})
    base = strategy.to_dict()
    max_eval = max(2, min(int(args.get("maxEvaluations") or 20), 200))
    if space.is_empty():
        combos: list[dict[str, Any]] = [{}]
    elif space.size() <= max_eval:
        combos = list(space.grid())
    else:
        import random as _random

        combos = space.sample(max_eval, _random.Random(int(args.get("seed") or 42)))
    symbols = args.get("symbols")
    trials: list[dict[str, Any]] = []
    for params in combos:
        try:
            spec = StrategySpec.model_validate(apply_params(base, params))
            cfg = BacktestConfig(
                initial_capital=float(args.get("initialCapital") or 100_000.0),
                risk_free_rate=float(args.get("riskFreeRate") or 0.0),
                random_seed=int(args.get("seed") or 42),
            )
            res = run_backtest(spec, dataset, cfg, symbols=symbols)
            returns = returns_from_equity([p["equity"] for p in res.equity_curve])
            trials.append({"params": params, "returns": returns,
                           "sharpe": _per_period_sharpe(returns)})
        except Exception:  # noqa: BLE001 - a bad combo is skipped, not fatal
            continue
    return trials


async def run_multiple_testing_diagnostics(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        returns = args.get("returns")
        trial_sharpes = args.get("trialSharpes")
        matrix = args.get("returnsMatrix")
        sr_var = args.get("srVariance")
        trial_count = args.get("trialCount")
        has_explicit_dsr = returns is not None and (
            trial_sharpes is not None or (sr_var is not None and trial_count is not None))

        sweep: Optional[dict[str, Any]] = None
        if matrix is None and not has_explicit_dsr:
            if not args.get("strategyId"):
                return ("ERROR — provide `returns`+`trialSharpes` / `returnsMatrix`, or a "
                        "`strategyId` + `paramSpace` to run a real sweep.",
                        {"status": "ERROR", "error": {"code": "MULTIPLE_TESTING_INPUT_REQUIRED"}})
            from .datasets import dataset_from_strategy

            store = t._store(ctx)
            strategy = await t._load_strategy(store, args)
            dataset = await dataset_from_strategy(
                t._gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
                symbols=args.get("symbols"))
            trials = _sweep_trials(strategy, dataset, args)
            if len(trials) < 2:
                return ("ERROR — the sweep produced fewer than 2 usable trials.",
                        {"status": "ERROR", "error": {"code": "MULTIPLE_TESTING_TOO_FEW_TRIALS"}})
            matrix = [tr["returns"] for tr in trials]
            trial_sharpes = [tr["sharpe"] for tr in trials]
            best = max(range(len(trials)), key=lambda i: trials[i]["sharpe"])
            returns = trials[best]["returns"]
            sweep = {"generatedFrom": "parameter_sweep", "trials": len(trials),
                     "bestSharpe": trial_sharpes[best], "bestParams": trials[best]["params"]}

        dsr: Optional[dict[str, Any]] = None
        if returns is not None:
            if trial_sharpes is not None:
                dsr = deflated_sharpe(returns, trial_sharpes=trial_sharpes)
            elif sr_var is not None and trial_count is not None:
                dsr = deflated_sharpe(returns, sr_variance=float(sr_var),
                                      trial_count=int(trial_count))
        pbo = pbo_cscv(matrix, n_splits=int(args.get("nSplits") or 16)) if matrix is not None else None

        parts = []
        if dsr and dsr.get("available"):
            parts.append(f"DSR={dsr['deflatedSharpeRatio']:.3f}")
        if pbo and pbo.get("available"):
            parts.append(f"PBO={pbo['probabilityOfBacktestOverfitting'] * 100:.1f}%")
        summary = ", ".join(parts) or "insufficient inputs"
        return (f"Multiple-testing diagnostics: {summary}.",
                {"status": "OK", "deflatedSharpe": dsr, "pbo": pbo, "sweep": sweep})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── Comparison ───────────────────────────────────────────────────────────────

_COMPARE_RISK_KEYS = ("symbols", "interval", "start", "end", "initialCapital")


async def compare_backtests(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        store = t._store(ctx)
        ids = [str(x) for x in (args.get("experimentIds") or [])]
        if len(ids) < 2:
            return ("ERROR — `experimentIds` needs at least two experiments.",
                    {"status": "ERROR", "error": {"code": "COMPARE_NEEDS_TWO"}})
        comparison = store.compare_experiments(ids)
        warnings = _comparability_warnings(comparison["experiments"])
        comparison["comparability"] = warnings
        lines = [f"  {e['experimentId']}: ret={e['metrics'].get('total_return')}, "
                 f"sharpe={e['metrics'].get('sharpe')}, maxDD={e['metrics'].get('max_drawdown')}"
                 for e in comparison["experiments"]]
        if warnings:
            lines.append("Comparability cautions:")
            lines.extend(f"  ! {w['message']}" for w in warnings)
        return (f"Compared {len(comparison['experiments'])} backtest(s):\n" + "\n".join(lines),
                {"status": "OK", **comparison})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


def _comparability_warnings(experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    def _differs(key: str) -> bool:
        return len({_freeze(e.get(key)) for e in experiments}) > 1

    for key in _COMPARE_RISK_KEYS:
        if _differs(key):
            warnings.append({
                "code": "COMPARABILITY_DIFFERENT_" + key.upper(),
                "message": f"experiments differ on `{key}`; the comparison is not like-for-like",
            })
    for e in experiments:
        cfg = e.get("configuration") or {}
        exec_cfg = cfg.get("execution") or {}
        if exec_cfg.get("frictionless"):
            warnings.append({
                "code": "COMPARABILITY_FRICTIONLESS",
                "message": f"{e['experimentId']} is frictionless; its return is not net of costs",
            })
    if warnings:
        warnings.append({
            "code": "COMPARABILITY_CAUTION",
            "message": "treat cross-run differences as descriptive, not as a fair ranking, "
                       "until data ranges, instruments and execution assumptions align",
        })
    return warnings


def _freeze(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


# ── Regime-aware uncertainty and the edge verdict ────────────────────────────

async def run_regime_monte_carlo(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Resample the trade sequence in blocks of same-regime runs."""
    t = _t()
    try:
        from .datasets import dataset_from_strategy
        from .montecarlo import MonteCarloConfig, MonteCarloEngine

        store = t._store(ctx)
        strategy = await t._load_strategy(store, args)
        dataset = await dataset_from_strategy(
            t._gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = MonteCarloConfig(
            method="regime_block_bootstrap",
            simulations=int(args.get("simulations") or 1000),
            seed=int(args.get("seed") or 42),
            ruin_threshold=float(args.get("ruinThreshold") or 0.5),
            regime_mix=str(args.get("regimeMix") or "resample"),
            regime_block_length=float(args.get("regimeBlockLength") or 1.0),
            regime_config=dict(args.get("regimeConfig") or {}),
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
        )
        result = MonteCarloEngine(strategy, dataset, config).run()
        exp_id = None
        if t._flag(args, "save", True):
            exp_id = store.save_experiment(
                result, strategy_id=strategy.id, strategy_version=strategy.version,
                kind="monte_carlo")
        payload = result.to_dict()
        payload["experimentId"] = exp_id
        attribution = payload.get("regimeAttribution") or {}
        regimes = attribution.get("regimes") or {}
        blocks = payload.get("regimeBlocks") or 0
        detail = ", ".join(
            f"{label}: {int(bucket.get('trades') or 0)} trades, "
            f"net {float(bucket.get('netPnl') or 0.0):.2f}"
            for label, bucket in list(regimes.items())[:6]) or "no regime was labelled"
        return (f"Regime-block Monte-Carlo: {blocks} same-regime block(s), mix="
                f"{payload.get('regimeMix')}, {payload.get('successful')} path(s). "
                f"P(loss)={payload.get('probabilityOfLoss')}%, "
                f"P(ruin)={payload.get('probabilityOfRuin')}%. {detail}.",
                {"status": "OK", **payload})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def grade_strategy_edge(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Grade the evidence behind a strategy's edge (A-F) and name the tells."""
    t = _t()
    try:
        from .verdict import grade_edge

        store = t._store(ctx)
        experiment_id = args.get("experimentId")
        monte_carlo_id = args.get("monteCarloExperimentId")

        if experiment_id:
            artifact = store.read_artifact(str(experiment_id))
            metrics = artifact.get("metrics") or {}
            trades = artifact.get("trades") or []
            equity = artifact.get("equityCurve") or []
            strategy_id = args.get("strategyId")
        else:
            if not args.get("strategyId"):
                return ("ERROR - provide `experimentId` or `strategyId`.",
                        {"status": "ERROR",
                         "error": {"code": "EDGE_VERDICT_INPUT_REQUIRED"}})
            strategy = await t._load_strategy(store, args)
            result = await t._run_one(strategy, t._gateway(ctx), args)
            metrics = result.metrics
            trades = result.trades
            equity = result.equity_curve
            strategy_id = strategy.id

        monte_carlo = store.read_artifact(str(monte_carlo_id)) if monte_carlo_id else None
        regimes = (monte_carlo or {}).get("regimeAttribution")

        verdict = grade_edge(metrics=metrics, trades=trades, equity_curve=equity,
                             monte_carlo=monte_carlo, regimes=regimes)
        verdict["strategyId"] = strategy_id
        verdict["experimentId"] = experiment_id
        verdict["monteCarloExperimentId"] = monte_carlo_id
        return (verdict["summary"], {"status": "OK", "verdict": verdict})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── Prop-firm evaluation ─────────────────────────────────────────────────────

async def run_prop_firm_simulation(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Evaluate a trade log against a prop firm's real rules."""
    t = _t()
    try:
        from .propfirm import get_spec, list_firms
        from .propfirm_mc import PropFirmMonteCarloConfig, run_prop_firm_monte_carlo

        firm = str(args.get("firm") or "").strip()
        if not firm:
            return (f"ERROR - provide `firm`. Known firms: "
                    f"{', '.join(f['id'] for f in list_firms())}.",
                    {"status": "ERROR",
                     "error": {"code": "PROP_FIRM_REQUIRED",
                               "available": [f["id"] for f in list_firms()]}})
        spec = get_spec(firm)
        size_id = str(args.get("size") or "").strip()
        if not size_id:
            return (f"ERROR - provide `size`. {spec.name} has: "
                    f"{', '.join(s.id for s in spec.sizes)}.",
                    {"status": "ERROR",
                     "error": {"code": "PROP_FIRM_SIZE_REQUIRED",
                               "available": [s.id for s in spec.sizes]}})
        try:
            size = spec.size(size_id)
        except Exception as exc:  # noqa: BLE001 - an unknown size is a named refusal
            return (f"ERROR - {exc}",
                    {"status": "ERROR",
                     "error": {"code": "PROP_FIRM_SIZE_UNKNOWN",
                               "available": [s.id for s in spec.sizes]}})

        trades = args.get("trades")
        if trades is None:
            experiment_id = args.get("experimentId")
            if not experiment_id:
                return ("ERROR - provide `trades` (a closed-trade log) or "
                        "`experimentId` (a stored backtest to read the trades "
                        "from). For a real trading log, call `journal_trades` "
                        "first and pass its trades here.",
                        {"status": "ERROR",
                         "error": {"code": "PROP_FIRM_INPUT_REQUIRED"}})
            store = t._store(ctx)
            artifact = store.read_artifact(str(experiment_id))
            trades = artifact.get("trades") or []

        config = PropFirmMonteCarloConfig(
            simulations=int(args.get("simulations") or 500),
            seed=int(args.get("seed") or 42),
            resample=str(args.get("resample") or "block"),
            block_length=float(args.get("blockLength") or 1.0),
            fee_per_attempt=float(args.get("feePerAttempt") or 0.0),
            reset_fee=float(args.get("resetFee") or 0.0),
            simulate_funded=bool(args.get("simulateFunded", True)),
        )
        report = run_prop_firm_monte_carlo(list(trades), spec, size, config)
        if not report.get("available"):
            return (f"Prop-firm simulation unavailable: {report.get('reason')}",
                    {"status": "OK", **report})

        mc = report["monteCarlo"]
        baseline = report["baseline"]["evaluation"]
        outcomes = ", ".join(f"{k}={v}" for k, v in mc["outcomes"].items() if v)
        return (f"{spec.name} {size.label}: pass probability "
                f"{mc['passProbability']:.1f}% over {mc['simulations']} resampled "
                f"paths ({outcomes}). The log as it actually happened: "
                f"{baseline['status']} - {baseline['reason']}. "
                f"Rules as of {spec.as_of}; confirm them with the firm.",
                {"status": "OK", **report})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def list_prop_firm_rules(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """The prop-firm rule sets the engine knows, with their source and date."""
    t = _t()
    try:
        from .propfirm import list_firms

        firms = list_firms()
        lines = [
            f"{f['name']} ({f['id']}) - sizes: "
            f"{', '.join(s['id'] for s in f['sizes'])}; rules as of {f['asOf']}"
            for f in firms
        ]
        lines.append("Firm rules change often: confirm the numbers with the firm "
                     "before acting on them.")
        return ("\n".join(lines), {"status": "OK", "firms": firms})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


# ── The Edge Report ──────────────────────────────────────────────────────────

async def generate_edge_report(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Build the Edge Report: the grade, the evidence and the figures."""
    t = _t()
    try:
        from ..charts.render import ChartRenderError
        from ..charts.service import register_chart_artifact, render_spec
        from ..charts.spec import ChartSpec
        from .edge_report import build_edge_report

        experiment_id = str(args.get("experimentId") or "")
        if not experiment_id:
            return ("ERROR - provide `experimentId` (the stored backtest to grade).",
                    {"status": "ERROR",
                     "error": {"code": "EDGE_REPORT_INPUT_REQUIRED"}})

        store = t._store(ctx)
        artifact = store.read_artifact(experiment_id)
        monte_carlo = None
        mc_id = args.get("monteCarloExperimentId")
        if mc_id:
            monte_carlo = store.read_artifact(str(mc_id))

        report = build_edge_report(artifact, monte_carlo)
        payload: dict[str, Any] = {
            "status": "OK",
            "verdict": report.verdict,
            "markdown": report.markdown,
            "warnings": report.warnings,
            "charts": [],
        }

        if args.get("renderCharts", True):
            for chart in report.charts:
                entry = {"name": chart["name"], "title": chart["title"],
                         "spec": chart["spec"]}
                try:
                    rendered = render_spec(ChartSpec.model_validate(chart["spec"]))
                except ChartRenderError as exc:
                    entry["error"] = {"code": exc.code, "reason": exc.reason}
                    payload["charts"].append(entry)
                    continue
                artifact_entry = register_chart_artifact(ctx, rendered,
                                                        source_tool="edge_report")
                entry["figure"] = rendered.to_dict()
                entry["artifactId"] = getattr(artifact_entry, "id", None)
                payload["charts"].append(entry)

        report_artifact = _register_report_artifact(ctx, report.markdown, experiment_id,
                                                     payload.get("verdict"))
        payload["reportArtifactId"] = getattr(report_artifact, "id", None)

        verdict = payload["verdict"]
        payload["summary"] = verdict.get("summary")
        return (str(verdict.get("summary")),
                {**payload, "experimentId": experiment_id,
                 "monteCarloExperimentId": mc_id})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


def _register_report_artifact(ctx: Any, markdown: str, experiment_id: str,
                               verdict: Optional[dict[str, Any]]) -> Optional[Any]:
    """Record the Edge Report document in the Artifact Center. Best-effort."""
    try:
        from ..artifacts.bootstrap import get_artifact_service
        from ..artifacts.model import ArtifactCategory

        service = getattr(ctx, "artifact_service", None) if ctx is not None else None
        service = service or get_artifact_service()
        if service is None:
            return None
        run_id = getattr(ctx, "run_id", None) if ctx is not None else None
        grade = (verdict or {}).get("grade")
        return service.register_bytes(
            markdown.encode("utf-8"),
            name=f"edge-report-{experiment_id}.md",
            owner_id="local",
            description=f"Edge Report for {experiment_id} — grade {grade}",
            category=ArtifactCategory.REPORT,
            mime_type="text/markdown",
            source_tool="edge_report",
            run_id=run_id,
            tags=["edge-report", "quant", "computed"],
            idempotency_key=f"edge-report:{experiment_id}:{run_id or 'none'}",
            metadata={"experimentId": experiment_id, "grade": grade,
                      "score": (verdict or {}).get("score")},
        )
    except Exception:  # noqa: BLE001 - registration must never fail the report
        return None


# ── The trade-log analysis ───────────────────────────────────────────────────

async def analyse_trade_log(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Read a trade log against the conditions in which each entry happened."""
    t = _t()
    try:
        from .trade_log import analyse_trade_log as _analyse

        trades = args.get("trades")
        source = "trades"
        if not trades:
            trades = await _journal_trades(ctx)
            source = "journal"
            if not trades:
                return ("ERROR - the Journal has no trades to analyse. Pass `trades` "
                        "explicitly, or record some first.",
                        {"status": "ERROR",
                         "error": {"code": "TRADE_LOG_EMPTY"}})

        symbols = list(args.get("symbols") or []) or sorted(
            {str(tr.get("symbol") or "") for tr in trades if tr.get("symbol")})
        series = await _bars_for_symbols(ctx, symbols, args)
        if not series:
            return ("ERROR - no bars could be loaded for "
                    f"{', '.join(symbols) or 'the traded symbols'}; the entries "
                    "cannot be placed in their market conditions.",
                    {"status": "ERROR",
                     "error": {"code": "TRADE_LOG_NO_BARS"}})

        analysis = _analyse(list(trades), series)
        payload = analysis.to_dict()
        payload["source"] = source
        payload["symbols"] = symbols

        best = max(payload["byRegime"].items(),
                   key=lambda kv: float(kv[1].get("netPnl") or 0.0),
                   default=(None, {}))
        return (f"{payload['entryCount']} trade(s) read against their own market "
                f"conditions ({source}): net {payload['totals']['netPnl']}, "
                f"{payload['coverage']['regimeCount']} regime(s) seen, "
                f"best regime {best[0]}. "
                f"{len(payload['warnings'])} warning(s).",
                {"status": "OK", **payload})
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


async def _journal_trades(ctx: Any) -> list[dict[str, Any]]:
    """The Journal's trades, through the same front door the journal tool uses."""
    from ..journal_tools import _journal_request

    status, payload = await _journal_request("GET", "/api/journal/trades")
    if status >= 400:
        return []
    return list((payload or {}).get("trades") or [])


async def _bars_for_symbols(ctx: Any, symbols: list[str],
                            args: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The bars each traded symbol has, from the ONE market data gateway."""
    market = getattr(ctx, "market", None)
    gateway = getattr(market, "gateway", None) if market is not None else None
    if gateway is None:
        return {}
    interval = str(args.get("interval") or "1d")
    start = args.get("start")
    end = args.get("end")
    out: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        if not symbol:
            continue
        try:
            series = await gateway.get_historical_prices(
                symbol, None, start=start, end=end, interval=interval)
        except Exception:  # noqa: BLE001 - a symbol we cannot load is reported
            continue
        rows = getattr(series, "bars", None)
        if rows is None and isinstance(series, dict):
            rows = series.get("bars")
        if not rows:
            continue
        out[symbol] = [
            {"time": getattr(row, "timestamp", None) or row.get("timestamp")
                if isinstance(row, dict) else getattr(row, "timestamp", None),
             "o": getattr(row, "open", None) if not isinstance(row, dict) else row.get("open"),
             "h": getattr(row, "high", None) if not isinstance(row, dict) else row.get("high"),
             "l": getattr(row, "low", None) if not isinstance(row, dict) else row.get("low"),
             "c": getattr(row, "close", None) if not isinstance(row, dict) else row.get("close"),
             "v": getattr(row, "volume", None) if not isinstance(row, dict) else row.get("volume"),
             }
            for row in rows
        ]
    return out


# ── Registration ─────────────────────────────────────────────────────────────

def register_advanced_tools(registry: Any) -> list[str]:
    from .tools import _STRATEGY_INPUT  # reuse the shared strategy input schema

    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 60_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
        ))

    _backtest_schema = {"type": "object", "properties": {
        "strategyId": {"type": "string"}, "version": {"type": "string"},
        "symbols": {"type": "array", "items": {"type": "string"}},
        "start": {"type": "string"}, "end": {"type": "string"},
        "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
        "randomSeed": {"type": "integer"}, "save": {"type": "boolean"}},
        "required": ["strategyId"]}

    _def("run_event_driven_backtest",
         "Run a strategy through the authoritative chronological event engine "
         "(order lifecycle, next-bar fills, protective legs, portfolio accounting, costs) "
         "over real historical data. Persists an experiment.",
         run_event_driven_backtest_tool, _backtest_schema, 120_000, long_running=True)
    _def("run_vectorized_backtest",
         "Run a strategy through the vectorized research engine for the representable subset "
         "(causal signals, no protective legs, single timeframe/symbol). Unsupported strategies "
         "are refused with VECTOR_UNSUPPORTED — never silently approximated.",
         run_vectorized_backtest_tool, _backtest_schema, 120_000, long_running=True)

    _orders = {"type": "array", "items": {"type": "object", "properties": {
        "symbol": {"type": "string"}, "side": {"type": "string", "enum": ["buy", "sell"]},
        "quantity": {"type": "number"}, "price": {"type": "number"},
        "open": {"type": "number"}, "high": {"type": "number"}, "low": {"type": "number"},
        "close": {"type": "number"}, "volume": {"type": "number"},
        "atr": {"type": "number"}, "avgVolume": {"type": "number"},
        "barSpread": {"type": "number"}},
        "required": ["side", "quantity", "price"]}}
    _cost_schema = {"type": "object", "properties": {
        "orders": _orders, "execution": {"type": "object"}, "seed": {"type": "integer"}},
        "required": ["orders"]}
    _def("simulate_transaction_costs",
         "Compute per-order commission under a declared commission model (fixed/percentage/"
         "per_share/per_contract/tiered), with an auditable breakdown and the model used.",
         _cost_handler("transaction"), _cost_schema)
    _def("simulate_slippage",
         "Compute per-order slippage under a declared slippage model (fixed/percentage/"
         "volatility/volume/randomized); missing model inputs are reported, never faked.",
         _cost_handler("slippage"), _cost_schema)
    _def("simulate_spread",
         "Compute per-order bid/ask spread cost under a declared spread model (fixed/percentage/"
         "bps/historical). Historical spread with no quote data is reported, not assumed away.",
         _cost_handler("spread"), _cost_schema)
    _def("simulate_market_impact",
         "Compute per-order market impact under the linear participation model; missing volume "
         "inputs are reported so an uncalibrated estimate is never presented as real impact.",
         _cost_handler("impact"), _cost_schema)

    _def("run_out_of_sample_test",
         "Run a frozen strategy on a chronological out-of-sample slice (the tail), running the "
         "in-sample slice separately, verifying the slices do not overlap and warning if the OOS "
         "window was used by an earlier optimization. Persists the OOS result.",
         run_out_of_sample_test, {"type": "object", "properties": {
             **_backtest_schema["properties"],
             "oosFraction": {"type": "number"},
             "oosStartIndex": {"type": "integer"}},
             "required": ["strategyId"]}, 120_000, long_running=True)

    _def("run_bootstrap_test",
         "Percentile bootstrap confidence interval for a return-series statistic (mean/total/std/"
         "sharpe) using IID, block or stationary resampling. Reproducible via seed; method "
         "assumptions are surfaced.",
         run_bootstrap_test, {"type": "object", "properties": {
             "experimentId": {"type": "string"},
             "returns": {"type": "array", "items": {"type": "number"}},
             "method": {"type": "string", "enum": ["iid", "block", "stationary"]},
             "statistic": {"type": "string", "enum": ["mean", "total", "std", "sharpe"]},
             "iterations": {"type": "integer"}, "seed": {"type": "integer"},
             "confidence": {"type": "number"}, "blockSize": {"type": "integer"},
             "interval": {"type": "string"}}}, 120_000, long_running=True)

    _def("compare_backtests",
         "Compare completed backtests on a fixed metric set and report comparability cautions "
         "(differing ranges/instruments/capital, frictionless runs) so a fair comparison is never "
         "implied when assumptions differ.",
         compare_backtests, {"type": "object", "properties": {
             "experimentIds": {"type": "array", "items": {"type": "string"}}},
             "required": ["experimentIds"]})

    _def("price_option",
         "Theoretical price and Greeks (delta/gamma/theta/vega/rho) for a European option via "
         "the market layer's Black-Scholes model. States its assumptions; unavailable inputs "
         "are reported, never fabricated.",
         price_option_tool, {"type": "object", "properties": {
             "type": {"type": "string", "enum": ["call", "put"]},
             "spot": {"type": "number"}, "strike": {"type": "number"},
             "timeToExpiry": {"type": "number", "description": "years to expiry"},
             "iv": {"type": "number"}, "riskFree": {"type": "number"},
             "dividendYield": {"type": "number"}},
             "required": ["type", "spot", "strike", "timeToExpiry", "iv"]})
    _def("implied_volatility",
         "Solve implied volatility from an option's market price by inverting Black-Scholes "
         "(bisection). Refuses prices outside no-arbitrage bounds.",
         implied_volatility_tool, {"type": "object", "properties": {
             "marketPrice": {"type": "number"}, "type": {"type": "string", "enum": ["call", "put"]},
             "spot": {"type": "number"}, "strike": {"type": "number"},
             "timeToExpiry": {"type": "number"}, "riskFree": {"type": "number"},
             "dividendYield": {"type": "number"}},
             "required": ["marketPrice", "type", "spot", "strike", "timeToExpiry"]})
    _def("analyze_option_strategy",
         "Multi-leg option strategy analytics: expiry payoff curve, net premium, break-evens, "
         "max profit/loss (reported null when unbounded) and net Greeks. No early exercise.",
         analyze_option_strategy_tool, {"type": "object", "properties": {
             "legs": {"type": "array", "items": {"type": "object", "properties": {
                 "type": {"type": "string", "enum": ["call", "put"]}, "strike": {"type": "number"},
                 "quantity": {"type": "number", "description": "+ long / - short"},
                 "premium": {"type": "number"}, "multiplier": {"type": "number"},
                 "iv": {"type": "number"}}, "required": ["type", "strike", "quantity", "premium"]}},
             "spotMin": {"type": "number"}, "spotMax": {"type": "number"},
             "points": {"type": "integer"}, "valuationSpot": {"type": "number"},
             "timeToExpiry": {"type": "number"}, "iv": {"type": "number"},
             "riskFree": {"type": "number"}},
             "required": ["legs", "spotMin", "spotMax"]})
    _def("build_continuous_contract",
         "Build a continuous futures series from ordered contracts + a roll schedule, with "
         "difference/ratio back-adjustment (or none). Records every roll; the newest contract "
         "is unadjusted. The result is an explicit backtest PROXY.",
         build_continuous_contract_tool, {"type": "object", "properties": {
             "contracts": {"type": "array", "items": {"type": "object"}},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "rollDates": {"type": "array", "items": {"type": "string"}},
             "adjustment": {"type": "string", "enum": ["none", "difference", "ratio"]},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["rollDates"]})

    _def("run_multiple_testing_diagnostics",
         "Deflated Sharpe Ratio (Bailey & López de Prado) and Probability of Backtest "
         "Overfitting (CSCV) to test whether a selected result survives the number of trials "
         "tried. Runs a real bounded parameter sweep from `paramSpace`, or accepts an explicit "
         "return series / trial Sharpes / returns matrix. Reports assumptions; never applies a "
         "test whose inputs are missing.",
         run_multiple_testing_diagnostics, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "paramSpace": {"type": "object"}, "maxEvaluations": {"type": "integer"},
             "returns": {"type": "array", "items": {"type": "number"}},
             "trialSharpes": {"type": "array", "items": {"type": "number"}},
             "returnsMatrix": {"type": "array", "items": {"type": "array",
                                                          "items": {"type": "number"}}},
             "srVariance": {"type": "number"}, "trialCount": {"type": "integer"},
             "nSplits": {"type": "integer"}, "seed": {"type": "integer"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"}},
             "required": []}, 180_000, long_running=True)

    _def("run_regime_monte_carlo",
         "Resample a strategy's trade sequence in blocks of consecutive trades that "
         "occurred in the same market regime (trend x volatility, classified causally "
         "from the same bars), so the clustering of good and bad conditions survives "
         "the resample. Reports the regime attribution of realised P&L and the "
         "per-regime contribution across paths.",
         run_regime_monte_carlo, {"type": "object", "properties": {
             **_backtest_schema["properties"],
             "regimeMix": {"type": "string", "enum": ["resample", "preserve"]},
             "regimeBlockLength": {"type": "number"},
             "regimeConfig": {"type": "object"}},
             "required": ["strategyId"]}, 180_000, long_running=True)

    _def("grade_strategy_edge",
         "Grade the evidence behind a strategy's edge from A to F across edge, "
         "robustness, risk and sample size, and name the overfit tells (a "
         "suspiciously smooth equity curve, P&L concentrated in a few trades, "
         "expectancy not positive, a sample too small to tell from luck). Reads a "
         "stored experiment or runs the backtest; optionally folds in a "
         "regime-block Monte-Carlo result.",
         grade_strategy_edge, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "experimentId": {"type": "string"},
             "monteCarloExperimentId": {"type": "string"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
             "randomSeed": {"type": "integer"}},
             "required": []}, 180_000, long_running=True)

    _def("run_prop_firm_simulation",
         "Evaluate a closed-trade log against a prop firm's REAL evaluation rules "
         "(profit target, maximum loss, daily loss limit, consistency rule, access "
         "period, payout split), then resample the trading days to estimate the "
         "pass probability, the days-to-pass and the net expected value. Reports "
         "the rule set's source and date; firm rules change, so they must be "
         "confirmed with the firm. Intraday equity is not modelled and says so.",
         run_prop_firm_simulation, {"type": "object", "properties": {
             "firm": {"type": "string",
                      "description": "topstep | apex_eod | ftmo_pro | tpt_pro"},
             "size": {"type": "string", "description": "the account size id"},
             "trades": {"type": "array", "items": {"type": "object"}},
             "experimentId": {"type": "string"},
             "simulations": {"type": "integer"}, "seed": {"type": "integer"},
             "resample": {"type": "string", "enum": ["block", "iid"]},
             "blockLength": {"type": "number"},
             "feePerAttempt": {"type": "number"},
             "resetFee": {"type": "number"},
             "simulateFunded": {"type": "boolean"}},
             "required": ["firm", "size"]}, 180_000, long_running=True)

    _def("list_prop_firm_rules",
         "List the prop-firm rule sets the engine knows, with every account size, "
         "the source each number came from and the date it was read. Use it "
         "before running a prop-firm simulation.",
         list_prop_firm_rules, {"type": "object", "properties": {}, "required": []})

    _def("analyse_trade_log",
         "Read a closed-trade log against the conditions in which each entry "
         "happened: every entry is placed on the regime of its entry bar (the same "
         "causal trend x volatility classifier the Edge Report uses), the P&L is "
         "attributed per regime, and the concentration of the profit is measured. "
         "Takes the Journal's own trades when no log is passed.",
         analyse_trade_log, {"type": "object", "properties": {
             "trades": {"type": "array", "items": {"type": "object"},
                        "description": "the closed trades; omit to use the Journal"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"},
             "start": {"type": "string"}, "end": {"type": "string"}},
             "required": []}, 180_000, long_running=True)

    _def("generate_edge_report",
         "Build the Edge Report for a stored backtest: the A-F grade, the four "
         "axes behind it, the overfit tells, the measured numbers, and the chart "
         "specs for the equity curve, the drawdown, the Monte-Carlo percentiles, "
         "the return distribution and the P&L by market regime. The report is a "
         "document, recorded in the Artifact Center; the figures are computed, "
         "never evidence.",
         generate_edge_report, {"type": "object", "properties": {
             "experimentId": {"type": "string"},
             "monteCarloExperimentId": {"type": "string"},
             "renderCharts": {"type": "boolean"}},
             "required": ["experimentId"]}, 180_000, long_running=True)

    return list(ADVANCED_TOOLS)


ADVANCED_TOOLS: tuple[str, ...] = (
    "run_event_driven_backtest",
    "run_vectorized_backtest",
    "simulate_transaction_costs",
    "simulate_slippage",
    "simulate_spread",
    "simulate_market_impact",
    "run_out_of_sample_test",
    "run_bootstrap_test",
    "compare_backtests",
    "run_multiple_testing_diagnostics",
    "run_regime_monte_carlo",
    "grade_strategy_edge",
    "run_prop_firm_simulation",
    "list_prop_firm_rules",
    "generate_edge_report",
    "price_option",
    "implied_volatility",
    "analyze_option_strategy",
    "build_continuous_contract",
)


__all__ = ["ADVANCED_TOOLS", "register_advanced_tools"]
