"""L3 strategic learning (round 4, W11 first slice) — the route that WORKED.

The learning layers (roadmap §W11): L1 episodic records what happened
(`mistakes.py`), L2 procedural grows reusable skills (`skills/learning.py`),
and L3 strategic improves the CHOICE — which route/strategy to prefer for a
recurring failure situation. This module is the L3 layer: it reads the EXISTING
durable recovery records (`RecoveryIncident.signature` + `RecoveryAttempt`
strategy/outcome) and derives a preference only when the evidence supports it —
no new store, no new loop, never a guess.

The measured statement is the preference's own success rate over its
observations; a situation without enough evidence yields None (an unmeasured
choice stays unmade).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: Success outcomes recorded on a recovery attempt.
_SUCCESS_OUTCOMES = frozenset({"succeeded", "resolved"})


@dataclass(frozen=True)
class StrategyPreference:
    """The route the ledger supports for one failure signature."""

    failure_signature: str
    strategy: str
    observations: int
    succeeded: int
    success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "failureSignature": self.failure_signature,
            "strategy": self.strategy,
            "observations": self.observations,
            "succeeded": self.succeeded,
            "successRate": round(self.success_rate, 4),
        }


def strategy_stats(
    incidents: list[dict[str, Any]],
    attempts_by_incident: dict[str, list[dict[str, Any]]],
    *,
    failure_signature: Optional[str] = None,
) -> dict[str, dict[str, dict[str, int]]]:
    """`signature → strategy → {attempts, succeeded}` from the durable records.

    Only attempts that actually named a strategy count; an attempt without an
    outcome is an observation that neither succeeded nor failed.
    """
    stats: dict[str, dict[str, dict[str, int]]] = {}
    for incident in incidents:
        signature = str(incident.get("signature") or "")
        if failure_signature is not None and signature != failure_signature:
            continue
        if not signature:
            continue
        bucket = stats.setdefault(signature, {})
        for attempt in attempts_by_incident.get(str(incident.get("id")), []):
            strategy = str(attempt.get("strategy") or "")
            if not strategy:
                continue
            row = bucket.setdefault(strategy, {"attempts": 0, "succeeded": 0})
            row["attempts"] += 1
            if str(attempt.get("outcome") or "") in _SUCCESS_OUTCOMES:
                row["succeeded"] += 1
    return stats


def preferred_strategy(
    stats_for_signature: dict[str, dict[str, int]],
    *,
    failure_signature: str = "",
    min_observations: int = 2,
    min_success_rate: float = 0.6,
) -> Optional[StrategyPreference]:
    """The best-supported strategy, or None when the evidence is too thin.

    Deterministic tie-break: success rate, then successes, then observations,
    then the strategy name — so the same ledger always yields the same choice.
    """
    eligible: list[tuple[float, int, int, str]] = []
    for strategy, row in (stats_for_signature or {}).items():
        observations = int(row.get("attempts") or 0)
        succeeded = int(row.get("succeeded") or 0)
        if observations < max(1, int(min_observations)):
            continue
        rate = succeeded / observations
        if rate < float(min_success_rate):
            continue
        eligible.append((rate, succeeded, observations, str(strategy)))
    if not eligible:
        return None
    rate, succeeded, observations, strategy = max(eligible)
    return StrategyPreference(
        failure_signature=failure_signature, strategy=strategy,
        observations=observations, succeeded=succeeded, success_rate=rate,
    )


def preference_from_store(
    store: Any,
    failure_signature: str,
    *,
    incident_limit: int = 100,
    min_observations: int = 2,
    min_success_rate: float = 0.6,
) -> Optional[StrategyPreference]:
    """The L3 preference for one signature, read from the recovery store."""
    if not failure_signature:
        return None
    try:
        incidents = [
            incident for incident in store.list_incidents(limit=incident_limit)
            if str(incident.get("signature") or "") == failure_signature
        ]
    except Exception:  # noqa: BLE001 - an unreadable ledger yields no preference
        return None
    if not incidents:
        return None
    attempts_by_incident = {
        str(incident.get("id")): store.list_attempts(incident["id"])
        for incident in incidents
    }
    stats = strategy_stats(
        incidents, attempts_by_incident, failure_signature=failure_signature,
    )
    return preferred_strategy(
        stats.get(failure_signature, {}),
        failure_signature=failure_signature,
        min_observations=min_observations, min_success_rate=min_success_rate,
    )


__all__ = [
    "StrategyPreference",
    "preference_from_store",
    "preferred_strategy",
    "strategy_stats",
]
