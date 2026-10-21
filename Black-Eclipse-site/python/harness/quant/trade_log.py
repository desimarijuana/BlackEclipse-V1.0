"""The trade-log analysis — what actually happened, and in what conditions.

A trade log on its own says what you made. It does not say *when* you made
it, which is the question that decides whether a strategy is worth trading:
did the money come from one lucky hour, or from a condition you could
expect to meet again?

This module answers that from the same machinery the Edge Report uses:

- every entry is placed on the **regime of its entry bar** (the causal
  trend x volatility classifier), so the log is read in the SAME vocabulary as
  the verdict, the Monte-Carlo and the report - one regime language, not two;
- the realised P&L is attributed per regime, with the share of gross positive
  P&L each regime carries;
- the **concentration** of the profit is measured: the share of gross positive
  P&L that the best few entries carry, which is the difference between an edge
  and a streak;
- each entry gets its own context (the regime, the volatility, the ATR, the
  distance from the entry to the exit in ATR terms), so a single trade can be
  interrogated.

The analysis is a **measurement**, not a verdict: it never says a strategy is
good. It says where the money came from, and it says what it could not
measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class EntryContext:
    """The market conditions at one entry."""

    trade_id: str
    symbol: str
    entry_ts: Optional[str] = None
    regime: Optional[str] = None
    trend: Optional[str] = None
    volatility: Optional[str] = None
    atr: Optional[float] = None
    bar_index: Optional[int] = None
    net_pnl: float = 0.0
    bars_held: int = 0
    r_multiple: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "symbol": self.symbol,
            "entryTs": self.entry_ts,
            "regime": self.regime,
            "trend": self.trend,
            "volatility": self.volatility,
            "atr": self.atr,
            "barIndex": self.bar_index,
            "netPnl": round(self.net_pnl, 6),
            "barsHeld": self.bars_held,
            "rMultiple": (round(self.r_multiple, 4)
                          if self.r_multiple is not None else None),
        }


@dataclass
class TradeLogAnalysis:
    """The result of reading a trade log against its own conditions."""

    entries: list[EntryContext] = field(default_factory=list)
    by_regime: dict[str, dict[str, Any]] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)
    concentration: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "entryCount": len(self.entries),
            "byRegime": self.by_regime,
            "totals": self.totals,
            "concentration": self.concentration,
            "coverage": self.coverage,
            "warnings": self.warnings,
        }


def _dataset_stamp(value: Any) -> Optional[str]:
    """Normalise a timestamp to the format the dataset stores.

    The dataset keeps timestamps as UTC to the second with no zone suffix
    (`2026-01-03T22:13:20`), while a trade log may carry an ISO string with a
    `Z`, a full-precision instant or an epoch. Both sides are normalised before
    they are matched, so a trade is never "unclassified" because two honest
    spellings of the same instant differ.
    """
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            moment = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
            return moment.strftime("%Y-%m-%dT%H:%M:%S")
        except (TypeError, ValueError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            moment = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _entry_bar_index(index_by_stamp: dict[str, int],
                     entry_ts: Optional[str]) -> Optional[int]:
    if not entry_ts:
        return None
    stamp = _dataset_stamp(entry_ts)
    if stamp is None:
        return None
    return index_by_stamp.get(stamp)


def _iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    from datetime import datetime, timezone

    try:
        return (datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc)
                .isoformat().replace("+00:00", "Z"))
    except (TypeError, ValueError, OSError):
        return None


def _atr(bars: list[dict[str, Any]], index: int, period: int = 14) -> Optional[float]:
    """The ATR at a bar (a simple rolling true range, causal)."""
    if index < 1 or index >= len(bars):
        return None
    window = bars[max(1, index - period + 1): index + 1]
    if len(window) < 2:
        return None
    ranges = []
    for previous, current in zip(window, window[1:]):
        high = float(current.get("h") or current.get("high") or 0.0)
        low = float(current.get("l") or current.get("low") or 0.0)
        prev_close = float(previous.get("c") or previous.get("close") or 0.0)
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return float(sum(ranges) / len(ranges)) if ranges else None


def analyse_trade_log(
    trades: list[dict[str, Any]],
    series_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    max_entries: int = 400,
) -> TradeLogAnalysis:
    """Read a trade log against the conditions in which each entry happened.

    `series_by_symbol` maps a symbol to the bars it traded on. A trade whose
    symbol has no bars is still counted in the totals, but it is reported as
    **unclassified** rather than being given a regime it was never measured in.
    """
    analysis = TradeLogAnalysis()
    if not trades:
        analysis.warnings.append({
            "code": "TRADE_LOG_EMPTY",
            "message": "the trade log has no trades to analyse",
        })
        return analysis

    from .regime import RegimeConfig, classify_dataset
    from .data import build_dataset, series_from_rows

    # Classify each instrument's bars ONCE, causally.
    classified: dict[str, Any] = {}
    index_by_stamp: dict[str, dict[str, int]] = {}
    for symbol, bars in (series_by_symbol or {}).items():
        # The dataset reads a numeric timestamp as SECONDS, so an epoch-ms bar
        # is normalised to the dataset's own format here rather than being
        # handed over raw and silently failing to parse.
        rows = [{
            "timestamp": _dataset_stamp(bar.get("time") or bar.get("ts")
                                       or bar.get("timestamp")),
            "open": bar.get("o") or bar.get("open") or 0.0,
            "high": bar.get("h") or bar.get("high") or 0.0,
            "low": bar.get("l") or bar.get("low") or 0.0,
            "close": bar.get("c") or bar.get("close") or 0.0,
            "volume": bar.get("v") or bar.get("volume") or 0.0,
        } for bar in bars or []]
        if not rows:
            continue
        try:
            dataset = build_dataset({symbol: series_from_rows(symbol, "1d", rows,
                                                              source="trade-log")})
            series = classify_dataset(dataset, RegimeConfig()).get(symbol)
        except Exception:  # noqa: BLE001 - an unclassifiable instrument is reported
            series = None
        if series is not None:
            classified[symbol] = series
            index_by_stamp[symbol] = {
                _dataset_stamp(stamp): i
                for i, stamp in enumerate(series.timestamps)
            }

    gross_positive = 0.0
    net_total = 0.0
    wins = 0
    losses = 0
    per_regime: dict[str, dict[str, Any]] = {}
    unclassified = 0

    for index, trade in enumerate(trades):
        symbol = str(trade.get("symbol") or "")
        pnl = _float(trade.get("netPnl") if trade.get("netPnl") is not None
                      else trade.get("pnl"))
        entry_ts = _trade_timestamp(trade)
        net_total += pnl
        if pnl > 0:
            wins += 1
            gross_positive += pnl
        elif pnl < 0:
            losses += 1

        series = classified.get(symbol)
        bar_index = _entry_bar_index(index_by_stamp.get(symbol, {}), entry_ts)
        regime = trend = volatility = None
        atr_value = None
        if series is not None and bar_index is not None:
            regime = series.labels[bar_index]
            trend = series.trend[bar_index]
            volatility = series.volatility[bar_index]
            atr_value = _atr(list(series_by_symbol.get(symbol) or []), bar_index)
        else:
            unclassified += 1

        bars_held = _int(trade.get("barsHeld"))
        r_multiple = None
        if atr_value and atr_value > 0:
            r_multiple = pnl / atr_value

        entry = EntryContext(
            trade_id=str(trade.get("id") or f"trade_{index}"),
            symbol=symbol, entry_ts=entry_ts, regime=regime, trend=trend,
            volatility=volatility, atr=atr_value, bar_index=bar_index,
            net_pnl=pnl, bars_held=bars_held, r_multiple=r_multiple,
        )
        analysis.entries.append(entry)

        bucket = per_regime.setdefault(regime or "unclassified", {
            "trades": 0, "netPnl": 0.0, "wins": 0, "grossPositive": 0.0,
        })
        bucket["trades"] += 1
        bucket["netPnl"] += pnl
        if pnl > 0:
            bucket["wins"] += 1
            bucket["grossPositive"] += pnl

    for bucket in per_regime.values():
        count = int(bucket["trades"])
        bucket["netPnl"] = round(float(bucket["netPnl"]), 6)
        bucket["grossPositive"] = round(float(bucket["grossPositive"]), 6)
        bucket["winRate"] = round(bucket["wins"] / count * 100.0, 4) if count else None
        bucket["avgPnl"] = round(float(bucket["netPnl"]) / count, 6) if count else None
        bucket["grossPositiveShare"] = (round(float(bucket["grossPositive"])
                                              / gross_positive * 100.0, 4)
                                        if gross_positive > 0 else None)
    analysis.by_regime = dict(sorted(per_regime.items(),
                                      key=lambda kv: -float(kv[1]["netPnl"])))

    count = len(analysis.entries)
    analysis.totals = {
        "trades": count,
        "netPnl": round(net_total, 6),
        "wins": wins,
        "losses": losses,
        "winRate": round(wins / count * 100.0, 4) if count else None,
        "grossPositive": round(gross_positive, 6),
    }

    # The concentration of the profit: the best few entries versus the rest.
    positives = sorted((e.net_pnl for e in analysis.entries if e.net_pnl > 0),
                       reverse=True)
    if positives and gross_positive > 0:
        top_n = max(1, int(round(len(positives) * 0.05)))
        top_share = sum(positives[:top_n]) / gross_positive * 100.0
        analysis.concentration = {
            "topEntries": top_n,
            "topShareOfGrossPositive": round(top_share, 4),
            "profitableEntries": len(positives),
            "singleEntryShare": (round(positives[0] / gross_positive * 100.0, 4)
                                 if positives else None),
        }
        if top_share >= 60.0:
            analysis.warnings.append({
                "code": "TRADE_LOG_PROFIT_CONCENTRATED",
                "message": (f"the best {top_n} of {len(positives)} profitable "
                            f"entr(ies) carry {top_share:.0f}% of the gross profit; "
                            f"the edge may be one streak rather than a rule"),
            })
    else:
        analysis.concentration = {}

    regimes_seen = {e.regime for e in analysis.entries if e.regime}
    from .regime import TREND_LABELS, VOL_LABELS

    known = {f"{t}_{v}" for t in TREND_LABELS for v in VOL_LABELS}
    analysis.coverage = {
        "regimesSeen": sorted(regimes_seen),
        "regimeCount": len(regimes_seen),
        "knownRegimes": len(known),
        "coverageShare": (round(len(regimes_seen & known) / len(known), 4)
                          if known else None),
        "unclassifiedEntries": unclassified,
        "instruments": sorted({e.symbol for e in analysis.entries if e.symbol}),
    }
    if unclassified:
        analysis.warnings.append({
            "code": "TRADE_LOG_ENTRIES_UNCLASSIFIED",
            "message": (f"{unclassified} entr(ies) could not be placed on a bar of "
                        f"their own symbol's series, so they carry no regime; they "
                        f"are counted in the totals and reported separately"),
        })

    if len(analysis.entries) > max_entries:
        analysis.entries = analysis.entries[:max_entries]
    return analysis


def _float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _trade_timestamp(trade: dict[str, Any]) -> Optional[str]:
    for key in ("exitTs", "exit_ts", "exitTime", "exit_time", "entryTs",
                "entry_ts", "entryTime", "entry_time", "timestamp", "ts"):
        value = trade.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)) and value:
            return _iso(int(value))
    return None


__all__ = ["EntryContext", "TradeLogAnalysis", "analyse_trade_log"]
