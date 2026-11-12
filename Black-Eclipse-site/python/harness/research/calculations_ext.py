"""Advanced deterministic risk/return metrics (split from calculations.py).

This module holds the return, correlation, covariance, tail-risk, drawdown,
rolling and matrix metrics. It reuses the validation and result machinery in
`research.calculations` (the ONE implementation of `_prepare`, `_returns`,
`_base_record`, `_finalize` and the period conventions), so no guard or formula
is duplicated. `research.calculations` re-exports these names, so the public
import surface is unchanged.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Any, Optional, Sequence

from .calculations import (
    CALCULATION_VERSION,
    MIN_OBSERVATIONS,
    PERIODS_PER_YEAR,
    RETURN_METHODS,
    CalculationError,
    CalculationResult,
    _base_record,
    _finalize,
    _is_finite,
    _prepare,
    _returns,
)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _sample_variance(values: Sequence[float], *, ddof: int = 1) -> float:
    n = len(values)
    if n - ddof <= 0:
        raise CalculationError(f"variance requires > {ddof} observations")
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / (n - ddof)


def _cumulative(returns: Sequence[float], method: str) -> float:
    if method == "log":
        return math.exp(sum(returns)) - 1.0
    total = 1.0
    for r in returns:
        total *= 1.0 + r
    return total - 1.0

# â”€â”€ Returns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def cumulative_return(
    observations: Sequence[dict[str, Any]],
    *,
    method: str = "simple",
    frequency: Optional[str] = None,
) -> CalculationResult:
    """Total compounded return over the whole ordered series (as a percentage).

    `method="simple"` compounds each period's simple return; `method="log"` sums
    log returns and exponentiates. A zero/negative price is rejected for a log
    return rather than silently coerced.
    """
    if method not in RETURN_METHODS:
        raise CalculationError(f"unknown return method {method!r}; expected {RETURN_METHODS}")
    series = _prepare(observations, metric="cumulative_return", frequency=frequency)
    returns = _returns(series.values, method)
    result = _base_record(
        "cumulative_return",
        "prod(1 + r_t) - 1" if method == "simple" else "exp(sum(ln(P_t/P_{t-1}))) - 1",
        series,
        observations,
    )
    result.unit = "%"
    result.value = _cumulative(returns, method) * 100.0
    result.assumptions.append(f"{method} returns")
    result.assumptions.append(f"compounded over {len(returns)} period(s)")
    return _finalize(result)


def annualized_return(
    observations: Sequence[dict[str, Any]],
    *,
    frequency: Optional[str] = None,
    years: Optional[float] = None,
    method: str = "simple",
) -> CalculationResult:
    """Geometric annualized return over an explicit span.

    Requires either an explicit `years` or a known `frequency` (the span is never
    inferred from row count alone). Distinct from `cagr`: it works from a price
    series and records the return convention.
    """
    if method not in RETURN_METHODS:
        raise CalculationError(f"unknown return method {method!r}; expected {RETURN_METHODS}")
    series = _prepare(observations, metric="annualized_return", frequency=frequency)
    returns = _returns(series.values, method)
    if years is None:
        if not frequency or frequency not in PERIODS_PER_YEAR:
            raise CalculationError(
                "annualized_return requires an explicit `years` or a known frequency "
                f"(one of {sorted(PERIODS_PER_YEAR)})"
            )
        years = len(returns) / PERIODS_PER_YEAR[frequency]
    if years <= 0:
        raise CalculationError("annualized_return requires a positive time span in years")
    years = float(years)
    cumulative = _cumulative(returns, method)
    if cumulative <= -1.0:
        raise CalculationError("annualized_return is undefined when the cumulative return is -100% or worse")
    result = _base_record(
        "annualized_return",
        "((1 + cumulative_return)^(1/years)) - 1",
        series,
        observations,
    )
    result.unit = "%"
    result.annualization = PERIODS_PER_YEAR.get(frequency) if frequency else None
    result.value = ((1.0 + cumulative) ** (1.0 / years) - 1.0) * 100.0
    result.assumptions.append(f"{method} returns")
    result.assumptions.append(f"time span = {years:.6g} years")
    return _finalize(result)


# â”€â”€ Alignment + correlation + covariance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _aligned_pairs(
    x_obs: Sequence[dict[str, Any]],
    y_obs: Sequence[dict[str, Any]],
    *,
    metric: str,
) -> tuple[list[str], list[float], list[float]]:
    """Two validated series joined on the INTERSECTION of their dates.

    A beta/correlation over mismatched timestamps is meaningless, so the join is
    on exact date equality (never positional) and an insufficient overlap is
    refused with the count.
    """
    xs = _prepare(x_obs, metric=metric)
    ys = _prepare(y_obs, metric=metric)
    xd = dict(zip(xs.dates, xs.values))
    yd = dict(zip(ys.dates, ys.values))
    common = sorted(set(xd) & set(yd))
    minimum = MIN_OBSERVATIONS.get(metric, 2)
    if len(common) < minimum:
        raise CalculationError(
            f"{metric} needs >= {minimum} date-aligned observations; found {len(common)}"
        )
    return common, [xd[d] for d in common], [yd[d] for d in common]


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks (1-based), ties resolved to their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    ma, mb = _mean(a), _mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        raise CalculationError("correlation is undefined when a series has zero variance")
    return cov / math.sqrt(va * vb)


def _kendall_tau_b(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    concordant = discordant = ties_a = ties_b = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            da = a[i] - a[j]
            db = b[i] - b[j]
            if da == 0 and db == 0:
                ties_a += 1
                ties_b += 1
            elif da == 0:
                ties_a += 1
            elif db == 0:
                ties_b += 1
            elif (da > 0) == (db > 0):
                concordant += 1
            else:
                discordant += 1
    n0 = n * (n - 1) / 2.0
    denom = math.sqrt((n0 - ties_a) * (n0 - ties_b))
    if denom == 0:
        raise CalculationError("Kendall tau is undefined when a series is constant")
    return (concordant - discordant) / denom


def correlation(
    x_observations: Sequence[dict[str, Any]],
    y_observations: Sequence[dict[str, Any]],
    *,
    method: str = "pearson",
) -> CalculationResult:
    """Correlation between two date-aligned series: pearson, spearman or kendall.

    Always clamped into [-1, 1] and rejected when a series has no variance.
    """
    if method not in ("pearson", "spearman", "kendall"):
        raise CalculationError(f"unknown correlation method {method!r}; expected pearson, spearman or kendall")
    common, a, b = _aligned_pairs(x_observations, y_observations, metric="correlation")
    if method == "spearman":
        value = _pearson(_rank(a), _rank(b))
        formula = "pearson correlation of the average ranks"
    elif method == "kendall":
        value = _kendall_tau_b(a, b)
        formula = "(concordant - discordant) / sqrt((n0 - ties_a)(n0 - ties_b))"
    else:
        value = _pearson(a, b)
        formula = "cov(x, y) / (sd(x) * sd(y))"
    value = max(-1.0, min(1.0, value))
    xs = _prepare(x_observations, metric="correlation")
    result = _base_record("correlation", formula, xs, x_observations)
    result.value = value
    result.assumptions.append(f"{method} correlation on {len(common)} date-aligned observation(s)")
    result.detail = {"method": method, "alignedDates": common, "observations": len(common)}
    return _finalize(result)


def covariance(
    x_observations: Sequence[dict[str, Any]],
    y_observations: Sequence[dict[str, Any]],
    *,
    ddof: int = 1,
) -> CalculationResult:
    """Covariance between two date-aligned series.

    `ddof=1` is the sample covariance (default); `ddof=0` is the population
    covariance. The choice is recorded as an assumption.
    """
    if ddof not in (0, 1):
        raise CalculationError(f"ddof must be 0 (population) or 1 (sample), got {ddof!r}")
    common, a, b = _aligned_pairs(x_observations, y_observations, metric="covariance")
    n = len(a)
    if n - ddof <= 0:
        raise CalculationError("covariance needs more observations than the ddof")
    ma, mb = _mean(a), _mean(b)
    value = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - ddof)
    xs = _prepare(x_observations, metric="covariance")
    result = _base_record(
        "covariance",
        "sum((x - mean_x) * (y - mean_y)) / (n - ddof)",
        xs,
        x_observations,
    )
    result.value = value
    result.detail = {"ddof": ddof, "observations": n, "alignedDates": common}
    result.assumptions.append(f"{'sample' if ddof == 1 else 'population'} covariance (ddof={ddof})")
    return _finalize(result)


def alpha(
    observations: Sequence[dict[str, Any]],
    benchmark: Sequence[dict[str, Any]],
    *,
    risk_free_rate: float,
    frequency: str = "daily",
    method: str = "simple",
) -> CalculationResult:
    """Jensen's alpha: Rp - [Rf + beta * (Rm - Rf)], annualized.

    Uses date-aligned returns; the beta and the risk-free rate are recorded on the
    result. An implicit risk-free rate is never assumed.
    """
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if risk_free_rate is None or not _is_finite(risk_free_rate):
        raise CalculationError("alpha requires a finite, explicit risk-free rate")
    _common, a_prices, b_prices = _aligned_pairs(observations, benchmark, metric="alpha")
    a = _returns(a_prices, method)
    b = _returns(b_prices, method)
    n = len(a)
    if n < 2:
        raise CalculationError("alpha needs at least 3 aligned observations (2 returns)")
    ma, mb = _mean(a), _mean(b)
    var_b = _sample_variance(b, ddof=1)
    if var_b == 0:
        raise CalculationError("alpha is undefined when benchmark variance is 0")
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
    beta_value = cov / var_b
    periods = PERIODS_PER_YEAR[frequency]
    rf_per = float(risk_free_rate) / periods
    alpha_per = ma - (rf_per + beta_value * (mb - rf_per))
    xs = _prepare(observations, metric="alpha")
    result = _base_record(
        "alpha",
        "mean(Rp) - [Rf_per_period + beta * (mean(Rm) - Rf_per_period)]; annualized",
        xs,
        observations,
    )
    result.unit = "%"
    result.annualization = periods
    result.riskFreeRate = float(risk_free_rate)
    result.value = alpha_per * periods * 100.0
    result.detail = {"beta": beta_value, "frequency": frequency, "method": method, "observations": n}
    result.assumptions.append(f"date-aligned {method} {frequency} returns")
    result.assumptions.append(f"annual risk-free rate {risk_free_rate} divided by {periods} periods per year")
    result.assumptions.append("alpha annualized by multiplying the per-period alpha by periods-per-year")
    return _finalize(result)


# â”€â”€ Downside / tail risk â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _var_index(n: int, confidence: float) -> int:
    """Nearest-rank tail index: the last of the ceil(alpha*n) worst observations."""
    alpha = 1.0 - confidence
    return max(0, min(n - 1, int(math.ceil(alpha * n - 1e-9)) - 1))


def cvar(
    observations: Sequence[dict[str, Any]],
    *,
    confidence: float = 0.95,
    frequency: str = "daily",
    horizon_periods: int = 1,
    method: str = "historical",
    simulations: int = 10_000,
    seed: int = 0,
    distribution: str = "normal",
    ddof: int = 1,
) -> CalculationResult:
    """Conditional VaR / Expected Shortfall â€” the mean loss beyond the VaR cutoff.

    Returned as a positive percentage (a loss). `historical` averages the worst
    empirical returns; `parametric` uses the normal expected-shortfall closed
    form; `monte_carlo` simulates a seeded return distribution. For every method
    the result is guaranteed at least as severe as the matching VaR.
    """
    if not (0.5 < confidence < 1.0):
        raise CalculationError(f"confidence must be in (0.5, 1.0), got {confidence!r}")
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if horizon_periods < 1:
        raise CalculationError("horizon_periods must be >= 1")
    if method not in ("historical", "parametric", "monte_carlo"):
        raise CalculationError(f"unknown cvar method {method!r}; expected historical, parametric or monte_carlo")
    series = _prepare(observations, metric="cvar", frequency=frequency)
    returns = _returns(series.values, "simple")
    if len(returns) < 5:
        raise CalculationError("cvar needs at least 6 observations (5 returns)")
    alpha = 1.0 - confidence
    warnings: list[str] = []
    provenance: dict[str, Any] = {"method": method, "confidence": confidence, "horizonPeriods": horizon_periods}

    if method == "parametric":
        mu = _mean(returns)
        sigma = math.sqrt(_sample_variance(returns, ddof=ddof))
        if sigma == 0:
            raise CalculationError("parametric cvar is undefined when return volatility is 0")
        z = NormalDist().inv_cdf(alpha)          # standard-normal quantile
        es_period = mu - sigma * (NormalDist().pdf(z) / alpha)
        value = -es_period * math.sqrt(horizon_periods) * 100.0
        provenance.update({"distribution": "normal", "mean": mu, "stdev": sigma, "ddof": ddof})
        warnings.append("parametric CVaR assumes normally distributed returns")
        formula = "tail mean of a normal distribution: mu - sigma * phi(z_alpha) / alpha"
    elif method == "monte_carlo":
        if simulations < 1000:
            raise CalculationError("monte_carlo cvar requires at least 1000 simulations")
        if distribution not in ("normal", "empirical"):
            raise CalculationError(f"unknown distribution {distribution!r}; expected normal or empirical")
        draws = _simulate_horizon_returns(returns, horizon_periods, simulations, seed, distribution)
        ordered = sorted(draws)
        idx = _var_index(len(ordered), confidence)
        tail = ordered[: idx + 1]
        value = -_mean(tail) * 100.0
        provenance.update({
            "distribution": distribution, "simulations": simulations, "seed": seed,
            "randomGenerator": "random.Random (Mersenne Twister)",
        })
        warnings.append("Monte-Carlo CVaR is reproducible only for the recorded seed and simulation count")
        formula = "mean of the worst simulated horizon returns (seeded)"
    else:
        ordered = sorted(returns)
        idx = _var_index(len(ordered), confidence)
        tail = ordered[: idx + 1]
        per_period = _mean(tail)
        value = -per_period * math.sqrt(horizon_periods) * 100.0
        provenance["tailObservations"] = len(tail)
        warnings.append("historical CVaR: only as good as the observed sample; not a tail guarantee")
        formula = "mean of the worst empirical returns, scaled by sqrt(horizon)"

    result = _base_record("cvar", formula, series, observations)
    result.unit = "%"
    result.warnings.extend(warnings)
    result.assumptions.append(f"confidence {confidence:.0%}; {method} method")
    result.assumptions.append(f"horizon {horizon_periods} period(s), scaled by sqrt(time)")
    result.assumptions.append("loss reported as a positive percentage")
    result.detail = provenance
    result.value = value
    return _finalize(result)


def parametric_var(
    observations: Sequence[dict[str, Any]],
    *,
    confidence: float = 0.95,
    frequency: str = "daily",
    horizon_periods: int = 1,
    ddof: int = 1,
) -> CalculationResult:
    """Parametric (normal) Value-at-Risk, scaled by sqrt(time).

    Returned as a positive percentage (a loss). Assumes normally distributed
    returns, which is recorded as an explicit warning.
    """
    if not (0.5 < confidence < 1.0):
        raise CalculationError(f"confidence must be in (0.5, 1.0), got {confidence!r}")
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if horizon_periods < 1:
        raise CalculationError("horizon_periods must be >= 1")
    series = _prepare(observations, metric="parametric_var", frequency=frequency)
    returns = _returns(series.values, "simple")
    if len(returns) < 5:
        raise CalculationError("parametric VaR needs at least 6 observations (5 returns)")
    mu = _mean(returns)
    sigma = math.sqrt(_sample_variance(returns, ddof=ddof))
    if sigma == 0:
        raise CalculationError("parametric VaR is undefined when return volatility is 0")
    z = NormalDist().inv_cdf(1.0 - confidence)
    value = -(mu + z * sigma) * math.sqrt(horizon_periods) * 100.0
    result = _base_record(
        "parametric_var",
        "-(mu + z_alpha * sigma) * sqrt(horizon); z = normal inverse CDF",
        series,
        observations,
    )
    result.unit = "%"
    result.detail = {"distribution": "normal", "mean": mu, "stdev": sigma, "ddof": ddof, "z": z}
    result.warnings.append("parametric VaR assumes normally distributed returns")
    result.assumptions.append(f"confidence {confidence:.0%}; horizon {horizon_periods} period(s)")
    result.assumptions.append("loss reported as a positive percentage")
    result.value = value
    return _finalize(result)


def _simulate_horizon_returns(
    returns: Sequence[float],
    horizon_periods: int,
    simulations: int,
    seed: int,
    distribution: str,
) -> list[float]:
    """Deterministic horizon-return simulation for Monte-Carlo risk metrics.

    `normal` draws from a fitted Normal(mean, stdev); `empirical` resamples the
    observed returns with replacement. The RNG is `random.Random(seed)` so the
    same seed always yields the same draws (Mersenne Twister).
    """
    rng = random.Random(seed)
    if distribution == "normal":
        mu = _mean(returns)
        sigma = math.sqrt(_sample_variance(returns, ddof=1))
        generator = (lambda: rng.gauss(mu, sigma))
    else:
        sample = list(returns)
        generator = (lambda: rng.choice(sample))
    return [sum(generator() for _ in range(horizon_periods)) for _ in range(simulations)]


def monte_carlo_var(
    observations: Sequence[dict[str, Any]],
    *,
    confidence: float = 0.95,
    frequency: str = "daily",
    horizon_periods: int = 1,
    simulations: int = 10_000,
    seed: int = 0,
    distribution: str = "normal",
) -> CalculationResult:
    """Seeded Monte-Carlo Value-at-Risk.

    The result records `simulations`, `seed` and the `distribution` so it is
    reproducible; two runs with the same seed and simulation count are identical.
    Horizon returns are simulated as the sum of per-period draws.
    """
    if not (0.5 < confidence < 1.0):
        raise CalculationError(f"confidence must be in (0.5, 1.0), got {confidence!r}")
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if horizon_periods < 1:
        raise CalculationError("horizon_periods must be >= 1")
    if simulations < 1000:
        raise CalculationError("monte_carlo_var requires at least 1000 simulations")
    if distribution not in ("normal", "empirical"):
        raise CalculationError(f"unknown distribution {distribution!r}; expected normal or empirical")
    series = _prepare(observations, metric="monte_carlo_var", frequency=frequency)
    returns = _returns(series.values, "simple")
    if len(returns) < 5:
        raise CalculationError("monte_carlo_var needs at least 6 observations (5 returns)")
    draws = sorted(_simulate_horizon_returns(returns, horizon_periods, simulations, seed, distribution))
    idx = _var_index(len(draws), confidence)
    value = -draws[idx] * 100.0
    result = _base_record(
        "monte_carlo_var",
        "empirical quantile of seeded simulated horizon returns",
        series,
        observations,
    )
    result.unit = "%"
    result.detail = {
        "method": "monte_carlo",
        "distribution": distribution,
        "simulations": simulations,
        "seed": seed,
        "randomGenerator": "random.Random (Mersenne Twister)",
        "confidence": confidence,
        "horizonPeriods": horizon_periods,
    }
    result.warnings.append("Monte-Carlo VaR is reproducible only for the recorded seed and simulation count")
    if distribution == "normal":
        result.warnings.append("the normal distribution is fitted to the observed returns")
    result.assumptions.append(f"confidence {confidence:.0%}; horizon {horizon_periods} period(s)")
    result.assumptions.append("loss reported as a positive percentage")
    result.value = value
    return _finalize(result)


# â”€â”€ Drawdown detail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def drawdown_analysis(
    observations: Sequence[dict[str, Any]],
    *,
    frequency: Optional[str] = None,
    top_n: int = 5,
) -> CalculationResult:
    """Full drawdown path: peak/trough/recovery dates, durations and episodes.

    The scalar `value` is the maximum drawdown (a negative percentage); `detail`
    carries the drawdown series, the top-N episodes and the underwater span.
    Durations are measured in observation intervals (the series' own frequency).
    """
    if top_n < 1:
        raise CalculationError("top_n must be >= 1")
    series = _prepare(observations, metric="drawdown_analysis", frequency=frequency)
    dates, values = series.dates, series.values
    peak_value = values[0]
    peak_idx = 0
    path: list[float] = []
    episodes: list[dict[str, Any]] = []
    open_peak_idx: Optional[int] = None
    open_peak_value: Optional[float] = None
    open_trough_idx: Optional[int] = None
    open_trough_value: Optional[float] = None

    def close_episode(end_idx: int) -> None:
        nonlocal open_peak_idx, open_peak_value, open_trough_idx, open_trough_value
        if open_peak_idx is None or open_trough_idx is None:
            return
        depth = open_trough_value / open_peak_value - 1.0
        if depth < 0:
            episodes.append({
                "peakDate": dates[open_peak_idx],
                "peakValue": open_peak_value,
                "troughDate": dates[open_trough_idx],
                "troughValue": open_trough_value,
                "depthPct": depth * 100.0,
                "drawdownDuration": open_trough_idx - open_peak_idx,
            })
        open_peak_idx = open_peak_value = open_trough_idx = open_trough_value = None

    for i, value in enumerate(values):
        if value >= peak_value:
            # A new high closes the current episode (if any).
            close_episode(i)
            peak_value = value
            peak_idx = i
            drawdown = 0.0
        else:
            drawdown = value / peak_value - 1.0
            if open_peak_idx is None:
                open_peak_idx = peak_idx
                open_peak_value = peak_value
            if open_trough_idx is None or value < open_trough_value:  # type: ignore[operator]
                open_trough_idx = i
                open_trough_value = value
        path.append(drawdown * 100.0)
    close_episode(len(values))

    # Recovery = first later date at or above the episode peak.
    for episode in episodes:
        peak_level = episode["peakValue"]
        trough_date = episode["troughDate"]
        trough_pos = dates.index(trough_date)
        recovery_date = None
        for j in range(trough_pos + 1, len(values)):
            if values[j] >= peak_level:
                recovery_date = dates[j]
                break
        episode["recoveryDate"] = recovery_date
        episode["recoveryDuration"] = (
            dates.index(recovery_date) - trough_pos if recovery_date else None
        )

    worst = min(episodes, key=lambda e: e["depthPct"]) if episodes else None
    top = sorted(episodes, key=lambda e: e["depthPct"])[:top_n]
    underwater_periods = sum(1 for d in path if d < 0)

    result = _base_record(
        "drawdown_analysis",
        "min over t of (value_t / running_peak_t - 1)",
        series,
        observations,
    )
    result.unit = "%"
    result.value = worst["depthPct"] if worst else 0.0
    result.detail = {
        "maxDrawdownPct": result.value,
        "peakDate": worst["peakDate"] if worst else None,
        "peakValue": worst["peakValue"] if worst else None,
        "troughDate": worst["troughDate"] if worst else None,
        "troughValue": worst["troughValue"] if worst else None,
        "recoveryDate": worst["recoveryDate"] if worst else None,
        "drawdownDuration": worst["drawdownDuration"] if worst else 0,
        "recoveryDuration": worst["recoveryDuration"] if worst else None,
        "underwaterPeriods": underwater_periods,
        "underwaterFraction": underwater_periods / len(path) if path else 0.0,
        "drawdownSeries": [
            {"date": dates[i], "drawdownPct": path[i]} for i in range(len(path))
        ],
        "topDrawdowns": top,
    }
    result.assumptions.append("drawdown measured peak-to-trough on the provided series only")
    result.assumptions.append(f"durations measured in observation intervals ({frequency or 'series frequency'})")
    result.warnings.append("max drawdown is path-dependent on the observation frequency")
    return _finalize(result)


# â”€â”€ Rolling metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def rolling_volatility(
    observations: Sequence[dict[str, Any]],
    *,
    window: int,
    frequency: str = "daily",
    method: str = "simple",
) -> CalculationResult:
    """Rolling annualized volatility; `value` is the latest window's reading.

    The full rolling series is returned in `detail`. An observation with too few
    predecessors is skipped, never filled.
    """
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if window < 2:
        raise CalculationError("window must be at least 2 returns")
    series = _prepare(observations, metric="rolling_volatility", frequency=frequency)
    values = series.values
    if len(values) - 1 < window:
        raise CalculationError(f"rolling_volatility needs at least {window + 1} observations")
    periods = PERIODS_PER_YEAR[frequency]
    points: list[dict[str, Any]] = []
    for i in range(window, len(values)):
        window_returns = _returns(values[i - window : i + 1], method)
        sd = math.sqrt(_sample_variance(window_returns, ddof=1))
        points.append({"date": series.dates[i], "value": sd * math.sqrt(periods) * 100.0})
    result = _base_record("rolling_volatility", "rolling stdev(returns) * sqrt(periods_per_year)", series, observations)
    result.unit = "%"
    result.annualization = periods
    result.value = points[-1]["value"]
    result.detail = {"window": window, "series": points}
    result.assumptions.append(f"{method} returns, sample standard deviation (n-1)")
    result.assumptions.append(f"window of {window} return(s); annualized with {periods} periods per year")
    return _finalize(result)


def rolling_correlation(
    x_observations: Sequence[dict[str, Any]],
    y_observations: Sequence[dict[str, Any]],
    *,
    window: int,
    method: str = "pearson",
) -> CalculationResult:
    """Rolling correlation on date-aligned returns; `value` is the latest window."""
    if method not in ("pearson", "spearman"):
        raise CalculationError("rolling_correlation supports pearson or spearman")
    if window < 3:
        raise CalculationError("window must be at least 3 observations")
    common, a_prices, b_prices = _aligned_pairs(x_observations, y_observations, metric="rolling_correlation")
    a = _returns(a_prices, "simple")
    b = _returns(b_prices, "simple")
    if len(a) < window:
        raise CalculationError(f"rolling_correlation needs at least {window + 1} aligned observations")
    dates = common[1:]  # return i sits at date i+1
    points: list[dict[str, Any]] = []
    for i in range(window, len(a) + 1):
        wa, wb = a[i - window : i], b[i - window : i]
        if method == "spearman":
            value = _pearson(_rank(wa), _rank(wb))
        else:
            value = _pearson(wa, wb)
        points.append({"date": dates[i - 1], "value": max(-1.0, min(1.0, value))})
    xs = _prepare(x_observations, metric="rolling_correlation")
    result = _base_record("rolling_correlation", "rolling covariance / (sd(x) * sd(y))", xs, x_observations)
    result.value = points[-1]["value"]
    result.detail = {"window": window, "method": method, "series": points}
    result.assumptions.append(f"{method} correlation over a rolling window of {window} return(s)")
    return _finalize(result)


def rolling_beta(
    observations: Sequence[dict[str, Any]],
    benchmark: Sequence[dict[str, Any]],
    *,
    window: int,
    frequency: str = "daily",
) -> CalculationResult:
    """Rolling CAPM beta on date-aligned returns; `value` is the latest window."""
    if frequency not in PERIODS_PER_YEAR:
        raise CalculationError(f"unknown frequency {frequency!r}; expected {sorted(PERIODS_PER_YEAR)}")
    if window < 3:
        raise CalculationError("window must be at least 3 observations")
    common, a_prices, b_prices = _aligned_pairs(observations, benchmark, metric="rolling_beta")
    a = _returns(a_prices, "simple")
    b = _returns(b_prices, "simple")
    if len(a) < window:
        raise CalculationError(f"rolling_beta needs at least {window + 1} aligned observations")
    dates = common[1:]
    points: list[dict[str, Any]] = []
    for i in range(window, len(a) + 1):
        wa, wb = a[i - window : i], b[i - window : i]
        ma, mb = _mean(wa), _mean(wb)
        var_b = _sample_variance(wb, ddof=1)
        if var_b == 0:
            continue
        cov = sum((x - ma) * (y - mb) for x, y in zip(wa, wb)) / (window - 1)
        points.append({"date": dates[i - 1], "value": cov / var_b})
    if not points:
        raise CalculationError("rolling_beta is undefined: no window had non-zero benchmark variance")
    xs = _prepare(observations, metric="rolling_beta")
    result = _base_record("rolling_beta", "rolling cov(asset, benchmark) / var(benchmark)", xs, observations)
    result.value = points[-1]["value"]
    result.detail = {"window": window, "series": points}
    result.assumptions.append(f"date-aligned simple {frequency} returns over a rolling window of {window}")
    return _finalize(result)


# â”€â”€ Matrices + risk decomposition â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def correlation_matrix(
    series: Sequence[dict[str, Any]],
    *,
    method: str = "pearson",
) -> CalculationResult:
    """Pairwise correlation matrix over named, date-aligned series.

    `series` is a list of `{"name": str, "observations": [...]}`. All series are
    joined on the INTERSECTION of their dates; a series with no overlap is
    refused. `detail.matrix` is a names Ã— names matrix of correlations.
    """
    names, aligned = _align_many(series, metric="correlation_matrix")
    n = len(names)
    matrix: list[list[Optional[float]]] = [[None] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            a, b = aligned[i], aligned[j]
            if method == "spearman":
                r = _pearson(_rank(a), _rank(b))
            elif method == "kendall":
                r = _kendall_tau_b(a, b)
            elif method == "pearson":
                r = _pearson(a, b)
            else:
                raise CalculationError(f"unknown correlation method {method!r}")
            r = max(-1.0, min(1.0, r))
            matrix[i][j] = matrix[j][i] = r
    result = CalculationResult(
        calculationId="",
        version=CALCULATION_VERSION,
        formula="pairwise correlation over date-aligned observations",
        metric="correlation_matrix",
        value=None,
        observationCount=len(aligned[0]) if aligned else 0,
        missingDataPolicy="intersection_no_interpolation",
    )
    result.detail = {"method": method, "names": names, "matrix": matrix}
    result.assumptions.append(f"{method} correlation on the date-intersection of {n} series")
    return _finalize(result)


def covariance_matrix(
    series: Sequence[dict[str, Any]],
    *,
    ddof: int = 1,
) -> CalculationResult:
    """Pairwise covariance matrix over named, date-aligned series (reusable by
    portfolio risk, VaR and optimization)."""
    if ddof not in (0, 1):
        raise CalculationError("ddof must be 0 (population) or 1 (sample)")
    names, aligned = _align_many(series, metric="covariance_matrix")
    n = len(names)
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            a, b = aligned[i], aligned[j]
            value = sum(
                (x - _mean(a)) * (y - _mean(b)) for x, y in zip(a, b)
            ) / (len(a) - ddof)
            matrix[i][j] = matrix[j][i] = value
    result = CalculationResult(
        calculationId="",
        version=CALCULATION_VERSION,
        formula="pairwise sum((x - mean_x)(y - mean_y)) / (n - ddof)",
        metric="covariance_matrix",
        value=None,
        observationCount=len(aligned[0]) if aligned else 0,
        missingDataPolicy="intersection_no_interpolation",
    )
    result.detail = {"ddof": ddof, "names": names, "matrix": matrix}
    result.assumptions.append(f"{'sample' if ddof == 1 else 'population'} covariance across {n} series")
    return _finalize(result)


def _align_many(
    series: Sequence[dict[str, Any]],
    *,
    metric: str,
) -> tuple[list[str], list[list[float]]]:
    if len(series) < 2:
        raise CalculationError(f"{metric} needs at least two series")
    names: list[str] = []
    maps: list[dict[str, float]] = []
    for entry in series:
        if not isinstance(entry, dict) or not entry.get("observations"):
            raise CalculationError(f"{metric}: every series needs a name and observations")
        prepared = _prepare(entry["observations"], metric=metric)
        names.append(str(entry.get("name") or f"series{len(names)}"))
        maps.append(dict(zip(prepared.dates, prepared.values)))
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    ordered = sorted(common)
    minimum = MIN_OBSERVATIONS.get(metric, 3)
    if len(ordered) < minimum:
        raise CalculationError(f"{metric} needs >= {minimum} common dates; found {len(ordered)}")
    aligned = [[m[d] for d in ordered] for m in maps]
    return names, aligned


def risk_contribution(
    weights: Sequence[float],
    covariance: Sequence[Sequence[float]],
    *,
    names: Optional[Sequence[str]] = None,
) -> CalculationResult:
    """Euler risk decomposition of a portfolio's volatility across its holdings.

    Marginal contribution = (Î£w)_i / portfolio_vol; component contribution =
    w_i * (Î£w)_i / portfolio_vol. Components are returned as weights summing to
    1 of portfolio volatility (with the sign preserved for short positions).
    """
    w = [float(x) for x in weights]
    n = len(w)
    if n == 0:
        raise CalculationError("risk_contribution needs at least one weight")
    if len(covariance) != n or any(len(row) != n for row in covariance):
        raise CalculationError("covariance must be a square matrix matching the weights")
    if abs(sum(w)) < 1e-12:
        raise CalculationError("risk_contribution is undefined when portfolio weights sum to zero")
    sigma_w = [sum(covariance[i][j] * w[j] for j in range(n)) for i in range(n)]
    variance = sum(w[i] * sigma_w[i] for i in range(n))
    if variance <= 0:
        raise CalculationError("portfolio variance must be positive to decompose risk")
    portfolio_vol = math.sqrt(variance)
    marginal = [sigma_w[i] / portfolio_vol for i in range(n)]
    component = [w[i] * marginal[i] for i in range(n)]
    labels = list(names) if names is not None else [f"asset{i}" for i in range(n)]
    result = CalculationResult(
        calculationId="",
        version=CALCULATION_VERSION,
        formula="component_i = w_i * (Cov w)_i / sqrt(w' Cov w)",
        metric="risk_contribution",
        value=portfolio_vol,
        missingDataPolicy="reject",
    )
    result.detail = {
        "portfolioVolatility": portfolio_vol,
        "names": labels,
        "weights": w,
        "marginal": [{"name": labels[i], "value": marginal[i]} for i in range(n)],
        "component": [{"name": labels[i], "value": component[i], "pctOfRisk": component[i] / portfolio_vol} for i in range(n)],
    }
    result.assumptions.append("Euler decomposition; components sum to portfolio volatility")
    return _finalize(result)



