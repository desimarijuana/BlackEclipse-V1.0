"""Discounted-cash-flow and WACC valuation (deterministic, provenance-first).

These are NOT simple ratios: WACC mixes a cost of equity (CAPM) with an
after-tax cost of debt, and a DCF discounts an explicit cash-flow forecast plus a
terminal value. Both are computed here in pure Python from caller-supplied,
auditable inputs, and both record every input and assumption on the resulting
`DerivedMetric`.

Nothing is defaulted silently. A missing beta, risk-free rate, equity-risk
premium, tax rate, forecast, discount rate or terminal assumption is refused with
a precise reason rather than guessed. A DCF is an OPINION/ESTIMATE, never a
reported fact: the output carries that classification and the full sensitivity of
its inputs.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .metrics import DerivationError
from .model import DerivedMetric
from .ttm import _numeric


def _finite(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DerivationError(f"{label} must be a number, got {value!r}") from None
    if not math.isfinite(number):
        raise DerivationError(f"{label} must be finite, got {value!r}")
    return number


@dataclass(frozen=True)
class WaccInputs:
    """The explicit inputs to a WACC (weighted average cost of capital)."""

    market_cap: float            # equity market value E
    total_debt: float            # debt value D (gross debt)
    risk_free_rate: float        # annual, decimal (e.g. 0.04)
    beta: float                  # equity beta
    equity_risk_premium: float   # annual ERP, decimal
    cost_of_debt: Optional[float] = None  # annual pre-tax Rd, decimal
    tax_rate: Optional[float] = None      # effective marginal tax rate, decimal
    currency: Optional[str] = None
    risk_free_source: Optional[str] = None


@dataclass(frozen=True)
class DcfInputs:
    """The explicit inputs to a discounted-cash-flow valuation."""

    free_cash_flows: tuple[float, ...]   # explicit forecast periods 1..n
    discount_rate: float                 # WACC, decimal
    terminal_growth: Optional[float] = None       # Gordon growth, decimal
    terminal_fcf: Optional[float] = None          # FCF in the terminal period
    exit_multiple: Optional[float] = None         # EV/EBITDA exit (alternative)
    terminal_metric: Optional[float] = None       # EBITDA for the exit multiple
    net_debt: float = 0.0                          # subtracted to reach equity
    shares_outstanding: Optional[float] = None    # to reach per-share value
    currency: Optional[str] = None


def wacc(inputs: WaccInputs, *, now: Optional[str] = None) -> DerivedMetric:
    """Weighted average cost of capital via CAPM cost of equity + after-tax debt.

        WACC = (E/V)·Re + (D/V)·Rd·(1 − tax)

    A cost of debt and tax rate are REQUIRED whenever debt is present: without
    them the after-tax cost of debt cannot be computed honestly, so the metric is
    refused (never approximated with a default rate).
    """
    e = _finite(inputs.market_cap, "market_cap")
    d = _finite(inputs.total_debt, "total_debt")
    rf = _finite(inputs.risk_free_rate, "risk_free_rate")
    beta = _finite(inputs.beta, "beta")
    erp = _finite(inputs.equity_risk_premium, "equity_risk_premium")
    if e < 0 or d < 0:
        raise DerivationError("market_cap and total_debt must be non-negative")
    v = e + d
    if v <= 0:
        raise DerivationError("WACC is undefined when the firm has no capital (E + D = 0)")

    cost_of_equity = rf + beta * erp
    warnings: list[str] = []
    if d > 0:
        if inputs.cost_of_debt is None:
            raise DerivationError("WACC requires a cost of debt when debt is present (no default rate is assumed)")
        if inputs.tax_rate is None:
            raise DerivationError("WACC requires a tax rate when debt is present (no default rate is assumed)")
        rd = _finite(inputs.cost_of_debt, "cost_of_debt")
        tax = _finite(inputs.tax_rate, "tax_rate")
        after_tax_rd = rd * (1.0 - tax)
        value = (e / v) * cost_of_equity + (d / v) * after_tax_rd
    else:
        # All-equity firm: WACC = cost of equity.
        rd = None
        after_tax_rd = None
        value = cost_of_equity
        warnings.append("no debt: WACC reduces to the CAPM cost of equity")

    calculated_at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs_rows = [
        {"name": "market_cap", "value": e},
        {"name": "total_debt", "value": d},
        {"name": "risk_free_rate", "value": rf},
        {"name": "beta", "value": beta},
        {"name": "equity_risk_premium", "value": erp},
    ]
    if rd is not None:
        inputs_rows.append({"name": "cost_of_debt", "value": rd})
        inputs_rows.append({"name": "tax_rate", "value": inputs.tax_rate})
    return DerivedMetric(
        metric="wacc",
        value=value * 100.0,
        formula="(E/V)*Re + (D/V)*Rd*(1 - tax); Re = rf + beta*ERP",
        inputs=tuple(inputs_rows),
        calculated_at=calculated_at,
        currency=inputs.currency,
        unit="%",
        warnings=tuple(warnings) + (
            "cost of equity uses CAPM; beta and ERP are estimates, not facts",
        ),
    )


def dcf(inputs: DcfInputs, *, now: Optional[str] = None) -> DerivedMetric:
    """Discounted-cash-flow enterprise/equity value from an explicit forecast.

    Discounts each forecast FCF, adds ONE terminal value (Gordon growth OR an
    exit multiple — never both silently), subtracts net debt, and optionally
    divides by shares for a per-share value. Every assumption is recorded and the
    result is classified as an estimate. The per-period schedule is attached in
    `detail` so the number is fully reconstructable.
    """
    breakdown = dcf_breakdown(inputs)
    calculated_at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    b = breakdown
    return DerivedMetric(
        metric="dcf_equity_value_per_share" if b.per_share is not None else "dcf_equity_value",
        value=b.per_share if b.per_share is not None else b.equity_value,
        formula="sum(FCF_t/(1+r)^t) + TV/(1+r)^n - net_debt [ / shares ]",
        inputs=tuple(b.inputs_rows),
        calculated_at=calculated_at,
        currency=inputs.currency,
        warnings=(
            f"terminal value via {b.terminal_desc}",
            "a DCF is an ESTIMATE/OPINION driven by the forecast and discount rate, not a reported fact",
            *b.terminal_assumptions,
        ),
        detail={
            "schedule": b.schedule,
            "discountRate": b.rate,
            "terminalValue": b.terminal_value,
            "presentValueExplicit": b.pv_explicit,
            "presentValueTerminal": b.pv_terminal,
            "enterpriseValue": b.enterprise_value,
            "netDebt": b.net_debt,
            "equityValue": b.equity_value,
            "valuePerShare": b.per_share,
        },
    )


@dataclass(frozen=True)
class DcfBreakdown:
    """The fully computed internal structure of a DCF (one formula, one place)."""

    rate: float
    fcf: tuple[float, ...]
    terminal_value: float
    terminal_desc: str
    terminal_assumptions: tuple[str, ...]
    pv_explicit: float
    pv_terminal: float
    enterprise_value: float
    net_debt: float
    equity_value: float
    per_share: Optional[float]
    schedule: list[dict]
    inputs_rows: list[dict]


def dcf_breakdown(inputs: DcfInputs) -> DcfBreakdown:
    """Validate and compute a DCF once, returning the full auditable breakdown.

    Every other DCF-shaped function (schedule, sensitivity, scenarios) is built
    on this, so there is exactly one implementation of the discounting formula.
    """
    fcf = tuple(_finite(x, f"free_cash_flows[{i}]") for i, x in enumerate(inputs.free_cash_flows))
    if not fcf:
        raise DerivationError("DCF requires at least one forecast free-cash-flow period")
    rate = _finite(inputs.discount_rate, "discount_rate")
    if not (0.0 < rate < 1.0):
        raise DerivationError(f"discount_rate must be in (0, 1), got {rate!r}")
    if (inputs.terminal_growth is None) == (inputs.exit_multiple is None):
        raise DerivationError(
            "DCF requires exactly ONE terminal method: terminal_growth OR exit_multiple"
        )
    if inputs.terminal_growth is not None:
        g = _finite(inputs.terminal_growth, "terminal_growth")
        if g >= rate:
            raise DerivationError("terminal growth must be strictly less than the discount rate")
        base_fcf = _finite(inputs.terminal_fcf, "terminal_fcf") if inputs.terminal_fcf is not None else fcf[-1]
        terminal_value = base_fcf * (1.0 + g) / (rate - g)
        terminal_desc = f"Gordon growth g={g:.4g}"
        terminal_assumptions = (f"terminal value = FCF*(1+g)/(r-g) with g={g:.4g}",)
    else:
        multiple = _finite(inputs.exit_multiple, "exit_multiple")
        if inputs.terminal_metric is None:
            raise DerivationError("an exit-multiple DCF requires the terminal_metric (e.g. terminal EBITDA)")
        metric_value = _finite(inputs.terminal_metric, "terminal_metric")
        terminal_value = multiple * metric_value
        terminal_desc = f"exit multiple {multiple:.4g}x on {metric_value:,.0f}"
        terminal_assumptions = (f"terminal value = {multiple:.4g}x × terminal metric",)

    n = len(fcf)
    schedule: list[dict] = []
    pv_explicit = 0.0
    for t, cf in enumerate(fcf):
        discount_factor = 1.0 / ((1.0 + rate) ** (t + 1))
        pv = cf * discount_factor
        pv_explicit += pv
        schedule.append({
            "period": t + 1,
            "freeCashFlow": cf,
            "discountFactor": discount_factor,
            "presentValue": pv,
        })
    pv_terminal = terminal_value / ((1.0 + rate) ** n)
    enterprise_value = pv_explicit + pv_terminal
    net_debt = _finite(inputs.net_debt, "net_debt")
    equity_value = enterprise_value - net_debt

    per_share: Optional[float] = None
    if inputs.shares_outstanding is not None:
        shares = _finite(inputs.shares_outstanding, "shares_outstanding")
        if shares <= 0:
            raise DerivationError("shares_outstanding must be positive to compute a per-share value")
        per_share = equity_value / shares

    rows = [{"name": f"fcf[t={i + 1}]", "value": cf} for i, cf in enumerate(fcf)]
    rows.append({"name": "discount_rate", "value": rate})
    rows.append({"name": "terminal_value", "value": terminal_value})
    rows.append({"name": "enterprise_value", "value": enterprise_value})
    rows.append({"name": "net_debt", "value": net_debt})
    if inputs.shares_outstanding is not None:
        rows.append({"name": "shares_outstanding", "value": inputs.shares_outstanding})

    return DcfBreakdown(
        rate=rate, fcf=fcf, terminal_value=terminal_value, terminal_desc=terminal_desc,
        terminal_assumptions=terminal_assumptions, pv_explicit=pv_explicit,
        pv_terminal=pv_terminal, enterprise_value=enterprise_value, net_debt=net_debt,
        equity_value=equity_value, per_share=per_share, schedule=schedule, inputs_rows=rows,
    )


def dcf_schedule(inputs: DcfInputs, *, now: Optional[str] = None) -> DerivedMetric:
    """A DCF with the full per-period discounting schedule in `detail`."""
    result = dcf(inputs, now=now)
    result.detail["scheduleExtended"] = [
        {
            **row,
            "discountedAt": f"r={result.detail['discountRate']:.6g}",
        }
        for row in result.detail["schedule"]
    ]
    return result


def dcf_sensitivity(
    inputs: DcfInputs,
    *,
    discount_rates: Optional[Sequence[float]] = None,
    terminal_growths: Optional[Sequence[float]] = None,
    now: Optional[str] = None,
) -> DerivedMetric:
    """A WACC × terminal-growth sensitivity grid for a Gordon-growth DCF.

    Invalid cells (terminal growth >= discount rate) are marked `None` — a
    mathematically meaningless value is refused, not returned. `detail` carries
    the axis values and both the enterprise-value and per-share matrices.
    """
    if inputs.terminal_growth is None:
        raise DerivationError("dcf_sensitivity requires a Gordon-growth DCF (terminal_growth, not exit_multiple)")
    base_rate = _finite(inputs.discount_rate, "discount_rate")
    base_growth = _finite(inputs.terminal_growth, "terminal_growth")
    rates = tuple(_finite(r, "discount_rate") for r in (discount_rates or _grid(base_rate, 0.01)))  # type: ignore[arg-type]
    growths = tuple(_finite(g, "terminal_growth") for g in (terminal_growths or _grid(base_growth, 0.005)))  # type: ignore[arg-type]
    if not rates or not growths:
        raise DerivationError("dcf_sensitivity needs at least one discount rate and one terminal growth")

    ev_matrix: list[list[Optional[float]]] = []
    ps_matrix: list[list[Optional[float]]] = []
    for r in rates:
        ev_row: list[Optional[float]] = []
        ps_row: list[Optional[float]] = []
        for g in growths:
            if g >= r:
                ev_row.append(None)
                ps_row.append(None)
                continue
            candidate = _replace_dcf(inputs, discount_rate=r, terminal_growth=g)
            try:
                b = dcf_breakdown(candidate)
            except DerivationError:
                ev_row.append(None)
                ps_row.append(None)
                continue
            ev_row.append(b.enterprise_value)
            ps_row.append(b.per_share)
        ev_matrix.append(ev_row)
        ps_matrix.append(ps_row)

    calculated_at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return DerivedMetric(
        metric="dcf_sensitivity",
        value=None,
        formula="enterprise value over a discount-rate × terminal-growth grid",
        calculated_at=calculated_at,
        currency=inputs.currency,
        warnings=(
            "a DCF sensitivity inherits every assumption of the base DCF",
            "cells where terminal growth >= discount rate are None (invalid), never a number",
        ),
        detail={
            "rowAxis": "discountRate",
            "columnAxis": "terminalGrowth",
            "discountRates": list(rates),
            "terminalGrowths": list(growths),
            "enterpriseValue": ev_matrix,
            "valuePerShare": ps_matrix,
        },
    )


def dcf_scenarios(
    base: DcfInputs,
    scenarios: dict[str, dict],
    *,
    now: Optional[str] = None,
) -> DerivedMetric:
    """Evaluate named DCF scenarios (e.g. bear/base/bull) from explicit overrides.

    Each scenario is a mapping of `DcfInputs` field → value; fields left out keep
    the base assumption. Every scenario's resolved assumptions are recorded, so a
    scenario can never silently differ from what is shown.
    """
    if not scenarios:
        raise DerivationError("dcf_scenarios requires at least one named scenario")
    allowed = set(DcfInputs.__dataclass_fields__)
    results: dict[str, Any] = {}
    for name, overrides in scenarios.items():
        if not isinstance(overrides, dict):
            raise DerivationError(f"scenario {name!r} must be a mapping of DcfInputs fields")
        unknown = set(overrides) - allowed
        if unknown:
            raise DerivationError(f"scenario {name!r} has unknown fields: {sorted(unknown)}")
        candidate = _replace_dcf(base, **overrides)
        b = dcf_breakdown(candidate)
        results[name] = {
            "assumptions": {
                "discountRate": b.rate,
                "terminalValue": b.terminal_value,
                "terminalDescription": b.terminal_desc,
                "freeCashFlows": list(b.fcf),
                "netDebt": b.net_debt,
                "sharesOutstanding": candidate.shares_outstanding,
            },
            "enterpriseValue": b.enterprise_value,
            "equityValue": b.equity_value,
            "valuePerShare": b.per_share,
        }
    calculated_at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return DerivedMetric(
        metric="dcf_scenarios",
        value=results.get("base", {}).get("valuePerShare"),
        formula="one DCF per named scenario, each with explicit assumptions",
        calculated_at=calculated_at,
        currency=base.currency,
        warnings=("each scenario is an ESTIMATE driven by its own stated assumptions",),
        detail={"scenarios": results},
    )


def _grid(center: float, step: float, *, count: int = 5) -> tuple[float, ...]:
    half = count // 2
    return tuple(round(center + (i - half) * step, 10) for i in range(count))


def _replace_dcf(inputs: DcfInputs, **overrides: Any) -> DcfInputs:
    allowed = set(DcfInputs.__dataclass_fields__)
    clean = {k: v for k, v in overrides.items() if k in allowed and v is not None}
    return dataclasses.replace(inputs, **clean)


__all__ = [
    "WaccInputs",
    "DcfInputs",
    "DcfBreakdown",
    "wacc",
    "dcf",
    "dcf_breakdown",
    "dcf_schedule",
    "dcf_sensitivity",
    "dcf_scenarios",
]
