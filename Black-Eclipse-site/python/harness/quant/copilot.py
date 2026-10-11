"""AI Strategy Copilot support — deterministic, grounded building blocks.

The LLM proposes; these functions compute. They turn a stored strategy into
auditable artifacts the copilot reasons over and cites:

  * `calculate_signals` — the strategy's entry/exit decision timeline, WITHOUT
    submitting a single order (signal generation never trades),
  * `build_research_plan` — an explicit research specification (splits,
    benchmark, costs, parameter search, acceptance criteria, known biases),
  * `build_report` — a Markdown report grounded in a real experiment artifact,
  * helpers to generate/validate entry-exit rules, position sizing and stops.

Nothing here fabricates results: unavailable inputs return explicit gaps, and a
report always references the experiment id it was built from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np

from . import rules as rule_eval
from .data import MarketDataset
from .engine import build_context
from .strategy import (
    Condition,
    Group,
    PositionSizing,
    StopSpec,
    StrategySpec,
    TakeProfitSpec,
    TrailingStopSpec,
    errors_only,
    validate_strategy,
)

_PRICE_FIELDS = ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4")


# ── Signals ──────────────────────────────────────────────────────────────────

@dataclass
class SignalPoint:
    index: int
    ts: Optional[str]
    symbol: str
    signal: str            # long_entry | short_entry | long_exit | short_exit | none
    reason: str
    indicators: dict[str, float]


def _warmup_bars(ctx: dict[str, np.ndarray]) -> int:
    min_bars = 2
    for key, arr in ctx.items():
        if key in _PRICE_FIELDS:
            continue
        if arr.ndim == 1 and len(arr) and np.isnan(arr).any():
            first_valid = int(np.argmax(~np.isnan(arr)))
            min_bars = max(min_bars, first_valid + 1)
    return min_bars


def calculate_signals(
    strategy: StrategySpec,
    dataset: MarketDataset,
    *,
    symbols: Optional[list[str]] = None,
    include_indicators: bool = True,
    max_points_per_symbol: int = 5000,
) -> dict[str, Any]:
    """The strategy's decision timeline (no orders, no fills, no portfolio)."""
    selected = [s.upper() for s in (symbols or strategy.universe.symbols)]
    points: dict[str, list[dict[str, Any]]] = {}
    warnings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for symbol in selected:
        series = dataset.series.get(symbol)
        if series is None:
            warnings.append({"code": "MISSING_DATA", "message": f"no series for {symbol}",
                             "detail": {"symbol": symbol}})
            continue
        higher = {tf: dataset.higher[(symbol, tf)] for tf in strategy.timeframes.confirmation
                  if (symbol, tf) in dataset.higher}
        ctx, ctx_warnings = build_context(strategy, symbol, series, higher)
        warnings.extend(w.to_dict() for w in ctx_warnings)
        warmup = _warmup_bars(ctx)
        indicator_keys = [k for k in ctx if k not in _PRICE_FIELDS]
        emitted = 0
        for i in range(series.length):
            signal, reason = "none", ""
            if i >= warmup:
                if strategy.rules.entry.long is not None and rule_eval.evaluate(
                        strategy.rules.entry.long, ctx, i):
                    signal, reason = "long_entry", "entry.long"
                elif strategy.rules.entry.short is not None and rule_eval.evaluate(
                        strategy.rules.entry.short, ctx, i):
                    signal, reason = "short_entry", "entry.short"
                elif strategy.rules.exit.long is not None and rule_eval.evaluate(
                        strategy.rules.exit.long, ctx, i):
                    signal, reason = "long_exit", "exit.long"
                elif strategy.rules.exit.short is not None and rule_eval.evaluate(
                        strategy.rules.exit.short, ctx, i):
                    signal, reason = "short_exit", "exit.short"
            if signal == "none":
                continue
            counts[signal] = counts.get(signal, 0) + 1
            point = SignalPoint(
                index=i, ts=series.timestamps[i], symbol=symbol, signal=signal, reason=reason,
                indicators=({k: _safe(ctx[k][i]) for k in indicator_keys}
                            if include_indicators else {}),
            )
            points.setdefault(symbol, []).append(asdict(point))
            emitted += 1
            if emitted >= max_points_per_symbol:
                warnings.append({"code": "SIGNALS_TRUNCATED",
                                 "message": f"{symbol}: signal list truncated",
                                 "detail": {"symbol": symbol, "cap": max_points_per_symbol}})
                break

    return {
        "strategyId": strategy.id,
        "strategyVersion": strategy.version,
        "symbols": selected,
        "warmupBars": None,
        "signalCounts": counts,
        "signals": points,
        "warnings": warnings,
    }


def _safe(value: Any) -> float:
    v = float(value)
    return v if not np.isnan(v) else float("nan")


# ── Research plan ────────────────────────────────────────────────────────────

_DEFAULT_METRICS = ["total_return", "cagr", "volatility", "sharpe", "sortino", "calmar",
                    "max_drawdown", "win_rate", "profit_factor", "expectancy", "turnover"]


def build_research_plan(
    strategy: StrategySpec,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark: Optional[str] = None,
    train_bars: int = 250,
    test_bars: int = 60,
    max_evaluations: int = 60,
    objective: str = "sharpe",
) -> dict[str, Any]:
    """A deterministic research specification the copilot can execute and cite."""
    param_space: dict[str, list[Any]] = {}
    for decl in strategy.indicators:
        for key in ("period", "fast", "slow", "signal", "num_std"):
            if key in decl.params and isinstance(decl.params[key], (int, float)):
                base = float(decl.params[key])
                axis = sorted({max(1, int(base * f)) for f in (0.5, 0.75, 1.0, 1.25, 1.5)})
                path = f"indicators.{strategy.indicators.index(decl)}.params.{key}"
                param_space[path] = axis

    return {
        "strategyId": strategy.id,
        "strategyVersion": strategy.version,
        "hypothesis": (
            f"{strategy.name} generates risk-adjusted excess return on "
            f"{', '.join(strategy.universe.symbols) or '(universe)'} at "
            f"{strategy.timeframes.primary}, net of the modelled execution costs."
        ),
        "assumptions": [
            "Signals are causal (no look-ahead); fills occur on the next bar.",
            "Execution costs use the strategy's declared commission/slippage/spread/impact/latency.",
        ],
        "universe": list(strategy.universe.symbols),
        "assetClass": strategy.asset_class,
        "timeframe": strategy.timeframes.primary,
        "dataRequirements": {
            "symbols": list(strategy.universe.symbols),
            "interval": strategy.timeframes.primary,
            "confirmation": list(strategy.timeframes.confirmation),
            "start": start, "end": end,
        },
        "periods": {
            "inSample": {"basis": "first 60% of the window"},
            "validation": {"basis": "next 20% of the window"},
            "holdout": {"basis": "final 20% — used ONCE for the final decision"},
        },
        "benchmark": benchmark or "equal-weight buy-and-hold of the universe",
        "costs": {
            "commission": strategy.execution.commission.model_dump(),
            "slippage": strategy.execution.slippage.model_dump(),
            "spread": strategy.execution.spread.model_dump(),
            "marketImpact": strategy.execution.market_impact.model_dump(),
            "latencyBars": strategy.execution.latency_bars,
        },
        "parameterSearch": {
            "space": param_space,
            "objective": objective,
            "maxEvaluations": max_evaluations,
            "method": "random",
        },
        "walkForward": {"trainBars": train_bars, "testBars": test_bars, "anchored": False},
        "robustness": ["sensitivity", "costMultipliers", "monteCarlo", "tradeConcentration"],
        "metrics": _DEFAULT_METRICS,
        "acceptanceCriteria": [
            "Out-of-sample Sharpe > 0 after costs.",
            "Walk-forward OOS does not collapse relative to IS (no large divergence).",
            "Results are not concentrated in a few trades (robustness verdict != fragile).",
        ],
        "potentialBiases": [
            "Survivorship: the universe must be point-in-time, not today's constituents.",
            "Overfitting: never select parameters on the holdout period.",
            "Look-ahead: confirmation-timeframe data is aligned to the primary bar's close.",
        ],
        "notFinancialAdvice": True,
    }


# ── Report ───────────────────────────────────────────────────────────────────

def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def build_report(experiment: dict[str, Any], artifact: Optional[dict[str, Any]] = None) -> str:
    """A Markdown report grounded ONLY in a stored experiment (+ its artifact)."""
    metrics = experiment.get("metrics", {}) or {}
    md = [
        f"# Strategy report — {experiment.get('strategyId') or '(portfolio)'} "
        f"v{experiment.get('strategyVersion')}",
        "",
        f"- **Experiment:** `{experiment.get('id')}`",
        f"- **Kind:** {experiment.get('kind')}",
        f"- **Symbols:** {', '.join(experiment.get('symbols', []) or [])}",
        f"- **Interval:** {experiment.get('interval')}",
        f"- **Period:** {experiment.get('start')} → {experiment.get('end')}",
        f"- **Initial capital:** {_fmt(experiment.get('initialCapital'))}",
        f"- **Engine version:** {experiment.get('engineVersion')} · seed {experiment.get('seed')}",
        "",
        "## Performance metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key in ("total_return", "cagr", "volatility", "sharpe", "sortino", "calmar",
                "max_drawdown", "win_rate", "profit_factor", "expectancy", "trade_count"):
        md.append(f"| {key} | {_fmt(metrics.get(key))} |")

    warnings = experiment.get("warnings", []) or []
    md += ["", "## Warnings", ""]
    md += [f"- `{w.get('code')}`: {w.get('message')}" for w in warnings] or ["- (none)"]

    if artifact:
        trades = artifact.get("trades", []) or []
        md += ["", "## Trades", "",
               f"- Count: {len(trades)}",
               f"- Execution: {len(artifact.get('orders', []) or [])} orders, "
               f"{len(artifact.get('fills', []) or [])} fills"]
        if trades:
            best = max(trades, key=lambda t: t.get("netPnl", 0))
            worst = min(trades, key=lambda t: t.get("netPnl", 0))
            md.append(f"- Best trade: {best.get('symbol')} {_fmt(best.get('netPnl'))}")
            md.append(f"- Worst trade: {worst.get('symbol')} {_fmt(worst.get('netPnl'))}")

    md += [
        "", "## Reproducibility", "",
        "Re-run this experiment with the SAME strategy version, symbols, window, "
        "initial capital and seed to obtain identical results.",
        "", "_No live orders were placed and no broker was contacted. This is a "
        "historical simulation, not investment advice._",
    ]
    return "\n".join(md)


# ── Rule / sizing / stop generators (copilot iteration helpers) ───────────────

def _operand_text(operand: Any) -> str:
    if operand.ref is not None:
        return operand.ref
    if operand.value is not None:
        return str(operand.value)
    expr = operand.expr
    if expr is not None:
        if hasattr(expr, "left"):
            return f"({_operand_text(expr.left)} {expr.op} {_operand_text(expr.right)})"
        if getattr(expr, "op", "") == "lag":
            return f"lag({_operand_text(expr.operand)}, {expr.bars})"
        return f"{expr.op}({_operand_text(expr.operand)})"
    return "?"


def _rule_to_text(node: Any) -> str:
    if isinstance(node, Condition):
        return f"{_operand_text(node.left)} {node.op} {_operand_text(node.right)}"
    if isinstance(node, Group):
        joiner = " AND " if node.combine == "all" else " OR "
        inner = [f"({_rule_to_text(c)})" if isinstance(c, Group) else _rule_to_text(c)
                 for c in node.conditions]
        return joiner.join(inner) if inner else "(empty)"
    return str(node)


def describe_rules(strategy: StrategySpec) -> dict[str, Any]:
    """Plain-language entry/exit rules (the copilot's human-readable summary)."""
    r = strategy.rules
    return {
        "entry": {
            "long": _rule_to_text(r.entry.long) if r.entry.long else None,
            "short": _rule_to_text(r.entry.short) if r.entry.short else None,
        },
        "exit": {
            "long": _rule_to_text(r.exit.long) if r.exit.long else None,
            "short": _rule_to_text(r.exit.short) if r.exit.short else None,
            "stopLoss": r.exit.stop_loss.model_dump() if r.exit.stop_loss else None,
            "takeProfit": r.exit.take_profit.model_dump() if r.exit.take_profit else None,
            "trailingStop": r.exit.trailing_stop.model_dump() if r.exit.trailing_stop else None,
            "timeStopBars": r.exit.time_stop_bars,
        },
    }


def with_position_sizing(strategy: StrategySpec, cfg: dict[str, Any]) -> tuple[StrategySpec, list[dict]]:
    """Return a copy with validated position sizing (does not persist)."""
    data = strategy.to_dict()
    data["position_sizing"] = {**data.get("position_sizing", {}), **cfg}
    spec = StrategySpec.model_validate(data)
    return spec, [i.to_dict() for i in validate_strategy(spec)]


def with_stops_and_targets(strategy: StrategySpec, cfg: dict[str, Any]) -> tuple[StrategySpec, list[dict]]:
    """Return a copy with validated stop/target config (does not persist)."""
    data = strategy.to_dict()
    exit_rules = data.setdefault("rules", {}).setdefault("exit", {})
    for key in ("stop_loss", "take_profit", "trailing_stop", "time_stop_bars"):
        if key in cfg and cfg[key] is not None:
            exit_rules[key] = cfg[key]
    spec = StrategySpec.model_validate(data)
    return spec, [i.to_dict() for i in validate_strategy(spec)]


__all__ = [
    "SignalPoint",
    "build_report",
    "build_research_plan",
    "calculate_signals",
    "describe_rules",
    "with_position_sizing",
    "with_stops_and_targets",
]
