"""Deterministic derived-metric calculations (Phase 4, Milestone 6).

A model must never be the authority on a calculation. This module computes the
named financial metrics in pure Python from explicit, auditable inputs and
records everything needed to reproduce the number:

    calculation id + version + formula
    input evidence ids + instrument identity
    date window, observation count, frequency, missing-data policy
    units/currency, annualization, risk-free source + assumptions
    result + warnings

It rejects (never silently repairs):
  * inputs drawn from more than one instrument/identity,
  * undocumented duplicate observation dates,
  * insufficient observations for the metric,
  * non-finite values,
  * missing required assumptions (e.g. Sharpe without a risk-free rate).

Values are returned as `derived` evidence by the caller — never as reported
facts. No interpolation or backfill is performed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence

from .ids import calculation_digest

# Bump when a formula or its conventions change so stored receipts stay
# interpretable.
CALCULATION_VERSION = "1.0.0"

# Annualization conventions (trading-periods-per-year). Explicit, not inferred.
PERIODS_PER_YEAR: dict[str, int] = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "annual": 1,
}

# Minimum observations required per metric (before any calculation is attempted).
MIN_OBSERVATIONS: dict[str, int] = {
    "period_change": 2,
    "cagr": 2,
    "annualized_volatility": 2,
    "max_drawdown": 2,
    "sharpe": 3,
    "sortino": 3,
    "value_at_risk": 5,
    "beta": 3,
}


class CalculationError(ValueError):
    """A calculation could not be performed honestly from the given inputs."""


@dataclass
class CalculationResult:
    """The full, auditable record of one deterministic calculation."""

    calculationId: str
    version: str
    formula: str
    metric: str
    value: Optional[float]
    inputs: list[dict[str, Any]] = field(default_factory=list)
    inputEvidenceIds: list[str] = field(default_factory=list)
    identity: Optional[str] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    window: Optional[dict[str, str]] = None
    observationCount: int = 0
    frequency: Optional[str] = None
    missingDataPolicy: str = "reject"
    annualization: Optional[int] = None
    riskFreeRate: Optional[float] = None
    riskFreeSource: Optional[str] = None
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "OK"  # OK | ERROR

    def to_dict(self) -> dict[str, Any]:
        return {
            "calculationId": self.calculationId,
            "version": self.version,
            "formula": self.formula,
            "metric": self.metric,
            "value": self.value,
            "inputs": self.inputs,
            "inputEvidenceIds": self.inputEvidenceIds,
            "identity": self.identity,
            "currency": self.currency,
            "unit": self.unit,
            "window": self.window,
            "observationCount": self.observationCount,
            "frequency": self.frequency,
            "missingDataPolicy": self.missingDataPolicy,
            "annualization": self.annualization,
            "riskFreeRate": self.riskFreeRate,
            "riskFreeSource": self.riskFreeSource,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
            "status": self.status,
        }


@dataclass
class _Series:
    """A validated, ordered observation series."""

    dates: list[str]
    values: list[float]
    identity: Optional[str]
    currency: Optional[str]
    evidence_ids: list[str]
    frequency: Optional[str]


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _prepare(
    observations: Sequence[dict[str, Any]],
    *,
    metric: str,
    frequency: Optional[str],
    allow_duplicate_dates: bool = False,
) -> _Series:
    """Validate and order raw observations into a clean series.

    Each observation is `{"date": ..., "value": ..., "identity": ...,
    "currency": ..., "evidenceId": ...}`. Rejects non-finite values, mixed
    identities, and undocumented duplicate dates. Missing values are dropped with
    a recorded policy — never interpolated.
    """
    if not observations:
        raise CalculationError("no observations supplied")

    parsed: list[tuple[str, float, Optional[str], Optional[str], Optional[str]]] = []
    identities: set[str] = set()
    currencies: set[str] = set()
    evidence_ids: list[str] = []

    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise CalculationError(f"observation {i} is not an object")
        value = obs.get("value")
        date_str = obs.get("date")
        if date_str is None:
            raise CalculationError(f"observation {i} is missing a date")
        if value is None:
            # Missing value → drop under the explicit "reject"/"omit" policy.
            continue
        if not _is_finite(value):
            raise CalculationError(f"observation {date_str}: non-finite value {value!r}")
        identity = obs.get("identity")
        if identity:
            identities.add(str(identity))
        currency = obs.get("currency")
        if currency:
            currencies.add(str(currency))
        evidence_id = obs.get("evidenceId")
        if evidence_id:
            evidence_ids.append(str(evidence_id))
        parsed.append((str(date_str), float(value), identity, currency, evidence_id))

    if not parsed:
        raise CalculationError("no usable observations (all values missing)")

    if len(identities) > 1:
        raise CalculationError(f"observations span multiple instruments: {sorted(identities)}")
    if len(currencies) > 1:
        raise CalculationError(f"observations span multiple currencies: {sorted(currencies)}")

    dates = [p[0] for p in parsed]
    duplicates = sorted({d for d in dates if dates.count(d) > 1})
    if duplicates and not allow_duplicate_dates:
        raise CalculationError(
            f"duplicate observation date(s) without a documented resolution: {duplicates}"
        )

    # Order by date and require it to be unambiguous (ISO-ish strings compare
    # chronologically; a non-sortable set is rejected rather than guessed).
    order = sorted(range(len(parsed)), key=lambda i: parsed[i][0])
    ordered = [parsed[i] for i in order]

    minimum = MIN_OBSERVATIONS.get(metric, 2)
    if len(ordered) < minimum:
        raise CalculationError(
            f"insufficient observations for {metric}: {len(ordered)} < required {minimum}"
        )

    return _Series(
        dates=[p[0] for p in ordered],
        values=[p[1] for p in ordered],
        identity=next(iter(identities), None),
        currency=next(iter(currencies), None),
        evidence_ids=evidence_ids,
        frequency=frequency,
    )


def _base_record(
    metric: str,
    formula: str,
    series: _Series,
    observations: Sequence[dict[str, Any]],
) -> CalculationResult:
    return CalculationResult(
        # Placeholder until `_finalize` computes a stable content-sensitive id.
        calculationId="",
        version=CALCULATION_VERSION,
        formula=formula,
        metric=metric,
        value=None,
        inputs=[{k: v for k, v in o.items() if k != "raw"} for o in observations],
        inputEvidenceIds=list(series.evidence_ids),
        identity=series.identity,
        currency=series.currency,
        window={"start": series.dates[0], "end": series.dates[-1]},
        observationCount=len(series.values),
        frequency=series.frequency,
        missingDataPolicy="omit_missing_no_interpolation",
    )


def _finalize(result: CalculationResult) -> CalculationResult:
    """Assign a stable, content-sensitive calculation id.

    Computed AFTER value/assumptions/etc are set so the digest covers them:
    distinct values for the same dates, or different assumptions, never collide.
    """
    result.calculationId = calculation_digest(result)
    return result


# ── Metrics ─────────────────────────────────────────────────────────────────


def period_change(
    start_value: float,
    end_value: float,
    *,
    observations: Optional[Sequence[dict[str, Any]]] = None,
    frequency: Optional[str] = None,
) -> CalculationResult:
    """Simple period-over-period change: (end - start) / |start|.

    The smallest comparison primitive — it anchors the
    `financial_comparison` flow. Expressed as a percentage.
    """
    # Default markers sort chronologically as strings ("0001" < "0002").
    obs = observations if observations is not None else [
        {"date": "0001", "value": start_value},
        {"date": "0002", "value": end_value},
    ]
    series = _prepare(obs, metric="period_change", frequency=frequency)
    if len(series.values) < 2:
        raise CalculationError("period_change needs at least two observations")
    if series.values[0] == 0:
        raise CalculationError("period_change is undefined when the starting value is 0")
    result = _base_record("period_change", "(end - start) / |start|", series, obs)
    result.unit = "%"
    change = (series.values[-1] - series.values[0]) / abs(series.values[0])
    result.value = change * 100.0
    result.assumptions.append("percentage change relative to the first observation")
    return _finalize(result)


def cagr(
    observations: Sequence[dict[str, Any]],
    *,
    years: Optional[float] = None,
    frequency: Optional[str] = None,
) -> CalculationResult:
    """Compound annual growth rate over an explicit number of years.

    Requires an explicit `years` (or a frequency + observation count); the
    elapsed span is never inferred from row count alone.
    """
    series = _prepare(observations, metric="cagr", frequency=frequency)
    if series.values[0] <= 0 or series.values[-1] <= 0:
        raise CalculationError("CAGR requires strictly positive start and end values")
    if years is None:
        if not frequency or frequency not in PERIODS_PER_YEAR:
            raise CalculationError(
                "CAGR requires an explicit `years` or a known frequency "
                f"(one of {sorted(PERIODS_PER_YEAR)})"
            )
        years = (len(series.values) - 1) / PERIODS_PER_YEAR[frequency]
    if years <= 0:
        raise CalculationError("CAGR requires a positive time span in years")
    result = _base_record("cagr", "((end/start)^(1/years) - 1)", series, observations)
    result.unit = "%"
    years = float(years)
    result.value = ((series.values[-1] / series.values[0]) ** (1.0 / years) - 1.0) * 100.0
    result.assumptions.append(f"time span = {years:.6g} years")
    result.assumptions.append("growth is compounded annually (geometric mean)")
    return _finalize(result)


def _returns(values: list[float]) -> list[float]:
    out: list[float] = []
    for prev, curr in zip(values, values[1:]):
        if prev == 0:
            raise CalculationError("a return is undefined when a prior price is 0")
        out.append(curr / prev - 1.0)
    return out


def annualized_volatility(
    observations: Sequence[dict[str, Any]],
    *,
    frequency: str = "daily",
    risk_free_rate: Optional[float] = None,
) -> CalculationResult:
    """Annualized standard deviation of returns (sample stdev, n-1).

    Requires an explicit frequency so the annualization factor is a stated
    assumption, not a guess.
    """
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    series = _prepare(observations, metric="annualized_volatility", frequency=frequency)
    returns = _returns(series.values)
    n = len(returns)
    if n < 2:
        raise CalculationError("annualized volatility needs at least 3 observations (2 returns)")
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    periods = PERIODS_PER_YEAR[frequency]
    result = _base_record(
        "annualized_volatility",
        "stdev(returns) * sqrt(periods_per_year)",
        series,
        observations,
    )
    result.unit = "%"
    result.annualization = periods
    result.value = math.sqrt(variance) * math.sqrt(periods) * 100.0
    result.assumptions.append(f"sample standard deviation (n-1) of {frequency} returns")
    result.assumptions.append(f"annualized with {periods} periods per year")
    result.assumptions.append("returns are simple returns (no log transform)")
    if risk_free_rate is not None:
        result.riskFreeRate = float(risk_free_rate)
        result.assumptions.append("risk-free rate supplied but not used for volatility")
    return _finalize(result)


def max_drawdown(
    observations: Sequence[dict[str, Any]],
    *,
    frequency: Optional[str] = None,
) -> CalculationResult:
    """Maximum peak-to-trough drawdown over the ordered series (as a percentage).

    Returned as a negative percentage (a drawdown), or 0.0 when the series is
    monotonic up.
    """
    series = _prepare(observations, metric="max_drawdown", frequency=frequency)
    peak = series.values[0]
    worst = 0.0
    peak_date = series.dates[0]
    trough_date = series.dates[0]
    for d, value in zip(series.dates, series.values):
        if value > peak:
            peak = value
            peak_date = d
        if peak == 0:
            raise CalculationError("drawdown is undefined when a running peak is 0")
        drawdown = value / peak - 1.0
        if drawdown < worst:
            worst = drawdown
            trough_date = d
    result = _base_record(
        "max_drawdown",
        "min over t of (value_t / running_peak_t - 1)",
        series,
        observations,
    )
    result.unit = "%"
    result.value = worst * 100.0
    result.assumptions.append("drawdown measured peak-to-trough on the provided series only")
    result.warnings.append("max drawdown is path-dependent on the observation frequency")
    if worst < 0:
        result.assumptions.append(f"peak {peak_date} → trough {trough_date}")
    return _finalize(result)


def sharpe(
    observations: Sequence[dict[str, Any]],
    *,
    risk_free_rate: float,
    frequency: str = "daily",
    risk_free_source: Optional[str] = None,
) -> CalculationResult:
    """Annualized Sharpe ratio.

    Requires an EXPLICIT annual risk-free rate and its source. The per-period
    risk-free rate is derived by dividing by the annualization factor, and that
    convention is recorded. A Sharpe without a documented risk-free rate is
    rejected rather than assumed to be zero.
    """
    if risk_free_rate is None:
        raise CalculationError("sharpe requires an explicit risk-free rate (no implicit 0)")
    if not _is_finite(risk_free_rate):
        raise CalculationError(f"risk-free rate must be finite, got {risk_free_rate!r}")
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    series = _prepare(observations, metric="sharpe", frequency=frequency)
    returns = _returns(series.values)
    n = len(returns)
    if n < 2:
        raise CalculationError("sharpe needs at least 3 observations (2 returns)")
    periods = PERIODS_PER_YEAR[frequency]
    rf_per_period = float(risk_free_rate) / periods
    excess = [r - rf_per_period for r in returns]
    mean = sum(excess) / n
    variance = sum((r - mean) ** 2 for r in excess) / (n - 1)
    stdev = math.sqrt(variance)
    result = _base_record(
        "sharpe",
        "(mean(excess) / stdev(excess)) * sqrt(periods_per_year)",
        series,
        observations,
    )
    result.annualization = periods
    result.riskFreeRate = float(risk_free_rate)
    result.riskFreeSource = risk_free_source
    result.assumptions.append("annual risk-free rate is divided by periods-per-year")
    result.assumptions.append(f"annualized with {periods} periods per year")
    result.assumptions.append("sample standard deviation (n-1) of excess returns")
    if risk_free_source is None:
        result.warnings.append("risk-free rate source not documented")
    if stdev == 0:
        raise CalculationError("sharpe is undefined when excess-return volatility is 0")
    result.value = (mean / stdev) * math.sqrt(periods)
    return _finalize(result)


def sortino(
    observations: Sequence[dict[str, Any]],
    *,
    risk_free_rate: float = 0.0,
    frequency: str = "daily",
    target: Optional[float] = None,
    risk_free_source: Optional[str] = None,
) -> CalculationResult:
    """Annualized Sortino ratio: excess return over downside deviation.

    Unlike Sharpe (which penalizes ALL volatility), Sortino uses only the
    downside deviation below a target (default: the per-period risk-free rate).
    Requires an explicit frequency so the annualization factor is a stated
    assumption.
    """
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if not _is_finite(risk_free_rate):
        raise CalculationError(f"risk-free rate must be finite, got {risk_free_rate!r}")
    series = _prepare(observations, metric="sortino", frequency=frequency)
    returns = _returns(series.values)
    n = len(returns)
    if n < 2:
        raise CalculationError("sortino needs at least 3 observations (2 returns)")
    periods = PERIODS_PER_YEAR[frequency]
    rf_per_period = float(risk_free_rate) / periods
    mar = float(target) if target is not None else rf_per_period
    excess = [r - rf_per_period for r in returns]
    mean = sum(excess) / n
    downside = [min(0.0, r - mar) for r in returns]
    downside_variance = sum(d * d for d in downside) / (n - 1)
    downside_dev = math.sqrt(downside_variance)
    result = _base_record(
        "sortino",
        "(mean(excess) / downside_deviation) * sqrt(periods_per_year)",
        series,
        observations,
    )
    result.annualization = periods
    result.riskFreeRate = float(risk_free_rate)
    result.riskFreeSource = risk_free_source
    result.assumptions.append("downside deviation uses only returns below the target")
    result.assumptions.append("sample downside deviation (n-1)")
    result.assumptions.append(f"annualized with {periods} periods per year")
    if risk_free_source is None:
        result.warnings.append("risk-free rate source not documented")
    if downside_dev == 0:
        raise CalculationError("sortino is undefined when downside deviation is 0")
    result.value = (mean / downside_dev) * math.sqrt(periods)
    return _finalize(result)


def value_at_risk(
    observations: Sequence[dict[str, Any]],
    *,
    confidence: float = 0.95,
    frequency: str = "daily",
    horizon_periods: int = 1,
) -> CalculationResult:
    """Historical (empirical) Value-at-Risk over a holding horizon.

    VaR is the loss threshold not exceeded with `confidence` probability, using
    the EMPIRICAL return distribution (no normal assumption). Returned as a
    positive percentage (a loss). `horizon_periods` scales by sqrt(time).
    """
    if not (0.5 < confidence < 1.0):
        raise CalculationError(f"confidence must be in (0.5, 1.0), got {confidence!r}")
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if horizon_periods < 1:
        raise CalculationError("horizon_periods must be >= 1")
    series = _prepare(observations, metric="value_at_risk", frequency=frequency)
    returns = _returns(series.values)
    if len(returns) < 5:
        raise CalculationError("value-at-risk needs at least 6 observations (5 returns)")
    ordered = sorted(returns)
    alpha = 1.0 - confidence
    idx = max(0, min(len(ordered) - 1, int(math.floor(alpha * len(ordered)))))
    per_period = ordered[idx]
    horiz = per_period * math.sqrt(horizon_periods)
    result = _base_record(
        "value_at_risk",
        "empirical quantile of returns, scaled by sqrt(horizon)",
        series,
        observations,
    )
    result.unit = "%"
    result.warnings.append("historical VaR: only as good as the observed sample; not a tail guarantee")
    result.assumptions.append(f"confidence {confidence:.0%}; empirical (historical) distribution")
    result.assumptions.append(f"horizon {horizon_periods} period(s), scaled by sqrt(time)")
    result.value = -horiz * 100.0
    return _finalize(result)


def beta(
    observations: Sequence[dict[str, Any]],
    benchmark: Sequence[dict[str, Any]],
    *,
    frequency: str = "daily",
) -> CalculationResult:
    """Capital-asset-pricing beta of a series against a benchmark.

    beta = cov(asset, benchmark) / var(benchmark), computed on a date-ALIGNED
    set of simple returns. Mismatched lengths or a zero benchmark variance are
    rejected. Both series must share the same currency/identity rules as any
    return series.
    """
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    asset = _prepare(observations, metric="beta", frequency=frequency)
    bench = _prepare(benchmark, metric="beta", frequency=frequency)
    a_returns = _returns(asset.values)
    b_returns = _returns(bench.values)
    if len(a_returns) != len(b_returns):
        raise CalculationError(
            f"beta needs date-aligned series: {len(a_returns)} asset vs {len(b_returns)} benchmark returns"
        )
    n = len(a_returns)
    if n < 2:
        raise CalculationError("beta needs at least 3 aligned observations (2 returns)")
    mean_a = sum(a_returns) / n
    mean_b = sum(b_returns) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_returns, b_returns)) / (n - 1)
    var_b = sum((b - mean_b) ** 2 for b in b_returns) / (n - 1)
    result = _base_record(
        "beta",
        "cov(asset_returns, benchmark_returns) / var(benchmark_returns)",
        asset,
        observations,
    )
    result.assumptions.append(f"date-aligned simple {frequency} returns")
    result.assumptions.append("benchmark series supplied by the caller")
    result.warnings.append("beta is only meaningful for the benchmark and window actually used")
    if var_b == 0:
        raise CalculationError("beta is undefined when benchmark variance is 0")
    result.value = cov / var_b
    return _finalize(result)


CALCULATORS = {
    "period_change": period_change,
    "cagr": cagr,
    "annualized_volatility": annualized_volatility,
    "max_drawdown": max_drawdown,
    "sharpe": sharpe,
    "sortino": sortino,
    "value_at_risk": value_at_risk,
    "beta": beta,
}


__all__ = [
    "CALCULATION_VERSION",
    "PERIODS_PER_YEAR",
    "MIN_OBSERVATIONS",
    "CalculationError",
    "CalculationResult",
    "period_change",
    "cagr",
    "annualized_volatility",
    "max_drawdown",
    "sharpe",
    "sortino",
    "value_at_risk",
    "beta",
    "CALCULATORS",
]
