"""Derived market analytics — computed ABOVE normalized market data.

These functions take canonical records (or plain series) and produce derived
figures. They never call a provider and are never embedded in an adapter. Each
returns a plain dict carrying the value, the method, the window and a
`derived=True` marker so a computed number is never confused with provider data.

Where a calculation already exists in `research.calculations` (Sharpe, Sortino,
VaR, beta, volatility, drawdown) this module delegates to it so there is ONE
implementation of each formula.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence


def _closes(bars: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for b in bars:
        c = getattr(b, "close", None)
        if c is None and isinstance(b, dict):
            c = b.get("close")
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            out.append(float(c))
    return out


def _highs(bars: Sequence[Any]) -> list[float]:
    return [float(getattr(b, "high", None) or (b.get("high") if isinstance(b, dict) else 0)) for b in bars]


def _lows(bars: Sequence[Any]) -> list[float]:
    return [float(getattr(b, "low", None) or (b.get("low") if isinstance(b, dict) else 0)) for b in bars]


def calculate_returns(prices: Sequence[float]) -> dict[str, Any]:
    """Simple periodic returns from a price series."""
    rets = [
        (prices[i] - prices[i - 1]) / prices[i - 1]
        for i in range(1, len(prices))
        if prices[i - 1]
    ]
    return {"returns": rets, "count": len(rets), "derived": True, "method": "simple_periodic"}


def calculate_volatility(returns: Sequence[float], periods_per_year: int = 252) -> dict[str, Any]:
    """Annualized volatility of a return series."""
    from ..research.calculations import annualized_volatility

    try:
        result = annualized_volatility(list(returns), periods_per_year=periods_per_year)
        return {"value": result.value, "method": "annualized_stdev", "derived": True,
                "periodsPerYear": periods_per_year}
    except Exception as exc:  # noqa: BLE001 - insufficient observations is honest
        return {"value": None, "error": str(exc), "derived": True}


def calculate_atr(bars: Sequence[Any], period: int = 14) -> dict[str, Any]:
    """Average True Range over OHLC bars (Wilder smoothing)."""
    highs, lows, closes = _highs(bars), _lows(bars), _closes(bars)
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return {"value": None, "error": "insufficient bars", "derived": True, "period": period}
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return {"value": atr, "method": "wilder_atr", "period": period, "derived": True}


def calculate_rsi(closes: Sequence[float], period: int = 14) -> dict[str, Any]:
    """Relative Strength Index (Wilder)."""
    if len(closes) < period + 1:
        return {"value": None, "error": "insufficient observations", "derived": True, "period": period}
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    return {"value": rsi, "method": "wilder_rsi", "period": period, "derived": True}


def _ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def calculate_macd(
    closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, Any]:
    """MACD line, signal line and histogram."""
    if len(closes) < slow + signal:
        return {"value": None, "error": "insufficient observations", "derived": True}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    histogram = macd_line[-1] - signal_line[-1]
    return {
        "macd": macd_line[-1], "signal": signal_line[-1], "histogram": histogram,
        "method": "ema_macd", "derived": True,
    }


def calculate_vwap(bars: Sequence[Any]) -> dict[str, Any]:
    """Volume-weighted average price over the supplied bars."""
    total_pv = 0.0
    total_v = 0.0
    for b in bars:
        h = getattr(b, "high", None) or (b.get("high") if isinstance(b, dict) else None)
        low = getattr(b, "low", None) or (b.get("low") if isinstance(b, dict) else None)
        close = getattr(b, "close", None) or (b.get("close") if isinstance(b, dict) else None)
        vol = getattr(b, "volume", None) or (b.get("volume") if isinstance(b, dict) else None)
        if None in (h, low, close, vol) or not vol:
            continue
        typical = (float(h) + float(low) + float(close)) / 3.0
        total_pv += typical * float(vol)
        total_v += float(vol)
    if total_v == 0:
        return {"value": None, "error": "no volume", "derived": True}
    return {"value": total_pv / total_v, "method": "typical_price_vwap", "derived": True}


def calculate_beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> dict[str, Any]:
    from ..research.calculations import beta

    try:
        result = beta(asset_returns=list(asset_returns), benchmark_returns=list(benchmark_returns))
        return {"value": result.value, "method": "ols_beta", "derived": True}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "error": str(exc), "derived": True}


def calculate_correlation(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    """Pearson correlation of two equal-length series."""
    n = min(len(a), len(b))
    if n < 2:
        return {"value": None, "error": "insufficient observations", "derived": True}
    xs, ys = list(a[:n]), list(b[:n])
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    varx = sum((x - mx) ** 2 for x in xs)
    vary = sum((y - my) ** 2 for y in ys)
    if varx == 0 or vary == 0:
        return {"value": None, "error": "zero variance", "derived": True}
    return {"value": cov / math.sqrt(varx * vary), "method": "pearson", "derived": True}


def calculate_drawdown(prices: Sequence[float]) -> dict[str, Any]:
    from ..research.calculations import max_drawdown

    try:
        result = max_drawdown(list(prices))
        return {"value": result.value, "method": "max_drawdown", "derived": True}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "error": str(exc), "derived": True}


def calculate_sharpe(returns: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 252) -> dict[str, Any]:
    from ..research.calculations import sharpe

    try:
        result = sharpe(list(returns), risk_free_rate=risk_free, periods_per_year=periods_per_year)
        return {"value": result.value, "method": "sharpe", "derived": True}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "error": str(exc), "derived": True}


def calculate_sortino(returns: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 252) -> dict[str, Any]:
    from ..research.calculations import sortino

    try:
        result = sortino(list(returns), risk_free_rate=risk_free, periods_per_year=periods_per_year)
        return {"value": result.value, "method": "sortino", "derived": True}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "error": str(exc), "derived": True}


def calculate_var(returns: Sequence[float], confidence: float = 0.95) -> dict[str, Any]:
    from ..research.calculations import value_at_risk

    try:
        result = value_at_risk(list(returns), confidence=confidence)
        return {"value": result.value, "method": "historical_var", "confidence": confidence, "derived": True}
    except Exception as exc:  # noqa: BLE001
        return {"value": None, "error": str(exc), "derived": True}


def calculate_liquidity(book: Any) -> dict[str, Any]:
    """A simple liquidity estimate from an order book (depth within 1%)."""
    from .models import OrderBook

    if not isinstance(book, OrderBook):
        return {"value": None, "error": "not an order book", "derived": True}
    mid = None
    if book.best_bid is not None and book.best_ask is not None:
        mid = (book.best_bid + book.best_ask) / 2.0
    if not mid:
        return {"value": None, "error": "no mid price", "derived": True}
    band = mid * 0.01
    depth = sum(l.quantity for l in book.bids if l.price >= mid - band)
    depth += sum(l.quantity for l in book.asks if l.price <= mid + band)
    return {"value": depth, "method": "depth_within_1pct", "derived": True}


def calculate_volume_profile(bars: Sequence[Any], bins: int = 10) -> dict[str, Any]:
    """Volume-at-price histogram over the supplied bars."""
    closes = _closes(bars)
    if not closes:
        return {"value": None, "error": "no closes", "derived": True}
    lo, hi = min(closes), max(closes)
    if hi == lo:
        return {"value": None, "error": "flat range", "derived": True}
    width = (hi - lo) / bins
    profile = [0.0] * bins
    for b in bars:
        c = getattr(b, "close", None) or (b.get("close") if isinstance(b, dict) else None)
        v = getattr(b, "volume", None) or (b.get("volume") if isinstance(b, dict) else None)
        if c is None or not v:
            continue
        idx = min(bins - 1, int((float(c) - lo) / width))
        profile[idx] += float(v)
    return {"bins": profile, "low": lo, "high": hi, "derived": True, "method": "volume_at_price"}


def calculate_orderbook_imbalance(book: Any) -> dict[str, Any]:
    from .models import OrderBook

    if not isinstance(book, OrderBook):
        return {"value": None, "error": "not an order book", "derived": True}
    return {"value": book.imbalance, "method": "bid_ask_depth_ratio", "derived": True}


def calculate_funding_zscore(rates: Sequence[float]) -> dict[str, Any]:
    """Z-score of the latest funding rate within its recent distribution."""
    if len(rates) < 2:
        return {"value": None, "error": "insufficient observations", "derived": True}
    mean = sum(rates) / len(rates)
    var = sum((r - mean) ** 2 for r in rates) / len(rates)
    sd = math.sqrt(var)
    if sd == 0:
        return {"value": None, "error": "zero variance", "derived": True}
    return {"value": (rates[-1] - mean) / sd, "method": "zscore", "derived": True}


def calculate_oi_change(current: Optional[float], previous: Optional[float]) -> dict[str, Any]:
    if current is None or previous is None:
        return {"value": None, "error": "need two observations", "derived": True}
    change = current - previous
    pct = (change / previous * 100.0) if previous else None
    return {"change": change, "changePct": pct, "method": "simple_difference", "derived": True}


# Registry so a future `calculate` tool can enumerate the set.
CALCULATORS: dict[str, Any] = {
    "returns": calculate_returns,
    "volatility": calculate_volatility,
    "atr": calculate_atr,
    "rsi": calculate_rsi,
    "macd": calculate_macd,
    "vwap": calculate_vwap,
    "beta": calculate_beta,
    "correlation": calculate_correlation,
    "drawdown": calculate_drawdown,
    "sharpe": calculate_sharpe,
    "sortino": calculate_sortino,
    "var": calculate_var,
    "liquidity": calculate_liquidity,
    "volume_profile": calculate_volume_profile,
    "orderbook_imbalance": calculate_orderbook_imbalance,
    "funding_zscore": calculate_funding_zscore,
    "oi_change": calculate_oi_change,
}


__all__ = [
    "CALCULATORS",
    "calculate_atr",
    "calculate_beta",
    "calculate_correlation",
    "calculate_drawdown",
    "calculate_funding_zscore",
    "calculate_liquidity",
    "calculate_macd",
    "calculate_oi_change",
    "calculate_orderbook_imbalance",
    "calculate_returns",
    "calculate_rsi",
    "calculate_sharpe",
    "calculate_sortino",
    "calculate_var",
    "calculate_volatility",
    "calculate_volume_profile",
    "calculate_vwap",
]
