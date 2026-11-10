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
from .discovery.taxonomy import FAMILIES, family_by_id
from .discovery.diagnostics import analyze_structure
from .playbook import build_playbook
from .errors import QuantError

DISCOVERY_TOOLS: tuple[str, ...] = (
    "list_method_families", "get_method_card", "recommend_methods",
    "scan_market_structure", "generate_method_hypotheses",
    "synthesize_method_strategy", "combine_methods", "mine_methods",
    "mine_universe_methods", "scan_current_setups", "scan_universe_setups",
    "generate_trading_playbook",
    "save_discovered_method", "list_discovered_methods",
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


async def mine_universe_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Mine the same method families across a bounded universe and aggregate support."""
    try:
        symbols = [str(s).strip().upper() for s in (args.get("symbols") or []) if str(s).strip()]
        if not symbols:
            raise QuantError("pass at least one symbol")
        max_symbols = int(args.get("maxSymbols") or 5)
        if len(symbols) > max_symbols:
            raise QuantError(f"at most {max_symbols} symbols per universe mine",
                             detail={"symbols": len(symbols)})
        interval = str(args.get("interval") or "1d")
        max_trials = int(args.get("maxTrials") or 6)
        method_ids = args.get("methodIds")
        per_symbol = []
        failures = []
        for symbol in symbols:
            try:
                rows, _ = await _load_rows(
                    ctx, symbol, interval, args.get("start"), args.get("end")
                )
                result = mine_methods(
                    rows, symbol=symbol, interval=interval, method_ids=method_ids,
                    max_trials=max_trials, oos_fraction=float(args.get("oosFraction") or 0.3),
                    combinations=int(args.get("combinations") or 0),
                )
                per_symbol.append({
                    "symbol": symbol, "trialCount": result["trialCount"],
                    "selected": result.get("selected"),
                    "rejectedCount": result["rejectedCount"],
                })
            except Exception as exc:  # noqa: BLE001
                failures.append({"symbol": symbol, "reason": str(exc)})

        # Aggregate support per method family: how many symbols selected it, and
        # the mean OOS Sharpe of those selections. A method with one lucky symbol
        # is visible as support=1, not hidden inside an average.
        aggregate: dict[str, dict[str, Any]] = {}
        for row in per_symbol:
            selected = row.get("selected")
            if not selected:
                continue
            method_id = selected.get("methodId")
            oos = (selected.get("outOfSample") or {}).get("sharpe")
            entry = aggregate.setdefault(method_id, {
                "methodId": method_id, "support": 0, "sharpes": [],
                "symbols": [],
            })
            entry["support"] += 1
            entry["symbols"].append(row["symbol"])
            if oos is not None:
                entry["sharpes"].append(float(oos))
        ranked = []
        for entry in aggregate.values():
            sharpes = entry.pop("sharpes")
            entry["meanOosSharpe"] = (sum(sharpes) / len(sharpes)) if sharpes else None
            entry["supportedSymbols"] = entry["support"] / max(1, len(per_symbol))
            ranked.append(entry)
        ranked.sort(key=lambda e: (-e["support"], -(e["meanOosSharpe"] or -99)))
        text = (f"Mined {len(per_symbol)} symbols ({len(failures)} failed); "
                f"{len(ranked)} method family/families survived at least one symbol.\n"
                + "\n".join(
                    f"- {r['methodId']}: {r['support']}/{len(per_symbol)} symbols, "
                    f"mean OOS Sharpe {r['meanOosSharpe']}"
                    for r in ranked[:8]
                )
                if ranked else
                f"No method survived across {len(per_symbol)} symbols.")
        return text, {
            "status": "OK", "interval": interval, "symbols": symbols,
            "perSymbol": per_symbol, "rankedMethods": ranked, "failures": failures,
            "warnings": [
                "cross-symbol support is evidence of robustness, not proof; a method "
                "can still fail on a new symbol or regime",
                "each symbol's trial count is real; do not treat the aggregate as free",
            ],
            "note": "universe mining ranks candidates; the normal validation gates still apply",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Current setups ──────────────────────────────────────────────────────────

async def _setups_for_symbol(ctx: Any, symbol: str, interval: str,
                             method_ids: list[str], start: Any = None,
                             end: Any = None) -> dict[str, Any]:
    from .engine import build_context  # noqa: PLC0415
    from . import rules as rule_eval  # noqa: PLC0415
    from .strategy import parse_strategy  # noqa: PLC0415

    _, series = await _load_rows(ctx, symbol, interval, start, end)
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
    return {
        "symbol": symbol, "interval": interval,
        "bar": series.timestamps[-1] if series.length else None,
        "setups": setups, "active": active,
    }


_DEFAULT_SETUP_METHODS = [
    "trend_ema_cross", "trend_donchian_breakout",
    "mean_reversion_bollinger", "mean_reversion_rsi", "volatility_breakout",
]


async def scan_current_setups_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Evaluate synthesized methods on the latest bar: is there a setup now?"""
    try:
        symbol = str(args["symbol"])
        interval = str(args.get("interval") or "1d")
        result = await _setups_for_symbol(
            ctx, symbol, interval,
            args.get("methodIds") or _DEFAULT_SETUP_METHODS,
            args.get("start"), args.get("end"),
        )
        active = result["active"]
        text = (f"{len(active)} active setup(s) for {symbol} on {interval}.\n"
                + "\n".join(f"- {s['name']}: {s['direction']}" for s in active)
                if active else
                f"No method has an active entry on the latest {symbol} {interval} bar.")
        return text, {
            "status": "OK", **result,
            "note": "a setup is a condition, not an order or a recommendation",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def scan_universe_setups_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Scan a bounded watchlist for methods with an active entry condition now."""
    try:
        symbols = [str(s).strip().upper() for s in (args.get("symbols") or []) if str(s).strip()]
        if not symbols:
            raise QuantError("pass at least one symbol")
        if len(symbols) > int(args.get("maxSymbols") or 12):
            raise QuantError(f"at most {args.get('maxSymbols') or 12} symbols per scan",
                             detail={"symbols": len(symbols)})
        interval = str(args.get("interval") or "1d")
        method_ids = args.get("methodIds") or _DEFAULT_SETUP_METHODS
        rows = []
        failures = []
        for symbol in symbols:
            try:
                result = await _setups_for_symbol(
                    ctx, symbol, interval, method_ids,
                    args.get("start"), args.get("end"),
                )
                for setup in result["active"]:
                    rows.append({
                        "symbol": symbol, "methodId": setup["methodId"],
                        "name": setup.get("name"), "direction": setup["direction"],
                        "bar": result["bar"], "close": setup.get("close"),
                    })
            except Exception as exc:  # noqa: BLE001 - one symbol cannot kill the scan
                failures.append({"symbol": symbol, "reason": str(exc)})
        rows.sort(key=lambda r: (r["symbol"], r["methodId"]))
        symbol_count = len({r['symbol'] for r in rows})
        text = (f"{len(rows)} active setup(s) across {symbol_count} of {len(symbols)} symbols.\n"
                + "\n".join(f"- {r['symbol']} · {r['methodId']}: {r['direction']}" for r in rows[:20])
                if rows else
                f"No active setup across {len(symbols)} symbols on the latest closed bar.")
        return text, {
            "status": "OK", "interval": interval, "symbols": symbols,
            "active": rows, "activeCount": len(rows),
            "symbolsWithSetups": symbol_count, "failures": failures,
            "note": "a setup is a condition, not an order or a recommendation; "
                    "each method still needs its own validation before use",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Trading playbook ────────────────────────────────────────────────────────

async def generate_trading_playbook_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        spec = args.get("spec")
        method = None
        symbol = args.get("symbol")
        interval = str(args.get("interval") or "1d")
        if args.get("methodId"):
            method = family_by_id(str(args["methodId"]))
            if method is None:
                raise QuantError(f"unknown method family {args['methodId']!r}")
            from .discovery.synthesize import build_strategy  # noqa: PLC0415
            spec = build_strategy(method.id, symbol=str(symbol or "SPY"),
                                  interval=interval, params=args.get("params"))
        if spec is None and args.get("strategyId"):
            record = _store(ctx).get_strategy(str(args["strategyId"]), args.get("version"))
            spec = record["spec"]
        if spec is None:
            raise QuantError("pass a methodId, strategyId or a strategy spec")
        evidence = None
        if args.get("experimentId"):
            experiment = _store(ctx).get_experiment(str(args["experimentId"]))
            evidence = {
                "experimentId": experiment.get("id"),
                "metrics": experiment.get("metrics"),
                "warnings": experiment.get("warnings"),
                "window": [experiment.get("start"), experiment.get("end")],
            }
        playbook = build_playbook(
            spec, symbol=symbol,
            evidence=evidence,
            method_family=method.to_dict() if method is not None else None,
        )
        text = (f"Trading playbook — {playbook['name']} on {playbook['symbol']} "
                f"({playbook['timeframe']})\n" + "\n".join(playbook["entry"])
                + "\n" + "\n".join(playbook["exit"])
                + f"\nSizing: {playbook['positionSizing']}")
        return text, {"status": "OK", "playbook": playbook}
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
    _def("mine_universe_methods",
         "Mine the same method families across a bounded universe (max 5 symbols) and "
         "aggregate per-method support and mean OOS Sharpe. Shows when an edge is one "
         "lucky symbol rather than a robust family.",
         mine_universe_methods_tool, {"type": "object", "properties": {
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "methodIds": {"type": "array", "items": {"type": "string"}},
             "maxTrials": {"type": "integer"}, "maxSymbols": {"type": "integer"},
             "oosFraction": {"type": "number"}, "combinations": {"type": "integer"},
             "start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["symbols"]}, 300_000)
    _def("scan_universe_setups",
         "Scan a bounded watchlist (max 12 symbols) for methods with an active entry "
         "condition on the latest closed bar. Ranks nothing as a recommendation; a "
         "setup is a condition, not an order.",
         scan_universe_setups_tool, {"type": "object", "properties": {
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "methodIds": {"type": "array", "items": {"type": "string"}},
             "start": {"type": "string"}, "end": {"type": "string"},
             "maxSymbols": {"type": "integer"}}, "required": ["symbols"]}, 180_000)
    _def("generate_trading_playbook",
         "Turn a method or a stored, tested strategy into a plain-language playbook: "
         "entry, exit, sizing, risk, execution assumptions, regime fit, invalidation, "
         "monitoring and the paper-first rule. Adds no rule the spec does not contain.",
         generate_trading_playbook_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "strategyId": {"type": "string"},
             "version": {"type": "string"}, "symbol": {"type": "string"},
             "interval": {"type": "string"}, "params": {"type": "object"},
             "experimentId": {"type": "string"}, "spec": {"type": "object"}}})
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
