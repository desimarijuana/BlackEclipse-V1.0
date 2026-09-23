"""Phase 4 — Evidence-Grounded Answering.

A small, deterministic layer that sits on top of the existing Financial
Retrieval Layer:

    objective → research mandate → per-leg retrieval/coverage → structured
    claims → answer validation → research receipt

The model interprets and explains. This package owns retrieval policy, evidence
identity, coverage status, calculation truth, structural validation and the
final accept/partial/reject decision. It adds no agent loop, no model adapter
and no second financial-data plane.
"""

from __future__ import annotations

from .calculations import (
    CALCULATORS,
    CALCULATION_VERSION,
    CalculationError,
    CalculationResult,
    annualized_volatility,
    cagr,
    max_drawdown,
    period_change,
    sharpe,
)
from .claims import (
    Claim,
    ClaimKind,
    ClaimSet,
    SupportStatus,
    Synthesis,
    ValidationOutcome,
    render_prose,
    validate_claims,
)
from .citations import (
    Citation,
    ResponseMetadata,
    build_citations,
    build_response_metadata,
    summarize_limitations,
)
from .coverage import (
    CoverageReport,
    CoverageStatus,
    LegCoverage,
    build_coverage,
)
from .failures import FailureClass, classify_failure
from .engine import ResearchOutcome, run_research
from .mandate import (
    FactLeg,
    MandateEntity,
    ResearchMandate,
    TaskType,
    parse_mandate,
)
from .receipt import EvidenceRef, ResearchReceipt, build_receipt

__all__ = [
    "CALCULATORS",
    "CALCULATION_VERSION",
    "CalculationError",
    "CalculationResult",
    "annualized_volatility",
    "cagr",
    "max_drawdown",
    "period_change",
    "sharpe",
    "Claim",
    "ClaimKind",
    "ClaimSet",
    "SupportStatus",
    "Synthesis",
    "ValidationOutcome",
    "render_prose",
    "validate_claims",
    "Citation",
    "ResponseMetadata",
    "build_citations",
    "build_response_metadata",
    "summarize_limitations",
    "FailureClass",
    "classify_failure",
    "CoverageReport",
    "CoverageStatus",
    "LegCoverage",
    "build_coverage",
    "FactLeg",
    "MandateEntity",
    "ResearchMandate",
    "TaskType",
    "parse_mandate",
    "ResearchOutcome",
    "run_research",
    "ResearchReceipt",
    "EvidenceRef",
    "build_receipt",
]
