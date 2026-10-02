"""Adapter: existing `NormalizedFinancialObject` → universal `FinancialFact`.

This is the seam between the retrieval layer (which already preserves value,
unit, currency, timestamps, basis, provenance) and the fact engine. It does not
touch the network and does not rewrite retrieval; it LIFTS what retrieval already
carries into the richer, accounting-aware model.

Anything the object does not state is left `unknown`/`None` — the adapter never
guesses a definition, a period type, a consolidation level or a source type.
"""

from __future__ import annotations

from typing import Any, Optional

from ..retrieval.contract import NormalizedFinancialObject
from ..research.periods import parse_period
from . import periods_ext, semantics
from .model import FinancialFact, FinancialPeriod

# Map a retrieval source tier onto the fact engine's source-type vocabulary.
_TIER_TO_SOURCE_TYPE: dict[str, str] = {
    "primary": "regulatory_filing",
    "official": "government",
    "structured": "financial_database",
    "secondary": "aggregator",
    "derived": "derived",
    "cache": "vault",
    "unknown": "unknown",
}


def _source_type(obj: NormalizedFinancialObject) -> str:
    name = str(getattr(obj.source, "source", "") or "")
    if name.upper() in ("JDDS", "JDdS") or "jdds" in name.lower():
        return "vault"
    tier = getattr(obj.source, "sourceType", "unknown")
    # A live price is a market-data fact, not a database fact.
    if obj.name in ("price", "volume", "changePct") and tier == "structured":
        return "market_data"
    return _TIER_TO_SOURCE_TYPE.get(tier, "unknown")


def _period(obj: NormalizedFinancialObject) -> Optional[FinancialPeriod]:
    label = obj.period or None
    end = obj.dataTimestamp or obj.observation_time or None
    ptype = periods_ext.parse_period_type(label) if label else None
    if ptype is None and label:
        parsed = parse_period(label)
        if parsed is not None:
            ptype = {"annual": "fy", "quarter": "quarter", "date": "daily", "range": "range"}.get(
                parsed.granularity, None
            )
    if ptype is None and end:
        # No explicit type: a bare timestamp is a dated observation.
        ptype = "daily"
    if ptype is None and not end:
        return None
    fy: Optional[int] = None
    fq: Optional[int] = None
    if label:
        parsed = parse_period(label)
        if parsed is not None:
            fy, fq = parsed.year, parsed.quarter
    start, end_iso = periods_ext.window_for(ptype, end) if end else (None, None)
    return FinancialPeriod(
        period_type=ptype or "daily",
        period_start=start,
        period_end=end_iso or end,
        fiscal_year=fy,
        fiscal_quarter=fq,
        label=label,
    )


def _attribution(obj: NormalizedFinancialObject, definition: Optional[str]) -> str:
    # Prefer an explicit provider field; else infer from the definition.
    raw = obj.raw if isinstance(obj.raw, dict) else {}
    explicit = str(raw.get("attribution") or "").lower()
    if explicit in ("group", "parent", "common", "nci", "preferred", "unattributed"):
        return explicit
    if definition in ("net_income_parent", "parent_equity"):
        return "parent"
    if definition in ("net_income_common", "common_equity"):
        return "common"
    if definition in ("net_income_nci", "nci_equity"):
        return "nci"
    if definition in ("net_income", "total_equity"):
        return "group"
    return "unknown"


def _consolidation(obj: NormalizedFinancialObject) -> str:
    basis = (obj.basis or "").strip().lower()
    raw = obj.raw if isinstance(obj.raw, dict) else {}
    explicit = str(raw.get("consolidation") or raw.get("consolidation_level") or "").lower()
    value = explicit or basis
    if value in ("full", "consolidated"):
        return "full"
    if value in ("proportionate", "proportional"):
        return "proportionate"
    if value in ("equity", "equity_method", "equity-method"):
        return "equity_method"
    if value in ("not_consolidated", "not-consolidated", "unconsolidated"):
        return "not_consolidated"
    if value in ("standalone",):
        # standalone is the parent-only view; not the group consolidation
        return "not_consolidated"
    return "unknown"


def to_fact(obj: NormalizedFinancialObject, *, entity_id: Optional[str] = None) -> FinancialFact:
    """Lift one normalized object into a FinancialFact. Never fabricates metadata."""
    definition = semantics.resolve_definition(obj.name)
    raw = obj.raw if isinstance(obj.raw, dict) else {}
    # A provider may name the standard explicitly; otherwise leave it unknown.
    accounting_standard = raw.get("accountingStandard") or raw.get("accounting_standard")
    reported_or_derived = "derived" if raw.get("derived") is True else "reported"

    return FinancialFact(
        fact_id=str(raw.get("evidenceId") or f"{obj.instrument or ''}:{obj.name}:{obj.period or obj.dataTimestamp or ''}"),
        metric=obj.name,
        definition=definition,
        value=obj.value,
        currency=obj.currency,
        unit=obj.unit,
        entity_id=entity_id or (obj.identity.key if obj.identity is not None else obj.instrument),
        ticker=obj.instrument,
        exchange=getattr(obj.identity, "exchange", None) if obj.identity is not None else None,
        asset_type=getattr(obj.identity, "assetClass", None) if obj.identity is not None else None,
        period=_period(obj),
        publication_timestamp=obj.publishedAt or None,
        source_timestamp=obj.observation_time or obj.dataTimestamp or None,
        retrieved_timestamp=obj.source.retrievedAt if obj.source is not None else None,
        source=str(obj.source.source) if obj.source is not None else None,
        source_type=_source_type(obj),  # type: ignore[arg-type]
        source_document=obj.documentId or None,
        accounting_standard=str(accounting_standard) if accounting_standard else None,
        consolidation_level=_consolidation(obj),  # type: ignore[arg-type]
        attribution=_attribution(obj, definition),  # type: ignore[arg-type]
        reported_or_derived=reported_or_derived,  # type: ignore[arg-type]
        supersedes_fact_id=obj.supersedesEvidenceId or None,
        warnings=tuple(obj.warnings or ()),
        raw=raw or None,
    )


__all__ = ["to_fact"]
