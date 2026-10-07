"""Freshness + point-in-time admissibility.

Five distinct timestamps are tracked (never conflated):

    published_at  — when the issuer published it
    updated_at    — when the issuer last revised it
    effective_at  — when the described fact takes effect
    known_at      — when the fact became knowable (publication, else retrieval)
    retrieved_at  — when this engine fetched it

Point-in-time research is mandatory for the financial architecture: a source
whose `known_at` is after the requested cutoff must NEVER be used. Missing
publication time is not a wildcard — it cannot be admitted for a strict cutoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .web_contracts import Evidence

_FRESHNESS_WINDOWS_SECONDS = {
    "1h": 3600,
    "24h": 86400,
    "1d": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
    "1y": 365 * 86400,
}


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def known_at(evidence: Evidence) -> Optional[str]:
    """When the fact became knowable: explicit `knownAt`, else publication."""
    return evidence.knownAt or evidence.publishedAt


def is_admissible_at(evidence: Evidence, as_of: Optional[str]) -> tuple[bool, Optional[str]]:
    """Point-in-time admissibility. Returns (admissible, reason_if_not).

    A strict cutoff with an unknown time is NOT admissible — future-leakage
    protection must fail closed. A source published after the cutoff is excluded.
    """
    if not as_of:
        return True, None
    cutoff = parse_ts(as_of)
    if cutoff is None:
        return False, f"point-in-time cutoff {as_of!r} is not a valid timestamp"
    when = parse_ts(known_at(evidence))
    if when is None:
        return False, "publication/known time is unknown; cannot be established before the cutoff"
    if when > cutoff:
        return False, f"known at {when.isoformat()} which is after the cutoff {as_of}"
    return True, None


def is_fresh(evidence: Evidence, freshness: Optional[str], *, now: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
    """Freshness validation against a window like `7d`/`24h`.

    Uses `updated_at` when present (a revision refreshes the fact), else
    `published_at`. `any`/None accepts anything. An unknown date is accepted
    (freshness is a preference); point-in-time is the hard guarantee.
    """
    if not freshness or freshness in ("any", "slow"):
        return True, None
    window = _FRESHNESS_WINDOWS_SECONDS.get(str(freshness).lower())
    if window is None:
        return True, None  # unknown window spec → do not silently reject
    when = parse_ts(evidence.updatedAt or evidence.publishedAt)
    if when is None:
        return True, None
    reference = now or datetime.now(timezone.utc)
    age = (reference - when).total_seconds()
    if age > window:
        return False, f"source age {int(age)}s exceeds the {freshness} freshness window"
    return True, None


def filter_admissible(
    evidence: list[Evidence],
    *,
    as_of: Optional[str] = None,
    freshness: Optional[str] = None,
) -> tuple[list[Evidence], list[dict[str, Any]]]:
    """Partition evidence into admissible and rejected, preserving provenance.

    Returns (admissible, rejections) where each rejection names the evidence and
    the exact reason, so a run can disclose what it excluded and why.
    """
    admissible: list[Evidence] = []
    rejections: list[dict[str, Any]] = []
    for item in evidence:
        ok_pt, why_pt = is_admissible_at(item, as_of)
        if not ok_pt:
            rejections.append({"evidenceId": item.evidenceId, "reason": why_pt, "kind": "point_in_time"})
            continue
        ok_fresh, why_fresh = is_fresh(item, freshness)
        if not ok_fresh:
            rejections.append({"evidenceId": item.evidenceId, "reason": why_fresh, "kind": "freshness"})
            continue
        admissible.append(item)
    return admissible, rejections


__all__ = ["parse_ts", "known_at", "is_admissible_at", "is_fresh", "filter_admissible"]
