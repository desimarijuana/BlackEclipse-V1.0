"""Evidence aggregation (Milestone 2I).

Combines outcomes from several retrieval paths into one `EvidenceSet` while
keeping the evidence kinds DISTINCT. Direct source data, derived calculations,
web evidence, cached information and unverified information are never collapsed
into anonymous text — each item retains its own provenance.
"""

from __future__ import annotations

from typing import Any, Optional

from .contract import (
    EvidenceItem,
    EvidenceKind,
    EvidenceSet,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    SourceReference,
)
from .sources import SourceOutcome


def outcome_to_evidence(outcome: SourceOutcome) -> Optional[EvidenceItem]:
    """Turn a structured outcome into one evidence item (if it has data)."""
    if outcome.status != "OK" or not outcome.objects:
        return None
    source = outcome.references[0] if outcome.references else SourceReference(source=outcome.source)
    return EvidenceItem(
        id=f"structured_{outcome.source}_{abs(hash(str(outcome.objects[0].value))) % 10**10}",
        kind="structured",
        summary=f"{outcome.source}: {len(outcome.objects)} normalized value(s)",
        objects=outcome.objects,
        source=source,
        quality="valid",
    )


def derive_evidence(
    name: str,
    value: Any,
    source: SourceReference,
    summary: str,
    inputs: Optional[list[NormalizedFinancialObject]] = None,
) -> EvidenceItem:
    """Record a deterministic calculation as `derived` evidence."""
    obj = NormalizedFinancialObject(
        name=name,
        value=value,
        source=source,
        quality="valid",
        warnings=["derived calculation — not a directly observed value"],
    )
    return EvidenceItem(
        id=f"derived_{name}_{abs(hash(str(value))) % 10**10}",
        kind="derived",
        summary=summary,
        data={"value": value, "inputs": [i.model_dump() for i in (inputs or [])]},
        objects=[obj],
        source=source,
        quality="valid",
        warnings=["derived: computed by the retrieval layer from structured inputs"],
    )


def user_evidence(summary: str, data: Any = None) -> EvidenceItem:
    source = SourceReference(source="user", sourceType="unknown", validationStatus="unknown")
    return EvidenceItem(
        id=f"user_{abs(hash(summary)) % 10**10}",
        kind="user",
        summary=summary,
        data=data,
        source=source,
        quality="unknown",
        warnings=["user-provided information — not independently verified"],
    )


def cached_evidence(result: FinancialRetrievalResult) -> Optional[EvidenceItem]:
    if not result.cached:
        return None
    source = result.sourceReferences[0] if result.sourceReferences else SourceReference(source="cache", sourceType="cache")
    return EvidenceItem(
        id=f"cached_{abs(hash(result.retrievedAt)) % 10**10}",
        kind="cached",
        summary="cached retrieval result (freshness preserved in provenance)",
        source=source,
        quality=result.quality,
        warnings=["served from cache"],
    )


def aggregate(
    objective: str,
    results: list[FinancialRetrievalResult],
    extra_warnings: Optional[list[str]] = None,
) -> EvidenceSet:
    """Merge one or more layer results into a single, provenance-preserving set."""
    items: list[EvidenceItem] = []
    warnings: list[str] = list(extra_warnings or [])

    for result in results:
        for item in result.evidence:
            items.append(item)
        cached = cached_evidence(result)
        if cached is not None:
            items.append(cached)
        for warning in result.warnings:
            if warning not in warnings:
                warnings.append(warning)

    return EvidenceSet(objective=objective, items=items, warnings=warnings)


__all__ = [
    "aggregate",
    "outcome_to_evidence",
    "derive_evidence",
    "user_evidence",
    "cached_evidence",
]
