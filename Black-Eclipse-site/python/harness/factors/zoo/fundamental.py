"""Fundamental zoo — declared, versioned, and HONESTLY unavailable.

These are real, documented value/quality factors. None of them can be computed
from the price surface Eclipse currently supplies: they need **point-in-time**
fundamentals (the value as it was FILED, not as it was later restated). A factor
built from a restated figure backtests with information the market did not have,
which is a lookahead bug that produces a beautiful, false IC.

So every entry ships `available=False` with an explicit `unavailableReason`, and
an expression that shows exactly what will be computed once a point-in-time
fundamental panel exists. Nothing here is fabricated from prices.

Inputs named below are the contract the data surface must satisfy:

    gross_profit, total_assets, revenue, net_income, operating_cash_flow,
    total_equity, total_debt, current_assets, current_liabilities,
    shares_outstanding, dividends_paid, ebitda, enterprise_value,
    operating_income, cfo_ttm, capex, market_cap, share_change
"""

from __future__ import annotations

from typing import Any

ZOO = "fundamental"
SOURCE = "Documented value/quality factors — declared pending point-in-time fundamentals"
REASON = (
    "point-in-time fundamentals (as filed, not restated) are not supplied by the "
    "current data surface; a restated value would be lookahead"
)
TOTAL = 15


def _factor(
    name: str,
    family: str,
    direction: str,
    inputs: list[str],
    description: str,
    expression: str,
    reference: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "direction": direction,
        "lookback": 1,
        "description": description,
        "expression": expression,
        "inputs": inputs,
        "available": False,
        "unavailableReason": REASON,
        "zoo": ZOO,
        "source": SOURCE,
        "reference": reference,
    }


FUNDAMENTAL_FACTORS: list[dict[str, Any]] = [
    _factor(
        "fund_gross_profitability", "quality", "positive",
        ["gross_profit", "total_assets"],
        "Gross profit over total assets.",
        "gross_profit / total_assets",
        "Novy-Marx (2013), The Other Side of Value",
    ),
    _factor(
        "fund_asset_turnover", "quality", "positive",
        ["revenue", "total_assets"],
        "Revenue over total assets.",
        "revenue / total_assets",
        "DuPont decomposition",
    ),
    _factor(
        "fund_operating_margin", "quality", "positive",
        ["operating_income", "revenue"],
        "Operating income over revenue.",
        "operating_income / revenue",
        "DuPont decomposition",
    ),
    _factor(
        "fund_roa", "quality", "positive",
        ["net_income", "total_assets"],
        "Net income over total assets.",
        "net_income / total_assets",
        "DuPont decomposition",
    ),
    _factor(
        "fund_accruals", "quality", "negative",
        ["net_income", "operating_cash_flow", "total_assets"],
        "Accruals: (net income - operating cash flow) / total assets.",
        "(net_income - operating_cash_flow) / total_assets",
        "Sloan (1996), Do Stock Prices Fully Reflect Information in Accruals",
    ),
    _factor(
        "fund_debt_to_equity", "leverage", "negative",
        ["total_debt", "total_equity"],
        "Total debt over total equity.",
        "total_debt / total_equity",
        "standard leverage ratio",
    ),
    _factor(
        "fund_current_ratio", "liquidity", "positive",
        ["current_assets", "current_liabilities"],
        "Current assets over current liabilities.",
        "current_assets / current_liabilities",
        "standard liquidity ratio",
    ),
    _factor(
        "fund_cfo_to_assets", "quality", "positive",
        ["cfo_ttm", "total_assets"],
        "Operating cash flow over total assets.",
        "cfo_ttm / total_assets",
        "cash-flow quality (Novy-Marx 2013)",
    ),
    _factor(
        "fund_fcf_yield", "value", "positive",
        ["cfo_ttm", "capex", "enterprise_value"],
        "Free cash flow over enterprise value.",
        "(cfo_ttm - capex) / enterprise_value",
        "free-cash-flow yield",
    ),
    _factor(
        "fund_ev_to_ebitda", "value", "negative",
        ["enterprise_value", "ebitda"],
        "Enterprise value over EBITDA (lower is cheaper).",
        "enterprise_value / ebitda",
        "standard EV multiple",
    ),
    _factor(
        "fund_dividend_yield", "value", "positive",
        ["dividends_paid", "market_cap"],
        "Dividends paid over market capitalisation.",
        "dividends_paid / market_cap",
        "dividend yield",
    ),
    _factor(
        "fund_buyback_yield", "value", "positive",
        ["share_change", "shares_outstanding"],
        "Net share reduction as a share of shares outstanding.",
        "0 - share_change / shares_outstanding",
        "net share issuance anomaly (Pontiff & Woodgate 2008)",
    ),
    _factor(
        "fund_asset_growth", "investment", "negative",
        ["total_assets"],
        "Year-over-year growth in total assets.",
        "pct_change(total_assets, 4)",
        "asset growth anomaly (Cooper, Gulen & Schill 2008)",
    ),
    _factor(
        "fund_sales_growth", "growth", "positive",
        ["revenue"],
        "Year-over-year revenue growth (four quarters back).",
        "pct_change(revenue, 4)",
        "sales growth (Lakonishok, Shleifer & Vishny 1994)",
    ),
    _factor(
        "fund_earnings_stability", "quality", "positive",
        ["net_income", "total_assets"],
        "Inverse volatility of return on assets over 20 quarters.",
        "0 - rolling_std(net_income / total_assets, 20)",
        "earnings quality / stability premium",
    ),
]

PORTED = len(FUNDAMENTAL_FACTORS)


def fundamental_positions_port() -> dict[str, Any]:
    """Coverage AND the blocker, in one record a tool or doc can print."""
    return {
        "zoo": ZOO,
        "declared": PORTED,
        "available": sum(1 for f in FUNDAMENTAL_FACTORS if f["available"]),
        "total": TOTAL,
        "blockedBy": REASON,
    }


__all__ = [
    "FUNDAMENTAL_FACTORS",
    "PORTED",
    "REASON",
    "TOTAL",
    "fundamental_positions_port",
]
