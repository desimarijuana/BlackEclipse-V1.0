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

import asyncio
import base64
import json
import os
import time
from typing import Any, Optional

from ..market.errors import MarketError
from . import StrategySpec, parse_strategy, validate_strategy
from .bundle import bundle_to_bytes, export_bundle, import_bundle, write_bundle
from .compiler import compile_graph
from .copilot_tools import COPILOT_TOOLS, register_copilot_tools
from .datasets import dataset_from_strategy, resolve_dataset
from .nodes import REGISTRY
from .ops_tools import OPS_TOOLS, register_strategy_ops_tools
from .pine_tools import PINE_TOOLS, register_pine_tools
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
from .sdk_runtime import run_strategy_source
from .strategy import bump_version, errors_only
from .strategy_schema import STRATEGY_SCHEMA
from .walkforward import WalkForwardConfig, WalkForwardEngine

_CAPABILITY = {
    "backtest": "available", "portfolioBacktest": "available",
    "strategies": "available", "experiments": "available",
    "indicators": "available", "metrics": "available",
    "walkForward": "available", "monteCarlo": "available",
    "optimization": "available", "robustness": "available", "sensitivity": "available",
    "graphCompiler": "available", "vectorizedBacktest": "available", "costDiagnostics": "available",
    "outOfSample": "available",
    "bootstrap": "available",
    "multipleTesting": "available",
    "pythonStrategies": "partial",
    # options: pricing/Greeks/implied-vol + multi-leg analytics are available;
    # historical options *backtesting* is not (needs dated chains). futures:
    # continuous-contract construction is available; backtesting trades the
    # continuous proxy, not deliverable contracts.
    "options": "partial", "futures": "partial",
    "optionAnalytics": "available", "continuousContracts": "available",
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


#: The wall clock one backtest may take (the CPU-bound part runs in a worker
#: thread, so the runtime's event loop is never blocked by it).
BACKTEST_TIMEOUT_S = 300


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
    # The backtest is CPU-BOUND and SYNCHRONOUS. Run it in a worker thread so
    # it cannot block the runtime's event loop (a long backtest used to stall
    # every other request), and bound it with a wall clock so a runaway is an
    # honest refusal rather than a hang.
    symbols = args.get("symbols")
    return await asyncio.wait_for(
        asyncio.to_thread(
            lambda: run_backtest(strategy, dataset, cfg, symbols=symbols)
        ),
        timeout=_backtest_timeout_s(),
    )


def _backtest_timeout_s() -> float:
    """The wall clock one backtest may take (overridable by the operator)."""
    raw = os.environ.get("HARNESS_QUANT_BACKTEST_TIMEOUT_S", "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return float(BACKTEST_TIMEOUT_S)


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


def _strategy_exports_root(store: Any) -> str:
    return os.path.join(os.path.dirname(store._root), "exports", "strategies")


def _bundle_source(args: dict[str, Any]) -> Any:
    if args.get("bundleBase64"):
        try:
            return base64.b64decode(str(args["bundleBase64"]))
        except (ValueError, TypeError) as exc:
            from .errors import StrategyBundleError

            raise StrategyBundleError("bundleBase64 is not valid base64") from exc
    if isinstance(args.get("bundle"), dict):
        return args["bundle"]
    raise ValueError("a `bundle` object or `bundleBase64` string is required")


def _graph_source(args: dict[str, Any]) -> Any:
    if isinstance(args.get("graph"), dict):
        return args["graph"]
    if args.get("graphJson"):
        return args["graphJson"]
    raise ValueError("a `graph` object or `graphJson` string is required")


def _compile_payload(result: Any) -> dict[str, Any]:
    return {
        "status": "OK" if result.ok else "INVALID",
        "ok": result.ok,
        "spec": result.spec.to_dict() if result.spec else None,
        "diagnostics": [d.to_dict() for d in result.diagnostics],
        "sourceMap": result.source_map,
        "ordering": result.ordering,
    }


def _series_rows(dataset: Any) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for symbol, series in dataset.series.items():
        rows[symbol] = [
            {
                "timestamp": series.timestamps[i], "open": float(series.open[i]),
                "high": float(series.high[i]), "low": float(series.low[i]),
                "close": float(series.close[i]), "volume": float(series.volume[i]),
            }
            for i in range(series.length)
        ]
    return rows


async def run_python_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Run a user Python `Strategy` (source) in the isolated SDK runtime."""
    try:
        store = _store(ctx)
        code = args.get("strategyCode")
        if not code or not str(code).strip():
            return ("ERROR — `strategyCode` (a Strategy subclass) is required.",
                    {"status": "ERROR", "error": {"code": "SDK_EMPTY_SOURCE",
                                                  "message": "strategyCode is required"}})
        symbols = [str(s).upper() for s in (args.get("symbols") or [])]
        if not symbols:
            return ("ERROR — `symbols` is required (the universe is code-defined).",
                    {"status": "ERROR", "error": {"code": "SDK_NO_SYMBOLS",
                                                  "message": "symbols required"}})
        interval = str(args.get("interval") or "1d")
        start, end = args.get("start"), args.get("end")
        dataset = await resolve_dataset(
            _gateway(ctx), symbols, primary=interval, start=start, end=end)
        rows = _series_rows(dataset)
        timeout_s = min(300.0, float(args.get("timeoutSeconds") or 60.0))
        result, err = await asyncio.to_thread(
            run_strategy_source,
            str(code), rows,
            symbols=symbols, interval=interval,
            initial_capital=float(args.get("initialCapital") or 100_000.0),
            risk_free_rate=float(args.get("riskFreeRate") or 0.0),
            random_seed=int(args.get("randomSeed") or 42),
            params=args.get("params") or {}, class_name=args.get("className"),
            strategy_id=args.get("strategyId"), timeout_s=timeout_s,
        )
        if err is not None:
            return (f"ERROR — {err.get('code')}: {err.get('message')}",
                    {"status": "ERROR", "error": err})
        assert result is not None
        exp_id = None
        if _flag(args, "save", True):
            exp_id = store.save_experiment(
                result, strategy_id=args.get("strategyId") or result.metadata.get("strategyId"),
                strategy_version=result.metadata.get("strategyVersion"), kind="python_backtest")
        return (_render_result(result, exp_id), _result_data(result, exp_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def compile_strategy_graph(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Compile a visual strategy graph into the canonical StrategySpec IR."""
    try:
        result = compile_graph(_graph_source(args))
        errs = result.errors()
        if errs:
            text = ("Graph compilation failed — "
                    + f"{len(errs)} error(s):\n"
                    + "\n".join(f"  - {d.node_id or d.path}: {d.message}" for d in errs[:20]))
        else:
            n_ind = len(result.spec.indicators) if result.spec else 0
            text = (f"Graph compiled to strategy {result.spec.id!r} "
                    f"v{result.spec.version} ({n_ind} indicator(s))." if result.spec
                    else "Graph compiled.")
        return (text, _compile_payload(result))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def validate_strategy_graph(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Validate a strategy graph (structure, types, cycle, IR validity)."""
    try:
        result = compile_graph(_graph_source(args))
        errs = result.errors()
        text = (f"Graph is valid ({len(result.diagnostics)} warning(s))." if not errs
                else "Graph is invalid:\n"
                + "\n".join(f"  - {d.node_id or d.path}: {d.message}" for d in errs[:20]))
        return (text, _compile_payload(result))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_strategy_nodes(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """List the strategy node registry (types, ports, config schema)."""
    try:
        nodes = REGISTRY.describe_all()
        text = "\n".join(f"  {n['type']} v{n['version']} [{n['category']}] — {n['title']}"
                         for n in nodes)
        return (f"{len(nodes)} node type(s):\n{text}", {"status": "OK", "nodes": nodes})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def export_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Export an immutable strategy version as a portable, checksummed bundle."""
    try:
        store = _store(ctx)
        sid = str(args.get("strategyId"))
        record = store.get_strategy(sid, args.get("version"))
        spec = StrategySpec.model_validate(record["spec"])
        provenance = {
            "source": "black-eclipse",
            "strategyId": sid,
            "version": record["version"],
            "contentHash": record.get("contentHash"),
            "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        }
        bundle = export_bundle(spec, provenance=provenance,
                               schema_version=record.get("schemaVersion"))
        manifest = bundle["manifest"]
        data: dict[str, Any] = {"status": "OK", "manifest": manifest, "strategy": bundle["strategy"]}
        text = (f"Exported {sid} v{record['version']} "
                f"(sha256 {str(manifest['contentHash'])[:12]}…).")
        if _flag(args, "write", True):
            path = os.path.join(_strategy_exports_root(store), f"{sid}@{record['version']}.zip")
            write_bundle(bundle, path)
            data["path"] = path
            text += f" Wrote bundle to {path}."
        if _flag(args, "includeBytes", False):
            data["bundleBase64"] = base64.b64encode(bundle_to_bytes(bundle)).decode("ascii")
        return (text, data)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def import_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Import a portable strategy bundle; validates before it is trusted."""
    try:
        result = import_bundle(_bundle_source(args))
        spec = result["spec"]
        issues = result["issues"]
        errs = errors_only(issues)
        data: dict[str, Any] = {
            "status": "INVALID" if errs else "OK",
            "strategy": spec.to_dict(),
            "manifest": result["manifest"],
            "issues": [i.to_dict() for i in issues],
            "warnings": result["warnings"],
            "contentHash": result["contentHash"],
        }
        if errs:
            return (
                "Imported bundle is invalid:\n"
                + "\n".join(f"  - {i.path}: {i.message}" for i in errs),
                data,
            )
        if _flag(args, "save", False):
            record = _store(ctx).save_strategy(spec)
            data["saved"] = record
            return (f"Imported and saved strategy {spec.id!r} v{spec.version}.", data)
        return (f"Imported strategy {spec.id!r} v{spec.version} (not saved; pass save=true).", data)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def diff_strategy_versions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Structurally diff two stored versions of a strategy."""
    try:
        store = _store(ctx)
        diff = store.diff_versions(str(args.get("strategyId")),
                                   str(args.get("from")), str(args.get("to")))
        if not diff["changes"]:
            text = f"No changes between v{diff['a']} and v{diff['b']}."
        else:
            lines = [f"  {c['kind']:<7} {c['path']}" for c in diff["changes"][:40]]
            text = (f"{diff['changeCount']} change(s) v{diff['a']} → v{diff['b']} "
                    f"(sameContent={diff['sameContent']}):\n" + "\n".join(lines))
        return (text, {"status": "OK", **diff})
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

_STRATEGY_INPUT = {"type": "object", "properties": {
    "strategy": STRATEGY_SCHEMA,
    "strategyYaml": {"type": "string", "description": "Strategy spec as YAML/JSON text."},
}}


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
    _GRAPH_INPUT = {"type": "object", "properties": {
        "graph": {"type": "object", "description": "Strategy graph (nodes + edges)."},
        "graphJson": {"type": "string", "description": "Strategy graph as JSON text."}}}
    _def("compile_strategy_graph",
         "Compile a visual/Python strategy graph (typed nodes + edges) into the canonical "
         "StrategySpec IR, with diagnostics and a source map. The IR is the source of truth.",
         compile_strategy_graph, _GRAPH_INPUT)
    _def("validate_strategy_graph",
         "Validate a strategy graph: node types/versions, port types, required inputs, cycles "
         "and the resulting IR. Returns every diagnostic.",
         validate_strategy_graph, _GRAPH_INPUT)
    _def("list_strategy_nodes",
         "List the versioned strategy node registry (types, ports, config schema) usable in a "
         "visual strategy graph.",
         list_strategy_nodes, {"type": "object", "properties": {}})
    _def("export_strategy",
         "Export a stored strategy version as a portable, checksummed bundle zip "
         "(manifest + canonical IR). The IR is the source of truth, independent of UI.",
         export_strategy, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "version": {"type": "string"},
             "write": {"type": "boolean", "description": "Write the .zip under the quant "
                                                         "exports dir (default true)."},
             "includeBytes": {"type": "boolean", "description": "Also return bundleBase64."}},
             "required": ["strategyId"]})
    _def("import_strategy",
         "Import a portable strategy bundle (bundle object or base64 zip). Validates the "
         "IR and schema; optionally persists it (save=true).",
         import_strategy, {"type": "object", "properties": {
             "bundle": {"type": "object"}, "bundleBase64": {"type": "string"},
             "save": {"type": "boolean"}}})
    _def("diff_strategy_versions",
         "Structurally diff two stored versions of a strategy (added/removed/changed paths).",
         diff_strategy_versions, {"type": "object", "properties": {
             "strategyId": {"type": "string"}, "from": {"type": "string"},
             "to": {"type": "string"}}, "required": ["strategyId", "from", "to"]})
    _def("run_python_strategy",
         "Run a user-authored Python `Strategy` (subclass of ~harness.quant.sdk.Strategy) in "
         "the isolated SDK runtime over real historical data; returns a full backtest result. "
         "The decision code runs in a separate, env-scrubbed, time-limited process; accounting "
         "uses the ONE engine.",
         run_python_strategy, {"type": "object", "properties": {
             "strategyCode": {"type": "string", "description": "Python source defining a Strategy subclass."},
             "className": {"type": "string"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "riskFreeRate": {"type": "number"},
             "randomSeed": {"type": "integer"}, "params": {"type": "object"},
             "timeoutSeconds": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyCode", "symbols"]}, 180_000, long_running=True)
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
    register_copilot_tools(registry)
    register_strategy_ops_tools(registry)

    # Advanced tools (engine/costs/OOS/bootstrap/multiple-testing/options/futures);
    # imported lazily to avoid a cycle with `advanced_tools`.
    from .advanced_tools import register_advanced_tools
    from .pine_tools import PINE_TOOLS, register_pine_tools

    register_advanced_tools(registry)
    register_pine_tools(registry)

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

    return list(QUANT_TOOLS)


# The quant tool names, importable by `agents.py` so an agent allowlist never
# drifts from what is actually registered.
QUANT_TOOLS: tuple[str, ...] = (
    "create_strategy", "load_strategy", "update_strategy", "validate_strategy",
    "clone_strategy", "version_strategy", "list_strategies", "archive_strategy",
    "compile_strategy_graph", "validate_strategy_graph", "list_strategy_nodes",
    "export_strategy", "import_strategy", "diff_strategy_versions", "run_python_strategy",
    "run_backtest", "run_portfolio_backtest", "calculate_metrics", "inspect_trades",
    "inspect_positions", "plot_equity_curve", "plot_drawdown", "compare_experiments",
    "list_experiments", "export_backtest", "quant_capabilities",
    "optimize_parameters", "run_walk_forward", "run_monte_carlo",
    "run_sensitivity_analysis", "run_robustness_analysis",
    *COPILOT_TOOLS,
    *OPS_TOOLS,
    # Advanced surfaces; literal to avoid a cycle (parity asserted by a test).
    "run_event_driven_backtest", "run_vectorized_backtest", "simulate_transaction_costs",
    "simulate_slippage", "simulate_spread", "simulate_market_impact",
    "run_out_of_sample_test", "run_bootstrap_test", "compare_backtests",
    "run_multiple_testing_diagnostics", "price_option", "implied_volatility",
    "analyze_option_strategy", "build_continuous_contract", "run_regime_monte_carlo", "grade_strategy_edge", "analyse_trade_log",
    "list_strategy_venues", "run_prop_firm_simulation", "list_prop_firm_rules", "generate_edge_report", *PINE_TOOLS,
    )


__all__ = ["QUANT_TOOLS", "register_quant_tools", "_CAPABILITY"]
