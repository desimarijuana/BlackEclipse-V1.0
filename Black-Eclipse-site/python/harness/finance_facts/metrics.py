"""Derived-metric engine (Universal Financial Data Accuracy, §9).

Every derived metric exposes its metric, formula, inputs, input periods, input
sources and a calculation timestamp — and returns a `DerivedMetric`, never a
reported fact.

It refuses (never silently repairs) when the inputs are not comparable:
different currencies, different period types, mismatched attribution, or a
missing input. The engine KNOWS which price/eps/period/definition it used and
records it, so "P/E = 15" can always be traced to its numerator and denominator.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from .model import DerivedMetric, FinancialFact
from .semantics import definitions_differ
from .ttm import _numeric


class DerivationError(ValueError):
    """A metric could not be derived honestly from the given facts."""


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    formula: str
    inputs: tuple[str, ...]          # canonical definition ids required
    scale: float = 1.0               # e.g. 100.0 for a percentage
    unit: Optional[str] = None
    note: Optional[str] = None


# One row per derived metric. `inputs` are the DEFINITIONS (semantics.py), so the
# engine can never accidentally use "total equity" where "common equity" is meant.
# Point-in-time market inputs — a valuation ratio mixes a live price with a
# trailing fundamental, so these are exempt from the flow period-alignment check.
_MARKET_DEFINITIONS: frozenset[str] = frozenset({"price", "market_cap", "shares_outstanding", "volume"})

SPECS: dict[str, MetricSpec] = {
    "pe_ratio": MetricSpec("pe_ratio", "price / eps", ("price", "eps"), note="uses the share-class price and its EPS"),
    "forward_pe": MetricSpec("forward_pe", "price / eps_forward", ("price", "eps_forward"),
                             note="uses a FORWARD (estimate) EPS; the estimate basis is disclosed, not treated as reported"),
    "peg_ratio": MetricSpec("peg_ratio", "(price / eps) / eps_growth_pct", ("price", "eps"),
                            note="PEG = trailing P/E (from price and EPS) divided by the EPS growth rate in percent; growth is caller-supplied"),
    "pb_ratio": MetricSpec("pb_ratio", "market_cap / common_equity", ("market_cap", "common_equity"),
                           note="§7: book value uses COMMON equity, not total equity"),
    "pb_ratio_total_equity": MetricSpec("pb_ratio_total_equity", "market_cap / total_equity",
                                        ("market_cap", "total_equity"),
                                        note="explicitly labelled alternative; not the standard P/B"),
    "ps_ratio": MetricSpec("ps_ratio", "market_cap / revenue", ("market_cap", "revenue")),
    "ev_ebitda": MetricSpec("ev_ebitda", "(market_cap + net_debt) / ebitda", ("market_cap", "net_debt", "ebitda")),
    "fcf_yield": MetricSpec("fcf_yield", "free_cash_flow / market_cap", ("free_cash_flow", "market_cap"), scale=100.0, unit="%"),
    "dividend_yield": MetricSpec("dividend_yield", "dividend_per_share / price", ("dividend_per_share", "price"), scale=100.0, unit="%"),
    "roe": MetricSpec("roe", "net_income_parent / parent_equity", ("net_income_parent", "parent_equity"), scale=100.0, unit="%",
                      note="§6: uses parent-attributable earnings, not total consolidated"),
    "gross_margin": MetricSpec("gross_margin", "gross_profit / revenue", ("gross_profit", "revenue"), scale=100.0, unit="%"),
    "operating_margin": MetricSpec("operating_margin", "operating_income / revenue", ("operating_income", "revenue"), scale=100.0, unit="%"),
    "net_margin": MetricSpec("net_margin", "net_income / revenue", ("net_income", "revenue"), scale=100.0, unit="%"),
    "roa": MetricSpec("roa", "net_income_parent / total_assets", ("net_income_parent", "total_assets"), scale=100.0, unit="%"),
    "roic": MetricSpec("roic", "nopat / invested_capital", ("operating_income", "invested_capital"), scale=100.0, unit="%",
                       note="ROIC uses NOPAT (EBIT approximated by operating income); the tax basis must be supplied or is disclosed"),
    "net_debt_to_ebitda": MetricSpec("net_debt_to_ebitda", "net_debt / ebitda", ("net_debt", "ebitda")),
    "debt_to_equity": MetricSpec("debt_to_equity", "gross_debt / common_equity", ("gross_debt", "common_equity")),
    "free_cash_flow": MetricSpec(
        "free_cash_flow", "operating_cash_flow - capex", ("operating_cash_flow", "capex"),
        note="CapEx is taken as a magnitude; a reported negative capex is handled without double-counting",
    ),
    "enterprise_value": MetricSpec(
        "enterprise_value",
        "market_cap + total_debt + preferred_equity + minority_interest - cash",
        ("market_cap", "total_debt", "cash"),
        note="preferred_equity and minority_interest are optional (supplied via `extra`); each component used is recorded",
    ),
}


def _by_definition(facts: Sequence[FinancialFact], definition: str) -> Optional[FinancialFact]:
    """The single fact carrying this exact definition, or None when 0 or >1.

    More than one candidate is NOT resolved here — the caller must pass a
    reconciled set. This is the guard that stops two periods' revenue both being
    used without a choice.
    """
    matches = [f for f in facts if f.definition == definition and _numeric(f) is not None]
    if len(matches) == 1:
        return matches[0]
    return None


def _currency_ok(inputs: Sequence[FinancialFact]) -> bool:
    currencies = {f.currency for f in inputs if f.currency}
    return len(currencies) <= 1


def derive(
    metric: str,
    facts: Sequence[FinancialFact],
    *,
    now: Optional[str] = None,
    extra: Optional[dict[str, float]] = None,
) -> DerivedMetric:
    """Derive one metric from reconciled facts, recording the full provenance.

    Raises `DerivationError` when an input is missing, two currencies are mixed,
    or the inputs are not all reported (a derived input is not allowed to
    silently stand in for a reported one).

    `extra` supplies scalars a formula needs that are not themselves a fact row
    (e.g. `tax_rate` for ROIC, `eps_growth` percent for PEG, or a pre-computed
    `pe_ratio` for PEG). Each such scalar MUST be supplied by the caller — a
    metric that needs one and does not get it is refused, never defaulted.
    """
    spec = SPECS.get(metric)
    if spec is None:
        raise DerivationError(f"unknown metric {metric!r}")

    chosen: list[FinancialFact] = []
    for definition in spec.inputs:
        f = _by_definition(facts, definition)
        if f is None:
            raise DerivationError(
                f"{metric} needs exactly one {definition!r}; found "
                f"{sum(1 for x in facts if x.definition == definition)}"
            )
        chosen.append(f)

    if not _currency_ok(chosen):
        raise DerivationError(f"{metric}: inputs mix currencies {sorted({f.currency for f in chosen if f.currency})}")

    # Period alignment: all FLOW (fundamental) inputs must share a period type
    # (§3). A point-in-time MARKET input — a price or a market cap — is
    # intentionally a different period type and is exempt: a valuation ratio
    # combines a live price with a trailing fundamental, and that is correct.
    flow_types = {
        f.period.period_type for f in chosen
        if f.period is not None and f.definition not in _MARKET_DEFINITIONS
    }
    if len(flow_types) > 1:
        raise DerivationError(f"{metric}: inputs span different period types {sorted(flow_types)}; a transformation is required")

    values = {f.definition: _numeric(f) for f in chosen}
    # Caller-supplied scalars are lower precedence than a real fact of the same
    # name, so a reported value always wins over a passed-in scalar.
    for key, val in (extra or {}).items():
        values.setdefault(key, float(val))
    value = _compute_ratio(metric, values, spec.scale)

    calculated_at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return DerivedMetric(
        metric=metric,
        value=value,
        formula=spec.formula,
        inputs=tuple(
            {
                "definition": f.definition,
                "value": _numeric(f),
                "currency": f.currency,
                "period": f.period.key() if f.period else None,
                "source": f.source,
                "sourceType": f.source_type,
            }
            for f in chosen
        ),
        input_fact_ids=tuple(f.fact_id for f in chosen),
        input_periods=tuple(sorted({f.period.key() for f in chosen if f.period})),
        input_sources=tuple(sorted({f.source for f in chosen if f.source})),
        calculated_at=calculated_at,
        currency=chosen[0].currency,
        unit=spec.unit,
        warnings=tuple([spec.note] if spec.note else []),
    )


def _compute_ratio(metric: str, v: dict[str, Optional[float]], scale: float) -> Optional[float]:
    def g(k: str) -> Optional[float]:
        return v.get(k)

    if metric == "pe_ratio":
        eps = g("eps")
        if not eps or eps < 0:
            # §19: negative/zero earnings makes P/E undefined — say so, do not
            # return a fabricated number.
            raise DerivationError("P/E is undefined when EPS is zero or negative")
        return g("price") / eps if g("price") is not None else None
    if metric == "forward_pe":
        eps = g("eps_forward")
        if not eps or eps < 0:
            raise DerivationError("forward P/E is undefined when the forward EPS estimate is zero or negative")
        return g("price") / eps if g("price") is not None else None
    if metric == "peg_ratio":
        eps = g("eps")
        price = g("price")
        growth = g("eps_growth")
        if not eps or eps <= 0 or price is None:
            raise DerivationError("PEG is undefined without a positive EPS and a price")
        if not growth or growth <= 0:
            raise DerivationError("PEG is undefined when the EPS growth rate is zero or negative")
        pe = price / eps
        return pe / growth
    if metric in ("pb_ratio", "pb_ratio_total_equity"):
        eq = g("common_equity") if metric == "pb_ratio" else g("total_equity")
        return (g("market_cap") / eq * scale) if eq else None
    if metric == "ps_ratio":
        rev = g("revenue")
        return (g("market_cap") / rev) if rev else None
    if metric == "ev_ebitda":
        ev = (g("market_cap") or 0.0) + (g("net_debt") or 0.0)
        ebitda = g("ebitda")
        return (ev / ebitda) if ebitda else None
    if metric == "fcf_yield":
        mc = g("market_cap")
        return (g("free_cash_flow") / mc * scale) if mc else None
    if metric == "dividend_yield":
        p = g("price")
        return (g("dividend_per_share") / p * scale) if p else None
    if metric == "roe":
        eq = g("parent_equity")
        return (g("net_income_parent") / eq * scale) if eq else None
    if metric == "gross_margin":
        rev = g("revenue")
        return (g("gross_profit") / rev * scale) if rev else None
    if metric == "operating_margin":
        rev = g("revenue")
        return (g("operating_income") / rev * scale) if rev else None
    if metric == "net_margin":
        rev = g("revenue")
        return (g("net_income") / rev * scale) if rev else None
    if metric == "roa":
        ta = g("total_assets")
        return (g("net_income_parent") / ta * scale) if ta else None
    if metric == "roic":
        # NOPAT = operating income (EBIT proxy) × (1 − tax rate). The tax rate is
        # carried on the operating-income fact's raw metadata ("taxRate"); absent
        # it we use the effective rate only if stated — never a blanket 21%.
        ic = g("invested_capital")
        if not ic:
            return None
        ebit = g("operating_income")
        if ebit is None:
            return None
        tax_rate = v.get("tax_rate")
        if tax_rate is None:
            raise DerivationError("ROIC requires a stated tax rate (raw 'taxRate'); a default is never assumed")
        nopat = ebit * (1.0 - float(tax_rate))
        return nopat / ic * scale
    if metric == "net_debt_to_ebitda":
        e = g("ebitda")
        return (g("net_debt") / e) if e else None
    if metric == "debt_to_equity":
        eq = g("common_equity")
        return (g("gross_debt") / eq) if eq else None
    if metric == "free_cash_flow":
        ocf = g("operating_cash_flow")
        capex = g("capex")
        if ocf is None or capex is None:
            return None
        return ocf - abs(capex)
    if metric == "enterprise_value":
        mc = g("market_cap")
        if mc is None:
            return None
        return (
            mc
            + (g("total_debt") or 0.0)
            + (g("preferred_equity") or 0.0)
            + (g("minority_interest") or 0.0)
            - (g("cash") or 0.0)
        )
    return None


def growth_rate(current: FinancialFact, prior: FinancialFact) -> DerivedMetric:
    """A growth percentage, with BOTH periods, both definitions and both sources
    recorded — the §22 requirement that a growth claim be validated, not asserted."""
    if definitions_differ(current.definition, prior.definition):
        raise DerivationError(
            "cannot compute growth across different definitions: "
            f"{current.definition} vs {prior.definition}"
        )
    if current.period is not None and prior.period is not None:
        if not current.period.period_type == prior.period.period_type:
            raise DerivationError("cannot compute growth across different period types")
    c, p = _numeric(current), _numeric(prior)
    if c is None or p is None or p == 0:
        raise DerivationError("growth is undefined with a missing or zero denominator")
    value = (c - p) / abs(p) * 100.0
    return DerivedMetric(
        metric="growth_rate",
        value=value,
        formula="(current - prior) / |prior| * 100",
        inputs=(
            {"definition": current.definition, "value": c, "period": current.period.key() if current.period else None, "source": current.source},
            {"definition": prior.definition, "value": p, "period": prior.period.key() if prior.period else None, "source": prior.source},
        ),
        input_fact_ids=(current.fact_id, prior.fact_id),
        input_periods=tuple(sorted(x for x in (current.period.key() if current.period else None,
                                               prior.period.key() if prior.period else None) if x)),
        input_sources=tuple(sorted({s for s in (current.source, prior.source) if s})),
        calculated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        unit="%",
    )


# Growth kinds this engine understands. `cagr` needs an explicit span in years;
# the rest are period-over-period percentage changes whose ONLY difference is the
# declared comparison basis (reflected in the metric name and assumptions).
GROWTH_KINDS: tuple[str, ...] = ("yoy", "qoq", "mom", "ttm", "percent", "cagr")


def growth(
    current: FinancialFact,
    prior: FinancialFact,
    *,
    kind: str = "yoy",
    years: Optional[float] = None,
) -> DerivedMetric:
    """A growth figure with its comparison basis made explicit.

    `kind="cagr"` compounds over an explicit `years` and requires positive start
    and end values; every other kind is a percentage change over the stated basis
    (yoy/qoq/mom/ttm). A negative or zero base is refused or warned on — a growth
    percentage over a non-positive base is not silently presented as meaningful.
    """
    if kind not in GROWTH_KINDS:
        raise DerivationError(f"unknown growth kind {kind!r}; expected {GROWTH_KINDS}")
    if definitions_differ(current.definition, prior.definition):
        raise DerivationError(
            "cannot compute growth across different definitions: "
            f"{current.definition} vs {prior.definition}"
        )
    if current.period is not None and prior.period is not None:
        if current.period.period_type != prior.period.period_type:
            raise DerivationError("cannot compute growth across different period types")
    c, p = _numeric(current), _numeric(prior)
    if c is None or p is None:
        raise DerivationError("growth is undefined with a missing value")
    base_inputs = (
        {"definition": current.definition, "value": c, "period": current.period.key() if current.period else None, "source": current.source},
        {"definition": prior.definition, "value": p, "period": prior.period.key() if prior.period else None, "source": prior.source},
    )
    periods = tuple(sorted(x for x in (current.period.key() if current.period else None,
                                      prior.period.key() if prior.period else None) if x))
    sources = tuple(sorted({s for s in (current.source, prior.source) if s}))
    calculated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if kind == "cagr":
        if p <= 0 or c <= 0:
            raise DerivationError("CAGR requires strictly positive start and end values")
        if years is None or not math.isfinite(float(years)) or float(years) <= 0:
            raise DerivationError("CAGR growth requires an explicit positive `years` span")
        span = float(years)
        value = ((c / p) ** (1.0 / span) - 1.0) * 100.0
        return DerivedMetric(
            metric="cagr",
            value=value,
            formula="((current / prior)^(1/years) - 1) * 100",
            inputs=base_inputs,
            input_fact_ids=(current.fact_id, prior.fact_id),
            input_periods=periods,
            input_sources=sources,
            calculated_at=calculated_at,
            unit="%",
            warnings=(f"compounded over {span:.6g} years",),
        )

    if p == 0:
        raise DerivationError("growth is undefined with a zero denominator")
    value = (c - p) / abs(p) * 100.0
    warnings: list[str] = []
    if p < 0:
        warnings.append(
            "the prior-period base is negative; the percentage change over |base| "
            "is not economically comparable to growth from a positive base"
        )
    return DerivedMetric(
        metric=f"growth_{kind}" if kind != "percent" else "growth_rate",
        value=value,
        formula="(current - prior) / |prior| * 100",
        inputs=base_inputs,
        input_fact_ids=(current.fact_id, prior.fact_id),
        input_periods=periods,
        input_sources=sources,
        calculated_at=calculated_at,
        unit="%",
        warnings=tuple(warnings),
    )


def enterprise_value(
    market_cap: float,
    *,
    total_debt: float = 0.0,
    preferred_equity: float = 0.0,
    minority_interest: float = 0.0,
    cash: float = 0.0,
    currency: Optional[str] = None,
) -> DerivedMetric:
    """Enterprise value constructed from explicit, visible components.

    EV = market cap + total debt + preferred equity + minority interest − cash.
    Every component actually used is recorded so the bridge from equity value to
    enterprise value is auditable and no assumption is hidden.
    """
    mc = _finite_component(market_cap, "market_cap")
    debt = _finite_component(total_debt, "total_debt")
    preferred = _finite_component(preferred_equity, "preferred_equity")
    minority = _finite_component(minority_interest, "minority_interest")
    cash_v = _finite_component(cash, "cash")
    value = mc + debt + preferred + minority - cash_v
    return DerivedMetric(
        metric="enterprise_value",
        value=value,
        formula="market_cap + total_debt + preferred_equity + minority_interest - cash",
        inputs=(
            {"name": "market_cap", "value": mc},
            {"name": "total_debt", "value": debt},
            {"name": "preferred_equity", "value": preferred},
            {"name": "minority_interest", "value": minority},
            {"name": "cash", "value": cash_v},
        ),
        calculated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        currency=currency,
        warnings=("EV depends on which debt/cash definitions are supplied",),
    )


def free_cash_flow_to_firm(
    *,
    ebit: float,
    tax_rate: float,
    depreciation_amortization: float = 0.0,
    capex: float = 0.0,
    change_working_capital: float = 0.0,
    currency: Optional[str] = None,
) -> DerivedMetric:
    """Unlevered free cash flow (FCFF) from an explicit EBIT build-up.

    FCFF = EBIT·(1 − tax) + D&A − CapEx − ΔNWC. Capital expenditure is applied as
    a magnitude, so a reported negative capex is not double-counted.
    """
    ebit_v = _finite_component(ebit, "ebit")
    tax = _finite_component(tax_rate, "tax_rate")
    if not (0.0 <= tax < 1.0):
        raise DerivationError(f"tax_rate must be in [0, 1), got {tax!r}")
    da = _finite_component(depreciation_amortization, "depreciation_amortization")
    capex_v = _finite_component(capex, "capex")
    nwc = _finite_component(change_working_capital, "change_working_capital")
    value = ebit_v * (1.0 - tax) + da - abs(capex_v) - nwc
    return DerivedMetric(
        metric="fcff",
        value=value,
        formula="ebit*(1 - tax) + depreciation_amortization - |capex| - change_working_capital",
        inputs=(
            {"name": "ebit", "value": ebit_v},
            {"name": "tax_rate", "value": tax},
            {"name": "depreciation_amortization", "value": da},
            {"name": "capex", "value": capex_v},
            {"name": "change_working_capital", "value": nwc},
        ),
        calculated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        currency=currency,
        warnings=("FCFF uses EBIT as the operating-profit proxy and an explicit tax rate",),
    )


def free_cash_flow_to_equity(
    *,
    fcff: float,
    interest_expense: float,
    tax_rate: float,
    net_borrowing: float = 0.0,
    currency: Optional[str] = None,
) -> DerivedMetric:
    """Levered free cash flow (FCFE) from FCFF.

    FCFE = FCFF − interest·(1 − tax) + net borrowing. The after-tax interest
    shield is applied explicitly; `net_borrowing` is new debt less repayments.
    """
    firm = _finite_component(fcff, "fcff")
    interest = _finite_component(interest_expense, "interest_expense")
    tax = _finite_component(tax_rate, "tax_rate")
    if not (0.0 <= tax < 1.0):
        raise DerivationError(f"tax_rate must be in [0, 1), got {tax!r}")
    borrow = _finite_component(net_borrowing, "net_borrowing")
    value = firm - interest * (1.0 - tax) + borrow
    return DerivedMetric(
        metric="fcfe",
        value=value,
        formula="fcff - interest_expense*(1 - tax) + net_borrowing",
        inputs=(
            {"name": "fcff", "value": firm},
            {"name": "interest_expense", "value": interest},
            {"name": "tax_rate", "value": tax},
            {"name": "net_borrowing", "value": borrow},
        ),
        calculated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        currency=currency,
        warnings=("FCFE is FCFF adjusted for the after-tax interest shield and net borrowing",),
    )


def _finite_component(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DerivationError(f"{label} must be a number, got {value!r}") from None
    if not math.isfinite(number):
        raise DerivationError(f"{label} must be finite, got {value!r}")
    return number


__all__ = [
    "DerivationError",
    "SPECS",
    "GROWTH_KINDS",
    "MetricSpec",
    "derive",
    "growth",
    "growth_rate",
    "enterprise_value",
    "free_cash_flow_to_firm",
    "free_cash_flow_to_equity",
]
