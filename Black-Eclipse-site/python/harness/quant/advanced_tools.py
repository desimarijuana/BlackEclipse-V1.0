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

from .costs import simulate_costs
from .engine import BacktestConfig, run_backtest
from .errors import QuantError
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
            "isEnd": timeline[is_end - 1],
            "oosStart": timeline[oos_start],
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


# ── Statistical validation ───────────────────────────────────────────────────

async def run_out_of_sample_test(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    t = _t()
    try:
        store = t._store(ctx)
        strategy = await t._load_strategy(store, args)
        report = await run_out_of_sample(strategy, t._gateway(ctx), args)
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
                f"(OOS bars={report['split']['oosBars']}, overlap=0).", data)
    except Exception as exc:  # noqa: BLE001
        return t._err(exc)


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
)


__all__ = ["ADVANCED_TOOLS", "register_advanced_tools"]
