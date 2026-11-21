"""Academic alpha zoo — documented factors on the safe formula engine.

Each entry is a *documented, versioned* definition whose behaviour is produced by
`harness.stats.formula` (no Python `eval`, no imports, no I/O). The `source` and
`reference` fields name where the idea comes from; the expression is a
re-implementation in Eclipse's DSL, not a copy of another project's code.

These are complementary to `factors.library.BUILTIN_FACTORS`: price/volume
structure, liquidity and intraday behaviour rather than the classic
momentum/value/quality set already there. A factor whose inputs the data surface
cannot supply ships `available=False` with a reason instead of a fake series.
"""

from __future__ import annotations

from typing import Any

#: Provenance shared by this zoo module.
ZOO = "academic"
SOURCE = "re-implementation of published factor definitions on harness.stats.formula"


def _factor(
    name: str,
    family: str,
    direction: str,
    lookback: int,
    description: str,
    expression: str,
    inputs: list[str],
    reference: str,
    *,
    available: bool = True,
    unavailable_reason: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "family": family,
        "direction": direction,
        "lookback": lookback,
        "description": description,
        "expression": expression,
        "inputs": inputs,
        "available": available,
        "zoo": ZOO,
        "source": SOURCE,
        "reference": reference,
    }
    if not available:
        record["unavailableReason"] = unavailable_reason
    return record


ZOO_FACTORS: list[dict[str, Any]] = [
    _factor(
        "overnight_gap_1d", "reversal", "negative", 2,
        "Overnight gap: open relative to the previous close.",
        "open / lag(close, 1) - 1", ["open", "close"],
        "overnight/intraday return decomposition (Lou, Polk & Skouras 2019)",
    ),
    _factor(
        "overnight_return_5d", "reversal", "negative", 6,
        "Mean overnight return over five sessions.",
        "rolling_mean(open / lag(close, 1) - 1, 5)", ["open", "close"],
        "overnight return premium (Cliff, Cooper & Gulen 2008)",
    ),
    _factor(
        "intraday_return_5d", "momentum", "positive", 6,
        "Mean intraday return (close/open - 1) over five sessions.",
        "rolling_mean(close / open - 1, 5)", ["open", "close"],
        "intraday momentum (Gao, Han, Li & Zhou 2018)",
    ),
    _factor(
        "close_location_value_20", "reversal", "negative", 21,
        "Where the close sits inside the day's range, averaged over 20 sessions.",
        "rolling_mean((close - low) / (high - low), 20)", ["high", "low", "close"],
        "close location value / Williams %R family",
    ),
    _factor(
        "range_position_60", "momentum", "positive", 61,
        "Close position inside the 60-session high-low range.",
        "(close - rolling_min(low, 60)) / (rolling_max(high, 60) - rolling_min(low, 60))",
        ["high", "low", "close"],
        "stochastic oscillator position (Lane)",
    ),
    _factor(
        "bollinger_position_20", "reversal", "negative", 21,
        "Close deviation from its 20-session mean in standard-deviation units.",
        "(close - sma(close, 20)) / rolling_std(close, 20)", ["close"],
        "Bollinger band position (Bollinger 1980s)",
    ),
    _factor(
        "rsi_reversal_14", "reversal", "positive", 15,
        "Negated 14-session RSI: oversold names score higher.",
        "0 - rsi(close, 14)", ["close"],
        "RSI mean reversion (Wilder 1978)",
    ),
    _factor(
        "volume_price_corr_20", "volume", "negative", 22,
        "Correlation of daily returns with daily volume changes over 20 sessions.",
        "correlation(pct_change(close, 1), pct_change(volume, 1), 20)", ["close", "volume"],
        "price-volume correlation / informed-trading proxy (Karpoff 1987)",
    ),
    _factor(
        "amihud_illiquidity_20", "liquidity", "positive", 21,
        "Amihud illiquidity: mean absolute return per unit of dollar volume.",
        "rolling_mean(abs(pct_change(close, 1)) / (volume * close), 20)",
        ["close", "volume"],
        "Amihud (2002) illiquidity ratio",
    ),
    _factor(
        "volume_shock_5_60", "volume", "negative", 61,
        "Short-window volume relative to its 60-session average.",
        "rolling_mean(volume, 5) / rolling_mean(volume, 60) - 1", ["volume"],
        "abnormal volume (Gervais, Kaniel & Mingelgrin 2001)",
    ),
    _factor(
        "drawdown_from_high_60", "momentum", "positive", 61,
        "Distance below the 60-session high (0 = at the high).",
        "close / rolling_max(close, 60) - 1", ["close"],
        "drawdown / 52-week-high proximity (George & Hwang 2004)",
    ),
    _factor(
        "up_day_ratio_60", "momentum", "positive", 61,
        "Share of the last 60 sessions that closed up.",
        "rolling_mean(greater_than(pct_change(close, 1), 0), 60)", ["close"],
        "win-rate persistence (Grinblatt & Moskowitz 2004)",
    ),
    _factor(
        "high_low_spread_20", "liquidity", "negative", 21,
        "Mean (high-low)/close over 20 sessions: a wider spread is penalised.",
        "0 - rolling_mean((high - low) / close, 20)", ["high", "low", "close"],
        "high-low spread estimator (Corwin & Schultz 2012)",
    ),
    _factor(
        "price_volume_trend_20", "volume", "positive", 21,
        "Volume-weighted momentum over 20 sessions.",
        "rolling_mean(pct_change(close, 1) * volume, 20)", ["close", "volume"],
        "price-volume trend (Granville)",
    ),
    _factor(
        "price_rank_252", "momentum", "positive", 252,
        "Where today's close sits inside its trailing 252-session window (0..1).",
        "ts_rank(close, 252)", ["close"],
        "52-week-high proximity (George & Hwang 2004), time-series rank form",
    ),
    _factor(
        "decayed_momentum_20", "momentum", "positive", 20,
        "Linearly weighted mean of the last 20 daily returns (recent weighted most).",
        "decay_linear(pct_change(close, 1), 20)", ["close"],
        "decayed momentum weighting (Jegadeesh & Titman 1993 follow-up literature)",
    ),
]


def zoo_names() -> list[str]:
    return [factor["name"] for factor in ZOO_FACTORS]


__all__ = ["SOURCE", "ZOO", "ZOO_FACTORS", "zoo_names"]
