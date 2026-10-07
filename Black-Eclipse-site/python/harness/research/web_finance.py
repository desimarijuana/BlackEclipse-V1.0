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

from typing import Any, Optional

from ..finance_facts import metrics as _metrics
from ..finance_facts import valuation as _valuation
from ..finance_facts.model import FinancialFact, FinancialPeriod
from ..research import calculations as _calc


# Every ratio/margin metric this adapter can compute, grouped for the model.
RATIO_METRICS: tuple[str, ...] = tuple(sorted(_metrics.SPECS))
SERIES_METRICS: tuple[str, ...] = tuple(sorted(_calc.CALCULATORS))
VALUATION_METRICS: tuple[str, ...] = ("wacc", "dcf", "dcf_equity_value", "dcf_equity_value_per_share")


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


def compute_series(
    metric: str,
    observations: list[dict[str, Any]],
    *,
    benchmark: Optional[list[dict[str, Any]]] = None,
    options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compute a time-series metric (sortino/VaR/beta/…) from dated observations."""
    if metric not in _calc.CALCULATORS:
        raise _calc.CalculationError(f"unknown series metric {metric!r}; known: {sorted(_calc.CALCULATORS)}")
    opts = options or {}
    if metric == "beta":
        if not benchmark:
            raise _calc.CalculationError("beta requires a `benchmark` observation series")
        result = _calc.beta(observations, benchmark, **_pick(opts, ("frequency",)))
    elif metric in ("period_change",):
        values = [o["value"] for o in observations if o.get("value") is not None]
        if len(values) < 2:
            raise _calc.CalculationError("period_change needs two values")
        result = _calc.period_change(values[0], values[-1], observations=observations, **_pick(opts, ("frequency",)))
    elif metric == "cagr":
        result = _calc.cagr(observations, **_pick(opts, ("years", "frequency")))
    elif metric == "annualized_volatility":
        result = _calc.annualized_volatility(observations, **_pick(opts, ("frequency", "risk_free_rate")))
    elif metric == "max_drawdown":
        result = _calc.max_drawdown(observations, **_pick(opts, ("frequency",)))
    elif metric == "sharpe":
        if "risk_free_rate" not in opts:
            raise _calc.CalculationError("sharpe requires `risk_free_rate` in options")
        result = _calc.sharpe(observations, **_pick(opts, ("risk_free_rate", "frequency", "risk_free_source")))
    elif metric == "sortino":
        result = _calc.sortino(observations, **_pick(opts, ("risk_free_rate", "frequency", "target", "risk_free_source")))
    else:  # value_at_risk
        result = _calc.value_at_risk(observations, **_pick(opts, ("confidence", "frequency", "horizon_periods")))
    return result.to_dict()


def compute_wacc(inputs: dict[str, Any]) -> dict[str, Any]:
    """WACC from explicit capital/CAPM inputs (no default rates)."""
    allowed = set(_valuation.WaccInputs.__dataclass_fields__)
    clean = {k: v for k, v in inputs.items() if k in allowed and v is not None}
    result = _valuation.wacc(_valuation.WaccInputs(**clean))
    return result.to_dict()


def compute_dcf(inputs: dict[str, Any]) -> dict[str, Any]:
    """DCF valuation from an explicit forecast (Gordon growth OR exit multiple)."""
    data = dict(inputs)
    if isinstance(data.get("free_cash_flows"), list):
        data["free_cash_flows"] = tuple(data["free_cash_flows"])
    if isinstance(data.get("free_cash_flows"), tuple):
        pass
    else:
        raise _valuation.DerivationError("dcf requires `free_cash_flows` as a list of period values")
    allowed = set(_valuation.DcfInputs.__dataclass_fields__)
    clean = {k: v for k, v in data.items() if k in allowed}
    result = _valuation.dcf(_valuation.DcfInputs(**clean))
    return result.to_dict()


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
    }


def _pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: source[k] for k in keys if k in source}


__all__ = [
    "RATIO_METRICS",
    "SERIES_METRICS",
    "VALUATION_METRICS",
    "compute_ratio",
    "compute_series",
    "compute_wacc",
    "compute_dcf",
    "describe_metrics",
]
