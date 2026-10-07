"""Accounting semantics ontology (Universal Financial Data Accuracy, §3/§4/§5/§6/§7).

Related-but-NON-EQUIVALENT financial concepts, as data. The engine must never
treat these as interchangeable:

    Revenue   ≠ Net Sales      ≠ Gross Revenue   ≠ Combined/Segment Revenue
    NetIncome ≠ attributable-to-parent ≠ attributable-to-common ≠ NCI
    Debt      ≠ Gross Debt     ≠ Financial Debt  ≠ Net Debt ≠ Debt+Leases
    Cash      ≠ Equivalents    ≠ Restricted Cash ≠ ST Investments

Nothing here names a company, a ticker or a sector. A metric is defined by its
accounting meaning; `resolve_definition` maps a raw provider label onto the
closest canonical definition *only* when the label is unambiguous, and otherwise
returns `None` so the fact is left unresolved rather than silently mis-typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AccountingDefinition:
    """One canonical accounting concept.

    `aliases` are labels that DO unambiguously mean this concept. A label that
    could mean two different concepts (e.g. bare "revenue") appears in the alias
    list of NO definition — it must be resolved by context or left unresolved.
    """

    id: str
    label: str
    aliases: tuple[str, ...]
    category: str  # income | balance | cashflow | per_share | market | ratio
    # Metrics that are sub-concepts of a broader one; used only to DETECT a
    # comparison between different definitions (never to auto-merge them).
    parent: Optional[str] = None
    is_shareholder_attributable: bool = False
    is_nci: bool = False


# The ontology. One row per concept; a new concept is a new row.
DEFINITIONS: dict[str, AccountingDefinition] = {}


def _define(
    id: str,
    label: str,
    category: str,
    aliases: tuple[str, ...] = (),
    *,
    parent: Optional[str] = None,
    shareholder: bool = False,
    nci: bool = False,
) -> None:
    DEFINITIONS[id] = AccountingDefinition(
        id=id, label=label, aliases=aliases, category=category,
        parent=parent, is_shareholder_attributable=shareholder, is_nci=nci,
    )


# ── Income statement ────────────────────────────────────────────────────────
# NOTE: bare "revenue"/"sales"/"turnover" are deliberately NOT aliases here —
# they are ambiguous (see AMBIGUOUS_LABELS). Only an explicit qualifier is
# canonical: "total revenue" is Revenue, "net sales" is Net Sales.
_define("revenue", "Revenue", "income", ("total revenue", "total revenues"))
_define("net_sales", "Net Sales", "income", ("net sales",))
_define("gross_revenue", "Gross Revenue", "income", ("gross revenue", "gross revenues"))
_define("net_revenue", "Net Revenue", "income", ("net revenue",))
_define("sales", "Sales", "income", ("total sales",))
_define("segment_revenue", "Segment Revenue", "income", ("segment revenue", "segment revenues"))
_define("combined_revenue", "Combined Revenue", "income", ("combined revenue",))

_define("cost_of_revenue", "Cost of Revenue", "income", ("cost of revenue", "cost of sales", "cogs"))
_define("gross_profit", "Gross Profit", "income", ("gross profit",))
_define("operating_income", "Operating Income", "income", ("operating income", "operating profit", "ebit"))
_define("ebit", "EBIT (Earnings Before Interest and Taxes)", "income",
        ("ebit", "earnings before interest and taxes", "earnings before interest and tax"))
_define("ebitda", "EBITDA", "income", ("ebitda", "earnings before interest taxes depreciation and amortization"))
_define("pretax_income", "Pre-tax Income", "income", ("pre-tax income", "pretax income", "income before tax"))

# Net income family — the §6 separation.
_define("net_income", "Net Income (total consolidated)", "income",
        ("net income", "net profit", "profit for the period", "net earnings"), parent="net_income")
_define("net_income_parent", "Net Income attributable to Parent", "income",
        ("net income attributable to owners of the parent",
         "net income attributable to parent",
         "profit attributable to owners of the parent",
         "net income attributable to the company",
         "net income attributable to shareholders"),
        parent="net_income", shareholder=True)
_define("net_income_common", "Net Income attributable to Common Shareholders", "income",
        ("net income attributable to common shareholders",
         "net income available to common shareholders",
         "net income applicable to common shares"),
        parent="net_income", shareholder=True)
_define("net_income_nci", "Net Income attributable to NCI", "income",
        ("net income attributable to non-controlling interests",
         "net income attributable to minority interests",
         "net income attributable to nci"),
        parent="net_income", nci=True)
_define("comprehensive_income", "Comprehensive Income", "income", ("comprehensive income",))
_define("adjusted_net_income", "Adjusted Net Income", "income",
        ("adjusted net income", "normalized net income", "core net income"))

# ── Per share ───────────────────────────────────────────────────────────────
_define("eps", "Earnings Per Share", "per_share", ("eps", "earnings per share", "basic eps", "diluted eps"))
_define("eps_forward", "Forward EPS (estimate)", "per_share",
        ("forward eps", "eps estimate", "consensus eps", "estimated eps", "forward earnings per share", "eps forecast"))
_define("book_value_per_share", "Book Value Per Share", "per_share", ("book value per share", "bvps"))
_define("dividend_per_share", "Dividend Per Share", "per_share", ("dividend per share", "dps"))
_define("dividend", "Dividend", "per_share", ("dividend", "dividends", "cash dividend", "dividend paid"))
_define("stock_split", "Stock Split", "corporate_action", ("stock split", "split", "share split"))
# ── Balance sheet ────────────────────────────────────────────────────────────
_define("total_assets", "Total Assets", "balance", ("total assets",))
_define("total_liabilities", "Total Liabilities", "balance", ("total liabilities",))

# Equity family — §7.
_define("total_equity", "Total Equity (incl. NCI)", "balance",
        ("total equity", "total shareholders equity", "stockholders equity"), parent="equity")
_define("parent_equity", "Equity attributable to Parent", "balance",
        ("equity attributable to owners of the parent",
         "equity attributable to parent",
         "total parent equity"), parent="equity", shareholder=True)
_define("common_equity", "Common Equity", "balance",
        ("common equity", "common shareholders equity", "book value of common equity"),
        parent="equity", shareholder=True)
_define("preferred_equity", "Preferred Equity", "balance", ("preferred equity", "preferred stock"))
_define("nci_equity", "Non-controlling Interests (equity)", "balance",
        ("non-controlling interests", "noncontrolling interests", "minority interest", "nci"),
        parent="equity", nci=True)

# Debt family.
_define("gross_debt", "Gross Debt", "balance", ("gross debt", "total borrowings"))
_define("total_debt", "Total Debt", "balance", ("total debt",))
_define("invested_capital", "Invested Capital", "balance",
        ("invested capital", "total invested capital", "capital employed"))
_define("financial_debt", "Financial Debt", "balance", ("financial debt",))
_define("short_term_debt", "Short-term Debt", "balance", ("short-term debt", "current borrowings"))
_define("long_term_debt", "Long-term Debt", "balance", ("long-term debt", "non-current borrowings"))
_define("lease_liabilities", "Lease Liabilities", "balance", ("lease liabilities", "finance lease obligations"))
_define("net_debt", "Net Debt", "balance", ("net debt",))
_define("net_financial_debt", "Net Financial Debt", "balance", ("net financial debt",))

# Cash family.
_define("cash", "Cash and Cash Equivalents", "balance", ("cash and cash equivalents", "cash & cash equivalents", "cash"))
_define("cash_equivalents", "Cash Equivalents", "balance", ("cash equivalents", "short-term investments", "marketable securities"))
_define("restricted_cash", "Restricted Cash", "balance", ("restricted cash",))
_define("liquid_assets", "Liquidity", "balance", ("liquidity", "total liquidity"))

# ── Cash flow ────────────────────────────────────────────────────────────────
_define("operating_cash_flow", "Operating Cash Flow", "cashflow", ("operating cash flow", "cash from operations"))
_define("capex", "Capital Expenditure", "cashflow", ("capital expenditure", "capital expenditures", "capex", "purchases of property"))
_define("free_cash_flow", "Free Cash Flow", "cashflow", ("free cash flow", "fcf"))
_define("investing_cash_flow", "Investing Cash Flow", "cashflow", ("investing cash flow", "cash from investing"))
_define("financing_cash_flow", "Financing Cash Flow", "cashflow", ("financing cash flow", "cash from financing"))

# ── Market ────────────────────────────────────────────────────────────────────
_define("price", "Price", "market", ("price", "last price", "close", "last"))
_define("market_cap", "Market Capitalisation", "market", ("market cap", "market capitalization", "marketcap"))
_define("shares_outstanding", "Shares Outstanding", "market",
        ("shares outstanding", "shares issued", "ordinary shares outstanding", "sharesoutstanding"))
_define("volume", "Volume", "market", ("volume",))
_define("change_pct", "Price Change (%)", "market", ("change", "change pct", "changepct", "percent change"))
_define("pe_ratio", "Price / Earnings", "ratio", ("pe", "p/e", "price to earnings", "pe ratio", "peratio"))
_define("forward_pe", "Forward Price / Earnings", "ratio",
        ("forward pe", "forward p/e", "forward price to earnings", "forwardperatio"))
_define("peg_ratio", "PEG Ratio", "ratio",
        ("peg", "peg ratio", "price earnings growth", "price/earnings to growth"))
_define("pb_ratio", "Price / Book", "ratio", ("pb", "p/b", "price to book", "pb ratio", "pbratio"))
_define("ps_ratio", "Price / Sales", "ratio", ("ps", "p/s", "price to sales", "ps ratio", "psratio"))
_define("ev_ebitda", "EV / EBITDA", "ratio", ("ev/ebitda", "enterprise value to ebitda", "evebitda"))
_define("dividend_yield", "Dividend Yield", "ratio", ("dividend yield", "yield", "dividendyield"))


# A label that maps to MORE THAN ONE definition is ambiguous and must resolve to
# None. Build the reverse index once, so ambiguity is data, not a special case.
# Labels are normalised (case-folded, camelCase split, separators collapsed) so
# a provider's `marketCap`, `market_cap` and `market cap` all hit the same row.
import re as _re


def _normalize_label(label: str) -> str:
    text = str(label).strip()
    text = _re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  # camelCase → spaced
    text = text.replace("_", " ").replace("-", " ").replace("/", " ").replace("%", " ")
    return _re.sub(r"\s+", " ", text).strip().lower()


_ALIAS_TO_DEFS: dict[str, list[str]] = {}
for _defn in DEFINITIONS.values():
    for _alias in _defn.aliases:
        _ALIAS_TO_DEFS.setdefault(_normalize_label(_alias), []).append(_defn.id)

# Labels that are ambiguous by CONVENTION, not because two definitions claim the
# exact alias: "revenue" could be Revenue, Net Revenue, Gross Revenue, Net Sales
# or Segment Revenue depending on the issuer. It resolves to None (unresolved)
# and is reported as ambiguous — it is never silently mapped to one concept.
AMBIGUOUS_LABELS: frozenset[str] = frozenset(
    {"revenue", "revenues", "sales", "turnover", "income", "earnings", "profit"}
)

_SELF_CONFLICTING = {alias for alias, ids in _ALIAS_TO_DEFS.items() if len(ids) > 1} | AMBIGUOUS_LABELS


def resolve_definition(label: Optional[str]) -> Optional[str]:
    """The canonical definition id for a raw label, or None when ambiguous/unknown.

    A bare label like "revenue" that could mean several concepts resolves to
    None — the caller must supply context or leave the fact unresolved. This is
    the guard that stops "revenue" and "net sales" from silently merging.
    """
    if not label:
        return None
    key = _normalize_label(label)
    if key in _SELF_CONFLICTING:
        return None
    ids = _ALIAS_TO_DEFS.get(key)
    if ids and len(ids) == 1:
        return ids[0]
    return None


def is_ambiguous_label(label: Optional[str]) -> bool:
    """True when a label genuinely maps to more than one concept."""
    if not label:
        return False
    return _normalize_label(label) in _SELF_CONFLICTING


def definitions_differ(a: Optional[str], b: Optional[str]) -> bool:
    """Do two definitions name genuinely different concepts?

    Two uncles (`net_income` vs `net_income_parent`) are different but related;
    `revenue` vs `net_sales` are different siblings. Either way they must not be
    silently compared — but the difference is semantic, not necessarily an error.
    """
    if a is None or b is None:
        return False
    return a != b


def definition(id: str) -> Optional[AccountingDefinition]:
    return DEFINITIONS.get(id)


__all__ = [
    "AccountingDefinition",
    "DEFINITIONS",
    "definition",
    "definitions_differ",
    "is_ambiguous_label",
    "resolve_definition",
]
