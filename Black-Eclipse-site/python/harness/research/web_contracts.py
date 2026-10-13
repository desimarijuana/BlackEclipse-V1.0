"""Evidence-Driven Web Research Engine — core contracts.

This module defines the provider-agnostic, provenance-first contracts for the
web research capability. It is deliberately additive to the existing Phase-4
research flow (`research/mandate.py`, `research/coverage.py`,
`research/claims.py`): the financial statement flow keeps its own mandate and
evidence gate; this package adds the *web research* contracts (search results,
sources, evidence, claims, conflicts, citations, plans).

The governing principle, stated once here and enforced throughout:

    SEARCH RESULTS ARE NOT EVIDENCE.

A search result is a pointer. Only fetched, normalized, provenance-tracked,
timestamped content becomes evidence. The model may reason OVER evidence; it is
never itself the source of truth.

Everything here is a pure data contract — no I/O, no provider names, no model.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Intent / depth vocabularies ───────────────────────────────────────────────


class ResearchIntent(str, Enum):
    """The kind of research being requested. Drives planning and routing."""

    FACT_LOOKUP = "fact_lookup"
    CURRENT_EVENT = "current_event"
    NEWS = "news"
    COMPANY_RESEARCH = "company_research"
    MARKET_RESEARCH = "market_research"
    COMPETITOR_RESEARCH = "competitor_research"
    ACADEMIC_RESEARCH = "academic_research"
    TECHNICAL_RESEARCH = "technical_research"
    LEARNING = "learning"
    FINANCIAL_RESEARCH = "financial_research"
    LEGAL_RESEARCH = "legal_research"
    DOCUMENT_RESEARCH = "document_research"
    DEEP_RESEARCH = "deep_research"
    COMPARISON = "comparison"
    VERIFICATION = "verification"
    DISCOVERY = "discovery"
    OSINT = "osint"


class ResearchDepth(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    FINANCIAL = "financial"
    FORENSIC = "forensic"


class SourceType(str, Enum):
    OFFICIAL_FILING = "official_filing"
    GOVERNMENT = "government"
    REGULATOR = "regulator"
    COMPANY = "company"
    INVESTOR_RELATIONS = "investor_relations"
    ACADEMIC = "academic"
    FINANCIAL_DATA = "financial_data"
    NEWS = "news"
    INDUSTRY = "industry"
    ANALYST = "analyst"
    # Learning-resource source types. A video is a first-class educational
    # resource, not "social media": the classifier routes youtube.com and the
    # established lecture channels to VIDEO so ranking can treat a coherent
    # lecture series as authoritative for a learning objective.
    VIDEO = "video"
    COURSE = "course"
    REPOSITORY = "repository"
    DOCUMENTATION = "documentation"
    TUTORIAL = "tutorial"
    DATASET = "dataset"
    PODCAST = "podcast"
    BLOG = "blog"
    SOCIAL = "social"
    FORUM = "forum"
    WIKI = "wiki"
    UNKNOWN = "unknown"


class Authority(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


# Source types that count as primary/authoritative for ranking.
PRIMARY_SOURCE_TYPES = frozenset(
    {
        SourceType.OFFICIAL_FILING,
        SourceType.GOVERNMENT,
        SourceType.REGULATOR,
        SourceType.INVESTOR_RELATIONS,
    }
)
SECONDARY_SOURCE_TYPES = frozenset(
    {
        SourceType.COMPANY,
        SourceType.FINANCIAL_DATA,
        SourceType.NEWS,
        SourceType.ACADEMIC,
        SourceType.INDUSTRY,
        SourceType.ANALYST,
        SourceType.DOCUMENTATION,
        SourceType.COURSE,
        SourceType.REPOSITORY,
    }
)
TERTIARY_SOURCE_TYPES = frozenset(
    {
        SourceType.BLOG,
        SourceType.SOCIAL,
        SourceType.FORUM,
        SourceType.WIKI,
        SourceType.UNKNOWN,
        SourceType.VIDEO,
        SourceType.TUTORIAL,
        SourceType.DATASET,
        SourceType.PODCAST,
    }
)


def authority_for(source_type: SourceType, *, is_primary_filing: bool = False) -> Authority:
    """Deterministic primary/secondary/tertiary classification."""
    if is_primary_filing or source_type in PRIMARY_SOURCE_TYPES:
        return Authority.PRIMARY
    if source_type in SECONDARY_SOURCE_TYPES:
        return Authority.SECONDARY
    return Authority.TERTIARY


# ── Search results (pointers, NOT evidence) ───────────────────────────────────


class SearchResult(BaseModel):
    """One normalized search result from any provider.

    This is a POINTER. It is never evidence: it carries no fetched content and
    no claim. `snippet` is provider-supplied and must never be presented as fact.
    """

    resultId: str
    title: str
    url: str
    domain: str = ""
    snippet: str = ""
    publishedAt: Optional[str] = None
    updatedAt: Optional[str] = None
    author: Optional[str] = None
    sourceType: SourceType = SourceType.UNKNOWN
    provider: str = "unknown"
    ranking: int = 0
    relevance: float = 0.0
    retrievedAt: str = Field(default_factory=_now)


class SearchResponse(BaseModel):
    """A normalized, provider-independent search answer."""

    query: str
    status: Literal["OK", "UNAVAILABLE", "ERROR"] = "OK"
    provider: Optional[str] = None
    results: list[SearchResult] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    failureClass: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    latencyMs: int = 0


# ── Sources / documents / evidence ─────────────────────────────────────────────


class Source(BaseModel):
    """A canonical source (a publication venue + a concrete URL)."""

    sourceId: str
    canonicalUrl: str
    domain: str = ""
    publisher: Optional[str] = None
    sourceType: SourceType = SourceType.UNKNOWN
    authority: Authority = Authority.TERTIARY
    retrievedAt: str = Field(default_factory=_now)
    publishedAt: Optional[str] = None
    sourceFamily: Optional[str] = None
    contentHash: Optional[str] = None
    title: Optional[str] = None
    reliability: Optional[float] = None


class Evidence(BaseModel):
    """The unified evidence contract: the most important object in the engine.

    Every field is copied from a real fetched artifact or left None — never
    guessed. `contentTrust` is always `UNTRUSTED` for web content; it is a
    machine-readable statement that the text is DATA, not instructions.
    """

    evidenceId: str
    sourceId: str
    sourceUrl: str
    sourceType: SourceType = SourceType.UNKNOWN
    publisher: Optional[str] = None
    entityId: Optional[str] = None

    publishedAt: Optional[str] = None
    updatedAt: Optional[str] = None
    effectiveAt: Optional[str] = None
    knownAt: Optional[str] = None
    retrievedAt: str = Field(default_factory=_now)

    documentId: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None

    rawText: str = ""
    claimText: Optional[str] = None

    structuredValue: Any = None
    unit: Optional[str] = None
    period: Optional[str] = None

    contentHash: str = ""
    confidence: float = 0.0
    contentTrust: Literal["UNTRUSTED"] = "UNTRUSTED"
    provenance: dict[str, Any] = Field(default_factory=dict)


def content_hash(text: str) -> str:
    """Stable content hash for an evidence/document artifact."""
    return "h_" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def evidence_id(*, source_url: str, raw_text: str, page: Optional[int] = None) -> str:
    """A stable evidence id derived from provenance + content (reproducible)."""
    payload = f"{source_url}|{page or ''}|{content_hash(raw_text)}"
    return "ev_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def source_id(url: str) -> str:
    return "src_" + hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:16]


# ── Claims / conflicts / citations ────────────────────────────────────────────

ClaimStatus = Literal[
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNSUPPORTED",
    "OUTDATED",
    "AMBIGUOUS",
    "CALCULATED",
    "INFERRED",
]

ConflictStatus = Literal["RESOLVED", "UNRESOLVED", "EXPLAINED", "MATERIAL", "NON_MATERIAL"]


class Claim(BaseModel):
    id: Optional[str] = None
    text: str
    kind: Literal["FACT", "CALCULATION", "INFERENCE", "OPINION", "UNCERTAINTY"] = "FACT"
    evidenceIds: list[str] = Field(default_factory=list)
    calculationId: Optional[str] = None
    status: ClaimStatus = "UNSUPPORTED"
    confidence: float = 0.0
    issues: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SourceConflict(BaseModel):
    metric: str
    period: Optional[str] = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    status: ConflictStatus = "UNRESOLVED"
    material: bool = True
    explanation: Optional[str] = None


class Citation(BaseModel):
    citationId: str
    claimText: str
    evidenceId: str
    sourceUrl: str
    title: Optional[str] = None
    section: Optional[str] = None
    page: Optional[int] = None
    retrievedAt: Optional[str] = None
    publishedAt: Optional[str] = None
    locator: Optional[str] = None


# ── Request / mandate / plan ────────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    """The normalized, user-facing research request."""

    question: str
    intent: Optional[ResearchIntent] = None
    depth: ResearchDepth = ResearchDepth.STANDARD
    freshness: Optional[str] = None  # e.g. "7d", "24h", "any"
    pointInTime: Optional[str] = None  # ISO date; no future leakage past this
    sourceTypes: list[SourceType] = Field(default_factory=list)
    minSources: int = 3
    maxSources: int = 12
    maxQueries: int = 12
    maxTimeSeconds: float = 120.0
    maxCost: float = 1.0
    citationsRequired: bool = True
    crossValidationRequired: bool = False
    primarySourcesRequired: bool = False
    financialMode: bool = False
    userContext: dict[str, Any] = Field(default_factory=dict)


class SubQuestion(BaseModel):
    id: str
    question: str
    intent: ResearchIntent = ResearchIntent.FACT_LOOKUP
    required: bool = True
    sourceTypes: list[SourceType] = Field(default_factory=list)
    primaryRequired: bool = False
    answered: bool = False
    evidenceIds: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WebResearchMandate(BaseModel):
    """The persisted execution contract for one web research run."""

    researchId: str
    question: str
    objective: str
    intent: ResearchIntent
    depth: ResearchDepth
    subQuestions: list[SubQuestion] = Field(default_factory=list)
    sourceTypes: list[SourceType] = Field(default_factory=list)
    freshness: Optional[str] = None
    pointInTime: Optional[str] = None
    minSources: int = 3
    maxSources: int = 12
    primarySourcesRequired: bool = False
    crossValidationRequired: bool = False
    citationsRequired: bool = True
    budget: dict[str, Any] = Field(default_factory=dict)
    stoppingCriteria: list[str] = Field(default_factory=list)
    createdAt: str = Field(default_factory=_now)


class ResearchPlan(BaseModel):
    researchId: str
    strategy: str = "standard"
    queries: list[str] = Field(default_factory=list)
    subQuestions: list[SubQuestion] = Field(default_factory=list)
    sourcesPlanned: list[str] = Field(default_factory=list)
    estimatedQueries: int = 0
    notes: list[str] = Field(default_factory=list)


# ── Status ────────────────────────────────────────────────────────────────────

ResearchState = Literal[
    "PLANNING",
    "SEARCHING",
    "EXTRACTING",
    "NORMALIZING",
    "VALIDATING",
    "COMPARING",
    "VERIFYING",
    "SYNTHESIZING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
]


class ResearchStatus(BaseModel):
    researchId: str
    state: ResearchState = "PLANNING"
    progress: float = 0.0
    questionsTotal: int = 0
    questionsAnswered: int = 0
    sourceCount: int = 0
    evidenceCount: int = 0
    claimCount: int = 0
    citationCount: int = 0
    conflictCount: int = 0
    unresolvedConflicts: int = 0
    stopReason: Optional[str] = None
    errors: list[str] = Field(default_factory=list)


__all__ = [
    "ResearchIntent",
    "ResearchDepth",
    "SourceType",
    "Authority",
    "PRIMARY_SOURCE_TYPES",
    "SECONDARY_SOURCE_TYPES",
    "TERTIARY_SOURCE_TYPES",
    "authority_for",
    "SearchResult",
    "SearchResponse",
    "Source",
    "Evidence",
    "content_hash",
    "evidence_id",
    "source_id",
    "ClaimStatus",
    "ConflictStatus",
    "Claim",
    "SourceConflict",
    "Citation",
    "ResearchRequest",
    "SubQuestion",
    "WebResearchMandate",
    "ResearchPlan",
    "ResearchState",
    "ResearchStatus",
]
