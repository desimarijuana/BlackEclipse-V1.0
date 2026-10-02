"""Research router (Universal Financial Data Accuracy, §24).

The agent should determine what information a question NEEDS before retrieving
data, instead of retrieving whatever JDdS happens to contain. Given a question and
the entity's sector, this module returns the required evidence areas — a REQUEST,
never evidence.

It is a deterministic rule table, not a model prompt: a question is classified by
keyword into an intent, and the intent + sector selects the evidence set. An
unknown question gets a broad default rather than a guess. No ticker-specific logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import sector as _sector

# Intent → the evidence areas it needs. An intent outside this table falls to the
# broad default below.
INTENT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "health": ("revenue_growth", "margins", "profitability", "balance_sheet", "liquidity",
               "debt", "cash_flow", "capital_efficiency", "dilution", "valuation",
               "recent_trends", "risks"),
    "valuation": ("price", "market_cap", "shares_outstanding", "eps", "book_value_per_share",
                  "revenue", "net_income_parent", "multiples", "growth"),
    "profitability": ("revenue", "gross_profit", "operating_income", "net_income_parent",
                      "margins", "roe"),
    "growth": ("revenue", "net_income_parent", "multiples", "period_over_period"),
    "debt": ("gross_debt", "net_debt", "financial_debt", "lease_liabilities", "cash",
             "parent_equity", "ebitda"),
    "cash_flow": ("operating_cash_flow", "capex", "free_cash_flow", "period_alignment"),
    "earnings": ("eps", "net_income_parent", "net_income_nci", "period", "estimates"),
    "dividend": ("dividend_per_share", "dividend_yield", "payout_ratio", "free_cash_flow"),
    "price": ("price", "change_pct", "volume", "observation_time", "market_cap"),
    "profile": ("name", "sector", "industry", "exchange", "currency", "description"),
    "risk": ("gross_debt", "net_debt", "cash", "free_cash_flow", "margins", "risks"),
    "comparison": ("revenue", "net_income_parent", "eps", "period_alignment", "fx_basis"),
}

_DEFAULT_EVIDENCE: tuple[str, ...] = ("price", "market_cap", "revenue", "net_income_parent",
                                      "eps", "balance_sheet", "cash_flow", "risks")

# Intent → trigger keywords. Ordered; the first match wins. Lowercased substrings.
_INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("health", ("financially healthy", "financial health", "healthy", "solvent", "solvency", "creditworthiness")),
    ("valuation", ("valuation", "valu", "expensive", "cheap", "p/e", "pe ratio", "price to", "overvalued", "undervalued")),
    ("growth", ("growth", "growing", "cagr", "yoy", "year over year", "increase in")),
    ("profitability", ("profitab", "margin", "roe", "return on equity", "bottom line")),
    ("dividend", ("dividend", "yield", "payout", "distribution")),
    ("earnings", ("earnings", "eps", "quarterly result", "results", "net income", "profit")),
    ("debt", ("debt", "leverage", "borrowing", "net debt", "gross debt", "liabilit")),
    ("cash_flow", ("free cash flow", "fcf", "cash flow", "capex", "capital expenditure")),
    ("price", ("price", "quote", "market cap", "market capitali", "share price", "trading at")),
    ("risk", ("risk", "exposure", "downside", "threat")),
    ("comparison", ("compare", "versus", " vs ", "better than", "relative to")),
    ("profile", ("profile", "sector", "industry", "what does", "what is the company", "about the company")),
)


@dataclass
class ResearchPlan:
    intent: str
    evidence: list[str] = field(default_factory=list)
    sector: Optional[str] = None
    sector_metrics: list[str] = field(default_factory=list)
    financial_framework: bool = False
    notes: list[str] = field(default_factory=list)


def route(question: str, *, sector: Optional[str] = None, contains_financial: bool = False) -> ResearchPlan:
    """The evidence areas a question needs, plus sector-specific additions.

    `sector` and `contains_financial` come from `sector.classify` on the entity's
    profile. The router does not retrieve; it states WHAT to retrieve.
    """
    text = f" {str(question or '').lower()} "
    intent = "general"
    for name, keywords in _INTENT_KEYWORDS:
        if any(kw in text for kw in keywords):
            intent = name
            break

    evidence = list(INTENT_EVIDENCE.get(intent, _DEFAULT_EVIDENCE))
    plan = ResearchPlan(intent=intent, evidence=evidence)

    if sector and sector != "generic":
        plan.sector = sector
        plan.sector_metrics = list(_sector.SECTOR_METRICS.get(sector, ()))
        for metric in plan.sector_metrics:
            if metric not in plan.evidence:
                plan.evidence.append(metric)
        plan.notes.append(
            f"this is a {sector} business; its sector-specific metrics are required "
            "and the standard industrial template is not sufficient"
        )

    if contains_financial:
        plan.financial_framework = True
        plan.notes.append(
            "the entity contains financial businesses, so net debt and free cash flow "
            "must not be interpreted with the industrial definition"
        )
    return plan


__all__ = ["INTENT_EVIDENCE", "ResearchPlan", "route"]
