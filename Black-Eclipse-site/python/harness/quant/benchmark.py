"""Benchmark-relative metrics: alpha, beta, correlation, tracking error, IR.

Computed deterministically from an experiment's equity curve and a benchmark
price series aligned on timestamps. Never fabricated: if the two series share too
few observations, the affected metrics are returned as `None` with a reason.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .metrics import _periods_per_year


def _levels_from_equity(equity_curve: list[dict[str, Any]]) -> list[tuple[Any, float]]:
    out: list[tuple[Any, float]] = []
    for point in equity_curve:
        ts = point.get("ts")
        eq = point.get("equity")
        if ts is None or eq is None:
            continue
        out.append((ts, float(eq)))
    return out


def _levels_from_bars(rows: list[dict[str, Any]]) -> list[tuple[Any, float]]:
    out: list[tuple[Any, float]] = []
    for row in rows:
        ts = row.get("timestamp")
        close = row.get("close")
        if ts is None or close is None:
            continue
        out.append((ts, float(close)))
    return out


def _returns(levels: list[tuple[Any, float]]) -> dict[Any, float]:
    out: dict[Any, float] = {}
    for i in range(1, len(levels)):
        prev, cur = levels[i - 1][1], levels[i][1]
        if prev:
            out[levels[i][0]] = cur / prev - 1.0
    return out


def benchmark_metrics(
    equity_curve: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    *,
    interval: str = "1d",
    risk_free_rate: float = 0.0,
    asset_class: Optional[str] = None,
) -> dict[str, Any]:
    """Alpha/beta/correlation/tracking-error/IR vs a benchmark price series.

    Annualization follows the metrics engine's convention: 252 sessions for
    equities/FX/bonds (365 only for crypto, or for sub-daily bars). Pass
    `asset_class` to match the strategy; `None` is treated as non-crypto.
    """
    strat = _returns(_levels_from_equity(equity_curve))
    bench = _returns(_levels_from_bars(benchmark_rows))
    common = sorted(set(strat) & set(bench))
    if len(common) < 3:
        return {
            "available": False,
            "reason": "fewer than 3 aligned return observations between strategy and benchmark",
            "observations": len(common),
        }
    s = np.array([strat[t] for t in common], dtype=float)
    b = np.array([bench[t] for t in common], dtype=float)
    bpy = _periods_per_year(interval, asset_class)
    rf_bar = (1.0 + risk_free_rate) ** (1.0 / bpy) - 1.0 if bpy else 0.0

    var_b = float(np.var(b, ddof=1))
    mean_s, mean_b = float(np.mean(s)), float(np.mean(b))
    beta = float(np.cov(s, b, ddof=1)[0, 1] / var_b) if var_b > 0 else None
    if beta is not None:
        alpha_bar = mean_s - rf_bar - beta * (mean_b - rf_bar)
        alpha = alpha_bar * bpy
    else:
        alpha = None
    std_s, std_b = float(np.std(s, ddof=1)), float(np.std(b, ddof=1))
    corr = (float(np.corrcoef(s, b)[0, 1])
            if std_s > 0 and std_b > 0 else None)
    active = s - b
    te = float(np.std(active, ddof=1) * np.sqrt(bpy))
    ir = (float(np.mean(active) / np.std(active, ddof=1) * np.sqrt(bpy))
          if np.std(active, ddof=1) > 0 else None)
    total_s = float(np.prod(1.0 + s) - 1.0)
    total_b = float(np.prod(1.0 + b) - 1.0)
    return {
        "available": True,
        "observations": len(common),
        "annualizationBars": bpy,
        "alpha": alpha,
        "beta": beta,
        "correlation": corr,
        "trackingError": te,
        "informationRatio": ir,
        "strategyTotalReturn": total_s * 100.0,
        "benchmarkTotalReturn": total_b * 100.0,
        "excessReturn": (total_s - total_b) * 100.0,
    }


__all__ = ["benchmark_metrics"]
