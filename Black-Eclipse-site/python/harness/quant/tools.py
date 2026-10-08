"""Agent-facing Quant Engine tools.

These expose the deterministic engine to the harness. The agent authors/edits a
*strategy specification* and calls a tool; the engine does the math. Every tool
returns a concise text summary plus a structured `data` payload (the front door
reads `data`; the model reads `text`). Errors are structured, never fabricated.

Tools registered here (Phase 1–2):
    create_strategy, load_strategy, update_strategy, validate_strategy,
    clone_strategy, version_strategy, list_strategies, archive_strategy,
    run_backtest, run_portfolio_backtest, calculate_metrics,
    inspect_trades, inspect_positions, plot_equity_curve, plot_drawdown,
    compare_experiments, list_experiments, export_backtest, quant_capabilities
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from ..market.errors import MarketError
from . import StrategySpec, parse_strategy, validate_strategy
from .datasets import dataset_from_strategy, resolve_dataset
from .engine import BacktestConfig, BacktestResult, run_backtest, run_portfolio_backtest
from .errors import QuantError, StoreUnavailable
from .montecarlo import MonteCarloConfig, MonteCarloEngine
from .optimize import OptimizationConfig, OptimizationEngine
from .params import ParamSpace
from .research import ResearchResult
from .robustness import (
    RobustnessConfig,
    RobustnessEngine,
    SensitivityConfig,
    SensitivityEngine,
)
from .strategy import bump_version, errors_only
from .walkforward import WalkForwardConfig, WalkForwardEngine

_CAPABILITY = {
    "backtest": "available", "portfolioBacktest": "available",
    "strategies": "available", "experiments": "available",
    "indicators": "available", "metrics": "available",
    "walkForward": "available", "monteCarlo": "available",
    "optimization": "available", "robustness": "available", "sensitivity": "available",
    "options": "unsupported", "futures": "partial",
}

_STRATEGY_SUMMARY_KEYS = (
    "total_return", "cagr", "max_drawdown", "sharpe", "sortino", "calmar",
    "volatility", "win_rate", "profit_factor", "trade_count", "expectancy",
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _store(ctx: Any):
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise StoreUnavailable(
            "the quant store is not configured; strategy/experiment persistence "
            "is unavailable in this runtime"
        )
    return store


def _gateway(ctx: Any):
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}", {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}", {"status": "ERROR", "error": {"message": str(exc)}})


def _flag(args: dict[str, Any], key: str, default: bool) -> bool:
    """A boolean tool arg with a real default (None must not mean False)."""
    value = args.get(key)
    return default if value is None else bool(value)


def _spec_from_args(args: dict[str, Any]) -> StrategySpec:
    if args.get("strategy") is not None:
        return parse_strategy(args["strategy"])
    if args.get("strategyYaml"):
        return parse_strategy(args["strategyYaml"])
    raise QuantError("a `strategy` object or `strategyYaml` string is required")


def _result_data(result: BacktestResult, exp_id: Optional[str]) -> dict[str, Any]:
    return {
        "status": result.status,
        "experimentId": exp_id,
        "metadata": result.metadata,
        "configuration": result.configuration,
        "metrics": result.metrics,
        "observability": result.observability,
        "warnings": result.warnings,
        "capability": result.capability,
        "tradeCount": len(result.trades),
    }


def _render_result(result: BacktestResult, exp_id: Optional[str]) -> str:
    m = result.metrics
    lines = [
        f"Backtest complete — strategy {result.metadata.get('strategyId')} "
        f"v{result.metadata.get('strategyVersion')} on {', '.join(result.metadata.get('symbols', []))}",
        f"Experiment: {exp_id or '(not persisted)'}",
        f"Bars {result.observability.get('barsProcessed')} | orders {result.observability.get('ordersCreated')} "
        f"| fills {result.observability.get('fills')} | trades {result.observability.get('trades')}",
    ]
    def fmt(name: str) -> str:
        v = m.get(name)
        return "n/a" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))
    lines.append(
        "Return {ret}% | CAGR {cagr}% | MaxDD {dd}% | Sharpe {sh} | Sortino {so}".format(
            ret=fmt("total_return"), cagr=fmt("cagr"), dd=fmt("max_drawdown"),
            sh=fmt("sharpe"), so=fmt("sortino"),
        )
    )
    lines.append(
        "Trades {n} | Win {wr}% | PF {pf} | Expectancy {ex}".format(
            n=fmt("trade_count"), wr=fmt("win_rate"), pf=fmt("profit_factor"), ex=fmt("expectancy"),
        )
    )
    if result.warnings:
        lines.append(f"Warnings: {len(result.warnings)}")
        for w in result.warnings[:5]:
            lines.append(f"  - {w['code']}: {w['message']}")
    return "\n".join(lines)


async def _persist(result: BacktestResult, strategy: StrategySpec, store, kind: str) -> Optional[str]:
    try:
        return store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version, kind=kind
        )
    except Exception:  # noqa: BLE001 - a persistence failure must not lose the result
        return None


async def _run_one(strategy: StrategySpec, gateway, args: dict[str, Any]) -> BacktestResult:
    dataset = await dataset_from_strategy(
        gateway, strategy, start=args.get("start"), end=args.get("end"),
        symbols=args.get("symbols"),
    )
    cfg = BacktestConfig(
        initial_capital=float(args.get("initialCapital") or 100_000.0),
        start=args.get("start"), end=args.get("end"),
        risk_free_rate=float(args.get("riskFreeRate") or 0.0),
        random_seed=int(args.get("randomSeed") or 42),
    )
    return run_backtest(strategy, dataset, cfg, symbols=args.get("symbols"))


# ── Handlers ─────────────────────────────────────────────────────────────────

async def create_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        spec = _spec_from_args(args)
        issues = validate_strategy(spec)
        errs = errors_only(issues)
        if errs:
            return (
                "Strategy is invalid:\n" + "\n".join(f"  - {i.path}: {i.message}" for i in errs),
                {"status": "INVALID", "issues": [i.to_dict() for i in issues]},
            )
        store = _store(ctx)
        record = store.save_strategy(spec)
        return (
            f"Strategy {spec.id!r} v{spec.version} saved.",
            {"status": "OK", "strategy": record, "issues": [i.to_dict() for i in issues]},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def load_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        record = store.get_strategy(str(args.get("strategyId")), args.get("version"))
        return (f"Loaded strategy {record['id']} v{record['version']}.", {"status": "OK", **record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def update_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        current = store.get_strategy(str(args.get("strategyId")), args.get("version"))
        merged = dict(current["spec"])
        updates = args.get("updates") or {}
        merged.update(updates)
        if _flag(args, "bumpVersion", True):
            part = args.get("bumpPart") or "patch"
            merged["version"] = bump_version(current["version"], part)
        spec = StrategySpec.model_validate(merged)
        issues = errors_only(validate_strategy(spec))
        if issues:
            return (
                "Updated strategy is invalid:\n" + "\n".join(f"  - {i.path}: {i.message}" for i in issues),
                {"status": "INVALID", "issues": [i.to_dict() for i in issues]},
            )
        record = store.save_strategy(spec)
        return (
            f"Strategy {spec.id!r} updated to v{spec.version}.",
            {"status": "OK", "strategy": record},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def validate_strategy_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        spec = _spec_from_args(args)
        issues = validate_strategy(spec)
        errs = errors_only(issues)
        if errs:
            return (
                f"Invalid — {len(errs)} error(s):\n"
                + "\n".join(f"  - {i.path}: {i.message}" for i in errs),
                {"status": "INVALID", "issues": [i.to_dict() for i in issues]},
            )
        summary = f"Valid. {len(issues)} warning(s)." if issues else "Valid."
        return (summary, {"status": "OK", "issues": [i.to_dict() for i in issues]})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def clone_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        current = store.get_strategy(str(args.get("strategyId")), args.get("version"))
        spec = dict(current["spec"])
        new_id = str(args.get("newId") or f"{spec['id']}_copy")
        spec["id"] = new_id
        spec["name"] = str(args.get("newName") or f"{current['name']} (copy)")
        spec["version"] = "1.0.0"
        new_spec = StrategySpec.model_validate(spec)
        errs = errors_only(validate_strategy(new_spec))
        if errs:
            return ("Clone target is invalid.", {"status": "INVALID",
                                                 "issues": [i.to_dict() for i in errs]})
        record = store.save_strategy(new_spec)
        return (f"Cloned {current['id']} → {new_id} v1.0.0.", {"status": "OK", "strategy": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def version_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        current = store.get_strategy(str(args.get("strategyId")), args.get("version"))
        spec = dict(current["spec"])
        spec["version"] = bump_version(current["version"], args.get("part") or "patch")
        new_spec = StrategySpec.model_validate(spec)
        record = store.save_strategy(new_spec)
        return (f"Versioned {current['id']} → v{spec['version']}.", {"status": "OK", "strategy": record})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_strategies(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        items = store.list_strategies(include_archived=bool(args.get("includeArchived")))
        text = "\n".join(f"  {s['id']} v{s['latestVersion']} — {s['name']}" for s in items) or "  (none)"
        return (f"{len(items)} strategy(ies):\n{text}", {"status": "OK", "strategies": items})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def archive_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        archived = _flag(args, "archived", True)
        store.archive_strategy(str(args.get("strategyId")), archived)
        return (f"Strategy {args.get('strategyId')} archived={archived}.", {"status": "OK"})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_backtest_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        spec = store.get_strategy(str(args.get("strategyId")), args.get("version"))["spec"]
        strategy = StrategySpec.model_validate(spec)
        result = await _run_one(strategy, _gateway(ctx), args)
        exp_id = await _persist(result, strategy, store, "backtest") if _flag(args, "save", True) else None
        return (_render_result(result, exp_id), _result_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_portfolio_backtest_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        ids = args.get("strategyIds") or []
        if not ids:
            return ("ERROR — at least one strategyId is required.",
                    {"status": "ERROR", "error": {"message": "strategyIds required"}})
        strategies = [StrategySpec.model_validate(store.get_strategy(sid)["spec"]) for sid in ids]
        start = args.get("start")
        end = args.get("end")
        symbols = sorted({s for strat in strategies for s in strat.universe.symbols})
        if len({strat.timeframes.primary for strat in strategies}) != 1:
            return ("ERROR — all strategies in a portfolio must share one primary timeframe.",
                    {"status": "ERROR", "error": {"message": "primary timeframe mismatch"}})
        primary = strategies[0].timeframes.primary
        confirmation = sorted({tf for strat in strategies for tf in strat.timeframes.confirmation})
        dataset = await resolve_dataset(
            _gateway(ctx), symbols, primary=primary, confirmation=confirmation,
            start=start, end=end,
        )
        cfg = BacktestConfig(
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            start=start, end=end, risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            random_seed=int(args.get("randomSeed") or 42),
        )
        result = run_portfolio_backtest(strategies, dataset, cfg)
        exp_id = None
        if _flag(args, "save", True):
            exp_id = store.save_experiment(
                result, strategy_id=None,
                strategy_version=",".join(s.version for s in strategies), kind="portfolio_backtest",
            )
        return (_render_result(result, exp_id), _result_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def calculate_metrics(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        exp = store.get_experiment(str(args.get("experimentId")), with_artifact=False)
        metrics = exp["metrics"]
        rows = [f"  {k}: {metrics.get(k)}" for k in _STRATEGY_SUMMARY_KEYS]
        return (f"Metrics for {exp['id']}:\n" + "\n".join(rows),
                {"status": "OK", "experimentId": exp["id"], "metrics": metrics,
                 "definitions": store.read_artifact(exp["id"]).get("metricDefinitions", {})})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def inspect_trades(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        artifact = store.read_artifact(str(args.get("experimentId")))
        trades = artifact.get("trades", [])
        symbol = args.get("symbol")
        if symbol:
            trades = [t for t in trades if t.get("symbol") == symbol]
        limit = int(args.get("limit") or 50)
        shown = trades[:limit]
        text = "\n".join(
            f"  {t['entryTs']} {t['symbol']} {t['direction']} qty {t['quantity']:.4f} "
            f"pnl {t['netPnl']:.2f} ({t['pnlPct']:.2f}%) {t.get('exitReason','')}"
            for t in shown
        ) or "  (no trades)"
        return (f"{len(trades)} trade(s){f' for {symbol}' if symbol else ''}:\n{text}",
                {"status": "OK", "trades": shown, "total": len(trades)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def inspect_positions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        artifact = store.read_artifact(str(args.get("experimentId")))
        positions = artifact.get("positions", {})
        return (f"Positions at end of run: {json.dumps(positions)[:1500]}",
                {"status": "OK", "positions": positions})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def plot_equity_curve(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    return await _plot(args, ctx, "equityCurve", "equity")


async def plot_drawdown(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    return await _plot(args, ctx, "drawdownCurve", "drawdown")


def _downsample(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    """Uniformly thin a series so a tool result cannot carry an unbounded curve.

    Keeps the first and last points (so start/end are exact) and samples evenly
    in between. The full series remains in the stored artifact.
    """
    n = len(points)
    if n <= max_points or max_points < 3:
        return points
    step = (n - 1) / (max_points - 1)
    indices = sorted({int(round(i * step)) for i in range(max_points)})
    return [points[i] for i in indices]


async def _plot(args: dict[str, Any], ctx: Any, series_key: str, value_key: str) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        artifact = store.read_artifact(str(args.get("experimentId")))
        full = artifact.get(series_key, [])
        max_points = int(args.get("maxPoints") or 2000)
        points = _downsample(full, max_points)
        suffix = "" if len(points) == len(full) else f" (downsampled from {len(full)})"
        return (
            f"{value_key} series: {len(points)} point(s){suffix} for {args.get('experimentId')}.",
            {"status": "OK", "seriesKey": series_key, "valueKey": value_key,
             "totalPoints": len(full), "points": points},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def compare_experiments(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        ids = args.get("experimentIds") or []
        comparison = store.compare_experiments(list(ids))
        lines = [f"  {e['experimentId']}: ret={e['metrics'].get('total_return')}, "
                 f"sharpe={e['metrics'].get('sharpe')}, maxDD={e['metrics'].get('max_drawdown')}"
                 for e in comparison["experiments"]]
        return (f"Compared {len(comparison['experiments'])} experiment(s):\n" + "\n".join(lines),
                {"status": "OK", **comparison})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_experiments(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        items = store.list_experiments(strategy_id=args.get("strategyId"),
                                       limit=int(args.get("limit") or 25))
        text = "\n".join(f"  {e['id']} {e['strategyId']} v{e['strategyVersion']} "
                         f"ret={e['metrics'].get('total_return')}" for e in items) or "  (none)"
        return (f"{len(items)} experiment(s):\n{text}", {"status": "OK", "experiments": items})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def export_backtest(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        exp_id = str(args.get("experimentId"))
        artifact = store.read_artifact(exp_id)
        export_dir = os.path.join(os.path.dirname(store._root), "exports", exp_id)
        os.makedirs(export_dir, exist_ok=True)
        written: list[str] = []
        # Trades CSV.
        trades = artifact.get("trades", [])
        if trades:
            import csv
            path = os.path.join(export_dir, "trades.csv")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(trades[0].keys()))
                writer.writeheader()
                writer.writerows(trades)
            written.append(path)
        # Equity CSV.
        equity = artifact.get("equityCurve", [])
        if equity:
            import csv
            path = os.path.join(export_dir, "equity.csv")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["index", "ts", "equity"])
                writer.writeheader()
                writer.writerows({"index": e["index"], "ts": e.get("ts"), "equity": e["equity"]}
                                 for e in equity)
            written.append(path)
        # Full JSON.
        path = os.path.join(export_dir, "result.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(artifact, fh)
        written.append(path)
        return (f"Exported experiment {exp_id} to {export_dir} ({len(written)} files).",
                {"status": "OK", "experimentId": exp_id, "files": written, "directory": export_dir})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_capabilities(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    text = "\n".join(f"  {k}: {v}" for k, v in _CAPABILITY.items())
    return (f"Quant engine capabilities:\n{text}", {"status": "OK", "capability": _CAPABILITY})


# ── Research handlers ────────────────────────────────────────────────────────

def _research_data(result: ResearchResult, exp_id: Optional[str]) -> dict[str, Any]:
    data = {
        "status": result.status, "kind": result.kind, "experimentId": exp_id,
        "metrics": result.metrics, "warnings": result.warnings,
        "observability": result.observability, "configuration": result.configuration,
    }
    _SUMMARY_BY_KIND = {
        "optimization": ("best", "leaderboard", "stability", "pareto"),
        "walk_forward": ("windows", "inSampleAggregate", "outOfSampleAggregate", "divergence"),
        "monte_carlo": ("returnPercentiles", "probabilityOfLoss", "probabilityOfRuin",
                        "expectedDrawdown", "worstDrawdown"),
        "sensitivity": ("parameters",),
        "robustness": ("verdict", "conclusions", "base", "costSensitivity", "concentration", "regime"),
    }
    for key in _SUMMARY_BY_KIND.get(result.kind, ()):
        if key in result.payload:
            data[key] = result.payload[key]
    return data


def _render_research(result: ResearchResult, exp_id: Optional[str]) -> str:
    lines = [f"{result.kind} — {result.status}"
             + (f" (experiment {exp_id})" if exp_id else " (not persisted)")]
    if result.kind == "optimization":
        best = result.payload.get("best")
        if best:
            lines.append(f"best {result.payload.get('objective')} = {best['score']} params={best['params']}")
            lines.append(f"trials={result.observability.get('trials')} "
                         f"trades={best['metrics'].get('trade_count')}")
    elif result.kind == "walk_forward":
        div = result.payload.get("divergence", {})
        lines.append(f"windows={result.observability.get('windows')} "
                     f"IS={div.get('inSample')} OOS={div.get('outOfSample')}")
    elif result.kind == "monte_carlo":
        p = result.payload.get("returnPercentiles", {})
        lines.append(f"return p5={p.get('p5'):.2f}% p50={p.get('p50'):.2f}% p95={p.get('p95'):.2f}% "
                     f"pLoss={result.payload.get('probabilityOfLoss'):.1f}% "
                     f"pRuin={result.payload.get('probabilityOfRuin'):.1f}%")
    elif result.kind == "robustness":
        lines.append(f"verdict={result.payload.get('verdict')}")
        for c in result.payload.get("conclusions", []):
            lines.append(f"  - {c}")
    elif result.kind == "sensitivity":
        collapses = [p for p, s in result.payload.get("parameters", {}).items() if s.get("collapse")]
        lines.append(f"parameters={len(result.payload.get('parameters', {}))} "
                     f"collapse={collapses}")
    for w in result.warnings[:4]:
        lines.append(f"  ! {w['code']}: {w['message']}")
    return "\n".join(lines)


async def _load_strategy(store, args: dict[str, Any]) -> StrategySpec:
    record = store.get_strategy(str(args.get("strategyId")), args.get("version"))
    return StrategySpec.model_validate(record["spec"])


async def optimize_parameters(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        strategy = await _load_strategy(store, args)
        space = ParamSpace.from_dict(args.get("paramSpace") or {})
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = OptimizationConfig(
            method=str(args.get("method") or "random"),
            objective=str(args.get("objective") or "sharpe"),
            objectives=list(args.get("objectives") or []),
            max_evaluations=int(args.get("maxEvaluations") or 60),
            seed=int(args.get("seed") or 42),
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            start=args.get("start"), end=args.get("end"), symbols=args.get("symbols"),
        )
        result = OptimizationEngine(strategy, dataset, space, config).run()
        exp_id = store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version,
            kind="optimization") if _flag(args, "save", True) else None
        return (_render_research(result, exp_id), _research_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_walk_forward(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        strategy = await _load_strategy(store, args)
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = WalkForwardConfig(
            train_bars=int(args.get("trainBars") or 250),
            test_bars=int(args.get("testBars") or 60),
            step_bars=args.get("stepBars"),
            method=str(args.get("method") or "random"),
            objective=str(args.get("objective") or "sharpe"),
            param_space=args.get("paramSpace") or {},
            max_evaluations=int(args.get("maxEvaluations") or 40),
            seed=int(args.get("seed") or 42),
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            anchored=bool(args.get("anchored", False)),
        )
        result = WalkForwardEngine(strategy, dataset, config).run()
        exp_id = store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version,
            kind="walk_forward") if _flag(args, "save", True) else None
        return (_render_research(result, exp_id), _research_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_monte_carlo(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        strategy = await _load_strategy(store, args)
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = MonteCarloConfig(
            method=str(args.get("method") or "trade_reshuffle"),
            simulations=int(args.get("simulations") or 1000),
            seed=int(args.get("seed") or 42),
            ruin_threshold=float(args.get("ruinThreshold") or 0.5),
            perturbation_pct=float(args.get("perturbationPct") or 0.10),
            perturbation=args.get("perturbation") or {},
            execution_perturbation=args.get("executionPerturbation") or {},
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
        )
        result = MonteCarloEngine(strategy, dataset, config).run()
        exp_id = store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version,
            kind="monte_carlo") if _flag(args, "save", True) else None
        return (_render_research(result, exp_id), _research_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_sensitivity_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        strategy = await _load_strategy(store, args)
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = SensitivityConfig(
            param_ranges=args.get("paramRanges") or {},
            objective=str(args.get("objective") or "sharpe"),
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            seed=int(args.get("seed") or 42),
        )
        result = SensitivityEngine(strategy, dataset, config).run()
        exp_id = store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version,
            kind="sensitivity") if _flag(args, "save", True) else None
        return (_render_research(result, exp_id), _research_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def run_robustness_analysis(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        strategy = await _load_strategy(store, args)
        dataset = await dataset_from_strategy(
            _gateway(ctx), strategy, start=args.get("start"), end=args.get("end"),
            symbols=args.get("symbols"))
        config = RobustnessConfig(
            param_ranges=args.get("paramRanges") or {},
            objective=str(args.get("objective") or "sharpe"),
            cost_multipliers=list(args.get("costMultipliers") or [1.0, 2.0, 5.0]),
            min_trades=int(args.get("minTrades") or 30),
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            seed=int(args.get("seed") or 42),
        )
        result = RobustnessEngine(strategy, dataset, config).run()
        exp_id = store.save_experiment(
            result, strategy_id=strategy.id, strategy_version=strategy.version,
            kind="robustness") if _flag(args, "save", True) else None
        return (_render_research(result, exp_id), _research_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Registration ─────────────────────────────────────────────────────────────

_STRATEGY_INPUT = {
    "type": "object",
    "properties": {
        "strategy": {"type": "object", "description": "Structured strategy spec."},
        "strategyYaml": {"type": "string", "description": "Strategy spec as YAML/JSON text."},
    },
}


def register_quant_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any], timeout: int = 30_000,
             long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
        ))

    _def("create_strategy",
         "Create (and persist) a versioned trading strategy from a structured spec. "
         "Validates the spec and returns every issue. Never runs code.",
         create_strategy, {
             "type": "object",
             "properties": {**_STRATEGY_INPUT["properties"],
                            "description": {"type": "string"}},
         })
    _def("load_strategy",
         "Load a persisted strategy by id (optionally a specific version).",
         load_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"}},
             "required": ["strategyId"]})
    _def("update_strategy",
         "Patch a strategy (partial merge), bump its version (default patch) and re-save.",
         update_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "updates": {"type": "object"}, "bumpVersion": {"type": "boolean"},
             "bumpPart": {"type": "string", "enum": ["major", "minor", "patch"]}},
             "required": ["strategyId", "updates"]})
    _def("validate_strategy",
         "Validate a strategy spec; returns all structural + semantic issues.",
         validate_strategy_tool, _STRATEGY_INPUT, 15_000)
    _def("clone_strategy",
         "Clone a strategy under a new id/name at version 1.0.0.",
         clone_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "newId": {"type": "string"}, "newName": {"type": "string"}},
             "required": ["strategyId"]})
    _def("version_strategy",
         "Create a new version of an existing strategy (major/minor/patch).",
         version_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "part": {"type": "string", "enum": ["major", "minor", "patch"]}},
             "required": ["strategyId"]})
    _def("list_strategies",
         "List persisted strategies.",
         list_strategies, {"type": "object", "properties": {
             "includeArchived": {"type": "boolean"}}})
    _def("archive_strategy",
         "Archive (or unarchive) a strategy.",
         archive_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "archived": {"type": "boolean"}},
             "required": ["strategyId"]})
    _def("run_backtest",
         "Run a deterministic event-driven backtest for a persisted strategy over real "
         "historical data, apply commission/slippage/spread/latency, and persist an experiment.",
         run_backtest_tool, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
             "randomSeed": {"type": "integer"}, "save": {"type": "boolean"}},
             "required": ["strategyId"]}, 120_000, long_running=True)
    _def("run_portfolio_backtest",
         "Run several strategies over ONE shared portfolio (shared cash + risk).",
         run_portfolio_backtest_tool, {"type": "object", "properties": {
             "strategyIds": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
             "randomSeed": {"type": "integer"}, "save": {"type": "boolean"}},
             "required": ["strategyIds"]}, 120_000, long_running=True)
    _def("calculate_metrics",
         "Return the computed metric set (with definitions) for a stored experiment.",
         calculate_metrics, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("inspect_trades",
         "List the trades of a stored experiment (optionally filtered by symbol).",
         inspect_trades, {"type": "object", "properties": {
             "experimentId": {"type": "string"}, "symbol": {"type": "string"},
             "limit": {"type": "integer"}}, "required": ["experimentId"]})
    _def("inspect_positions",
         "Show the positions at the end of a stored experiment.",
         inspect_positions, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("plot_equity_curve",
         "Return the equity curve of a stored experiment as chart points.",
         plot_equity_curve, {"type": "object", "properties": {
             "experimentId": {"type": "string"},
             "maxPoints": {"type": "integer", "description": "Cap on returned points (default 2000)."}},
             "required": ["experimentId"]})
    _def("plot_drawdown",
         "Return the drawdown curve of a stored experiment as chart points.",
         plot_drawdown, {"type": "object", "properties": {
             "experimentId": {"type": "string"},
             "maxPoints": {"type": "integer", "description": "Cap on returned points (default 2000)."}},
             "required": ["experimentId"]})
    _def("compare_experiments",
         "Compare stored experiments on a fixed metric set.",
         compare_experiments, {"type": "object", "properties": {
             "experimentIds": {"type": "array", "items": {"type": "string"}}},
             "required": ["experimentIds"]})
    _def("list_experiments",
         "List stored experiments (optionally for one strategy).",
         list_experiments, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "limit": {"type": "integer"}}})
    _def("export_backtest",
         "Export a stored experiment to CSV/JSON files under the quant exports dir.",
         export_backtest, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("quant_capabilities",
         "Report which quant-engine capabilities are available/partial/unsupported.",
         quant_capabilities, {"type": "object", "properties": {}})

    _PARAM_SPACE = {"type": "object", "description":
                    "Map dotted strategy path → list of values or {start,stop,step|count}."}
    _def("optimize_parameters",
         "Optimize a strategy's parameters (grid/random/evolutionary/bayesian) on a metric "
         "objective (sharpe/sortino/calmar/return_drawdown/...), with parameter-stability and "
         "sample-size evidence. Persists the run as an experiment.",
         optimize_parameters, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "paramSpace": _PARAM_SPACE,
             "method": {"type": "string", "enum": ["grid", "random", "evolutionary", "bayesian"]},
             "objective": {"type": "string"},
             "objectives": {"type": "array", "items": {"type": "string"}},
             "maxEvaluations": {"type": "integer"}, "seed": {"type": "integer"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
             "save": {"type": "boolean"}}, "required": ["strategyId", "paramSpace"]},
         120_000, long_running=True)
    _def("run_walk_forward",
         "Walk-forward analysis: optimize on each training window (only), evaluate on the unseen "
         "test window, and report in-sample / out-of-sample / combined with IS→OOS divergence.",
         run_walk_forward, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "paramSpace": _PARAM_SPACE,
             "trainBars": {"type": "integer"}, "testBars": {"type": "integer"},
             "stepBars": {"type": "integer"},
             "method": {"type": "string", "enum": ["grid", "random", "evolutionary", "bayesian"]},
             "objective": {"type": "string"}, "maxEvaluations": {"type": "integer"},
             "seed": {"type": "integer"}, "anchored": {"type": "boolean"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyId", "paramSpace", "trainBars", "testBars"]},
         120_000, long_running=True)
    _def("run_monte_carlo",
         "Monte-Carlo analysis (trade reshuffle / return bootstrap / parameter perturbation / "
         "execution perturbation): percentiles, probability of loss/ruin, expected + worst "
         "drawdown. Reproducible via seed.",
         run_monte_carlo, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "method": {"type": "string", "enum": [
                 "trade_reshuffle", "return_bootstrap", "parameter_perturbation",
                 "execution_perturbation"]},
             "simulations": {"type": "integer"}, "seed": {"type": "integer"},
             "ruinThreshold": {"type": "number"}, "perturbationPct": {"type": "number"},
             "perturbation": {"type": "object"}, "executionPerturbation": {"type": "object"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyId"]}, 120_000, long_running=True)
    _def("run_sensitivity_analysis",
         "Sweep one parameter at a time and report the objective curve, best value, collapse and "
         "stability per parameter.",
         run_sensitivity_analysis, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "paramRanges": _PARAM_SPACE, "objective": {"type": "string"},
             "seed": {"type": "integer"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyId", "paramRanges"]}, 120_000, long_running=True)
    _def("run_robustness_analysis",
         "Combine sensitivity, cost sensitivity, trade concentration, sample size and regime "
         "dependence into a deterministic robustness verdict with plain-language conclusions.",
         run_robustness_analysis, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "paramRanges": _PARAM_SPACE, "objective": {"type": "string"},
             "costMultipliers": {"type": "array", "items": {"type": "number"}},
             "minTrades": {"type": "integer"}, "seed": {"type": "integer"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyId"]}, 120_000, long_running=True)

    return [
        "create_strategy", "load_strategy", "update_strategy", "validate_strategy",
        "clone_strategy", "version_strategy", "list_strategies", "archive_strategy",
        "run_backtest", "run_portfolio_backtest", "calculate_metrics", "inspect_trades",
        "inspect_positions", "plot_equity_curve", "plot_drawdown", "compare_experiments",
        "list_experiments", "export_backtest", "quant_capabilities",
        "optimize_parameters", "run_walk_forward", "run_monte_carlo",
        "run_sensitivity_analysis", "run_robustness_analysis",
    ]


__all__ = ["register_quant_tools", "_CAPABILITY"]
