"""Financial Retrieval Layer (Phase 2) — provider-agnostic hybrid retrieval.

The agent requests *what it needs* (an objective + data type + instrument), not
*which provider* to call. This package owns:

    contract.py   the unified request/result/evidence models
    planner.py    task-aware source selection (deterministic, explainable)
    structured.py structured providers (JDdS, yfinance) behind one interface
    web.py        first-class web research (search → retrieve → evidence)
    normalize.py  provider payloads → one NormalizedFinancialObject
    cache.py      freshness-policy cache
    parallel.py   concurrent retrieval with error isolation
    validate.py   data-quality checks (valid/warning/invalid/unknown)
    conflicts.py  explicit source-conflict preservation/resolution
    aggregate.py  EvidenceSet assembly
    layer.py      the orchestrator the tools call
    registry.py   the declarative provider capability registry
    ratelimit.py  centralized per-provider rate limits / quota
    crypto.py     crypto market data as a first-class source

Providers are never named anywhere above the `layer`. JDdS, yfinance, the TS
web-research bridge and any future provider are implementation details.
"""

from .contract import (
    DataType,
    EvidenceItem,
    EvidenceKind,
    EvidenceSet,
    FreshnessRequirement,
    FinancialRetrievalRequest,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    QualityStatus,
    RetrievalStatus,
    SourceReference,
    SourceTier,
)
from .authority import AUTHORITY, DataTypeAuthority, SourceDecision, decide_source
from .layer import FinancialRetrievalLayer
from .registry import ProviderDescriptor, ProviderRegistry, build_default_registry
from .ratelimit import RateLimitManager

__all__ = [
    "DataType",
    "EvidenceItem",
    "EvidenceKind",
    "EvidenceSet",
    "FreshnessRequirement",
    "FinancialRetrievalRequest",
    "FinancialRetrievalResult",
    "NormalizedFinancialObject",
    "QualityStatus",
    "RetrievalStatus",
    "SourceReference",
    "SourceTier",
    "FinancialRetrievalLayer",
    "AUTHORITY",
    "DataTypeAuthority",
    "SourceDecision",
    "decide_source",
    "ProviderDescriptor",
    "ProviderRegistry",
    "build_default_registry",
    "RateLimitManager",
]
