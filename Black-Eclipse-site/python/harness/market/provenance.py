"""Provenance + point-in-time for market records.

Two concerns live here:

  1. **Provenance** — converting a canonical market record into the retrieval
     layer's `EvidenceItem` / `NormalizedFinancialObject` shape, so market data
     flows into the SAME Evidence & Research Engine (the run `source_sink`, the
     `finance_facts` analysis) that every other structured source uses. There is
     no second provenance format.

  2. **Point-in-time correctness** — deciding whether a record was actually
     knowable at a given instant. Financial research must never let future
     information leak into a historical view. The rule fails closed: a record
     with no usable timestamp is NOT admissible at a cutoff.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from ..retrieval.contract import (
    EvidenceItem,
    InstrumentIdentity,
    NormalizedFinancialObject,
    SourceReference,
)
from .models import MarketRecord

# Capability → the freshness class the retrieval layer understands.
_FRESHNESS_MAP = {
    "quote": "realtime",
    "orderbook": "realtime",
    "trades": "realtime",
    "funding": "realtime",
    "ohlcv": "intraday",
    "volume": "intraday",
    "open_interest": "intraday",
    "market_cap": "daily",
    "supply": "daily",
    "options": "daily",
    "historical": "slow",
    "bonds": "slow",
    "fx": "realtime",
}


def _parse_ts(value: Optional[str]) -> Optional[_dt.datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def knows_at(record: MarketRecord, as_of: Optional[str]) -> bool:
    """Whether `record` was knowable at `as_of`. Fails closed.

    A record is knowable at `as_of` when its retrieval time (or its event time,
    when no retrieval time exists) is at or before `as_of`. No usable timestamp
    ⇒ not knowable.
    """
    cutoff = _parse_ts(as_of)
    if cutoff is None:
        return True  # no cutoff requested
    stamp = record.meta.retrieved_at or record.meta.published_at or record.meta.event_time
    parsed = _parse_ts(stamp)
    if parsed is None:
        return False
    return parsed <= cutoff


def filter_point_in_time(records: list[MarketRecord], as_of: Optional[str]) -> tuple[list[MarketRecord], list[str]]:
    """Split records into (admissible, rejection-reasons) for a cutoff."""
    if not as_of:
        return list(records), []
    admissible: list[MarketRecord] = []
    rejected: list[str] = []
    for record in records:
        if knows_at(record, as_of):
            admissible.append(record)
        else:
            rejected.append(
                f"{record.meta.symbol or '?'}: not knowable at {as_of} "
                f"(retrieved {record.meta.retrieved_at or 'unknown'})"
            )
    return admissible, rejected


def _identity(record: MarketRecord) -> Optional[InstrumentIdentity]:
    meta = record.meta
    if not meta.symbol or not (meta.venue or meta.exchange or meta.asset_type):
        return None
    return InstrumentIdentity(
        market=str(meta.venue or meta.exchange or meta.asset_type).upper(),
        symbol=str(meta.symbol).upper(),
        currency=meta.currency,
        assetClass=meta.asset_type,
        securityType=meta.asset_type,
    )


def to_objects(record: MarketRecord) -> list[NormalizedFinancialObject]:
    """Flatten a market record's scalar fields into normalized objects.

    Only scalar values become objects; the identity + provenance ride on each.
    A conflict is NOT turned into a value — it is surfaced on the evidence item.
    """
    identity = _identity(record)
    source = SourceReference(
        source=str(record.meta.provider or record.meta.source or "market"),
        sourceType="structured",
        url=None,
        publishedAt=record.meta.published_at,
        retrievedAt=record.meta.retrieved_at,
        validationStatus="valid" if record.meta.quality != "invalid" else "invalid",
    )
    out: list[NormalizedFinancialObject] = []
    data = record.model_dump(mode="json", exclude_none=True)
    meta_keys = {"meta", "raw", "conflict"}
    for key, value in data.items():
        if key in meta_keys:
            continue
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            out.append(
                NormalizedFinancialObject(
                    name=key,
                    value=value,
                    currency=record.meta.currency,
                    dataTimestamp=record.meta.event_time or record.meta.retrieved_at,
                    instrument=record.meta.symbol,
                    identity=identity,
                    source=source,
                    observation_time=record.meta.event_time,
                    observation_source=record.meta.observation_source
                    if record.meta.observation_source != "retrieval_clock"
                    else "unknown",
                    quality=record.meta.quality,
                )
            )
    return out


def to_evidence(record: MarketRecord, capability: str) -> EvidenceItem:
    """Convert a market record into a retrieval `EvidenceItem`."""
    objects = to_objects(record)
    summary = _summary(record, capability)
    return EvidenceItem(
        id=f"market:{capability}:{record.meta.instrument_id or record.meta.symbol}:{record.meta.retrieved_at}",
        kind="structured",
        summary=summary,
        data=record.to_dict(),
        objects=objects,
        source=SourceReference(
            source=str(record.meta.provider or record.meta.source or "market"),
            sourceType="structured",
            publishedAt=record.meta.published_at,
            retrievedAt=record.meta.retrieved_at,
            query=f"{capability} {record.meta.symbol}",
            validationStatus="valid" if record.meta.quality != "invalid" else "invalid",
        ),
        quality=record.meta.quality,
        warnings=list(record.meta.warnings),
    )


def _summary(record: MarketRecord, capability: str) -> str:
    meta = record.meta
    parts = [f"{capability} for {meta.symbol or '?'}"]
    if meta.provider:
        parts.append(f"provider={meta.provider}")
    if meta.event_time:
        parts.append(f"as-of={meta.event_time}")
    if meta.quality:
        parts.append(f"quality={meta.quality}")
    return "; ".join(parts)


__all__ = [
    "filter_point_in_time",
    "knows_at",
    "to_evidence",
    "to_objects",
]
