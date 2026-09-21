"""Retrieval source contract — the seam every provider implements.

A source declares which data types it can serve, its trust tier, and how to
retrieve. The planner picks among sources; the layer never knows a provider's
name. This is what keeps the agent provider-agnostic while still allowing
JDdS, yfinance and the web-research bridge to coexist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from .contract import (
    DataType,
    EvidenceItem,
    FinancialRetrievalRequest,
    NormalizedFinancialObject,
    QualityStatus,
    SourceReference,
)


@dataclass
class SourceOutcome:
    """What a single source returned. Failure is data, never an exception."""

    source: str
    status: str = "UNAVAILABLE"  # OK | UNAVAILABLE | ERROR
    objects: list[NormalizedFinancialObject] = field(default_factory=list)
    references: list[SourceReference] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: Optional[Any] = None
    cached: bool = False
    error: Optional[str] = None
    latencyMs: int = 0


@runtime_checkable
class RetrievalSource(Protocol):
    """A provider of one or more data types."""

    name: str
    tier: str
    dataTypes: tuple[DataType, ...]

    def available(self, request: FinancialRetrievalRequest) -> bool:
        """True when this source can attempt the request (config present)."""
        ...

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        """Attempt the request. Never raise; return an UNAVAILABLE outcome."""
        ...


__all__ = ["RetrievalSource", "SourceOutcome"]
