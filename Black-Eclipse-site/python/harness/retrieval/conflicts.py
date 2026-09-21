"""Source conflict resolution (Milestone 2K).

When two structured providers disagree (e.g. $185.20 vs $184.95) the discrepancy
is PRESERVED, never silently resolved to one number. The resolver compares
timestamps, source tier, instrument identity and session, and either resolves the
disagreement with a stated reason or reports `conflicting`.

A resolved conflict is only declared when the explanation is concrete (different
observation times, or a clearly higher-tier source for the same instant).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contract import NormalizedFinancialObject
from .policies import tier_rank

# Relative tolerance under which two values are treated as the same fact.
DEFAULT_REL_TOLERANCE = 0.005  # 0.5%


@dataclass
class ConflictResolution:
    status: str  # "consistent" | "resolved" | "conflicting"
    chosen: Optional[NormalizedFinancialObject]
    reason: str
    candidates: list[NormalizedFinancialObject]


def _close(a: float, b: float, rel: float = DEFAULT_REL_TOLERANCE) -> bool:
    if a == b:
        return True
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= rel


def resolve_group(
    name: str,
    candidates: list[NormalizedFinancialObject],
    rel_tolerance: float = DEFAULT_REL_TOLERANCE,
) -> ConflictResolution:
    """Resolve several observations of the same metric."""
    numeric = [c for c in candidates if isinstance(c.value, (int, float))]
    if len(numeric) <= 1:
        return ConflictResolution("consistent", numeric[0] if numeric else None, "single source", numeric)

    values = [float(c.value) for c in numeric]
    if _close(min(values), max(values), rel_tolerance):
        # All agree (within tolerance): pick the strongest-tier, newest one.
        chosen = _best(numeric)
        return ConflictResolution("consistent", chosen, "sources agree within tolerance", numeric)

    # They disagree. Can timestamps explain it?
    stamps = {c.dataTimestamp for c in numeric if c.dataTimestamp}
    if len(stamps) > 1:
        chosen = _best(numeric)
        return ConflictResolution(
            "resolved",
            chosen,
            f"values differ but observation timestamps differ ({', '.join(sorted(stamps))}); using the most recent/highest-tier source",
            numeric,
        )

    # Same instant, different tier → prefer the higher tier, but say so.
    ranks = {tier_rank(c.source.sourceType) for c in numeric}
    if len(ranks) > 1 and max(ranks) > 0:
        chosen = _best(numeric)
        return ConflictResolution(
            "resolved",
            chosen,
            "values differ at the same timestamp; using the higher-tier source",
            numeric,
        )

    return ConflictResolution(
        "conflicting",
        None,
        f"unresolved disagreement between sources: {sorted(set(values))}",
        numeric,
    )


def _best(candidates: list[NormalizedFinancialObject]) -> NormalizedFinancialObject:
    return max(
        candidates,
        key=lambda c: (tier_rank(c.source.sourceType), c.dataTimestamp or "", -abs(float(c.value or 0))),
    )


def detect_conflicts(
    groups: dict[str, list[NormalizedFinancialObject]],
) -> tuple[dict[str, NormalizedFinancialObject], list[str], bool]:
    """Resolve every metric group.

    Returns (chosen_by_name, warnings, any_unresolved).
    """
    chosen: dict[str, NormalizedFinancialObject] = {}
    warnings: list[str] = []
    unresolved = False
    for name, candidates in groups.items():
        resolution = resolve_group(name, candidates)
        if resolution.status == "conflicting":
            unresolved = True
            warnings.append(f"conflict on {name}: {resolution.reason}")
            continue
        if resolution.chosen is not None:
            chosen[name] = resolution.chosen
        if resolution.status == "resolved":
            warnings.append(f"resolved conflict on {name}: {resolution.reason}")
    return chosen, warnings, unresolved


__all__ = ["ConflictResolution", "resolve_group", "detect_conflicts"]
