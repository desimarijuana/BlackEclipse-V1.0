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
    "roa": MetricSpec("roa", "net_income_parent / total_assets", ("net_income_parent", "total_assets"), scale=100.0, unit="%"),
    "net_debt_to_ebitda": MetricSpec("net_debt_to_ebitda", "net_debt / ebitda", ("net_debt", "ebitda")),
    "debt_to_equity": MetricSpec("debt_to_equity", "gross_debt / common_equity", ("gross_debt", "common_equity")),
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


def derive(metric: str, facts: Sequence[FinancialFact], *, now: Optional[str] = None) -> DerivedMetric:
    """Derive one metric from reconciled facts, recording the full provenance.

    Raises `DerivationError` when an input is missing, two currencies are mixed,
    or the inputs are not all reported (a derived input is not allowed to
    silently stand in for a reported one).
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
    if metric == "roa":
        ta = g("total_assets")
        return (g("net_income_parent") / ta * scale) if ta else None
    if metric == "net_debt_to_ebitda":
        e = g("ebitda")
        return (g("net_debt") / e) if e else None
    if metric == "debt_to_equity":
        eq = g("common_equity")
        return (g("gross_debt") / eq) if eq else None
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


__all__ = ["DerivationError", "SPECS", "MetricSpec", "derive", "growth_rate"]
