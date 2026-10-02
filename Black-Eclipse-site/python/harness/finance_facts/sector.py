"""Sector classification and sector-aware fundamentals (Universal Financial Data
Accuracy, §12 and §13-sector-awareness).

One universal fundamental template is wrong: a bank has no meaningful
Debt−Cash "net debt" or OCF−CapEx "free cash flow"; a REIT is analysed on FFO/AFFO;
an insurer on combined ratio. This module classifies an entity into a business
type from its facts/profile and exposes the appropriate metric set.

Classification is DATA (keyword → sector), never `if ticker == ...`. It is
deliberately conservative: an unknown company gets the GENERIC template, and a
`financial` flag is set separately so the analysis layer can change its framework
even for a conglomerate that merely CONTAINS a bank.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# Business sectors the templates understand. `generic` is the safe default.
SECTORS: tuple[str, ...] = (
    "technology", "bank", "insurance", "reit", "energy", "mining",
    "industrial", "consumer", "holding", "crypto", "utility", "generic",
)

# Sector-specific metrics (§12). A metric outside the generic set is valid only
# for the sectors that list it; the analysis layer must not apply it elsewhere.
SECTOR_METRICS: dict[str, tuple[str, ...]] = {
    "technology": ("arr", "recurring_revenue", "gross_margin", "r_and_d", "rule_of_40",
                   "free_cash_flow", "stock_based_comp"),
    "bank": ("roe", "rote", "nim", "npl", "cet1", "loan_growth", "deposit_growth",
             "cost_of_risk", "efficiency_ratio"),
    "insurance": ("premiums", "combined_ratio", "loss_ratio", "expense_ratio",
                  "solvency_ratio", "investment_income"),
    "reit": ("ffo", "affo", "nav", "occupancy", "same_store_noi", "net_debt_to_ebitda"),
    "energy": ("production", "realized_price", "refining_margin", "reserves", "capex",
               "free_cash_flow", "net_debt"),
    "mining": ("production", "aisc", "reserves", "commodity_exposure", "capex", "net_debt"),
    "industrial": ("orders", "backlog", "revenue", "margin", "roic", "capex", "free_cash_flow"),
    "consumer": ("volume", "pricing", "gross_margin", "inventory", "same_store_sales", "free_cash_flow"),
    "holding": ("nav", "holding_discount", "subsidiary_ownership", "nci", "net_cash_debt",
                "dividend_flows", "asset_sales", "capital_allocation"),
    "crypto": ("market_cap", "circulating_supply", "staking_yield", "on_chain_volume",
               "network_fees", "hash_rate"),
    "utility": ("regulated_asset_base", "rate_base", "load_growth", "capex", "dividend_payout"),
    "generic": (),
}

# Keyword → sector. Checked against name/industry/asset-class text. Ordered so a
# more specific sector wins before `industrial`/`generic`. Lowercased substrings.
# `conglomerate`/`diversified` are STRUCTURAL signals checked first: a holding
# company that CONTAINS a bank is still a holding company (the bank ownership is
# reported by `contains_financial`, it does not redefine the primary sector).
_STRUCTURAL_HOLDING = ("conglomerate", "diversified group", "diversified holding")

_SECTOR_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("crypto", ("crypto", "bitcoin", "ethereum", "digital asset", "token", "blockchain")),
    ("reit", ("reit", "real estate investment trust")),
    ("bank", ("bank", "banking", "banco", "banca")),
    ("insurance", ("insurance", "insurer", "assurance", "reinsurance")),
    ("mining", ("mining", "miner", "metals", "gold ", "copper")),
    ("energy", ("oil", "gas", "energy", "petroleum", "refin", "exploration")),
    ("utility", ("utility", "utilities", "electric power", "water works")),
    ("technology", ("technology", "software", "semiconductor", "internet", "tech")),
    ("consumer", ("consumer", "retail", "beverage", "food", "apparel", "restaurant")),
    ("holding", ("holding", "conglomerate", "group", "holding company")),
    ("industrial", ("industrial", "manufactur", "machinery", "engineering", "construction")),
)

# Sub-sectors that make an entity FINANCIAL even inside a conglomerate. A holding
# company that contains a bank must not be given the industrial FCF/net-debt lens.
_FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "bank", "insurance", "insurer", "brokerage", "asset management", "consumer finance",
    "leasing", "fintech", "mortgage", "financial services", "capital markets",
)


@dataclass(frozen=True)
class SectorClassification:
    sector: str
    contains_financial: bool
    matched_on: Optional[str]
    confidence: str  # high | low  (low = defaulted to generic)


def classify(*texts: Optional[str], asset_type: Optional[str] = None) -> SectorClassification:
    """Classify an entity from ANY descriptive text (name, industry, profile…).

    Never takes a ticker. An entity whose text matches nothing is `generic` with
    `confidence="low"` — the honest default, not a guess.
    """
    haystack = " ".join(str(t) for t in texts if t).lower()
    contains_financial = asset_type in ("fx", "crypto") or any(k in haystack for k in _FINANCIAL_KEYWORDS)

    if asset_type == "crypto":
        return SectorClassification("crypto", True, "asset_type=crypto", "high")

    # A holding/conglomerate is a STRUCTURAL classification that outranks a
    # sub-business keyword: a conglomerate containing a bank is a holding, not a
    # bank. The bank ownership still sets `contains_financial` above.
    if any(k in haystack for k in _STRUCTURAL_HOLDING) or "holding" in haystack:
        return SectorClassification("holding", contains_financial, "holding/conglomerate", "high")

    for sector, keywords in _SECTOR_KEYWORDS:
        for kw in keywords:
            if kw in haystack:
                return SectorClassification(sector, contains_financial, kw.strip(), "high")

    return SectorClassification("generic", contains_financial, None, "low")


def metrics_for(sector: str, generic_metrics: Iterable[str] = ()) -> tuple[str, ...]:
    """The metric set appropriate to a sector: generic metrics plus its own."""
    own = SECTOR_METRICS.get(sector, ())
    merged = list(generic_metrics)
    for m in own:
        if m not in merged:
            merged.append(m)
    return tuple(merged)


def financial_framework_warning(classification: SectorClassification) -> Optional[str]:
    """A sentence the analysis layer must show when the standard industrial lens
    (Debt−Cash net debt, OCF−CapEx FCF) would be misleading."""
    if not classification.contains_financial:
        return None
    return (
        "this entity contains financial businesses, so the standard industrial "
        "interpretation of net debt and free cash flow does not apply; use the "
        "sector-specific metrics instead"
    )


__all__ = [
    "SECTORS",
    "SECTOR_METRICS",
    "SectorClassification",
    "classify",
    "financial_framework_warning",
    "metrics_for",
]
