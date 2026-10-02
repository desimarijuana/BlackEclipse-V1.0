"""Universal Financial Data Accuracy & Evidence engine (foundation).

A deterministic, pure-Python layer that makes every financial fact carry WHAT it
represents, WHERE it came from, WHEN it applies, WHO it belongs to, HOW it was
derived and HOW reliable it is — so the LLM reasons OVER validated facts instead
of substituting for them.

This is the foundation slice. It is deliberately independent of retrieval and the
research engine (no I/O), and it EXTENDS, never replaces, the Phase-4 evidence
machinery (`research/claims.py`, `research/supersession.py`,
`research/calculations.py`, `research/periods.py`).

Nothing here is ticker-specific: an entity is described by its facts and its
sector classification, never by an `if ticker == ...` branch.
"""

from .model import (
    AttributionLevel,
    ConfidenceLevel,
    ConsolidationLevel,
    CorporateAction,
    DerivedMetric,
    FactConflict,
    FinancialFact,
    FinancialPeriod,
    OwnershipLevel,
    ReportedOrDerived,
    Restatement,
    SourceType,
)

__all__ = [
    "AttributionLevel",
    "ConfidenceLevel",
    "ConsolidationLevel",
    "CorporateAction",
    "DerivedMetric",
    "FactConflict",
    "FinancialFact",
    "FinancialPeriod",
    "OwnershipLevel",
    "ReportedOrDerived",
    "Restatement",
    "SourceType",
]
