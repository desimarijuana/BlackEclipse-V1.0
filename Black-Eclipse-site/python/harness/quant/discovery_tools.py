"""Agent tools for method discovery — find, adapt, invent, and scan for setups.

This is the surface a user reaches when they ask "what methods can I use?", "find
me a strategy", "does this work now?", or "invent something better". It is the
core of quant mode, not an add-on.
"""

from __future__ import annotations

from typing import Any, Optional

from .discovery.hypotheses import generate_hypotheses
from .discovery.library import get_method_card, list_method_families, recommend_methods
from .discovery.miner import mine_methods
from .discovery.synthesize import build_combination, synthesize_method
from .discovery.taxonomy import FAMILIES
from .discovery.diagnostics import analyze_structure
from .errors import QuantError

DISCOVERY_TOOLS: tuple[str, ...] = (
    "list_method_families", "get_method_card", "recommend_methods",
    "scan_market_structure", "generate_method_hypotheses",
    "synthesize_method_strategy", "combine_methods", "mine_methods",
    "scan_current_setups", "save_discovered_method", "list_discovered_methods",
    "promote_discovered_method",
)


def _store(ctx: Any):
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise QuantError("the quant store is not configured in this runtime")
    return store


def _gateway(ctx: Any):
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}",
                {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


def _rows_from_series(series: Any) -> list[dict[str, Any]]:
    out = []
    for i in range(series.length):
        out.append({
            "timestamp": series.timestamps[i],
            "open": float(series.open[i]), "high": float(series.high[i]),
            "low": float(series.low[i]), "close": float(series.close[i]),
            "volume": float(series.volume[i]),
        })
    return out


async def _load_rows(ctx: Any, symbol: str, interval: str,
                     start: Optional[str], end: Optional[str]):
    from .datasets import dataset_from_strategy  # noqa: PLC0415
    from .strategy import parse_strategy  # noqa: PLC0415

    spec = parse_strategy({
        "strategy": {"id": "discovery_probe", "name": "Discovery probe", "version": "1.0.0"},
        "universe": {"symbols": [symbol]},
        "timeframes": {"primary": interval},
    })
    dataset = await dataset_from_strategy(
        _gateway(ctx), spec, start=start, end=end, symbols=[symbol]
    )
    series = dataset.series.get(symbol) or dataset.series.get(symbol.upper())
    if series is None:
        raise QuantError(f"no data for {symbol}", detail={"symbol": symbol})
    return _rows_from_series(series), series


# ── Library ──────────────────────────────────────────────────────────────────

async def list_method_families_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        methods = list_method_families(
            category=args.get("category"), asset_class=args.get("assetClass"),
            horizon=args.get("horizon"), max_complexity=args.get("maxComplexity"),
        )
        text = "\n".join(f"- {m['id']}: {m['name']} ({m['category']})" for m in methods)
        return f"{len(methods)} method families\n{text}", {"status": "OK", "methods": methods}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def get_method_card_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        card = get_method_card(str(args["methodId"]), symbol=args.get("symbol"),
                               interval=str(args.get("interval") or "1d"))
        text = (f"{card['name']}\nThesis: {card['thesis']}\n"
                f"Edge source: {card['edge_source']}\n"
                f"Fails when: {', '.join(card['failure_modes'])}\n"
                f"Validate with: {card['validation']}")
        return text, {"status": "OK", "card": card}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def recommend_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = recommend_methods(args, limit=int(args.get("limit") or 5))
        top = result["recommendations"]
        text = "Method fit (a prior, not an edge):\n" + "\n".join(
            f"- {r['name']} — {r['fitPercent']}% · {r['category']}"
            for r in top
        )
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Diagnostics & hypotheses ─────────────────────────────────────────────────

async def scan_market_structure_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        rows, _ = await _load_rows(
            ctx, str(args["symbol"]), str(args.get("interval") or "1d"),
            args.get("start"), args.get("end"),
        )
        result = analyze_structure(rows, interval=str(args.get("interval") or "1d"),
                                   oos_fraction=float(args.get("oosFraction") or 0.3))
        text = (f"{args['symbol']} structure: {result['structure']}\n"
                + "\n".join(f"- {line}" for line in result["insights"])
                + "\nCandidate methods: "
                + ", ".join(c["methodId"] for c in result["candidateMethods"]))
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def generate_hypotheses_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        diagnostics = args.get("diagnostics")
        symbol = str(args.get("symbol") or "")
        if diagnostics is None:
            if not symbol:
                raise QuantError("pass diagnostics or a symbol to scan")
            rows, _ = await _load_rows(
                ctx, symbol, str(args.get("interval") or "1d"),
                args.get("start"), args.get("end"),
            )
            diagnostics = analyze_structure(rows)
        result = generate_hypotheses(
            diagnostics, symbol=symbol, max_hypotheses=int(args.get("max") or 8)
        )
        text = f"{len(result['hypotheses'])} hypotheses\n" + "\n".join(
            f"- [{h['priority']}] {h['statement']}" for h in result["hypotheses"]
        )
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Synthesis, combinations, mining ──────────────────────────────────────────

async def synthesize_method_strategy_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        result = synthesize_method(
            str(args["methodId"]), symbol=str(args["symbol"]),
            interval=str(args.get("interval") or "1d"),
            params=args.get("params"), name=args.get("name"),
        )
        text = (f"{result['spec']['strategy']['name']} synthesized; "
                f"valid={result['valid']} ({len(result['issues'])} issue(s))")
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def combine_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        spec = build_combination(
            str(args["primaryMethodId"]), str(args["filterMethodId"]),
            symbol=str(args["symbol"]), interval=str(args.get("interval") or "1d"),
            primary_params=args.get("primaryParams"), filter_params=args.get("filterParams"),
        )
        return (f"Combined method synthesized: {spec['strategy']['name']}",
                {"status": "OK", "spec": spec})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def mine_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        rows, _ = await _load_rows(
            ctx, str(args["symbol"]), str(args.get("interval") or "1d"),
            args.get("start"), args.get("end"),
        )
        result = mine_methods(
            rows, symbol=str(args["symbol"]), interval=str(args.get("interval") or "1d"),
            method_ids=args.get("methodIds"), max_trials=int(args.get("maxTrials") or 24),
            oos_fraction=float(args.get("oosFraction") or 0.3),
            combinations=int(args.get("combinations") or 0),
        )
        selected = result.get("selected")
        text = (f"Mined {result['trialCount']} trials on {args['symbol']} "
                f"({result['isBars']} IS / {result['oosBars']} OOS bars).\n"
                + (f"Selected: {selected['methodId']} {selected['params']} "
                   f"OOS Sharpe {selected['outOfSample'].get('sharpe')}"
                   if selected else "No candidate survived.")
                + f"\n{result['rejectedCount']} rejected.")
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Current setups ──────────────────────────────────────────────────────────

async def scan_current_setups_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Evaluate synthesized methods on the latest bar: is there a setup now?"""
    try:
        from .engine import build_context  # noqa: PLC0415
        from . import rules as rule_eval  # noqa: PLC0415

        symbol = str(args["symbol"])
        interval = str(args.get("interval") or "1d")
        rows, series = await _load_rows(ctx, symbol, interval, args.get("start"), args.get("end"))
        method_ids = args.get("methodIds") or [
            "trend_ema_cross", "trend_donchian_breakout",
            "mean_reversion_bollinger", "mean_reversion_rsi", "volatility_breakout",
        ]
        from .strategy import parse_strategy  # noqa: PLC0415
        setups = []
        for method_id in method_ids:
            try:
                synthesized = synthesize_method(method_id, symbol=symbol, interval=interval)
                spec = parse_strategy(synthesized["spec"])
                ctx_arrays, _ = build_context(spec, symbol, series, {})
                i = series.length - 1
                long_rule = spec.rules.entry.long
                short_rule = spec.rules.entry.short
                is_long = bool(long_rule and rule_eval.evaluate(long_rule, ctx_arrays, i))
                is_short = bool(short_rule and rule_eval.evaluate(short_rule, ctx_arrays, i))
                direction = "long" if is_long else "short" if is_short else "none"
                setups.append({
                    "methodId": method_id,
                    "name": synthesized["spec"]["strategy"]["name"],
                    "direction": direction,
                    "bar": series.timestamps[i],
                    "close": float(series.close[i]),
                    "reason": ("the entry condition is true on the latest closed bar"
                               if direction != "none"
                               else "no entry condition on the latest closed bar"),
                })
            except Exception as exc:  # noqa: BLE001
                setups.append({"methodId": method_id, "direction": "error",
                               "reason": str(exc)})
        active = [s for s in setups if s["direction"] in ("long", "short")]
        text = (f"{len(active)} active setup(s) for {symbol} on {interval}.\n"
                + "\n".join(f"- {s['name']}: {s['direction']}" for s in active)
                if active else
                f"No method has an active entry on the latest {symbol} {interval} bar.")
        return text, {
            "status": "OK", "symbol": symbol, "interval": interval,
            "bar": series.timestamps[-1] if series.length else None,
            "setups": setups, "active": active,
            "note": "a setup is a condition, not an order or a recommendation",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Persistence ─────────────────────────────────────────────────────────────

async def save_discovered_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        method = store.save_method(
            name=str(args["name"]),
            method_family=str(args.get("methodFamily") or "custom"),
            spec=args.get("spec"), evidence=args.get("evidence"),
            status=str(args.get("status") or "discovered"),
            strategy_id=args.get("strategyId"),
        )
        return (f"Method {method['id']} saved ({method['status']}): {method['name']}",
                {"status": "OK", "method": method})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def list_discovered_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        methods = _store(ctx).list_methods(
            status=args.get("status"), limit=int(args.get("limit") or 50)
        )
        return (f"{len(methods)} discovered methods",
                {"status": "OK", "methods": methods})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def promote_discovered_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        method = _store(ctx).promote_method(
            str(args["methodId"]), str(args["status"]),
            strategy_id=args.get("strategyId"),
        )
        return (f"Method {method['id']} is now {method['status']}",
                {"status": "OK", "method": method})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def register_discovery_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 30_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout,
        ))

    _def("list_method_families",
         "List the quantitative method families a user can understand and choose from, "
         "filterable by category, asset class, horizon and complexity.",
         list_method_families_tool, {"type": "object", "properties": {
             "category": {"type": "string"}, "assetClass": {"type": "string"},
             "horizon": {"type": "string"}, "maxComplexity": {"type": "integer"}}})
    _def("get_method_card",
         "Explain one method: thesis, edge source, signals, failure modes, regime fit, "
         "validation plan, capacity and an example spec.",
         get_method_card_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "symbol": {"type": "string"},
             "interval": {"type": "string"}}, "required": ["methodId"]})
    _def("recommend_methods",
         "Rank method families for a user's asset class, horizon, risk tolerance, "
         "objective, available data and regime. Deterministic and explainable.",
         recommend_methods_tool, {"type": "object", "properties": {
             "assetClass": {"type": "string"}, "horizon": {"type": "string"},
             "riskTolerance": {"type": "string"}, "objective": {"type": "string"},
             "capital": {"type": "number"}, "availableData": {"type": "array", "items": {"type": "string"}},
             "allowShort": {"type": "boolean"}, "complexityMax": {"type": "integer"},
             "regime": {"type": "string"}, "symbol": {"type": "string"},
             "interval": {"type": "string"}, "limit": {"type": "integer"}}})
    _def("scan_market_structure",
         "Analyze a series for trend/mean-reversion/volatility-clustering/seasonality "
         "and suggest method families to test. Descriptive, not a signal.",
         scan_market_structure_tool, {"type": "object", "properties": {
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "start": {"type": "string"}, "end": {"type": "string"},
             "oosFraction": {"type": "number"}}, "required": ["symbol"]})
    _def("generate_method_hypotheses",
         "Turn market-structure diagnostics into falsifiable hypotheses with tests, "
         "acceptance rules and invalidation conditions.",
         generate_hypotheses_tool, {"type": "object", "properties": {
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "diagnostics": {"type": "object"}, "max": {"type": "integer"}}})
    _def("synthesize_method_strategy",
         "Turn a method family into a valid StrategySpec with explicit costs, sizing "
         "and risk, ready for the normal backtest/validation path.",
         synthesize_method_strategy_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "symbol": {"type": "string"},
             "interval": {"type": "string"}, "params": {"type": "object"},
             "name": {"type": "string"}}, "required": ["methodId", "symbol"]})
    _def("combine_methods",
         "Compose two single-asset methods into a NEW conjunction (e.g. trend entry + "
         "volatility filter), then validate the combined spec.",
         combine_methods_tool, {"type": "object", "properties": {
             "primaryMethodId": {"type": "string"}, "filterMethodId": {"type": "string"},
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "primaryParams": {"type": "object"}, "filterParams": {"type": "object"}},
             "required": ["primaryMethodId", "filterMethodId", "symbol"]})
    _def("mine_methods",
         "Search a bounded grid of method parameterizations with an IS/OOS split, "
         "record the REAL trial count, and deflate the selected Sharpe. Returns "
         "candidates, not validated strategies.",
         mine_methods_tool, {"type": "object", "properties": {
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "start": {"type": "string"}, "end": {"type": "string"},
             "methodIds": {"type": "array", "items": {"type": "string"}},
             "maxTrials": {"type": "integer"}, "oosFraction": {"type": "number"},
             "combinations": {"type": "integer"}}, "required": ["symbol"]}, 180_000)
    _def("scan_current_setups",
         "Evaluate a set of validated methods on the latest closed bar and report which "
         "have an active long/short setup now. A condition, not an order.",
         scan_current_setups_tool, {"type": "object", "properties": {
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "methodIds": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["symbol"]}, 60_000)
    _def("save_discovered_method",
         "Persist a discovered/composed method with its spec and evidence so it can be "
         "reused, versioned and promoted.",
         save_discovered_method_tool, {"type": "object", "properties": {
             "name": {"type": "string"}, "methodFamily": {"type": "string"},
             "spec": {"type": "object"}, "evidence": {"type": "object"},
             "status": {"type": "string"}, "strategyId": {"type": "string"}},
             "required": ["name"]})
    _def("list_discovered_methods",
         "List persisted discovered methods and their status.",
         list_discovered_methods_tool, {"type": "object", "properties": {
             "status": {"type": "string"}, "limit": {"type": "integer"}}})
    _def("promote_discovered_method",
         "Move a discovered method to validated/promoted/rejected. Promotion is a "
         "bookkeeping decision; it does not create evidence.",
         promote_discovered_method_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "status": {"type": "string"},
             "strategyId": {"type": "string"}}, "required": ["methodId", "status"]})
    return list(DISCOVERY_TOOLS)


__all__ = ["DISCOVERY_TOOLS", "register_discovery_tools"]
