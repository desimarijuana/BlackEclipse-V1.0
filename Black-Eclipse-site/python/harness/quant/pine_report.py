"""The Pine report — grading a Pine run with Eclipse's own machinery.

A Pine script and an Eclipse strategy produce the same *kind* of evidence: a
sequence of trades on a sequence of bars. Everything downstream of that —
the metrics, the regime attribution, the Monte-Carlo, the Edge Verdict, the
Edge Report — already exists and is tested. This module is the **adapter**
that lets a Pine run use it, so a TradingView script gets an Eclipse-native
A-F grade instead of a pile of raw trades.

The adapter is deliberately thin. It does three things and nothing else:

1. **Translate** the Pine engine's trades into the engine's own trade shape.
2. **Rebuild** the equity and drawdown curves the metrics engine needs, from
   the bars the script was actually run on.
3. **Hand over** to the existing engines: `metrics.MetricsEngine` computes the
   numbers, `regime` classifies the conditions, `montecarlo` resamples the
   sequence, `verdict` grades it, `edge_report` writes the document.

What it does NOT do: re-account the trades. The Pine engine's own fills, sizes
and P&L are taken as produced. Re-deriving them here would be a second
accounting path that could disagree with the engine - and the report says so
where it matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .metrics import MetricInputs, MetricsEngine
from .models import EquityPoint, TradeRecord


def _iso(ts: Optional[int]) -> Optional[str]:
    """Epoch milliseconds → an ISO timestamp (the shape the engine uses)."""
    if ts is None:
        return None
    from datetime import datetime, timezone

    try:
        return (datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc)
                .isoformat().replace("+00:00", "Z"))
    except (TypeError, ValueError, OSError):
        return None


def pine_trades_to_records(
    trades: list[dict[str, Any]],
    *,
    symbol: str = "UNKNOWN",
) -> list[TradeRecord]:
    """Translate the Pine engine's trades into the engine's trade shape.

    The Pine engine's `profit` is taken as the NET P&L of the trade and its
    commission is reported alongside it; that is the engine's own accounting,
    and re-deriving it here would be a second accounting path.
    """
    records: list[TradeRecord] = []
    for index, trade in enumerate(trades or []):
        profit = trade.get("profit")
        try:
            net = float(profit) if profit is not None else 0.0
        except (TypeError, ValueError):
            net = 0.0
        try:
            commission = float(trade.get("commission") or 0.0)
        except (TypeError, ValueError):
            commission = 0.0
        entry_price = trade.get("entryPrice")
        exit_price = trade.get("exitPrice")
        try:
            entry = float(entry_price) if entry_price is not None else 0.0
            exit_ = float(exit_price) if exit_price is not None else 0.0
        except (TypeError, ValueError):
            entry = exit_ = 0.0
        quantity = trade.get("quantity")
        try:
            qty = float(quantity) if quantity is not None else 0.0
        except (TypeError, ValueError):
            qty = 0.0
        pnl_pct = (net / (entry * qty) * 100.0) if entry and qty else 0.0
        entry_bar = trade.get("entryBarIndex")
        exit_bar = trade.get("exitBarIndex")
        try:
            bars_held = max(0, int(exit_bar) - int(entry_bar)) if exit_bar is not None \
                and entry_bar is not None else 0
        except (TypeError, ValueError):
            bars_held = 0
        direction = str(trade.get("direction") or "long")
        records.append(TradeRecord(
            id=str(trade.get("id") or f"pine_trade_{index}"),
            symbol=symbol,
            direction="short" if direction == "short" else "long",
            entry_ts=_iso(trade.get("entryTime")),
            exit_ts=_iso(trade.get("exitTime")),
            entry_price=entry,
            exit_price=exit_,
            quantity=qty,
            gross_pnl=net,
            net_pnl=net,
            commission=commission,
            bars_held=bars_held,
            pnl_pct=pnl_pct,
            exit_reason=str(trade.get("exitId") or ""),
            mae=trade.get("maxDrawdown"),
            mfe=trade.get("maxRunup"),
        ))
    return records


def _bar_times(bars: list[dict[str, Any]]) -> list[Optional[str]]:
    out: list[Optional[str]] = []
    for bar in bars or []:
        value = bar.get("time") or bar.get("ts") or bar.get("timestamp")
        try:
            out.append(_iso(int(value)) if value is not None else None)
        except (TypeError, ValueError):
            out.append(None)
    return out


def build_equity_curve(
    bars: list[dict[str, Any]],
    records: list[TradeRecord],
    *,
    initial_capital: float,
) -> tuple[list[float], list[Optional[str]], list[EquityPoint]]:
    """Rebuild the equity curve the metrics engine reads.

    A trade's P&L lands on its EXIT bar, which is when the money is actually
    realised. Bars with no exit are carried forward.
    """
    times = _bar_times(bars)
    count = max(len(bars or []), 1)
    exits: dict[int, float] = {}
    for record in records:
        index = _exit_bar_index(record, bars)
        if index is None:
            continue
        exits[index] = exits.get(index, 0.0) + record.net_pnl

    equity: list[float] = []
    points: list[EquityPoint] = []
    value = float(initial_capital)
    for index in range(count):
        value += exits.get(index, 0.0)
        equity.append(value)
        points.append(EquityPoint(
            index=index, ts=times[index] if index < len(times) else None,
            equity=value, cash=value, positions_value=0.0,
            gross_exposure=0.0, net_exposure=0.0, leverage=0.0,
        ))
    return equity, times, points


def _exit_bar_index(record: TradeRecord, bars: list[dict[str, Any]]) -> Optional[int]:
    """The bar a trade closed on, matched by its exit timestamp."""
    if not record.exit_ts:
        return None
    times = _bar_times(bars)
    try:
        return times.index(record.exit_ts)
    except ValueError:
        return None


def drawdown_curve(equity: list[float]) -> list[dict[str, Any]]:
    """The drawdown series the metrics and the report read."""
    out: list[dict[str, Any]] = []
    peak = equity[0] if equity else 0.0
    for index, value in enumerate(equity):
        peak = max(peak, value)
        drawdown = (value / peak - 1.0) * 100.0 if peak else 0.0
        out.append({"index": index, "drawdown": drawdown})
    return out


@dataclass
class PineArtifact:
    """A Pine run, shaped like a stored experiment artifact.

    Everything downstream - the verdict, the Edge Report, the charts - reads
    this shape, so a Pine run and an Eclipse backtest are the same thing from
    there on.
    """

    artifact: dict[str, Any]
    records: list[TradeRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.artifact


def build_pine_artifact(
    result: Any,
    bars: list[dict[str, Any]],
    *,
    symbol: str = "UNKNOWN",
    timeframe: str = "1d",
    initial_capital: Optional[float] = None,
    risk_free_rate: float = 0.0,
) -> PineArtifact:
    """Turn a Pine run into the artifact shape the rest of the engine reads."""
    diagnostics = getattr(result, "diagnostics", {}) or {}
    capital = float(initial_capital
                    if initial_capital is not None
                    else (diagnostics.get("initialCapital") or 0.0))
    if capital <= 0:
        capital = 100_000.0

    records = pine_trades_to_records(list(getattr(result, "trades", []) or []),
                                     symbol=symbol)
    equity, times, points = build_equity_curve(bars, records,
                                               initial_capital=capital)
    metrics_engine = MetricsEngine(MetricInputs(
        equity=equity, timestamps=times, trades=records, exposure=points,
        interval=timeframe, initial_capital=capital, risk_free_rate=risk_free_rate,
    ))
    metrics = metrics_engine.values()
    definitions = metrics_engine.definitions()

    artifact = {
        "status": "OK",
        "metadata": {
            "strategyId": f"pine:{symbol}",
            "strategyVersion": "pine",
            "symbols": [symbol],
            "interval": timeframe,
            "engineVersion": "pine-engine",
        },
        "configuration": {
            "interval": timeframe, "initialCapital": capital,
            "riskFreeRate": risk_free_rate,
            "source": "pine",
        },
        "metrics": metrics,
        "metricDefinitions": definitions,
        "trades": [record.to_dict() for record in records],
        "equityCurve": [point.to_dict() for point in points],
        "drawdownCurve": drawdown_curve(equity),
        "warnings": [
            {
                "code": "PINE_EQUITY_MARKED_AT_EXIT",
                "message": "the equity curve is marked at each trade's EXIT bar, because "
                           "the Pine engine reports fills, not a mark-to-market curve. "
                           "Per-bar volatility is therefore understated and the "
                           "risk-adjusted ratios are optimistic relative to a "
                           "mark-to-market curve.",
            },
            {
                "code": "PINE_FILLS_ARE_THE_ENGINES_OWN",
                "message": "the fills, sizes and P&L are the Pine engine's own broker "
                           "model; they are not re-accounted here, so they are not "
                           "comparable to an Eclipse backtest's fills.",
            },
        ],
        "observability": {
            "barsProcessed": len(bars or []),
            "trades": len(records),
            "fills": len(records),
        },
        "capability": {"pine": "available", "source": "pine-engine"},
    }
    return PineArtifact(artifact=artifact, records=records)


def regime_attribution(
    bars: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify the bars the script ran on and attribute the trades to them.

    The trade is placed on its **entry bar**, by index - the Pine engine
    reports the bar index, so this needs no timestamp string matching and
    cannot be fooled by two formats of the same instant.
    """
    from .data import build_dataset, series_from_rows
    from .regime import RegimeConfig, attribute_regimes, classify_dataset

    rows = []
    for bar in bars or []:
        raw = bar.get("time") or bar.get("ts") or bar.get("timestamp")
        try:
            stamp: Optional[str] = _iso(int(raw)) if raw is not None else None
        except (TypeError, ValueError):
            stamp = str(raw) if raw is not None else None
        rows.append({
            "timestamp": stamp,
            "open": bar.get("o") or bar.get("open") or 0.0,
            "high": bar.get("h") or bar.get("high") or 0.0,
            "low": bar.get("l") or bar.get("low") or 0.0,
            "close": bar.get("c") or bar.get("close") or 0.0,
            "volume": bar.get("v") or bar.get("volume") or 0.0,
        })
    if not rows:
        return {"regimes": {}, "regimeCount": 0, "grossPositivePnl": 0.0}

    dataset = build_dataset({"PINE": series_from_rows("PINE", "1d", rows,
                                                      source="pine")})
    classified = classify_dataset(dataset, RegimeConfig())
    series = classified.get("PINE")
    if series is None:
        return {"regimes": {}, "regimeCount": 0, "grossPositivePnl": 0.0}

    labels: list[Optional[str]] = []
    normalized: list[dict[str, Any]] = []
    for trade in trades or []:
        index = trade.get("entryBarIndex")
        try:
            position = int(index) if index is not None else -1
        except (TypeError, ValueError):
            position = -1
        label = series.labels[position] if 0 <= position < len(series.labels) else None
        labels.append(label)
        try:
            profit = float(trade.get("profit") or 0.0)
        except (TypeError, ValueError):
            profit = 0.0
        normalized.append({"netPnl": profit})
    return attribute_regimes(normalized, labels)


__all__ = [
    "PineArtifact",
    "build_equity_curve",
    "build_pine_artifact",
    "drawdown_curve",
    "pine_trades_to_records",
    "regime_attribution",
]
