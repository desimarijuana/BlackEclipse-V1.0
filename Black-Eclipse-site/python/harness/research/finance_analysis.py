"""High-level deterministic financial analysis (security + portfolio).

This is the ANALYSIS PLANNER layer: it composes the primitive calculators
(`research.calculations`, `finance_facts.metrics`, `finance_facts.valuation`) into
a security or portfolio report. It performs NO new financial formula of its own —
every number comes from a primitive, so a formula is never duplicated.

Design rules:
  * The caller supplies named, dated INPUTS; the engine computes the numbers.
  * A metric that cannot be computed is reported with a structured error and a
    warning — never a fabricated value, never a silent omission.
  * Every section carries the underlying calculation's formula, inputs,
    assumptions and provenance so the report is auditable end to end.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from . import calculations as _calc
from ..finance_facts import metrics as _metrics
from ..finance_facts import valuation as _valuation
from ..finance_facts.model import FinancialFact, FinancialPeriod


# Metrics attempted for a security when their inputs are available. The order is
# the order they appear in the report.
_FUNDAMENTAL_METRICS: tuple[str, ...] = (
    "pe_ratio", "forward_pe", "peg_ratio", "pb_ratio", "ps_ratio", "ev_ebitda",
    "fcf_yield", "dividend_yield", "roe", "roa", "roic", "gross_margin",
    "operating_margin", "net_margin", "net_debt_to_ebitda", "debt_to_equity",
    "free_cash_flow", "enterprise_value",
)


def _fact(definition: str, value: Any, *, currency: Optional[str]) -> FinancialFact:
    return FinancialFact(
        fact_id=f"input:{definition}",
        metric=definition,
        definition=definition,
        value=value,
        currency=currency,
        period=FinancialPeriod(period_type="fy"),
        source="caller",
        source_type="unknown",
        reported_or_derived="reported",
    )


def _run(fn, *args, **kwargs) -> dict[str, Any]:
    """Run one primitive, returning a structured OK/ERROR envelope.

    A refused metric is an honest result: it is returned with its reason, not
    swallowed and not replaced by a default.
    """
    try:
        result = fn(*args, **kwargs)
        return {"status": "OK", "result": result.to_dict()}
    except Exception as exc:  # noqa: BLE001 - a refused calculation is an answer
        return {"status": "UNAVAILABLE", "error": str(exc), "errorType": type(exc).__name__}


def _quality(computed: int, requested: int, warnings: Sequence[str]) -> dict[str, Any]:
    if requested == 0:
        state = "INVALID"
    elif computed == requested and not warnings:
        state = "COMPLETE"
    elif computed == requested:
        state = "GOOD"
    elif computed >= max(1, requested // 2):
        state = "PARTIAL"
    elif computed > 0:
        state = "DEGRADED"
    else:
        state = "INVALID"
    return {"state": state, "computed": computed, "requested": requested, "warningsCount": len(warnings)}


def security_analysis(payload: dict[str, Any], *, now: Optional[str] = None) -> dict[str, Any]:
    """Compose a deterministic security analysis from caller-supplied inputs.

    Recognised payload keys:
      priceObservations      list[{date, value}] (required for market/risk sections)
      benchmarkObservations  list[{date, value}] (enables beta/alpha/correlation)
      riskFreeRate           annual decimal (enables sharpe/sortino/alpha)
      frequency              daily|weekly|monthly|quarterly|annual (default daily)
      currency               ISO code
      fundamentals           {definitionId: value} for ratio metrics
      includeFundamentals    list[str] restricting which ratios are attempted
      valuation              DcfInputs-shaped mapping (enables a DCF)
      dcfSensitivity         {discountRates: [...], terminalGrowths: [...]}
    """
    frequency = str(payload.get("frequency") or "daily")
    currency = payload.get("currency")
    rf = payload.get("riskFreeRate")
    price_obs = payload.get("priceObservations")
    bench_obs = payload.get("benchmarkObservations")

    sections: dict[str, Any] = {}
    warnings: list[str] = []
    requested = 0
    computed = 0

    def attempt(section: str, name: str, fn, *args, **kwargs) -> None:
        nonlocal requested, computed
        requested += 1
        outcome = _run(fn, *args, **kwargs)
        sections.setdefault(section, {})[name] = outcome
        if outcome["status"] == "OK":
            computed += 1
        else:
            warnings.append(f"{name}: {outcome['error']}")

    # ── Returns + volatility ────────────────────────────────────────────────
    if isinstance(price_obs, list) and len(price_obs) >= 2:
        attempt("returns", "cumulativeReturn", _calc.cumulative_return, price_obs, frequency=frequency)
        attempt("returns", "annualizedReturn", _calc.annualized_return, price_obs, frequency=frequency)
        attempt("volatility", "annualizedVolatility", _calc.annualized_volatility, price_obs, frequency=frequency)
    else:
        warnings.append("priceObservations are required for market and risk sections")

    # ── Risk ────────────────────────────────────────────────────────────────
    if isinstance(price_obs, list) and len(price_obs) >= 3:
        attempt("risk", "maxDrawdown", _calc.drawdown_analysis, price_obs, frequency=frequency)
        attempt("risk", "valueAtRisk", _calc.value_at_risk, price_obs, confidence=0.95, frequency=frequency)
        attempt("risk", "conditionalVaR", _calc.cvar, price_obs, confidence=0.95, frequency=frequency)
        if isinstance(rf, (int, float)):
            attempt(
                "risk", "sharpe", _calc.sharpe, price_obs,
                risk_free_rate=float(rf), frequency=frequency,
                risk_free_source=payload.get("riskFreeSource"),
            )
            attempt("risk", "sortino", _calc.sortino, price_obs, risk_free_rate=float(rf), frequency=frequency)

    # ── Market (needs a benchmark) ──────────────────────────────────────────
    if isinstance(price_obs, list) and isinstance(bench_obs, list):
        attempt("market", "beta", _calc.beta, price_obs, bench_obs, frequency=frequency)
        attempt("market", "correlation", _calc.correlation, price_obs, bench_obs, method="pearson")
        attempt("market", "covariance", _calc.covariance, price_obs, bench_obs)
        if isinstance(rf, (int, float)):
            attempt(
                "market", "alpha", _calc.alpha, price_obs, bench_obs,
                risk_free_rate=float(rf), frequency=frequency,
            )
    else:
        warnings.append("a benchmark series is required for beta/alpha/correlation")

    # ── Fundamentals ────────────────────────────────────────────────────────
    fundamentals = payload.get("fundamentals")
    if isinstance(fundamentals, dict) and fundamentals:
        include = payload.get("includeFundamentals")
        names = [n for n in _FUNDAMENTAL_METRICS if (not include or n in include)]
        extra = payload.get("fundamentalExtra") if isinstance(payload.get("fundamentalExtra"), dict) else {}
        facts = [_fact(name, value, currency=currency) for name, value in fundamentals.items()]
        for name in names:
            attempt("fundamentals", name, _metrics.derive, name, facts, extra=extra)

    # ── Valuation ───────────────────────────────────────────────────────────
    valuation_inputs = payload.get("valuation")
    if isinstance(valuation_inputs, dict):
        dcf_inputs = _metrics_dcf_inputs(valuation_inputs)
        attempt("valuation", "dcf", _valuation.dcf, dcf_inputs)
        sens = payload.get("dcfSensitivity")
        if isinstance(sens, dict):
            attempt(
                "valuation", "dcfSensitivity", _valuation.dcf_sensitivity, dcf_inputs,
                discount_rates=sens.get("discountRates"), terminal_growths=sens.get("terminalGrowths"),
            )

    quality = _quality(computed, requested, warnings)
    return {
        "status": "OK" if computed else "UNAVAILABLE",
        "kind": "security_analysis",
        "frequency": frequency,
        "currency": currency,
        "sections": sections,
        "warnings": warnings,
        "quality": quality,
    }


def _metrics_dcf_inputs(data: dict[str, Any]) -> "_valuation.DcfInputs":
    allowed = set(_valuation.DcfInputs.__dataclass_fields__)
    clean = {k: v for k, v in data.items() if k in allowed}
    if isinstance(clean.get("free_cash_flows"), list):
        clean["free_cash_flows"] = tuple(clean["free_cash_flows"])
    return _valuation.DcfInputs(**clean)  # type: ignore[arg-type]


# ── Portfolio ─────────────────────────────────────────────────────────────────


def _aligned_return_series(assets: Sequence[dict[str, Any]]) -> tuple[list[str], list[list[float]]]:
    """Date-align asset prices and convert to simple returns.

    Returns (dates, returns_by_asset) where `dates` are the return dates. Assets
    are joined on the intersection of their dates; a missing asset on a date drops
    that date for every asset (never interpolated).
    """
    if len(assets) < 1:
        raise _calc.CalculationError("portfolio_analysis needs at least one asset")
    prepared: list[tuple[list[str], list[float]]] = []
    for asset in assets:
        obs = asset.get("observations")
        if not isinstance(obs, list) or len(obs) < 2:
            raise _calc.CalculationError(f"asset {asset.get('name')!r} needs at least two observations")
        series = _calc._prepare(obs, metric="annualized_volatility")  # validated, ordered
        prepared.append((series.dates, series.values))
    common = set(prepared[0][0])
    for dates, _ in prepared[1:]:
        common &= set(dates)
    ordered = sorted(common)
    if len(ordered) < 3:
        raise _calc.CalculationError(f"portfolio assets share only {len(ordered)} common dates")
    returns_by_asset: list[list[float]] = []
    for dates, values in prepared:
        index = {d: i for i, d in enumerate(dates)}
        series_values = [values[index[d]] for d in ordered]
        returns_by_asset.append(_calc._returns(series_values, "simple"))
    return ordered, returns_by_asset


def portfolio_analysis(payload: dict[str, Any], *, now: Optional[str] = None) -> dict[str, Any]:
    """Compose a deterministic portfolio risk analysis from weighted assets.

    Recognised payload keys:
      assets            list[{name, observations:[{date,value}], weight}] (required)
      benchmarkObservations  optional benchmark for beta/alpha
      riskFreeRate      annual decimal (enables sharpe/sortino/alpha)
      frequency         default daily
      confidence        VaR/CVaR confidence (default 0.95)
    The portfolio price series is built from the WEIGHTED asset returns, then every
    risk metric is computed by the shared primitive engine.
    """
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return {"status": "ERROR", "error": "assets is required", "kind": "portfolio_analysis"}
    frequency = str(payload.get("frequency") or "daily")
    confidence = float(payload.get("confidence") or 0.95)
    rf = payload.get("riskFreeRate")
    weights = [float(a.get("weight") or 0.0) for a in assets]
    weight_sum = sum(weights)
    if weight_sum == 0:
        return {"status": "ERROR", "error": "asset weights must not all be zero", "kind": "portfolio_analysis"}

    try:
        dates, returns_by_asset = _aligned_return_series(assets)
    except _calc.CalculationError as exc:
        return {"status": "UNAVAILABLE", "error": str(exc), "kind": "portfolio_analysis"}

    n = len(returns_by_asset[0])
    normalized = [w / weight_sum for w in weights]
    portfolio_returns = [
        sum(normalized[i] * returns_by_asset[i][t] for i in range(len(assets)))
        for t in range(n)
    ]
    # Rebuild a portfolio value path (base 100) for the path-based primitives.
    value = 100.0
    portfolio_prices: list[dict[str, Any]] = [{"date": dates[0] if dates else "0000", "value": value}]
    for t, r in enumerate(portfolio_returns):
        value *= 1.0 + r
        portfolio_prices.append({"date": dates[t + 1] if t + 1 < len(dates) else f"p{t}", "value": value})

    warnings: list[str] = []
    requested = 0
    computed = 0
    sections: dict[str, Any] = {}

    def attempt(section: str, name: str, fn, *args, **kwargs) -> None:
        nonlocal requested, computed
        requested += 1
        outcome = _run(fn, *args, **kwargs)
        sections.setdefault(section, {})[name] = outcome
        if outcome["status"] != "OK":
            warnings.append(f"{name}: {outcome['error']}")
        else:
            computed += 1

    # Portfolio-level return/risk on the synthetic portfolio series.
    attempt("returns", "portfolioCumulativeReturn", _calc.cumulative_return, portfolio_prices, frequency=frequency)
    attempt("returns", "portfolioAnnualizedReturn", _calc.annualized_return, portfolio_prices, frequency=frequency)
    attempt("risk", "portfolioVolatility", _calc.annualized_volatility, portfolio_prices, frequency=frequency)
    attempt("risk", "maxDrawdown", _calc.drawdown_analysis, portfolio_prices, frequency=frequency)
    attempt("risk", "valueAtRisk", _calc.value_at_risk, portfolio_prices, confidence=confidence, frequency=frequency)
    attempt("risk", "conditionalVaR", _calc.cvar, portfolio_prices, confidence=confidence, frequency=frequency)
    if isinstance(rf, (int, float)):
        attempt("risk", "sharpe", _calc.sharpe, portfolio_prices, risk_free_rate=float(rf), frequency=frequency)
        attempt("risk", "sortino", _calc.sortino, portfolio_prices, risk_free_rate=float(rf), frequency=frequency)

    # Covariance/correlation matrix + Euler risk contribution.
    series = [{"name": a.get("name") or f"asset{i}", "observations": a.get("observations")} for i, a in enumerate(assets)]
    cov = _run(_calc.covariance_matrix, series)
    sections.setdefault("risk", {})["covarianceMatrix"] = cov
    requested += 1
    if cov["status"] == "OK":
        computed += 1
    corr = _run(_calc.correlation_matrix, series)
    sections["risk"]["correlationMatrix"] = corr
    requested += 1
    if corr["status"] == "OK":
        computed += 1
    if cov["status"] == "OK":
        matrix = cov["result"]["detail"]["matrix"]
        names = [a.get("name") or f"asset{i}" for i, a in enumerate(assets)]
        rc = _run(_calc.risk_contribution, normalized, matrix, names=names)
        sections["risk"]["riskContribution"] = rc
        requested += 1
        if rc["status"] == "OK":
            computed += 1

    # Benchmark-relative metrics.
    benchmark = payload.get("benchmarkObservations")
    if isinstance(benchmark, list):
        attempt("market", "beta", _calc.beta, portfolio_prices, benchmark, frequency=frequency)
        attempt("market", "correlation", _calc.correlation, portfolio_prices, benchmark)
        if isinstance(rf, (int, float)):
            attempt("market", "alpha", _calc.alpha, portfolio_prices, benchmark, risk_free_rate=float(rf), frequency=frequency)
    else:
        warnings.append("a benchmark series is required for beta/alpha")

    # Concentration (HHI over normalized weights).
    hhi = sum(w * w for w in normalized)
    effective_n = 1.0 / hhi if hhi > 0 else 0.0
    sections["concentration"] = {
        "weights": normalized,
        "herfindahlHirschmanIndex": hhi,
        "effectiveNumberOfHoldings": effective_n,
    }

    quality = _quality(computed, requested, warnings)
    return {
        "status": "OK" if computed else "UNAVAILABLE",
        "kind": "portfolio_analysis",
        "frequency": frequency,
        "assets": [a.get("name") or f"asset{i}" for i, a in enumerate(assets)],
        "sections": sections,
        "warnings": warnings,
        "quality": quality,
    }


__all__ = ["security_analysis", "portfolio_analysis"]
