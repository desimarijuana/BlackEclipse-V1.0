"""One canonical definition of what an advisory row needs to be scorable.

Both the scorecard and the learning gate call these helpers. The distinction the
old code conflated:

* `unscored`  — no stated horizon; nothing can ever be scored without one;
* `no_entry_price` — a horizon exists, but no stored entry price (cannot mark);
* `not_due`  — scorable in principle, but the horizon has not elapsed;
* `scorable` — entry price + stated horizon + elapsed dueAt + no outcome;
* `evaluated` — an outcome row exists.

No outcome is invented. A legacy row with no entry price is `no_entry_price`,
not a score of zero.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def entry_price(decision: Mapping[str, Any]) -> Optional[float]:
    for basis in decision.get("basis") or []:
        if isinstance(basis, Mapping) and basis.get("kind") == "entry_price":
            try:
                value = float(basis.get("ref"))
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
    return None


def classify(
    decision: Mapping[str, Any],
    *,
    has_outcome: bool,
    now: str,
) -> str:
    """The canonical state of one recommendation at `now`."""
    if has_outcome:
        return "evaluated"
    horizon = str(decision.get("horizon") or "").strip().lower()
    if not horizon or horizon == "unscored":
        return "unscored"
    if entry_price(decision) is None:
        return "no_entry_price"
    due_at = str(decision.get("dueAt") or "").strip()
    if not due_at or due_at > now:
        return "not_due"
    return "scorable"


def counts(
    decisions: list[Mapping[str, Any]],
    outcomes_by_decision: Mapping[str, Any],
    *,
    now: str,
) -> dict[str, int]:
    buckets = {
        "evaluated": 0,
        "scorable": 0,
        "no_entry_price": 0,
        "unscored": 0,
        "not_due": 0,
    }
    for decision in decisions:
        decision_id = str(decision.get("id") or "")
        state = classify(
            decision, has_outcome=decision_id in outcomes_by_decision, now=now,
        )
        buckets[state] += 1
    # Canonical aliases used by the gate/scorecard.
    buckets["needsBackfill"] = buckets["no_entry_price"] + buckets["unscored"]
    buckets["overdue"] = buckets["scorable"]
    buckets["total"] = len(decisions)
    return buckets


__all__ = ["classify", "counts", "entry_price"]
