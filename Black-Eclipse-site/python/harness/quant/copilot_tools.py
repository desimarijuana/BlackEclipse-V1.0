"""AI Strategy Copilot agent tools.

Thin, grounded handlers over `quant/copilot.py` and the existing store/engine.
Every tool either computes a deterministic artifact (signals, a research plan, a
report) or delegates to an existing engine entry point — none of them fabricate
results, run live orders, or bypass validation.
"""

from __future__ import annotations

from typing import Any

from .copilot import (
    build_report,
    build_research_plan,
    calculate_signals,
    describe_rules,
    with_position_sizing,
    with_stops_and_targets,
)
from .errors import QuantError, StoreUnavailable
from .strategy import StrategySpec


def _store(ctx: Any):
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise StoreUnavailable("the quant store is not configured")
    return store


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}", {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


def _gateway(ctx: Any):
    from ..market.tools import _gateway as market_gateway

    return market_gateway(ctx)


def _load_spec(store: Any, strategy_id: str, version: Any) -> StrategySpec:
    return StrategySpec.model_validate(store.get_strategy(strategy_id, version)["spec"])


# ── Signals / plan / report ──────────────────────────────────────────────────

async def calculate_signals_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .datasets import dataset_from_strategy

        store = _store(ctx)
        spec = _load_spec(store, str(args.get("strategyId")), args.get("version"))
        symbols = args.get("symbols")
        dataset = await dataset_from_strategy(
            _gateway(ctx), spec, start=args.get("start"), end=args.get("end"), symbols=symbols)
        result = calculate_signals(
            spec, dataset, symbols=symbols,
            include_indicators=bool(args.get("includeIndicators", True)),
            max_points_per_symbol=int(args.get("maxPoints") or 5000),
        )
        counts = ", ".join(f"{k}={v}" for k, v in result["signalCounts"].items()) or "none"
        return (f"Signals for {spec.id} v{spec.version}: {counts}.", {"status": "OK", **result})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def create_research_plan_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        spec = _load_spec(store, str(args.get("strategyId")), args.get("version"))
        plan = build_research_plan(
            spec, start=args.get("start"), end=args.get("end"),
            benchmark=args.get("benchmark"), train_bars=int(args.get("trainBars") or 250),
            test_bars=int(args.get("testBars") or 60),
            max_evaluations=int(args.get("maxEvaluations") or 60),
            objective=str(args.get("objective") or "sharpe"),
        )
        return (f"Research plan for {spec.id}: {plan['hypothesis']}",
                {"status": "OK", "plan": plan})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def generate_strategy_report_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        exp_id = str(args.get("experimentId"))
        experiment = store.get_experiment(exp_id)
        artifact = store.read_artifact(exp_id) if args.get("withArtifact", True) else None
        report = build_report(experiment, artifact)
        return (report, {"status": "OK", "experimentId": exp_id, "report": report,
                         "format": "markdown"})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Rule / sizing / stop generation ──────────────────────────────────────────

async def generate_entry_exit_rules_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        spec = _load_spec(store, str(args.get("strategyId")), args.get("version"))
        rules = describe_rules(spec)
        text = "\n".join(
            f"  {section}.{side}: {rule}" for section in ("entry", "exit")
            for side, rule in rules[section].items() if isinstance(rule, str) and rule
        ) or "  (no signal rules)"
        return (f"Rules for {spec.id}:\n{text}", {"status": "OK", "rules": rules})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def configure_position_sizing_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        spec = _load_spec(store, str(args.get("strategyId")), args.get("version"))
        updated, issues = with_position_sizing(spec, args.get("config") or {})
        errs = [i for i in issues if i["severity"] == "error"]
        return (("Configured sizing." if not errs else f"{len(errs)} sizing error(s)."),
                {"status": "INVALID" if errs else "OK", "strategy": updated.to_dict(),
                 "issues": issues})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def configure_stops_and_targets_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        spec = _load_spec(store, str(args.get("strategyId")), args.get("version"))
        updated, issues = with_stops_and_targets(spec, args.get("config") or {})
        errs = [i for i in issues if i["severity"] == "error"]
        return (("Configured stops/targets." if not errs else f"{len(errs)} stop error(s)."),
                {"status": "INVALID" if errs else "OK", "strategy": updated.to_dict(),
                 "issues": issues})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Lifecycle / research convenience tools ───────────────────────────────────

async def get_experiment_status_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        run_id = args.get("runId")
        if run_id:
            from .runner import get_runner

            run = get_runner().get(str(run_id), include_result=bool(args.get("result")))
            if run is None:
                return (f"ERROR — run {run_id!r} not found",
                        {"status": "ERROR", "error": {"code": "RUN_NOT_FOUND"}})
            return (f"Run {run_id}: {run['status']} ({run.get('percent')}%).",
                    {"status": "OK", "run": run})
        store = _store(ctx)
        exp = store.get_experiment(str(args.get("experimentId")))
        return (f"Experiment {exp['id']}: {exp['status']}.", {"status": "OK", "experiment": exp})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def cancel_experiment_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .runner import get_runner

        run_id = str(args.get("runId"))
        cancelled = get_runner().cancel(run_id)
        return (f"{'Cancelled' if cancelled else 'Could not cancel'} run {run_id}.",
                {"status": "OK", "runId": run_id, "cancelled": cancelled})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def calculate_performance_metrics_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .tools import calculate_metrics

    return await calculate_metrics(args, ctx)


async def analyze_trade_log_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        artifact = store.read_artifact(str(args.get("experimentId")))
        trades = artifact.get("trades", []) or []
        wins = [t for t in trades if t.get("netPnl", 0) > 0]
        losses = [t for t in trades if t.get("netPnl", 0) < 0]
        gross_win = sum(t["netPnl"] for t in wins)
        gross_loss = abs(sum(t["netPnl"] for t in losses))
        by_symbol: dict[str, int] = {}
        by_exit: dict[str, int] = {}
        for t in trades:
            by_symbol[t.get("symbol", "?")] = by_symbol.get(t.get("symbol", "?"), 0) + 1
            by_exit[t.get("exitReason", "?")] = by_exit.get(t.get("exitReason", "?"), 0) + 1
        summary = {
            "count": len(trades), "wins": len(wins), "losses": len(losses),
            "winRate": (len(wins) / len(trades)) if trades else None,
            "totalNetPnl": round(sum(t.get("netPnl", 0) for t in trades), 4),
            "avgWin": round(gross_win / len(wins), 4) if wins else None,
            "avgLoss": round(-gross_loss / len(losses), 4) if losses else None,
            "profitFactor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
            "best": max((t["netPnl"] for t in trades), default=None),
            "worst": min((t["netPnl"] for t in trades), default=None),
            "avgBarsHeld": (round(sum(t.get("barsHeld", 0) for t in trades) / len(trades), 2)
                            if trades else None),
            "bySymbol": by_symbol, "byExitReason": by_exit,
        }
        return (f"Trade log: {summary['count']} trade(s), win rate "
                f"{summary['winRate'] if summary['winRate'] is not None else '—'}, "
                f"net {summary['totalNetPnl']}.",
                {"status": "OK", "summary": summary})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def compare_strategies_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        ids = args.get("strategyIds") or []
        exp_ids: list[str] = []
        for sid in ids:
            exps = store.list_experiments(strategy_id=str(sid), limit=1)
            if exps:
                exp_ids.append(exps[0]["id"])
        if not exp_ids:
            return ("No experiments found for the given strategies.",
                    {"status": "OK", "experiments": []})
        return await _compare(store, exp_ids)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def _compare(store: Any, exp_ids: list[str]) -> tuple[str, Any]:
    comparison = store.compare_experiments(exp_ids)
    lines = [f"  {e['experimentId']}: ret={e['metrics'].get('total_return')}, "
             f"sharpe={e['metrics'].get('sharpe')}" for e in comparison["experiments"]]
    return (f"Compared {len(comparison['experiments'])} strategy experiment(s):\n"
            + "\n".join(lines), {"status": "OK", **comparison})


async def run_parameter_sweep_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    from .tools import optimize_parameters

    sweep = dict(args)
    sweep.setdefault("method", "grid")
    sweep.setdefault("paramSpace", args.get("paramRanges") or {})
    return await optimize_parameters(sweep, ctx)


# ── Registration ─────────────────────────────────────────────────────────────

def register_copilot_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 60_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
        ))

    _sid = {"strategyId": {"type": "string"}, "version": {"type": "string"}}
    _def("calculate_signals",
         "Compute a strategy's entry/exit decision timeline (no orders, no fills) over real "
         "historical data, with reason codes and indicator snapshots.",
         calculate_signals_tool, {"type": "object", "properties": {
             **_sid, "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "includeIndicators": {"type": "boolean"}, "maxPoints": {"type": "integer"}},
             "required": ["strategyId"]}, 120_000, long_running=True)
    _def("create_research_plan",
         "Generate an explicit research specification (hypothesis, splits, benchmark, costs, "
         "parameter search, metrics, walk-forward, robustness, acceptance criteria, biases).",
         create_research_plan_tool, {"type": "object", "properties": {
             **_sid, "start": {"type": "string"}, "end": {"type": "string"},
             "benchmark": {"type": "string"}, "trainBars": {"type": "integer"},
             "testBars": {"type": "integer"}, "maxEvaluations": {"type": "integer"},
             "objective": {"type": "string"}}, "required": ["strategyId"]})
    _def("generate_strategy_report",
         "Build a Markdown report grounded in a stored experiment (metrics, warnings, trades, "
         "reproducibility) — never fabricated.",
         generate_strategy_report_tool, {"type": "object", "properties": {
             "experimentId": {"type": "string"}, "withArtifact": {"type": "boolean"}},
             "required": ["experimentId"]})
    _def("generate_entry_exit_rules",
         "Describe a strategy's entry/exit rules in plain language (and stops/targets).",
         generate_entry_exit_rules_tool, {"type": "object", "properties": {**_sid},
                                          "required": ["strategyId"]})
    _def("configure_position_sizing",
         "Return a strategy copy with validated position sizing applied (does not persist).",
         configure_position_sizing_tool, {"type": "object", "properties": {
             **_sid, "config": {"type": "object"}}, "required": ["strategyId", "config"]})
    _def("configure_stops_and_targets",
         "Return a strategy copy with validated stop-loss/take-profit/trailing/time-stop applied.",
         configure_stops_and_targets_tool, {"type": "object", "properties": {
             **_sid, "config": {"type": "object"}}, "required": ["strategyId", "config"]})
    _def("get_experiment_status",
         "Status of an experiment (by id) or a background run (by runId).",
         get_experiment_status_tool, {"type": "object", "properties": {
             "experimentId": {"type": "string"}, "runId": {"type": "string"},
             "result": {"type": "boolean"}}})
    _def("cancel_experiment",
         "Cancel a running background experiment by runId.",
         cancel_experiment_tool, {"type": "object", "properties": {"runId": {"type": "string"}},
                                  "required": ["runId"]})
    _def("calculate_performance_metrics",
         "Return the computed metric set (with definitions) for a stored experiment.",
         calculate_performance_metrics_tool, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("analyze_trade_log",
         "Summarize a stored experiment's trades (win rate, profit factor, by-symbol/exit).",
         analyze_trade_log_tool, {"type": "object", "properties": {
             "experimentId": {"type": "string"}}, "required": ["experimentId"]})
    _def("compare_strategies",
         "Compare the latest experiment of each given strategy on a fixed metric set.",
         compare_strategies_tool, {"type": "object", "properties": {
             "strategyIds": {"type": "array", "items": {"type": "string"}}},
             "required": ["strategyIds"]})
    _def("run_parameter_sweep",
         "Grid-sweep a strategy's parameters over a parameter space (a convenience over "
         "optimize_parameters with method=grid).",
         run_parameter_sweep_tool, {"type": "object", "properties": {
             **_sid, "paramRanges": {"type": "object"}, "objective": {"type": "string"},
             "seed": {"type": "integer"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "initialCapital": {"type": "number"}, "save": {"type": "boolean"}},
             "required": ["strategyId", "paramRanges"]}, 300_000, long_running=True)

    return list(COPILOT_TOOLS)


COPILOT_TOOLS: tuple[str, ...] = (
    "calculate_signals", "create_research_plan", "generate_strategy_report",
    "generate_entry_exit_rules", "configure_position_sizing", "configure_stops_and_targets",
    "get_experiment_status", "cancel_experiment", "calculate_performance_metrics",
    "analyze_trade_log", "compare_strategies", "run_parameter_sweep",
)


__all__ = ["COPILOT_TOOLS", "register_copilot_tools"]
