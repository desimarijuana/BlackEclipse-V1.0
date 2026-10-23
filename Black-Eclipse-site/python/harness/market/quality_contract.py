"""ONE data-quality contract shared by market, fundamental, macro and FX tools.

Every data-producing tool emits a :class:`DataQualityEnvelope`. The envelope is
the single vocabulary for "what is this value, where did it come from, how old
is it, and can it be trusted?".

Invariants enforced here (never weakened by a caller):

* a missing value stays missing (``None``), never interpolated;
* two disagreeing sources are never averaged - both candidates are carried;
* a result may not be ``VALID`` while it carries a conflict, a stale
  observation beyond its cadence tolerance, or zero providers.

The verdict enum is deliberately small and provider-neutral. A caller renders
``qualityVerdict``; it must never invent its own "valid" label.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field

QualityVerdict = Literal[
    "VALID",
    "STALE",
    "DIVERGENT",
    "SCALE_MISMATCH",
    "UNAVAILABLE",
    "UNVERIFIED",
]

# Round factors that commonly indicate a lot/board-lot or unit split rather
# than a genuinely different market price.
ROUND_SCALE_FACTORS: tuple[float, ...] = (2.0, 10.0, 100.0, 1000.0)


class EnvelopeConflict(BaseModel):
    """One disagreement, with BOTH values, providers and timestamps preserved."""

    metric: str
    relativeGap: Optional[float] = None
    scaleFactor: Optional[float] = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class DataQualityEnvelope(BaseModel):
    """The shared result envelope. Additive to the existing tool payloads."""

    value: Any = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    provider: Optional[str] = None
    observationTimestamp: Optional[str] = None
    retrievalTimestamp: Optional[str] = None
    nativeCadence: Optional[str] = None
    qualityVerdict: QualityVerdict = "UNVERIFIED"
    conflicts: list[EnvelopeConflict] = Field(default_factory=list)
    routesSkipped: list[dict[str, Any]] = Field(default_factory=list)
    stale: bool = False
    reasonCode: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=False)


def relative_gap(a: float, b: float) -> float:
    denom = max(abs(float(a)), abs(float(b)))
    if denom == 0:
        return 0.0
    return abs(float(a) - float(b)) / denom


def scale_factor(a: float, b: float) -> Optional[float]:
    """Return the near-round multiplier between two values, when one exists."""
    try:
        small = min(abs(float(a)), abs(float(b)))
        large = max(abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return None
    if small <= 0 or large <= 0:
        return None
    ratio = large / small
    for factor in ROUND_SCALE_FACTORS:
        if abs(ratio - factor) / factor <= 0.02:
            return factor
    return None


def compare_values(
    a: float,
    b: float,
    *,
    tolerance: float = 0.01,
) -> tuple[QualityVerdict, float, Optional[float]]:
    """Classify two source values. Never returns a chosen/blended value.

    Returns ``(verdict, relative_gap, scale_factor)`` where verdict is
    ``VALID`` (agree), ``SCALE_MISMATCH`` (near a round factor) or
    ``DIVERGENT`` (material disagreement not explained by a unit split).
    """
    gap = relative_gap(a, b)
    if gap <= tolerance:
        return "VALID", gap, None
    factor = scale_factor(a, b)
    if factor is not None:
        return "SCALE_MISMATCH", gap, factor
    return "DIVERGENT", gap, None


def conflict_block(
    metric: str,
    candidates: Iterable[dict[str, Any]],
    *,
    tolerance: float = 0.01,
    verdict: QualityVerdict = "DIVERGENT",
    gap: Optional[float] = None,
    factor: Optional[float] = None,
) -> EnvelopeConflict:
    return EnvelopeConflict(
        metric=metric,
        relativeGap=gap,
        scaleFactor=factor,
        candidates=list(candidates),
    )


def evaluate_envelope_invariants(env: DataQualityEnvelope, *, cadence_tolerance_s: Optional[float] = None,
                                 now: Optional[_dt.datetime] = None) -> list[str]:
    """Return invariant violations for an envelope (empty when honest)."""
    problems: list[str] = []
    if env.qualityVerdict == "VALID" and env.conflicts:
        problems.append("quality=VALID while carrying a conflict")
    if not env.provider:
        problems.append("no provider recorded")
    if env.stale and env.qualityVerdict == "VALID":
        problems.append("quality=VALID while stale=true")
    if cadence_tolerance_s is not None and env.observationTimestamp and not env.stale:
        age = _age_seconds(env.observationTimestamp, now=now)
        if age is not None and age > cadence_tolerance_s:
            problems.append(
                f"quality=VALID while observation is {int(age)}s old "
                f"(cadence tolerance {int(cadence_tolerance_s)}s)"
            )
    return problems


def envelope_from_record(record: Any, *, cadence: Optional[str] = None) -> DataQualityEnvelope:
    """Build the shared envelope from any market record (duck-typed).

    The record's quality vocabulary is intentionally NOT copied verbatim; it is
    mapped onto the shared verdict so a market record can never claim "valid"
    while its conflict block is populated.
    """
    meta = getattr(record, "meta", None)
    conflict = getattr(record, "conflict", None)
    quality = str(getattr(meta, "quality", "unknown") or "unknown").lower()
    status = str(getattr(meta, "data_status", "OK") or "OK").upper()
    conflicts: list[EnvelopeConflict] = []
    verdict: QualityVerdict
    if conflict:
        metric = str(conflict.get("metric") or "value")
        factor = conflict.get("scaleFactor")
        gap = conflict.get("relativeGap")
        candidates = conflict.get("candidates") or []
        conflicts.append(EnvelopeConflict(
            metric=metric,
            relativeGap=gap if isinstance(gap, (int, float)) else None,
            scaleFactor=factor if isinstance(factor, (int, float)) else None,
            candidates=candidates if isinstance(candidates, list) else [],
        ))
        verdict = "SCALE_MISMATCH" if factor else "DIVERGENT"
    elif status in ("UNAVAILABLE", "UNKNOWN") or quality == "invalid":
        verdict = "UNAVAILABLE"
        if status == "STALE":
            verdict = "STALE"
    elif status == "STALE" or quality == "stale":
        verdict = "STALE"
    elif quality in ("valid",):
        verdict = "VALID"
    elif quality == "warning":
        verdict = "UNVERIFIED"
    else:
        verdict = "UNVERIFIED"
    # Find the primary scalar value without inventing one.
    value = None
    for name in ("price", "mid", "rate", "market_cap", "total_volume",
                 "open_interest", "funding_rate", "yield_", "bid", "ask"):
        candidate = getattr(record, name, None)
        if candidate is not None and isinstance(candidate, (int, float)):
            value = candidate
            break
    if value is None:
        bars = getattr(record, "bars", None)
        if bars:
            value = getattr(bars[-1], "close", None)
    return DataQualityEnvelope(
        value=value,
        unit="currency" if getattr(meta, "currency", None) else None,
        currency=getattr(meta, "currency", None),
        provider=getattr(meta, "provider", None),
        observationTimestamp=getattr(meta, "event_time", None),
        retrievalTimestamp=getattr(meta, "retrieved_at", None),
        nativeCadence=cadence,
        qualityVerdict=verdict,
        conflicts=conflicts,
        stale=verdict == "STALE",
        reasonCode="DATA_CONFLICT" if conflicts else (
            "DATA_STALE" if verdict == "STALE" else (
                "DATA_NOT_AVAILABLE" if verdict == "UNAVAILABLE" else None)),
    )


def _age_seconds(timestamp: str, *, now: Optional[_dt.datetime] = None) -> Optional[float]:
    text = str(timestamp).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    ref = now or _dt.datetime.now(_dt.timezone.utc)
    return (ref - parsed).total_seconds()


__all__ = [
    "DataQualityEnvelope",
    "EnvelopeConflict",
    "QualityVerdict",
    "ROUND_SCALE_FACTORS",
    "compare_values",
    "conflict_block",
    "envelope_from_record",
    "evaluate_envelope_invariants",
    "relative_gap",
    "scale_factor",
]
