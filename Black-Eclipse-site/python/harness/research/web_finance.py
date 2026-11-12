"""Deterministic financial-metric tools for the research engine.

These tools give the model DETERMINISTIC financial math with full provenance — it
never has to compute a critical metric itself. They are thin adapters over the
existing engines (never a second calculator):

  * ratio metrics, margins and ROIC → `finance_facts.metrics.derive` (FinancialFact)
  * WACC and DCF valuation          → `finance_facts.valuation`
  * time-series risk metrics        → `research.calculations` (sortino/VaR/beta)

The caller supplies NAMED inputs (definition → value). A metric whose required
input is missing is refused with a precise reason (never defaulted). Every result
is a `DerivedMetric`/`CalculationResult`: formula + inputs + sources + assumptions,
so "P/E = 15" always traces to its numerator and denominator.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from ..finance_facts import metrics as _metrics
from ..finance_facts import valuation as _valuation
from ..finance_facts.model import FinancialFact, FinancialPeriod
from ..research import calculations as _calc


# Every ratio/margin metric this adapter can compute, grouped for the model.
RATIO_METRICS: tuple[str, ...] = tuple(sorted(_metrics.SPECS))
SERIES_METRICS: tuple[str, ...] = tuple(sorted(set(_calc.CALCULATORS) | set(_calc.MATRIX_CALCULATORS)))
VALUATION_METRICS: tuple[str, ...] = (
    "wacc", "dcf", "dcf_equity_value", "dcf_equity_value_per_share",
    "dcf_sensitivity", "dcf_scenarios", "enterprise_value", "fcff", "fcfe",
)


def _fact_from_input(definition: str, value: Any, *, currency: Optional[str]) -> FinancialFact:
    """A minimal, clearly-caller-sourced FinancialFact from a supplied value."""
    return FinancialFact(
        fact_id=f"caller:{definition}",
        metric=definition,
        definition=definition,
        value=value,
        currency=currency,
        period=FinancialPeriod(period_type="fy"),
        source="caller",
        source_type="unknown",
        reported_or_derived="reported",
    )


def compute_ratio(
    metric: str,
    inputs: dict[str, Any],
    *,
    extra: Optional[dict[str, Any]] = None,
    currency: Optional[str] = None,
) -> dict[str, Any]:
    """Compute a named ratio/margin metric from caller-supplied inputs.

    `inputs` maps a definition id (e.g. "price", "eps", "market_cap") to its value.
    `extra` supplies scalars a formula needs (e.g. `tax_rate` for ROIC,
    `eps_growth` percent for PEG). Refuses on any missing/ambiguous input.
    """
    if metric not in _metrics.SPECS:
        raise _metrics.DerivationError(f"unknown metric {metric!r}; known: {sorted(_metrics.SPECS)}")
    facts = [_fact_from_input(name, value, currency=currency) for name, value in inputs.items()]
    result = _metrics.derive(metric, facts, extra=extra)
    return result.to_dict()


_INPUT_KINDS = ("prices", "returns")


def _normalize_series_input(
    observations: list[dict[str, Any]], input_kind: str
) -> tuple[list[dict[str, Any]], str]:
    """Resolve a series' input kind and return a LEVEL path for the calculators.

    Every calculator in `research.calculations` differences its observations, so
    it expects price/equity levels. When the caller supplies RETURNS we compound
    them once here (`P_t = P_{t-1}(1+r_t)`) and hand the calculators a level
    path; the recovered returns are then exactly the caller's returns. A return
    of -100% or less is rejected (it cannot be compounded).

    `auto` infers returns only when the series has a negative value and every
    value is within [-1, 1]; otherwise it is treated as levels. The inference is
    recorded on the result; callers that know the kind should pass it explicitly.
    """
    kind = (input_kind or "auto").strip().lower()
    if kind in ("level", "price", "prices"):
        return list(observations), "prices"
    if kind in ("return", "returns", "pct_returns"):
        kind = "returns"
    elif kind in ("", "auto"):
        values = []
        for observation in observations:
            value = observation.get("value") if isinstance(observation, dict) else None
            if value is None:
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                raise _calc.CalculationError("every observation needs a finite numeric `value`")
        returns_like = bool(values) and any(v < 0 for v in values) and all(abs(v) <= 1.0 for v in values)
        kind = "returns" if returns_like else "prices"
    else:
        raise _calc.CalculationError(
            f"unknown input kind {input_kind!r}; expected 'prices', 'returns' or 'auto'"
        )

    if kind == "prices":
        return list(observations), "prices"

    level = 1.0
    normalized: list[dict[str, Any]] = []
    # Anchor the synthetic level path one step BEFORE the first return. The
    # calculators difference their input, so n+1 levels yield exactly the n
    # supplied returns (without the anchor the first return is lost and every
    # metric is computed on n-1 observations).
    if observations:
        first = observations[0] if isinstance(observations[0], dict) else {}
        anchor_date = "0000-01-01"
        normalized.append({
            **first,
            "date": anchor_date,
            "value": 1.0,
            "syntheticAnchor": True,
        })
    for observation in observations:
        if not isinstance(observation, dict):
            raise _calc.CalculationError("every observation must be an object with {date, value}")
        value = observation.get("value")
        if value is None:
            normalized.append(dict(observation))
            continue
        try:
            period_return = float(value)
        except (TypeError, ValueError):
            raise _calc.CalculationError("every observation needs a finite numeric `value`")
        if not math.isfinite(period_return):
            raise _calc.CalculationError("every observation needs a finite numeric `value`")
        if period_return <= -1.0:
            raise _calc.CalculationError(
                "a return of -100% or less cannot be compounded into a level path"
            )
        level *= 1.0 + period_return
        normalized.append({**observation, "value": level})
    return normalized, "returns"


def compute_series(
    metric: str,
    observations: list[dict[str, Any]],
    *,
    benchmark: Optional[list[dict[str, Any]]] = None,
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compute a time-series metric from dated observations.

    Every metric is dispatched to exactly one primitive in
    `research.calculations`; this adapter adds no formula of its own. Metrics that
    need a second series (beta/alpha/correlation/covariance and their rolling
    forms) require `benchmark`; matrix metrics require `options["series"]`.

    `options["input"]` is `prices` or `returns` (default `auto`). The calculators
    operate on a LEVEL path, so a returns input is compounded once here and the
    interpretation is recorded on the result. This is the ONE place the price /
    return distinction is resolved; no calculator differences raw input again.
    """
    if metric not in _calc.CALCULATORS and metric not in _calc.MATRIX_CALCULATORS:
        raise _calc.CalculationError(
            f"unknown series metric {metric!r}; known: {sorted(set(_calc.CALCULATORS) | set(_calc.MATRIX_CALCULATORS))}"
        )
    opts = dict(options or {})
    requested_input = str(opts.get("input") or opts.get("input_kind") or "auto").strip().lower()
    observations, resolved_input = _normalize_series_input(observations, requested_input)
    if benchmark is not None:
        benchmark, _ = _normalize_series_input(benchmark, requested_input)
    if isinstance(opts.get("series"), list):
        opts["series"] = [
            {
                **item,
                "observations": _normalize_series_input(
                    list(item.get("observations") or []), requested_input
                )[0],
            }
            if isinstance(item, dict)
            else item
            for item in opts["series"]
        ]


    if metric in ("beta", "rolling_beta"):
        if not benchmark:
            raise _calc.CalculationError(f"{metric} requires a `benchmark` observation series")
        result = getattr(_calc, metric)(observations, benchmark, **_pick(opts, ("frequency", "window")))
    elif metric in ("correlation", "covariance", "rolling_correlation"):
        if not benchmark:
            raise _calc.CalculationError(f"{metric} requires a `benchmark` observation series")
        if metric == "correlation":
            result = _calc.correlation(observations, benchmark, **_pick(opts, ("method",)))
        elif metric == "covariance":
            result = _calc.covariance(observations, benchmark, **_pick(opts, ("ddof",)))
        else:
            if "window" not in opts:
                raise _calc.CalculationError("rolling_correlation requires `window` in options")
            result = _calc.rolling_correlation(observations, benchmark, **_pick(opts, ("window", "method")))
    elif metric in ("correlation_matrix", "covariance_matrix"):
        series = opts.get("series")
        if not isinstance(series, list):
            raise _calc.CalculationError(f"{metric} requires `options.series` (a list of {{name, observations}})")
        if metric == "correlation_matrix":
            result = _calc.correlation_matrix(series, **_pick(opts, ("method",)))
        else:
            result = _calc.covariance_matrix(series, **_pick(opts, ("ddof",)))
    elif metric == "alpha":
        if not benchmark:
            raise _calc.CalculationError("alpha requires a `benchmark` observation series")
        if "risk_free_rate" not in opts:
            raise _calc.CalculationError("alpha requires `risk_free_rate` in options")
        result = _calc.alpha(observations, benchmark, **_pick(opts, ("risk_free_rate", "frequency", "method")))
    elif metric == "period_change":
        values = [o["value"] for o in observations if o.get("value") is not None]
        if len(values) < 2:
            raise _calc.CalculationError("period_change needs two values")
        result = _calc.period_change(values[0], values[-1], observations=observations, **_pick(opts, ("frequency",)))
    elif metric == "cagr":
        result = _calc.cagr(observations, **_pick(opts, ("years", "frequency")))
    elif metric == "annualized_volatility":
        result = _calc.annualized_volatility(observations, **_pick(opts, ("frequency", "risk_free_rate", "method")))
    elif metric == "max_drawdown":
        result = _calc.max_drawdown(observations, **_pick(opts, ("frequency",)))
    elif metric == "drawdown_analysis":
        result = _calc.drawdown_analysis(observations, **_pick(opts, ("frequency", "top_n")))
    elif metric == "sharpe":
        if "risk_free_rate" not in opts:
            raise _calc.CalculationError("sharpe requires `risk_free_rate` in options")
        result = _calc.sharpe(observations, **_pick(opts, ("risk_free_rate", "frequency", "risk_free_source")))
    elif metric == "sortino":
        result = _calc.sortino(observations, **_pick(opts, ("risk_free_rate", "frequency", "target", "risk_free_source")))
    elif metric == "cumulative_return":
        result = _calc.cumulative_return(observations, **_pick(opts, ("method", "frequency")))
    elif metric == "annualized_return":
        result = _calc.annualized_return(observations, **_pick(opts, ("method", "frequency", "years")))
    elif metric == "value_at_risk":
        result = _calc.value_at_risk(observations, **_pick(opts, ("confidence", "frequency", "horizon_periods")))
    elif metric == "parametric_var":
        result = _calc.parametric_var(observations, **_pick(opts, ("confidence", "frequency", "horizon_periods", "ddof")))
    elif metric == "monte_carlo_var":
        result = _calc.monte_carlo_var(observations, **_pick(opts, ("confidence", "frequency", "horizon_periods", "simulations", "seed", "distribution")))
    elif metric == "cvar":
        result = _calc.cvar(observations, **_pick(opts, ("confidence", "frequency", "horizon_periods", "method", "simulations", "seed", "distribution", "ddof")))
    elif metric == "rolling_volatility":
        if "window" not in opts:
            raise _calc.CalculationError("rolling_volatility requires `window` in options")
        result = _calc.rolling_volatility(observations, **_pick(opts, ("window", "frequency", "method")))
    else:
        raise _calc.CalculationError(f"series metric {metric!r} is not wired")
    payload = result.to_dict()
    payload["inputKind"] = resolved_input
    assumptions = payload.get("assumptions")
    if isinstance(assumptions, list):
        if resolved_input == "returns":
            assumptions.append(
                "input interpreted as periodic RETURNS; compounded once to a level path "
                "before the metric (so the calculator's return series is the supplied series)"
            )
        else:
            assumptions.append("input interpreted as price/equity LEVELS")
        if requested_input in ("", "auto"):
            assumptions.append(f"input kind was inferred as {resolved_input!r}; pass options.input explicitly")
    return payload


def compute_wacc(inputs: dict[str, Any]) -> dict[str, Any]:
    """WACC from explicit capital/CAPM inputs (no default rates)."""
    allowed = set(_valuation.WaccInputs.__dataclass_fields__)
    clean = {k: v for k, v in inputs.items() if k in allowed and v is not None}
    result = _valuation.wacc(_valuation.WaccInputs(**clean))
    return result.to_dict()


def compute_dcf(inputs: dict[str, Any]) -> dict[str, Any]:
    """DCF valuation from an explicit forecast (Gordon growth OR exit multiple)."""
    result = _valuation.dcf(_dcf_inputs(inputs))
    return result.to_dict()


def compute_dcf_sensitivity(
    inputs: dict[str, Any],
    *,
    discount_rates: Optional[list[float]] = None,
    terminal_growths: Optional[list[float]] = None,
) -> dict[str, Any]:
    """WACC × terminal-growth sensitivity grid for a Gordon-growth DCF."""
    result = _valuation.dcf_sensitivity(
        _dcf_inputs(inputs),
        discount_rates=tuple(discount_rates) if discount_rates else None,
        terminal_growths=tuple(terminal_growths) if terminal_growths else None,
    )
    return result.to_dict()


def compute_dcf_scenarios(base: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
    """Evaluate named DCF scenarios (bear/base/bull) from explicit overrides."""
    result = _valuation.dcf_scenarios(_dcf_inputs(base), scenarios)
    return result.to_dict()


def _dcf_inputs(inputs: dict[str, Any]) -> "_valuation.DcfInputs":
    data = dict(inputs)
    fcf = data.get("free_cash_flows")
    if isinstance(fcf, list):
        data["free_cash_flows"] = tuple(fcf)
    if not isinstance(data.get("free_cash_flows"), tuple):
        raise _valuation.DerivationError("dcf requires `free_cash_flows` as a list of period values")
    allowed = set(_valuation.DcfInputs.__dataclass_fields__)
    clean = {k: v for k, v in data.items() if k in allowed}
    return _valuation.DcfInputs(**clean)


def compute_growth(
    current: Any,
    prior: Any,
    *,
    kind: str = "yoy",
    years: Optional[float] = None,
    currency: Optional[str] = None,
) -> dict[str, Any]:
    """Explicit-basis growth (yoy/qoq/mom/ttm/percent/cagr) from two values."""
    def _fact(value: Any) -> "FinancialFact":
        return FinancialFact(
            fact_id="caller:growth", metric="growth", definition="growth",
            value=value, currency=currency, period=None, source="caller",
        )

    result = _metrics.growth(_fact(current), _fact(prior), kind=kind, years=years)
    return result.to_dict()


def compute_fcf(kind: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Free cash flow: simple (OCF−CapEx), FCFF (unlevered) or FCFE (levered)."""
    if kind == "free_cash_flow":
        allowed = set(_metrics.SPECS["free_cash_flow"].inputs)
        clean = {k: v for k, v in inputs.items() if k in allowed}
        facts = [_fact_from_input(name, value, currency=inputs.get("currency")) for name, value in clean.items()]
        return _metrics.derive("free_cash_flow", facts).to_dict()
    if kind == "fcff":
        return _metrics.free_cash_flow_to_firm(**_finite_kwargs(inputs, (
            "ebit", "tax_rate", "depreciation_amortization", "capex", "change_working_capital", "currency",
        ))).to_dict()
    if kind == "fcfe":
        return _metrics.free_cash_flow_to_equity(**_finite_kwargs(inputs, (
            "fcff", "interest_expense", "tax_rate", "net_borrowing", "currency",
        ))).to_dict()
    raise _metrics.DerivationError(f"unknown fcf kind {kind!r}; expected free_cash_flow, fcff or fcfe")


def compute_enterprise_value(inputs: dict[str, Any]) -> dict[str, Any]:
    """Enterprise value from explicit, visible components."""
    return _metrics.enterprise_value(**_finite_kwargs(inputs, (
        "market_cap", "total_debt", "preferred_equity", "minority_interest", "cash", "currency",
    ))).to_dict()


def _finite_kwargs(inputs: dict[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in inputs.items() if k in allowed and v is not None}


def describe_metrics() -> dict[str, Any]:
    """The metric catalog: names, grouped, so the model can request one."""
    return {
        "ratios": {
            name: {
                "formula": spec.formula,
                "inputs": list(spec.inputs),
                "unit": spec.unit,
                "note": spec.note,
            }
            for name, spec in sorted(_metrics.SPECS.items())
        },
        "series": {
            name: {"minObservations": _calc.MIN_OBSERVATIONS.get(name, 2)}
            for name in SERIES_METRICS
        },
        "valuation": list(VALUATION_METRICS),
        "growthKinds": list(_metrics.GROWTH_KINDS),
    }


#: The closed-form business calculations an agent must never do mentally.
#: Formulas MATCH the evaluation grader (`graders/financial.py::_simple`); a
#: test asserts the two agree, so a change on one side fails loudly.
SIMPLE_FORMULAS: dict[str, tuple[str, str]] = {
    "percentage_change": ("(end - start) / |start| * 100", "%"),
    "return": ("(end - start) / |start| * 100", "%"),
    "period_return": ("(end - start) / |start| * 100", "%"),
    "gross_margin": ("gross_profit / revenue * 100", "%"),
    "net_margin": ("net_income / revenue * 100", "%"),
    "operating_margin": ("operating_income / revenue * 100", "%"),
    "margin": ("operating_income (or net_income) / revenue * 100", "%"),
    "eps": ("net_income / shares", "per-share"),
    "pe": ("price / eps", "x"),
    "ps": ("price / sales_per_share", "x"),
    "position_size": ("reward / |risk|", "R"),
    "risk_reward": ("reward / |risk|", "R"),
    "risk_reward_ratio": ("reward / |risk|", "R"),
    "weight": ("value / total", ""),
    "portfolio_weights": ("value / total", ""),
    "cagr": ("((end / start) ** (1 / years) - 1) * 100", "%"),
    "fcf": ("operating_cash_flow - capex", "currency"),
}


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_simple(metric: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Compute one closed-form metric, or refuse with a named reason.

    The result carries the formula and the inputs so an answer can cite both.
    Never guesses: a missing input or a zero denominator is an error.
    """
    name = str(metric or "").strip().lower()
    if name not in SIMPLE_FORMULAS:
        raise ValueError(
            f"unknown metric {metric!r}; known: {sorted(SIMPLE_FORMULAS)}"
        )
    formula, unit = SIMPLE_FORMULAS[name]
    g = inputs.get if isinstance(inputs, dict) else (lambda _k, _d=None: None)

    def need(*keys: str) -> list[float]:
        values = [_num(g(k)) for k in keys]
        missing = [k for k, v in zip(keys, values) if v is None]
        if missing:
            raise ValueError(f"{name} requires numeric input(s): {', '.join(missing)}")
        return values  # type: ignore[return-value]

    value: Optional[float]
    if name in ("percentage_change", "return", "period_return"):
        start, end = need("start", "end")
        if start == 0:
            raise ValueError(f"{name} is undefined with a zero start")
        value = (end - start) / abs(start) * 100.0
    elif name in ("gross_margin", "net_margin", "operating_margin", "margin"):
        if name == "gross_margin":
            num_key = "gross_profit"
        elif name == "net_margin":
            num_key = "net_income"
        else:
            num_key = "operating_income" if g("operating_income") is not None else "net_income"
        num, revenue = need(num_key, "revenue")
        if revenue == 0:
            raise ValueError(f"{name} is undefined with zero revenue")
        value = num / revenue * 100.0
    elif name == "eps":
        net_income, shares = need("net_income", "shares")
        if shares == 0:
            raise ValueError("eps is undefined with zero shares")
        value = net_income / shares
    elif name == "pe":
        price, eps = need("price", "eps")
        if eps == 0:
            raise ValueError("pe is undefined with zero eps")
        value = price / eps
    elif name == "ps":
        price, sps = need("price", "sales_per_share")
        if sps == 0:
            raise ValueError("ps is undefined with zero sales_per_share")
        value = price / sps
    elif name in ("position_size", "risk_reward", "risk_reward_ratio"):
        risk, reward = need("risk", "reward")
        if risk == 0:
            raise ValueError(f"{name} is undefined with zero risk")
        value = reward / abs(risk)
    elif name in ("weight", "portfolio_weights"):
        part, total = need("value", "total")
        if total == 0:
            raise ValueError(f"{name} is undefined with zero total")
        value = part / total
    elif name == "cagr":
        start, end, years = need("start", "end", "years")
        if start <= 0 or end <= 0 or years <= 0:
            raise ValueError("cagr requires positive start, end and years")
        value = ((end / start) ** (1.0 / years) - 1.0) * 100.0
    else:  # fcf
        ocf = _num(g("operating_cash_flow"))
        if ocf is None:
            raise ValueError("fcf requires numeric input(s): operating_cash_flow")
        capex = _num(g("capex")) or 0.0
        value = ocf - capex

    return {
        "metric": name,
        "value": round(float(value), 10),
        "unit": unit,
        "formula": formula,
        "inputs": dict(inputs or {}),
    }


def _pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: source[k] for k in keys if k in source}


__all__ = [
    "SIMPLE_FORMULAS",
    "compute_simple",
    "RATIO_METRICS",
    "SERIES_METRICS",
    "VALUATION_METRICS",
    "compute_ratio",
    "compute_series",
    "compute_wacc",
    "compute_dcf",
    "compute_dcf_sensitivity",
    "compute_dcf_scenarios",
    "compute_growth",
    "compute_fcf",
    "compute_enterprise_value",
    "describe_metrics",
]
