"""Unified retrieval contract (Milestone 2A).

The agent expresses an *objective* and a *data type*; the retrieval layer decides
which source satisfies it. Nothing here names yfinance, JDdS or any search
provider — those are implementation details behind the layer.

These are internal Python contracts (pydantic), not the harness wire contract.
They are deliberately provider-agnostic so a new provider can satisfy the same
shape without touching a tool.
"""

from __future__ import annotations

import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ── Vocabulary ──────────────────────────────────────────────────────────────

# What the agent is asking for. The planner maps each to candidate sources.
DataType = Literal[
    "current_quote",       # latest price / change for an instrument
    "historical_prices",   # OHLCV series over a date range
    "company_profile",     # sector/industry/description/universe metadata
    "financial_statements",  # income / balance / cash flow (periods)
    "earnings",            # reported or upcoming earnings info
    "macro_series",        # economic indicator time series
    "news",                # current qualitative news / market commentary
    "web_research",        # general qualitative web evidence
    "world_events",        # geopolitical / world-state events
    "derived_metric",      # a calculated figure (e.g. Sharpe) from data
]

# How fresh the caller requires the data to be. Drives cache policy + planning.
FreshnessRequirement = Literal["realtime", "intraday", "daily", "slow", "any"]

# Where a value came from, in trust order (higher tier = stronger evidence).
SourceTier = Literal[
    "primary",    # filings, IR pages, central banks, official releases
    "official",   # government / exchange / regulator
    "structured",  # a market-data provider or the vault (JDdS / yfinance)
    "secondary",  # reputable news / market media
    "derived",    # computed from structured data by this layer
    "cache",      # a previously retrieved copy
    "unknown",
]

RetrievalStatus = Literal[
    "OK",
    "PARTIAL",       # some evidence retrieved, some failed
    "AMBIGUOUS",     # the instrument identity could not be pinned to one thing
    "UNAVAILABLE",   # no evidence could be retrieved
    "CONFLICTING",   # sources disagree and it could not be resolved
    "INVALID",       # data was retrieved but failed validation
]

EvidenceKind = Literal[
    "structured",  # a numeric observation from a structured provider
    "web",         # a retrieved web page / article
    "filing",      # a primary-source filing or IR document
    "derived",     # a calculation performed by this layer
    "user",        # information the caller supplied
    "cached",      # a cached result returned as-is
    "unverified",  # retrieved but provenance could not be confirmed
]

QualityStatus = Literal["valid", "warning", "invalid", "unknown"]


class SourceReference(BaseModel):
    """Provenance for one piece of data. Never fabricated."""

    source: str                      # provider id, e.g. "JDDS", "yfinance", host
    sourceType: SourceTier = "unknown"
    url: Optional[str] = None
    title: Optional[str] = None
    publishedAt: Optional[str] = None  # None when unknown — never guessed
    retrievedAt: str = Field(default_factory=lambda: _now())
    # The query/prompt that produced this, for auditability.
    query: Optional[str] = None
    # Validation of this specific reference. `unverified` is distinct from
    # `warning`: it means the source could not be retrieved, so only a snippet
    # was seen — it must never be presented as a read, verified page.
    validationStatus: Literal["valid", "warning", "invalid", "unknown", "unverified"] = "unknown"


class InstrumentIdentity(BaseModel):
    """Canonical identity of the instrument a payload is *about*.

    A ticker alone is not an identity: it is ambiguous across venues, asset
    classes and issuers, and carries no currency. Every instrument payload must
    carry this so a consumer can detect a provider answering for a different
    instrument. `market` + `symbol` are the required pair; the rest is filled
    when the source knows it.
    """

    market: str                      # canonical market id (e.g. "PK", "US")
    symbol: str                      # venue-local ticker
    currency: Optional[str] = None   # ISO 4217, when known
    assetClass: Optional[str] = None
    securityType: Optional[str] = None
    name: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.market}:{self.symbol}"


class NormalizedFinancialObject(BaseModel):
    """One provider observation, normalized (Milestone 2F).

    Preserves value + unit + currency + timestamp + period + instrument +
    provenance through normalization. Unit/currency transforms are recorded in
    `transformations`, never applied silently.
    """

    name: str                        # metric name, e.g. "price", "revenue"
    value: Any = None
    unit: Optional[str] = None       # e.g. "%", "USD", "shares"
    currency: Optional[str] = None
    dataTimestamp: Optional[str] = None  # when the value is *about*
    period: Optional[str] = None     # fiscal period / interval (e.g. "2024-Q1")
    instrument: Optional[str] = None  # symbol / ticker / series id
    identity: Optional[InstrumentIdentity] = None  # canonical instrument identity
    source: SourceReference
    freshness: FreshnessRequirement = "any"
    quality: QualityStatus = "unknown"
    warnings: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    raw: Optional[dict[str, Any]] = None


class EvidenceItem(BaseModel):
    """A unit of evidence returned to the agent (Milestone 2I)."""

    id: str
    kind: EvidenceKind
    summary: str
    data: Optional[Any] = None
    objects: list[NormalizedFinancialObject] = Field(default_factory=list)
    source: SourceReference
    quality: QualityStatus = "unknown"
    warnings: list[str] = Field(default_factory=list)


class FinancialRetrievalRequest(BaseModel):
    """What the agent asks for. Provider-agnostic by construction."""

    objective: str
    dataType: DataType
    instrument: Optional[str] = None
    market: Optional[str] = None
    dateRange: Optional[dict[str, str]] = None  # {"start": ..., "end": ...}
    freshnessRequirement: FreshnessRequirement = "any"
    preferredSource: Optional[str] = None  # a *tier hint*, not a provider lock
    requiredEvidence: Optional[list[EvidenceKind]] = None
    quantity: Optional[str] = None  # interval/period, or a derived metric name
    query: Optional[str] = None      # free-text for web/news research
    allowWeb: bool = True            # caller may forbid web research
    allowStale: bool = False         # caller may accept explicitly-stale cache
    metadata: Optional[dict[str, Any]] = None


class FinancialRetrievalResult(BaseModel):
    """The layer's answer — always provenance-carrying, never fabricated."""

    status: RetrievalStatus
    objective: str
    dataType: DataType
    instrument: Optional[str] = None
    identity: Optional[InstrumentIdentity] = None  # canonical instrument identity
    data: Optional[Any] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    sourceReferences: list[SourceReference] = Field(default_factory=list)
    freshness: FreshnessRequirement = "any"
    quality: QualityStatus = "unknown"
    warnings: list[str] = Field(default_factory=list)
    retrievedAt: str = Field(default_factory=lambda: _now())
    cached: bool = False
    strategy: list[str] = Field(default_factory=list)  # selected source names
    latencyMs: Optional[int] = None
    # ── D3: degradation is TOP-LEVEL, never nested metadata. A consumer cannot
    # miss it, and it is structurally impossible to render a value whose identity
    # was not verified without the flag being set alongside it.
    degraded: bool = False
    degradation: Optional[str] = None  # user-safe reason, when degraded=True
    # D2: true when a parse was detected as truncated/partial. Such a result is
    # never emitted with a value; it is UNAVAILABLE + incomplete.
    incomplete: bool = False
    # C4: sources that disagree on the same quantity. Present ⇒ the agent must
    # surface the disagreement rather than choose one.
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    # D3: provenance is REQUIRED for an OK result with a value. This flag is set
    # by the finalizer when the provenance chain is complete.
    provenanceVerified: bool = False


class EvidenceSet(BaseModel):
    """Aggregated evidence from one or more retrieval paths (Milestone 2I).

    Keeps direct source data, derived calculations, web evidence, user-provided
    information, cached information and unverified information distinct — it does
    NOT collapse everything into anonymous text.
    """

    objective: str
    items: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def by_kind(self, kind: EvidenceKind) -> list[EvidenceItem]:
        return [i for i in self.items if i.kind == kind]

    def objects(self) -> list[NormalizedFinancialObject]:
        out: list[NormalizedFinancialObject] = []
        for item in self.items:
            out.extend(item.objects)
        return out


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() % 1 * 1000):03d}Z"


__all__ = [
    "DataType",
    "EvidenceItem",
    "EvidenceKind",
    "EvidenceSet",
    "FreshnessRequirement",
    "FinancialRetrievalRequest",
    "FinancialRetrievalResult",
    "InstrumentIdentity",
    "NormalizedFinancialObject",
    "QualityStatus",
    "RetrievalStatus",
    "SourceReference",
    "SourceTier",
]
