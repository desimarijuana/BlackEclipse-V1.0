"""Deterministic risk/return metric nodes.

These are PURE computations over an incoming INDICATOR series. They add no
engine, no provider call and no state: the same input always produces the same
output. The math is intentionally small and explicit so it can be audited here
and in the tests; the heavier strategy simulations remain in
``quant_nodes.py`` (walk-forward, optimization, Monte Carlo).

Every metric is either a real number or ``None`` (undefined). A zero-denominator
case (e.g. a flat series has no Sharpe ratio) is reported as ``None`` with a
warning — never as ``0``, which would read as a real result.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .finance_nodes import numeric_series, series_payload
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
_INPUT_KINDS = ("returns", "prices")


# ── Numeric helpers ─────────────────────────────────────────────────────────


def _finite(values: Any) -> list[float]:
    out: list[float] = []
    for value in list(values):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out.append(number)
    return out


def _simple_returns(values: list[float]) -> list[float]:
    returns: list[float] = []
    for index in range(1, len(values)):
        prior = values[index - 1]
        if prior == 0:
            continue
        returns.append(values[index] / prior - 1.0)
    return returns


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float], *, sample: bool = True) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = _mean(values)
    divisor = len(values) - 1 if sample else len(values)
    variance = sum((value - mean) ** 2 for value in values) / divisor
    return math.sqrt(variance)


def _percentile(ordered: list[float], q: float) -> Optional[float]:
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2.0 + 1.0
        for offset in range(index, end + 1):
            ranks[order[offset]] = average
        index = end + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> Optional[float]:
    if len(x) != len(y) or len(x) < 2:
        return None
    mean_x = _mean(x)
    mean_y = _mean(y)
    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]
    sxx = sum(value * value for value in dx)
    syy = sum(value * value for value in dy)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum(a * b for a, b in zip(dx, dy))
    return sxy / math.sqrt(sxx * syy)


def _safe(value: Optional[float]) -> Optional[float]:
    return value if value is not None and math.isfinite(value) else None


def _align(left: list[float], right: list[float]) -> tuple[list[float], list[float]]:
    """Trim to the shared length and keep pairwise-finite points only."""
    length = min(len(left), len(right))
    x = left[-length:]
    y = right[-length:]
    pairs = [(a, b) for a, b in zip(x, y) if math.isfinite(a) and math.isfinite(b)]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _input_series(
    context: NodeExecContext,
    port: str,
    label: str,
    input_kind: str,
) -> list[float]:
    values = _finite(numeric_series(context.inputs.get(port), label))
    if input_kind == "prices":
        values = _simple_returns(values)
    if len(values) < 2:
        raise ValueError(f"{label} needs at least two finite points")
    return values


def _closes(rows: Any, label: str) -> list[float]:
    closes: list[float] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("close") is None:
            continue
        try:
            close = float(row["close"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(close):
            closes.append(close)
    if len(closes) < 2:
        raise ValueError(f"{label} found fewer than two usable close prices")
    return closes


def _series_source(payload: Any, label: str) -> tuple[list[float], str]:
    """Accept an INDICATOR payload, a raw number list, or OHLCV bars.

    Returning the detected source lets the caller pick the right default
    interpretation: bars are price levels, not returns.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("values"), list):
            return _finite(payload["values"]), "indicator"
        if isinstance(payload.get("rows"), list):
            return _closes(payload["rows"], label), "ohlcv"
    if isinstance(payload, list):
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in payload):
            return _finite(payload), "indicator"
        if all(isinstance(row, dict) for row in payload):
            return _closes(payload, label), "ohlcv"
    raise ValueError(f"{label} expects an indicator series or OHLCV bars")


# ── Executors ───────────────────────────────────────────────────────────────


def exec_risk_metrics(context: NodeExecContext) -> dict[str, Any]:
    values, source = _series_source(context.inputs.get("values"), "quant.risk_metrics")
    configured = str(context.config.get("inputKind") or "returns")
    if configured not in _INPUT_KINDS:
        raise ValueError("inputKind must be returns or prices")
    # OHLCV bars are price levels; a wired bar series wins over the stored
    # preference so `history -> risk_metrics` works without an extra node.
    input_kind = "prices" if source == "ohlcv" else configured
    returns = _simple_returns(values) if input_kind == "prices" else values
    if len(returns) < 2:
        raise ValueError("quant.risk_metrics needs at least two finite points")
    warnings: list[str] = []

    periods = int(context.config.get("periodsPerYear", 252))
    confidence = float(context.config.get("confidence", 0.95))
    risk_free = float(context.config.get("riskFreeRate", 0))
    period_free = risk_free / periods

    mean = _mean(returns)
    stdev = _stdev(returns)
    downside = _stdev([min(value, 0.0) for value in returns], sample=False)

    annual_return = mean * periods
    annual_vol = stdev * math.sqrt(periods) if stdev is not None else None
    sharpe = None
    if stdev is not None and stdev > 0:
        sharpe = (mean - period_free) / stdev * math.sqrt(periods)
    else:
        warnings.append("sharpe is undefined for a zero-variance series")

    sortino = None
    if downside is not None and downside > 0:
        sortino = (mean - period_free) / downside * math.sqrt(periods)
    else:
        warnings.append("sortino is undefined (no downside deviation)")

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)

    ordered = sorted(returns)
    var = _percentile(ordered, 1.0 - confidence)
    tail = [value for value in returns if var is not None and value <= var]
    cvar = _mean(tail) if tail else None

    n = len(returns)
    skew = None
    kurtosis = None
    if stdev is not None and stdev > 0:
        third = sum((value - mean) ** 3 for value in returns) / n
        fourth = sum((value - mean) ** 4 for value in returns) / n
        skew = third / (stdev ** 3)
        kurtosis = fourth / (stdev ** 4) - 3.0

    metrics = {
        "observations": n,
        "mean": _safe(mean),
        "stdev": _safe(stdev),
        "annualizedReturn": _safe(annual_return),
        "annualizedVolatility": _safe(annual_vol),
        "sharpe": _safe(sharpe),
        "sortino": _safe(sortino),
        "maxDrawdown": _safe(max_drawdown),
        "var": _safe(var),
        "cvar": _safe(cvar),
        "best": _safe(max(returns)),
        "worst": _safe(min(returns)),
        "skew": _safe(skew),
        "kurtosis": _safe(kurtosis),
        "hitRate": _safe(sum(1 for value in returns if value > 0) / n),
        "confidence": confidence,
        "periodsPerYear": periods,
        "inputKind": input_kind,
        "source": source,
        "notes": warnings,
    }
    context.emit(
        f"risk: {n} returns, vol {annual_vol:.4f}" if annual_vol is not None else f"risk: {n} returns"
    )
    return {"metrics": metrics}


def exec_drawdown(context: NodeExecContext) -> dict[str, Any]:
    values, source = _series_source(context.inputs.get("values"), "quant.drawdown")
    configured = str(context.config.get("inputKind") or "equity")
    if configured not in ("equity", "returns"):
        raise ValueError("inputKind must be equity or returns")
    # OHLCV bars are price levels, so they are already an equity curve.
    input_kind = "equity" if source == "ohlcv" else configured
    if input_kind == "returns":
        if not values:
            raise ValueError("quant.drawdown needs at least one return")
        equity: list[float] = [1.0]
        for value in values:
            equity.append(equity[-1] * (1.0 + value))
    else:
        equity = values
    if len(equity) < 2:
        raise ValueError("quant.drawdown needs at least two finite points")

    drawdowns: list[float] = []
    running_peak = equity[0]
    peak_index = 0
    max_drawdown = 0.0
    max_index = 0
    current_streak = 0
    longest_streak = 0
    for index, value in enumerate(equity):
        if value > running_peak:
            running_peak = value
            peak_index = index
        drawdown = value / running_peak - 1.0 if running_peak else 0.0
        drawdowns.append(drawdown)
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_index = index
        if drawdown < 0:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0

    metrics = {
        "observations": len(equity),
        "maxDrawdown": max_drawdown,
        "currentDrawdown": drawdowns[-1],
        "peakValue": equity[peak_index] if peak_index < len(equity) else None,
        "troughIndex": max_index,
        "longestDrawdownBars": longest_streak,
        "recovered": drawdowns[-1] >= 0,
        "inputKind": input_kind,
        "source": source,
    }
    context.emit(f"drawdown: max {max_drawdown:.4f}, current {drawdowns[-1]:.4f}")
    return {
        "values": series_payload("drawdown", {"drawdown": drawdowns}),
        "metrics": metrics,
    }


def exec_correlation(context: NodeExecContext) -> dict[str, Any]:
    method = str(context.config.get("method") or "pearson")
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be pearson or spearman")
    raw_window = int(context.config.get("window", 0))
    left = _finite(numeric_series(context.inputs.get("a"), "quant.correlation (a)"))
    right = _finite(numeric_series(context.inputs.get("b"), "quant.correlation (b)"))
    x, y = _align(left, right)
    if len(x) < 2:
        raise ValueError("quant.correlation needs at least two shared finite points")
    if method == "spearman":
        x = _ranks(x)
        y = _ranks(y)

    r = _pearson(x, y)
    rolling: list[Optional[float]] = []
    window = max(0, raw_window)
    if window > 1:
        for index in range(len(x) - window + 1):
            rolling.append(_pearson(x[index:index + window], y[index:index + window]))
    result = {
        "method": method,
        "r": _safe(r),
        "r2": _safe(r * r) if r is not None else None,
        "n": len(x),
        "window": window,
        "rolling": rolling,
        "last": rolling[-1] if rolling else _safe(r),
    }
    context.emit(f"correlation {method}: r={result['r']} over {len(x)} points")
    return {"correlation": result}


def exec_beta(context: NodeExecContext) -> dict[str, Any]:
    input_kind = str(context.config.get("inputKind") or "returns")
    if input_kind not in _INPUT_KINDS:
        raise ValueError("inputKind must be returns or prices")
    asset = _input_series(context, "asset", "quant.beta (asset)", input_kind)
    benchmark = _input_series(context, "benchmark", "quant.beta (benchmark)", input_kind)
    x, y = _align(asset, benchmark)
    if len(x) < 2:
        raise ValueError("quant.beta needs at least two shared finite points")

    periods = int(context.config.get("periodsPerYear", 252))
    risk_free = float(context.config.get("riskFreeRate", 0))
    period_free = risk_free / periods
    mean_x = _mean(x)
    mean_y = _mean(y)
    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]
    variance = sum(value * value for value in dy) / (len(y) - 1)
    if variance <= 0:
        raise ValueError("quant.beta needs a benchmark with non-zero variance")
    covariance = sum(a * b for a, b in zip(dx, dy)) / (len(x) - 1)
    beta = covariance / variance
    alpha_period = mean_x - period_free - beta * (mean_y - period_free)
    r = _pearson(x, y)

    raw_window = int(context.config.get("window", 0))
    rolling: list[Optional[float]] = []
    window = max(0, raw_window)
    if window > 1:
        for index in range(len(x) - window + 1):
            wx = x[index:index + window]
            wy = y[index:index + window]
            my = _mean(wy)
            var = sum((value - my) ** 2 for value in wy) / (len(wy) - 1)
            if var <= 0:
                rolling.append(None)
                continue
            mx = _mean(wx)
            cov = sum((a - mx) * (b - my) for a, b in zip(wx, wy)) / (len(wx) - 1)
            rolling.append(cov / var)

    result = {
        "beta": _safe(beta),
        "alpha": _safe(alpha_period * periods),
        "alphaPerPeriod": _safe(alpha_period),
        "correlation": _safe(r),
        "r2": _safe(r * r) if r is not None else None,
        "n": len(x),
        "window": window,
        "rolling": rolling,
        "last": rolling[-1] if rolling else _safe(beta),
        "periodsPerYear": periods,
        "inputKind": input_kind,
    }
    context.emit(f"beta {result['beta']} over {len(x)} points")
    return {"beta": result}


# ── Definitions ─────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type)


def build_quant_metric_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.risk_metrics",
            version="1.0.0",
            label="Risk metrics",
            category="quant",
            # `any` on purpose: choose returns/prices with an indicator series,
            # or wire OHLCV bars directly (close prices are used).
            inputs=(_port("values", "Values", PortType.ANY),),
            outputs=(_port("metrics", "Metrics", PortType.OBJECT),),
            config_fields=(
                ConfigField("inputKind", "enum", "returns", enum=_INPUT_KINDS),
                ConfigField("riskFreeRate", "number", 0, minimum=-0.5, maximum=0.5),
                ConfigField("confidence", "number", 0.95, minimum=0.5, maximum=0.999),
                ConfigField("periodsPerYear", "integer", 252, minimum=1, maximum=1_000),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_risk_metrics,
            metadata={
                "docs": (
                    "Volatility, Sharpe/Sortino, drawdown, historical VaR/CVaR, skew and "
                    "kurtosis over a returns series, a price series, or OHLCV bars "
                    "(close prices). An undefined ratio is null with a note, never zero."
                ),
            },
        ),
        NodeDef(
            type="quant.drawdown",
            version="1.0.0",
            label="Drawdown",
            category="quant",
            # See `quant.risk_metrics`: an OHLCV series is accepted directly.
            inputs=(_port("values", "Values", PortType.ANY),),
            outputs=(
                _port("values", "Values", PortType.INDICATOR),
                _port("metrics", "Metrics", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("inputKind", "enum", "equity", enum=("equity", "returns")),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_drawdown,
            metadata={
                "docs": (
                    "Underwater curve from an equity series, OHLCV bars (close prices) or "
                    "returns converted to an equity curve, with max/current drawdown, "
                    "trough index and recovery."
                ),
            },
        ),
        NodeDef(
            type="quant.correlation",
            version="1.0.0",
            label="Correlation",
            category="quant",
            inputs=(
                _port("a", "Series A", PortType.INDICATOR),
                _port("b", "Series B", PortType.INDICATOR),
            ),
            outputs=(_port("correlation", "Correlation", PortType.OBJECT),),
            config_fields=(
                ConfigField("method", "enum", "pearson", enum=("pearson", "spearman")),
                ConfigField("window", "integer", 0, minimum=0, maximum=2_000),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_correlation,
            metadata={
                "docs": (
                    "Pairwise correlation over the shared finite points, with an optional "
                    "rolling window. `window: 0` computes one full-sample value."
                ),
            },
        ),
        NodeDef(
            type="quant.beta",
            version="1.0.0",
            label="Beta & alpha",
            category="quant",
            inputs=(
                _port("asset", "Asset", PortType.INDICATOR),
                _port("benchmark", "Benchmark", PortType.INDICATOR),
            ),
            outputs=(_port("beta", "Beta", PortType.OBJECT),),
            config_fields=(
                ConfigField("inputKind", "enum", "returns", enum=_INPUT_KINDS),
                ConfigField("riskFreeRate", "number", 0, minimum=-0.5, maximum=0.5),
                ConfigField("periodsPerYear", "integer", 252, minimum=1, maximum=1_000),
                ConfigField("window", "integer", 0, minimum=0, maximum=2_000),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_beta,
            metadata={
                "docs": (
                    "CAPM beta and annualized alpha against a benchmark, with correlation, "
                    "R² and an optional rolling window. A flat benchmark is an explicit failure."
                ),
            },
        ),
    ]


__all__ = [
    "build_quant_metric_nodes",
    "exec_risk_metrics",
    "exec_drawdown",
    "exec_correlation",
    "exec_beta",
]
