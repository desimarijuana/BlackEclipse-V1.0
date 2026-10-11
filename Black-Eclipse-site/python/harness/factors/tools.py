"""Agent-facing Factor & Alpha Research Lab tools.

Twelve typed, permission-checked tools that execute the REAL deterministic
engine. Data-fetching tools go through the run's market gateway (the ONE data
path). Handlers return a concise text summary plus the full structured payload;
failures are structured and never fabricated.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from ..stats.base import StatsError
from . import engine as E
from . import service as S
from .models import FactorDefinition

FACTOR_TOOLS: tuple[str, ...] = (
    "list_factor_definitions",
    "inspect_factor_inputs",
    "create_factor_definition",
    "preview_factor_values",
    "run_factor_evaluation",
    "run_quantile_portfolio",
    "analyze_factor_redundancy",
    "analyze_factor_stability",
    "compose_alpha_model",
    "compare_factor_experiments",
    "validate_alpha_experiment",
    "promote_factor_to_strategy",
    "factor_capabilities",
)


def _error(tool: str, args: dict[str, Any], exc: Exception) -> tuple[str, Any]:
    code = getattr(exc, "code", "FACTOR_ERROR")
    return (f"{tool} — error [{code}]: {exc}",
            {"status": "error", "tool": tool, "error": {"code": code, "message": str(exc)}})


def _gateway(ctx: Any) -> Any:
    from ..market.tools import _gateway as market_gateway  # noqa: PLC0415

    return market_gateway(ctx)


async def _fetch(gateway: Any, symbols: list[str], interval: str, start: Optional[str],
                 end: Optional[str]) -> tuple[list[str], list[str], dict[str, dict[str, list[float]]]]:
    from ..stats.datasets import resolve_frame  # noqa: PLC0415

    close = await resolve_frame(gateway, symbols, interval=interval, start=start, end=end, field="close")
    ts = close["timestamps"]
    syms = close["symbols"]
    series: dict[str, dict[str, list[float]]] = {}
    for si, sym in enumerate(syms):
        series[sym] = {"close": [float(v) if v is not None else math.nan for v in close["values"][si]]}
    try:
        vol = await resolve_frame(gateway, symbols, interval=interval, start=start, end=end, field="volume")
        vidx = {t: i for i, t in enumerate(vol["timestamps"])}
        for si, sym in enumerate(vol["symbols"]):
            col = series.setdefault(sym, {})
            col["volume"] = [
                float(vol["values"][si][vidx[t]]) if t in vidx and vol["values"][si][vidx[t]] is not None
                else math.nan for t in ts
            ]
    except Exception:  # noqa: BLE001 - volume is optional
        pass
    return syms, [str(t) for t in ts], series


def _panel_from_args(args: dict[str, Any], key: str) -> Optional[np.ndarray]:
    raw = args.get(key)
    if raw is None:
        return None
    arr = np.asarray(raw, dtype=float)
    return arr if arr.ndim == 2 else None


# ── registry tools ───────────────────────────────────────────────────────────

async def list_factor_definitions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        factors = S.list_factors(family=args.get("family"))
        if args.get("includeLibrary"):
            factors = factors + [{"library": f} for f in S.list_library()]
        return (f"{len(factors)} factor definition(s)", {"status": "ok", "factors": factors})
    except Exception as exc:  # noqa: BLE001
        return _error("list_factor_definitions", args, exc)


async def inspect_factor_inputs(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        factor_id = args.get("factorId")
        expression = args.get("expression")
        if factor_id:
            ver = S.get_factor_version(factor_id, args.get("version"))
            if ver is None:
                raise StatsError("NOT_FOUND", f"factor {factor_id} not found", 404)
            expression = ver["expression"]
        validation = S.validate_expression(expression or "", sample=args.get("sample"))
        spec = S.get_builtin_spec(str(args.get("name"))) if args.get("name") else None
        return (f"inputs: {validation['variables']}; functions: {validation['functions']}",
                {"status": "ok", "expression": expression, "validation": validation, "library": spec})
    except Exception as exc:  # noqa: BLE001
        return _error("inspect_factor_inputs", args, exc)


async def create_factor_definition(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        defn = FactorDefinition(
            name=str(args["name"]), description=str(args.get("description") or ""),
            family=str(args.get("family") or "custom"), owner=args.get("owner"),
            direction=args.get("direction"), frequency=str(args.get("frequency") or "1d"),
            asset_class=str(args.get("assetClass") or "equity"),
            expression=str(args.get("expression") or ""), inputs=list(args.get("inputs") or []),
            parameters=dict(args.get("parameters") or {}),
            normalization=str(args.get("normalization") or "cross_sectional_zscore"),
            missing_policy=str(args.get("missingPolicy") or "drop"),
            lookback=int(args.get("lookback") or 1), output_type=str(args.get("outputType") or "float"),
            tags=list(args.get("tags") or []), pit_safe=bool(args.get("pitSafe", True)),
            factor_id=args.get("factorId"),
        )
        result = S.save_factor(defn, bump=str(args.get("bump") or "minor"), changelog=args.get("changelog"))
        v = result["version"]
        return (f"factor {result['factor']['name']} -> v{v['version']} "
                f"({'valid' if result['validation']['valid'] else 'INVALID'})",
                {"status": "ok", **result})
    except Exception as exc:  # noqa: BLE001
        return _error("create_factor_definition", args, exc)


async def preview_factor_values(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        expression = str(args.get("expression") or "")
        sample = args.get("sample")
        if sample is None and args.get("symbols"):
            _, _, series = await _fetch(_gateway(ctx), list(args["symbols"]),
                                        str(args.get("interval") or "1d"), args.get("start"), args.get("end"))
            sample = next(iter(series.values()), {})
        validation = S.validate_expression(expression, sample=sample if isinstance(sample, dict) else None)
        return (f"preview: {validation['status']}, coverage={validation.get('coverage')}",
                {"status": "ok", "validation": validation})
    except Exception as exc:  # noqa: BLE001
        return _error("preview_factor_values", args, exc)


# ── evaluation tools ─────────────────────────────────────────────────────────

async def run_factor_evaluation(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        symbols = [str(s) for s in (args.get("symbols") or [])]
        if not symbols:
            raise StatsError("INVALID_INPUT", "symbols are required")
        syms, dates, series = await _fetch(_gateway(ctx), symbols,
                                           str(args.get("interval") or "1d"),
                                           args.get("start"), args.get("end"))
        horizons = [int(h) for h in (args.get("horizons") or [1, 5, 21])]
        result = S.evaluate(
            str(args["expression"]), series, syms, horizons=horizons,
            method=str(args.get("method") or "pearson"), min_obs=int(args.get("minObs") or 5),
            periods_per_year=args.get("periodsPerYear"), expected_direction=args.get("expectedDirection"),
        )
        result["symbols"] = syms
        result["dates"] = dates
        summ = result["ic"]["summary"]
        return (f"IC mean={summ.get('meanIC')} rankIC mean={result['rankIC']['summary'].get('meanIC')}",
                {"status": "ok", "evaluation": result})
    except Exception as exc:  # noqa: BLE001
        return _error("run_factor_evaluation", args, exc)


async def run_quantile_portfolio(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        symbols = [str(s) for s in (args.get("symbols") or [])]
        if not symbols:
            raise StatsError("INVALID_INPUT", "symbols are required")
        syms, dates, series = await _fetch(_gateway(ctx), symbols,
                                           str(args.get("interval") or "1d"),
                                           args.get("start"), args.get("end"))
        result = S.quantile_portfolio(
            str(args["expression"]), series, syms, quantiles=int(args.get("quantiles") or 5),
            weighting=str(args.get("weighting") or "equal"),
            long_short=bool(args.get("longShort", True)), rebalance=int(args.get("rebalance") or 1),
            cost_bps=float(args.get("costBps") or 0.0), min_obs=int(args.get("minObs") or 5),
            periods_per_year=int(args.get("periodsPerYear") or 252),
            risk_free=float(args.get("riskFree") or 0.0),
        )
        result["dates"] = dates
        ls = result.get("longShortMetrics", {})
        return (f"long-short net total={ls.get('totalReturn')} sharpe={ls.get('sharpe')}",
                {"status": "ok", "portfolio": result})
    except Exception as exc:  # noqa: BLE001
        return _error("run_quantile_portfolio", args, exc)


async def analyze_factor_redundancy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        panels = args.get("panels")
        if panels:
            result = S.analyze_redundancy([np.asarray(p, dtype=float) for p in panels],
                                          threshold=float(args.get("threshold") or 0.9))
        else:
            expressions = list(args.get("expressions") or [])
            symbols = [str(s) for s in (args.get("symbols") or [])]
            if not expressions or not symbols:
                raise StatsError("INVALID_INPUT", "provide panels or expressions+symbols")
            syms, _, series = await _fetch(_gateway(ctx), symbols, str(args.get("interval") or "1d"),
                                           args.get("start"), args.get("end"))
            panels_built = [S.build_factor_panel(e, series, syms)[0] for e in expressions]
            result = S.analyze_redundancy(panels_built, threshold=float(args.get("threshold") or 0.9))
            result["labels"] = expressions
        return (f"redundancy: {len(result['pairs'])} pair(s) above threshold",
                {"status": "ok", "redundancy": result})
    except Exception as exc:  # noqa: BLE001
        return _error("analyze_factor_redundancy", args, exc)


async def analyze_factor_stability(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        symbols = [str(s) for s in (args.get("symbols") or [])]
        if not symbols:
            raise StatsError("INVALID_INPUT", "symbols are required")
        syms, dates, series = await _fetch(_gateway(ctx), symbols, str(args.get("interval") or "1d"),
                                           args.get("start"), args.get("end"))
        horizon = int(args.get("horizon") or 1)
        window = int(args.get("window") or 63)
        panel, warnings = S.build_factor_panel(str(args["expression"]), series, syms)
        prices = S.series_panel(series, syms, "close")
        T = min(panel.shape[0], prices.shape[0])
        fwd = E.forward_returns(prices[:T], horizon)
        ic, counts = E.cross_sectional_ic(panel[:T], fwd, min_obs=int(args.get("minObs") or 5))
        rolling = E.rolling_mean_ic(ic, window)
        # regime split by realised cross-sectional dispersion of factor values
        dispersion = np.nanstd(panel[:T], axis=1)
        finite = np.isfinite(dispersion)
        labels = np.array(["unknown"] * T, dtype=object)
        if finite.sum() >= 4:
            med = float(np.nanmedian(dispersion))
            labels[finite] = np.where(dispersion[finite] >= med, "high_dispersion", "low_dispersion")
        regimes = E.regime_ic(panel[:T], fwd, labels, min_obs=int(args.get("minObs") or 5))
        return (f"stability: {len(rolling)} rolling IC points; regimes={list(regimes)}",
                {"status": "ok", "stability": {
                    "rollingIC": E._list(rolling),  # noqa: SLF001
                    "window": window, "regimes": regimes, "warnings": warnings,
                }})
    except Exception as exc:  # noqa: BLE001
        return _error("analyze_factor_stability", args, exc)


async def compose_alpha_model(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        factors = list(args.get("factors") or [])
        if not factors:
            raise StatsError("INVALID_INPUT", "at least one factor is required")
        symbols = [str(s) for s in (args.get("symbols") or [])]
        if not symbols:
            raise StatsError("INVALID_INPUT", "symbols are required")
        syms, _, series = await _fetch(_gateway(ctx), symbols, str(args.get("interval") or "1d"),
                                       args.get("start"), args.get("end"))
        panels = [S.build_factor_panel(str(f.get("expression")), series, syms)[0] for f in factors]
        prices = S.series_panel(series, syms, "close")
        T = min(p.shape[0] for p in panels)
        fwd = E.forward_returns(prices[:T], int(args.get("horizon") or 1))
        panels = [p[:T] for p in panels]
        result = S.compose(panels, method=str(args.get("method") or "equal_zscore"),
                           weights=args.get("weights"), forward=fwd,
                           training_rows=args.get("trainingRows"))
        return (f"composed alpha via {result['method']}; weights={result['weights']}",
                {"status": "ok", "alpha": result})
    except Exception as exc:  # noqa: BLE001
        return _error("compose_alpha_model", args, exc)


# ── experiment / validation / promotion ──────────────────────────────────────

async def compare_factor_experiments(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = S.get_factor_store()
        if store is None:
            raise StatsError("UNAVAILABLE", "the factor store is unavailable", 503)
        ids = list(args.get("experimentIds") or [])
        experiments = [store.get_experiment(i) for i in ids] if ids else store.list_experiments(
            limit=int(args.get("limit") or 20))
        return (f"{len(experiments)} experiment(s)", {"status": "ok", "experiments": experiments})
    except Exception as exc:  # noqa: BLE001
        return _error("compare_factor_experiments", args, exc)


async def validate_alpha_experiment(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        evaluation = args.get("evaluation")
        portfolio = args.get("portfolio")
        if evaluation is None:
            symbols = [str(s) for s in (args.get("symbols") or [])]
            if not symbols:
                raise StatsError("INVALID_INPUT", "provide evaluation or symbols+expression")
            syms, _, series = await _fetch(_gateway(ctx), symbols, str(args.get("interval") or "1d"),
                                           args.get("start"), args.get("end"))
            evaluation = S.evaluate(str(args["expression"]), series, syms,
                                    horizons=[int(h) for h in (args.get("horizons") or [1, 5, 21])],
                                    periods_per_year=args.get("periodsPerYear"),
                                    expected_direction=args.get("expectedDirection"))
        ic_sum = (evaluation or {}).get("ic", {}).get("summary", {})
        hac = ic_sum.get("hac", {}) or {}
        qrets = None
        net_cum = None
        avg_turn = None
        if portfolio:
            qm = portfolio.get("quantileMetrics", {})
            qrets = [qm[k].get("averagePeriodReturn") for k in qm]
            ls = portfolio.get("longShortMetrics", {})
            net_cum = ls.get("totalReturn")
            avg_turn = (portfolio.get("turnover") or {}).get("average")
        gate = E.validation_gate(
            ic_mean=ic_sum.get("meanIC"), ic_pvalue=hac.get("pValue"),
            expected_direction=args.get("expectedDirection"),
            average_cross_section=ic_sum.get("averageCrossSectionSize"),
            net_cumulative=net_cum, average_turnover=avg_turn, quantile_returns=qrets,
            min_cross_section=int(args.get("minCrossSection") or 20),
            max_turnover=float(args.get("maxTurnover") or 1.0),
            alpha=float(args.get("alpha") or 0.05),
        )
        return (f"validation: {gate['outcome']} ({len(gate['checks'])} checks)",
                {"status": "ok", "validation": gate})
    except Exception as exc:  # noqa: BLE001
        return _error("validate_alpha_experiment", args, exc)


async def promote_factor_to_strategy(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        from .promotion import promote_to_strategy  # noqa: PLC0415

        factor_id = str(args["factorId"])
        quant_store = getattr(ctx, "quant_store", None)
        if quant_store is None:
            raise StatsError("DEPENDENCY_MISSING", "the quant store is unavailable in this runtime", 503)
        symbols = [str(s) for s in (args.get("symbols") or [])]
        if not symbols:
            raise StatsError("INVALID_INPUT", "symbols are required to promote and backtest", 422)
        syms, _, series = await _fetch(_gateway(ctx), symbols, str(args.get("interval") or "1d"),
                                       args.get("start"), args.get("end"))
        config = {
            "name": args.get("name"), "interval": str(args.get("interval") or "1d"),
            "quantiles": args.get("quantiles"), "longShort": args.get("longShort", True),
            "rebalance": args.get("rebalance"), "costBps": args.get("costBps"),
            "weighting": args.get("weighting"),
        }
        result = promote_to_strategy(
            factor_id=factor_id, version=args.get("version"), config=config, symbols=syms,
            series_by_symbol=series, quant_store=quant_store, actor=args.get("actor"),
            request_approval=bool(args.get("requestApproval", True)),
        )
        return (f"promoted to strategy {result['strategyId']}@{result['strategyVersion']}; "
                f"experiment {result['experimentId']}; approval requested",
                {"status": "ok", "promotion": result})
    except Exception as exc:  # noqa: BLE001
        return _error("promote_factor_to_strategy", args, exc)


async def factor_capabilities(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    return ("Factor & Alpha Research Lab: registry, IC/rank-IC/decay, quantile "
            "portfolios, alpha composition, redundancy, stability, validation gate",
            {"status": "ok", "tools": list(FACTOR_TOOLS),
             "families": ["momentum", "reversal", "value", "quality", "size", "carry",
                          "low_volatility", "liquidity", "trend"]})


def register_factor_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 60_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, long_running=long_running,
            version="1.0.0",
        ))

    _def("list_factor_definitions", "List registered factor definitions and versions.",
         list_factor_definitions, {"type": "object", "properties": {
             "family": {"type": "string"}, "includeLibrary": {"type": "boolean"}}})
    _def("inspect_factor_inputs", "Show a factor's inputs, functions and validation.",
         inspect_factor_inputs, {"type": "object", "properties": {
             "factorId": {"type": "string"}, "version": {"type": "string"},
             "expression": {"type": "string"}, "name": {"type": "string"},
             "sample": {"type": "object"}}}, 5_000)
    _def("create_factor_definition", "Create or re-version a factor definition.",
         create_factor_definition, {"type": "object", "properties": {
             "factorId": {"type": "string"}, "name": {"type": "string"},
             "description": {"type": "string"}, "family": {"type": "string"},
             "direction": {"type": "string"}, "expression": {"type": "string"},
             "inputs": {"type": "array", "items": {"type": "string"}},
             "parameters": {"type": "object"}, "lookback": {"type": "integer"},
             "tags": {"type": "array", "items": {"type": "string"}}, "bump": {"type": "string"},
             "changelog": {"type": "string"}}, "required": ["name"]}, 15_000)
    _def("preview_factor_values", "Validate and preview a factor formula on sample or fetched data.",
         preview_factor_values, {"type": "object", "properties": {
             "expression": {"type": "string"}, "sample": {"type": "object"},
             "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["expression"]}, 120_000, long_running=True)
    _def("run_factor_evaluation", "Compute IC, Rank IC and decay for a factor over a universe.",
         run_factor_evaluation, {"type": "object", "properties": {
             "expression": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "horizons": {"type": "array", "items": {"type": "integer"}}, "method": {"type": "string"},
             "minObs": {"type": "integer"}, "expectedDirection": {"type": "string"}},
             "required": ["expression", "symbols"]}, 120_000, long_running=True)
    _def("run_quantile_portfolio", "Simulate factor quantile portfolios with cost-aware accounting.",
         run_quantile_portfolio, {"type": "object", "properties": {
             "expression": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "quantiles": {"type": "integer"}, "weighting": {"type": "string"},
             "longShort": {"type": "boolean"}, "rebalance": {"type": "integer"},
             "costBps": {"type": "number"}, "periodsPerYear": {"type": "integer"}},
             "required": ["expression", "symbols"]}, 120_000, long_running=True)
    _def("analyze_factor_redundancy", "Detect highly correlated factor pairs.",
         analyze_factor_redundancy, {"type": "object", "properties": {
             "panels": {"type": "array"}, "expressions": {"type": "array", "items": {"type": "string"}},
             "symbols": {"type": "array", "items": {"type": "string"}}, "threshold": {"type": "number"}}},
         120_000, long_running=True)
    _def("analyze_factor_stability", "Rolling IC and regime-split IC for a factor.",
         analyze_factor_stability, {"type": "object", "properties": {
             "expression": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "horizon": {"type": "integer"}, "window": {"type": "integer"}},
             "required": ["expression", "symbols"]}, 120_000, long_running=True)
    _def("compose_alpha_model", "Combine factor panels into a versioned composite alpha.",
         compose_alpha_model, {"type": "object", "properties": {
             "factors": {"type": "array"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "method": {"type": "string"}, "weights": {"type": "array"},
             "trainingRows": {"type": "integer"}, "horizon": {"type": "integer"},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
             "required": ["factors", "symbols"]}, 120_000, long_running=True)
    _def("compare_factor_experiments", "List or fetch factor experiments for comparison.",
         compare_factor_experiments, {"type": "object", "properties": {
             "experimentIds": {"type": "array", "items": {"type": "string"}},
             "limit": {"type": "integer"}}})
    _def("validate_alpha_experiment", "Run the structured research-validation gate.",
         validate_alpha_experiment, {"type": "object", "properties": {
             "evaluation": {"type": "object"}, "portfolio": {"type": "object"},
             "expression": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "expectedDirection": {"type": "string"}, "alpha": {"type": "number"},
             "minCrossSection": {"type": "integer"}, "maxTurnover": {"type": "number"}},
             "required": []}, 120_000, long_running=True)
    _def("promote_factor_to_strategy",
         "Promote a validated factor into a persisted, approval-gated quant strategy and run "
         "its cross-sectional factor portfolio through the quant experiment store.",
         promote_factor_to_strategy, {"type": "object", "properties": {
             "factorId": {"type": "string"}, "version": {"type": "string"},
             "name": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}},
             "interval": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
             "quantiles": {"type": "integer"}, "weighting": {"type": "string"},
             "longShort": {"type": "boolean"}, "rebalance": {"type": "integer"},
             "costBps": {"type": "number"}, "actor": {"type": "string"},
             "requestApproval": {"type": "boolean"}}, "required": ["factorId", "symbols"]},
         120_000, long_running=True)
    _def("factor_capabilities", "Report Factor Lab capabilities.",
         factor_capabilities, {"type": "object", "properties": {}}, 5_000)
    return list(FACTOR_TOOLS)


__all__ = ["FACTOR_TOOLS", "register_factor_tools"]
