"""Universal financial-fact model (Universal Financial Data Accuracy engine, §2/§5/§32).

Every financial fact carries, alongside its value, WHAT it represents, WHERE it
came from, WHEN it applies, WHO it belongs to, HOW it was derived and HOW
reliable it is. A naked value is never stored.

This is a PURE data module: no I/O, no retrieval, no model. The LLM reasons over
facts produced here; it never substitutes for them. Nothing here is
ticker-specific — a company is described by its facts and classifications, never
by an `if ticker == ...` branch.

It deliberately EXTENDS the existing evidence machinery (Phase 4):
`research/calculations.py` already records formula + input evidence ids + digest,
`research/supersession.py` already models restatement links, and
`retrieval/contract.py::NormalizedFinancialObject` already carries value/unit/
currency/timestamps/basis. Those are reused; this module adds the dimensions they
do not carry (accounting definition, consolidation/ownership, period type,
reported-vs-derived, confidence, freshness).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ── Controlled vocabularies (the reusable abstractions, §32) ─────────────────

# How a company's figures are consolidated into the group.
ConsolidationLevel = Literal[
    "full",             # 100% consolidated
    "proportionate",    # proportionately consolidated (JVs)
    "equity_method",    # equity-accounted (associates)
    "not_consolidated",  # held as an investment
    "unknown",
]

# Whose claim on the figure it is.
AttributionLevel = Literal[
    "group",            # total consolidated, before splitting ownership
    "parent",           # attributable to owners of the parent
    "common",           # attributable to common shareholders (after preferred)
    "nci",              # non-controlling interests
    "preferred",        # preferred shareholders
    "unattributed",
    "unknown",
]

# The relationship of the reporting entity to the fact.
OwnershipLevel = Literal[
    "parent",
    "subsidiary",
    "joint_venture",
    "associate",
    "affiliate",
    "investment",
    "unknown",
]

ReportedOrDerived = Literal["reported", "derived", "estimated", "pro_forma", "unknown"]

# Accounting / reporting standard. Kept as a string, not an enum: the universe is
# open (US GAAP, IFRS, local GAAP variants, regulatory basis).
SourceType = Literal[
    "regulatory_filing",
    "exchange_filing",
    "company_report",
    "investor_relations",
    "government",
    "financial_database",
    "aggregator",
    "market_data",
    "vault",
    "derived",
    "unknown",
]

# DataFreshness is its own module; forward-referenced as a plain string here to
# keep this module dependency-free.
FreshnessState = str
ConfidenceLevel = Literal["high", "medium", "low", "unverified"]


@dataclass(frozen=True)
class FinancialPeriod:
    """A period a fact applies to, with its period TYPE (§3).

    `period_type` is what tells FY2025 EPS apart from TTM EPS, and H1 from FY.
    `period_start`/`period_end` are ISO dates when known; a point-in-time fact
    (a price) has a start == end == its instant.
    """

    period_type: str            # see finance_facts.periods_ext.PeriodType
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    label: Optional[str] = None  # the label as the source wrote it ("FY2025", "Q2 2026")

    def key(self) -> str:
        if self.period_type in ("fy", "cy") and self.fiscal_year:
            prefix = "FY" if self.period_type == "fy" else "CY"
            return f"{prefix}{self.fiscal_year}"
        if self.period_type == "quarter" and self.fiscal_year and self.fiscal_quarter:
            return f"FY{self.fiscal_year}-Q{self.fiscal_quarter}"
        if self.period_start and self.period_end:
            return f"{self.period_start}..{self.period_end}"
        return self.label or self.period_type


@dataclass(frozen=True)
class FinancialFact:
    """One financial fact with full provenance and semantics (§2).

    A value is NEVER stored alone. `definition` names the exact accounting
    concept (see finance_facts.semantics), so "revenue" and "net sales" are not
    silently the same number.
    """

    fact_id: str
    metric: str                        # canonical metric id, or the raw name if unresolved
    definition: Optional[str] = None   # AccountingDefinition id (semantics.py)
    value: Any = None
    currency: Optional[str] = None
    unit: Optional[str] = None

    # Identity
    entity_id: Optional[str] = None    # canonical instrument key ("US:AAPL")
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    asset_type: Optional[str] = None

    # Period (§3)
    period: Optional[FinancialPeriod] = None

    # Time (§14/§15) — kept DISTINCT, never conflated.
    publication_timestamp: Optional[str] = None  # when the source made it public
    source_timestamp: Optional[str] = None       # the market time the value is about
    retrieved_timestamp: Optional[str] = None    # when we fetched it

    # Provenance
    source: Optional[str] = None
    source_type: SourceType = "unknown"
    source_document: Optional[str] = None

    # Semantics (§4/§5/§6/§7)
    accounting_standard: Optional[str] = None
    reporting_standard: Optional[str] = None
    consolidation_level: ConsolidationLevel = "unknown"
    attribution: AttributionLevel = "unknown"
    ownership_level: OwnershipLevel = "unknown"

    # Derivation (§9)
    reported_or_derived: ReportedOrDerived = "unknown"
    calculation_formula: Optional[str] = None
    input_fact_ids: tuple[str, ...] = ()

    # Reliability (§14/§20)
    freshness: FreshnessState = "UNVERIFIED"
    confidence: ConfidenceLevel = "unverified"

    # Revision (§16)
    supersedes_fact_id: Optional[str] = None
    restated: bool = False

    warnings: tuple[str, ...] = ()
    raw: Optional[dict[str, Any]] = None

    def is_naked(self) -> bool:
        """True when the fact lacks the metadata that makes it trustworthy.

        A naked value is a defect, not a fact: it has no period, no source, no
        definition and no time. Used by the quality gates to refuse it.
        """
        return self.period is None and self.source is None and self.definition is None


@dataclass(frozen=True)
class Restatement:
    """A source-grounded revision of a prior fact (§16).

    Never inferred from a differing value — only produced when a source exposes
    revision metadata (see `research/supersession.py`). Both the original and the
    restated value are retained; history is never overwritten.
    """

    original_fact_id: str
    restated_fact_id: str
    restatement_date: Optional[str]
    reason: Optional[str]
    source: Optional[str]
    relationship_kind: str  # amends | restates | corrects | withdraws


@dataclass(frozen=True)
class CorporateAction:
    """A corporate action that can invalidate a naive historical comparison (§17)."""

    kind: str  # split | reverse_split | buyback | issuance | rights | dividend | spinoff | m_and_a | adr_ratio | ticker_change | name_change | delisting | relisting
    effective_date: Optional[str]
    ratio: Optional[float] = None  # e.g. 2.0 for a 2-for-1 split
    source: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class FactConflict:
    """A structured, semantic disagreement between two facts (§13/§26).

    Two numbers can BOTH be correct (consolidated vs parent-attributable). This
    record explains the difference; it does not suppress one. `preferred` is set
    only when a rule justifies a preference, with the reason recorded.
    """

    metric: str
    source_a: str
    source_b: str
    period: Optional[str]
    definition_a: Optional[str]
    definition_b: Optional[str]
    value_a: Any
    value_b: Any
    difference: Optional[float]
    relative_difference: Optional[float]
    explanation: str
    preferred: Optional[str] = None   # "a" | "b" | None
    reason: Optional[str] = None
    confidence: ConfidenceLevel = "unverified"
    # True when the two values differ by DEFINITION rather than by error — the
    # §26 case where both are correct and the answer must explain, not choose.
    semantic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "sourceA": self.source_a,
            "sourceB": self.source_b,
            "period": self.period,
            "definitionA": self.definition_a,
            "definitionB": self.definition_b,
            "valueA": self.value_a,
            "valueB": self.value_b,
            "difference": self.difference,
            "relativeDifference": self.relative_difference,
            "explanation": self.explanation,
            "preferred": self.preferred,
            "reason": self.reason,
            "confidence": self.confidence,
            "semantic": self.semantic,
        }


@dataclass(frozen=True)
class DerivedMetric:
    """A computed figure and everything needed to reproduce it (§9).

    Extends `research/calculations.py`'s record: the formula, the inputs and a
    calculation timestamp. It is NEVER a reported fact.
    """

    metric: str
    value: Optional[float]
    formula: str
    inputs: tuple[dict[str, Any], ...] = ()
    input_fact_ids: tuple[str, ...] = ()
    input_periods: tuple[str, ...] = ()
    input_sources: tuple[str, ...] = ()
    calculated_at: Optional[str] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    warnings: tuple[str, ...] = ()
    # Structured, machine-readable payload for a metric whose answer is more than
    # one number (a DCF schedule, a sensitivity matrix, a scenario table). The
    # calculation layer returns structured data; presentation formats it.
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "formula": self.formula,
            "inputs": list(self.inputs),
            "inputFactIds": list(self.input_fact_ids),
            "inputPeriods": list(self.input_periods),
            "inputSources": list(self.input_sources),
            "calculatedAt": self.calculated_at,
            "currency": self.currency,
            "unit": self.unit,
            "warnings": list(self.warnings),
            "detail": self.detail,
        }


__all__ = [
    "AttributionLevel",
    "ConfidenceLevel",
    "ConsolidationLevel",
    "CorporateAction",
    "DerivedMetric",
    "FactConflict",
    "FinancialFact",
    "FinancialPeriod",
    "FreshnessState",
    "OwnershipLevel",
    "ReportedOrDerived",
    "Restatement",
    "SourceType",
]
