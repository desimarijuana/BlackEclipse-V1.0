"""Research mandate contract + narrow task classifier (Phase 4, Milestone 2).

A mandate is the harness's explicit statement of *what facts an answer must
establish*: which entities, metrics, periods, bases, units and cutoffs apply.
It is a REQUEST, never evidence — generating it does not retrieve or assert any
financial fact.

Scope is deliberately narrow: the initial supported task is
`financial_comparison` (period-over-period financial comparison). Everything
else classifies as `general` and continues through the existing chat path
unchanged. This is not a universal planner.

Parsing combines:
  * a deterministic rule-based pass (tickers, metrics, periods, comparison
    markers), and
  * an optional model-assisted structured extraction (`from_model`) that is
    validated against this schema — the model may only *propose*, and unknown
    concepts stay unresolved rather than being invented.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

TaskType = Literal["financial_comparison", "general"]

# Metrics the narrow comparison flow understands. A metric outside this set is
# left unresolved — never guessed — so retrieval is not silently misdirected.
KNOWN_METRICS: dict[str, list[str]] = {
    "revenue": ["revenue", "sales", "turnover", "top line"],
    "netIncome": ["net income", "net profit", "profit", "bottom line", "earnings"],
    "eps": ["eps", "earnings per share"],
    "grossProfit": ["gross profit"],
    "operatingIncome": ["operating income", "operating profit", "ebit"],
    "freeCashFlow": ["free cash flow", "fcf"],
    "operatingCashFlow": ["operating cash flow"],
    "totalAssets": ["total assets"],
    "totalLiabilities": ["total liabilities", "liabilities"],
    "equity": ["shareholders equity", "shareholder equity", "book value", "equity"],
}

# A small, explicit ticker vocabulary for the deterministic pass. It is not an
# identity resolver — it only recognises the SHAPE of a symbol. Canonical
# identity is resolved later by the retrieval layer (the instrument master),
# never by this parser.
_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_YEAR_RE = re.compile(r"\b(?:FY\s*)?((?:19|20)\d{2})\b", re.IGNORECASE)
_QUARTER_RE = re.compile(r"\b(?:Q([1-4])\s*(?:FY)?\s*((?:19|20)\d{2})|((?:19|20)\d{2})\s*Q([1-4]))\b", re.IGNORECASE)
_COMPARE_RE = re.compile(
    r"\b(vs\.?|versus|compared to|compare|comparison|year[- ]over[- ]year|yoy|qoq|growth|change)\b",
    re.IGNORECASE,
)
_ASOF_RE = re.compile(r"\bas\s+of\s+([0-9]{4}-[0-9]{2}-[0-9]{2})\b", re.IGNORECASE)

# Words that look like tickers but are not.
_STOPWORDS = {
    "A", "I", "AN", "THE", "AND", "OR", "VS", "FY", "QOQ", "YOY", "EPS", "USD",
    "EUR", "GBP", "PKR", "INR", "JPY", "CNY", "FCF", "EBIT", "GAAP", "IFRS",
    "CEO", "CFO", "IPO", "ESG", "ETF", "NAV", "AI", "US", "UK", "EU", "IR",
}


class MandateEntity(BaseModel):
    """One entity the answer is about.

    `symbol`/`market` are what the parser detected; `canonical` is filled only
    once retrieval resolves it against the instrument master. `ambiguous` marks
    an entity that cannot be pinned to one instrument.
    """

    raw: str
    symbol: Optional[str] = None
    market: Optional[str] = None
    name: Optional[str] = None
    canonical: Optional[dict[str, Any]] = None
    ambiguous: bool = False
    reason: Optional[str] = None


class FactLeg(BaseModel):
    """One fact the answer must establish for one entity."""

    id: str
    metric: str
    entityRaw: str
    entitySymbol: Optional[str] = None
    market: Optional[str] = None
    period: Optional[str] = None
    basis: Optional[str] = None  # consolidated | standalone
    unit: Optional[str] = None
    currency: Optional[str] = None
    required: bool = True
    sourceTier: Optional[str] = None
    resolution: Optional[str] = None  # unresolved when the metric is unknown
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchMandate(BaseModel):
    """The typed research mandate. The plan is a request, not evidence."""

    taskType: TaskType = "general"
    objective: str
    entities: list[MandateEntity] = Field(default_factory=list)
    factLegs: list[FactLeg] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    asOf: Optional[str] = None
    timezone: Optional[str] = None
    parseWarnings: list[str] = Field(default_factory=list)
    ambiguity: str = "none"  # none | entity | period | basis | metric
    schemaVersion: str = "1.0.0"
    source: str = "deterministic"  # deterministic | model

    @property
    def supported(self) -> bool:
        """True ONLY when the request is an unambiguous period-over-period
        comparison. Anything uncertain (missing entity, missing two periods,
        multiple entities, an unsupported concept) is not routed into the
        evidence gate — it continues on the existing chat path instead.
        """
        return (
            self.taskType == "financial_comparison"
            and bool(self.factLegs)
            and self.ambiguity == "none"
            and len(self.entities) == 1
        )


def _detect_metrics(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for canonical, aliases in KNOWN_METRICS.items():
        for alias in aliases:
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
                found.append(canonical)
                break
    return found


def _detect_periods(text: str) -> list[str]:
    periods: list[str] = []
    for match in _QUARTER_RE.finditer(text):
        if match.group(1):
            periods.append(f"FY{match.group(2)}-Q{match.group(1)}")
        else:
            periods.append(f"FY{match.group(3)}-Q{match.group(4)}")
    if not periods:
        periods = [f"FY{m.group(1)}" for m in _YEAR_RE.finditer(text)]
    # Preserve order, de-duplicate.
    seen: set[str] = set()
    out: list[str] = []
    for p in periods:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _detect_tickers(text: str) -> list[str]:
    out: list[str] = []
    for match in _TICKER_RE.finditer(text):
        token = match.group(1)
        if token.upper() in _STOPWORDS:
            continue
        if token not in out:
            out.append(token)
    return out


def _detect_basis(text: str) -> Optional[str]:
    lowered = text.lower()
    if "standalone" in lowered or "separate" in lowered:
        return "standalone"
    if "consolidated" in lowered or "group" in lowered:
        return "consolidated"
    return None


def _detect_unit(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (unit, currency) when the objective names them explicitly."""
    currencies = {
        "usd": "USD", "dollar": "USD", "dollars": "USD",
        "eur": "EUR", "euro": "EUR", "euros": "EUR",
        "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
        "pkr": "PKR", "rupee": "PKR", "rupees": "PKR", "inr": "INR",
        "jpy": "JPY", "yen": "JPY", "cny": "CNY", "rmb": "CNY",
    }
    lowered = text.lower()
    for token, iso in currencies.items():
        if re.search(rf"(?<![a-z]){token}(?![a-z])", lowered):
            # A named currency is a currency requirement, not a unit requirement.
            return None, iso
    if "percent" in lowered or "%" in text:
        return "%", None
    return None, None


def parse_mandate(
    objective: str,
    *,
    ticker: Optional[str] = None,
    market: Optional[str] = None,
    as_of: Optional[str] = None,
) -> ResearchMandate:
    """Deterministically classify an objective into a mandate (or `general`).

    Unknown concepts remain unresolved (a warning + an unresolved leg), never
    invented. A non-comparison objective returns `taskType=general` with no
    legs and therefore continues down the existing chat path.
    """
    text = (objective or "").strip()
    mandate = ResearchMandate(objective=text)
    if not text:
        mandate.parseWarnings.append("empty objective")
        return mandate

    metrics = _detect_metrics(text)
    periods = _detect_periods(text)
    is_comparison = bool(_COMPARE_RE.search(text)) or len(periods) >= 2

    # Entities: an explicit ticker param, else detected symbols.
    raw_symbols: list[str] = []
    if ticker:
        raw_symbols.append(str(ticker).strip().upper())
    for detected in _detect_tickers(text):
        if detected not in raw_symbols:
            raw_symbols.append(detected)
    for symbol in raw_symbols:
        mandate.entities.append(
            MandateEntity(
                raw=symbol,
                symbol=symbol,
                market=(market.upper() if market else None),
            )
        )

    # Only claim financial_comparison when we have the minimum to act on.
    if not (is_comparison and metrics):
        mandate.taskType = "general"
        if periods and not is_comparison:
            mandate.parseWarnings.append("periods detected but no comparison intent")
        return mandate

    mandate.taskType = "financial_comparison"

    entity_raw = mandate.entities[0].raw if mandate.entities else ""
    if not mandate.entities:
        mandate.ambiguity = "entity"
        mandate.parseWarnings.append("no entity could be identified for the comparison")

    if len(periods) < 2:
        mandate.ambiguity = "period" if mandate.ambiguity == "none" else mandate.ambiguity
        mandate.parseWarnings.append(
            "comparison requested but fewer than two periods were stated"
        )

    # Two distinct entities is a company-vs-company comparison, not a
    # period-over-period one — this flow does not support it, so fall back.
    if len(mandate.entities) > 1:
        mandate.ambiguity = "entity" if mandate.ambiguity == "none" else mandate.ambiguity
        mandate.parseWarnings.append(
            "two or more entities were named; company-vs-company comparison is not supported"
        )

    unit, currency = _detect_unit(text)
    basis = _detect_basis(text)

    legs: list[FactLeg] = []
    for metric in metrics:
        for period in (periods or [None]):
            legs.append(
                FactLeg(
                    id=f"leg_{metric}_{period or 'latest'}_{len(legs)}",
                    metric=metric,
                    entityRaw=entity_raw,
                    entitySymbol=mandate.entities[0].symbol if mandate.entities else None,
                    market=mandate.entities[0].market if mandate.entities else None,
                    period=period,
                    basis=basis,
                    unit=unit,
                    currency=currency,
                    required=True,
                    sourceTier="structured",
                )
            )
    mandate.factLegs = legs
    mandate.deliverables = ["period_change" for _ in metrics] if len(periods) >= 2 else []
    mandate.asOf = as_of or (_ASOF_RE.search(text).group(1) if _ASOF_RE.search(text) else None)

    if not periods:
        mandate.parseWarnings.append("no period stated; the flow will use the latest available")
    return mandate


def from_model(payload: dict[str, Any], *, objective: str) -> ResearchMandate:
    """Build a mandate from model-assisted structured extraction.

    The model's output is validated against this schema; a malformed or
    unsupported extraction degrades to the deterministic `general` path rather
    than being trusted. The model may not set canonical identity.
    """
    try:
        mandate = ResearchMandate(**payload)
    except Exception:  # noqa: BLE001 - a bad extraction is not a mandate
        fallback = parse_mandate(objective)
        fallback.parseWarnings.append("model extraction was invalid; used deterministic parse")
        return fallback

    mandate.objective = objective
    mandate.source = "model"
    # Canonical identity is never model-authored: clear any it supplied.
    for entity in mandate.entities:
        entity.canonical = None
        entity.ambiguous = False
    # Re-run the deterministic guard so a model cannot widen the supported task
    # beyond `financial_comparison`.
    if mandate.taskType == "financial_comparison" and not mandate.factLegs:
        mandate.taskType = "general"
        mandate.parseWarnings.append("model claimed a comparison with no fact legs")
    return mandate


__all__ = [
    "TaskType",
    "KNOWN_METRICS",
    "MandateEntity",
    "FactLeg",
    "ResearchMandate",
    "parse_mandate",
    "from_model",
]
