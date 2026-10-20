"""Multi-objective frontier for RSL v2.

The hill climb ranks with one weighted utility. A Pareto frontier answers a
different, honest question: which states are not beaten on every measured
dimension? It is a read-only view over recorded states; it never accepts,
promotes or ranks a state as "best".

Missing objectives are neutral, not zero: a state without a measured cost is
neither better nor worse on cost. A state only dominates when it is no worse on
every comparable objective and strictly better on at least one.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from .utility import UtilityWeights, utility

#: objective name -> "max" or "min"
OBJECTIVES: dict[str, str] = {
    "success": "max",
    "target": "max",
    "coverage": "max",
    "cost": "min",
    "latency": "min",
}


def vector(metrics: Any, *, weights: Optional[UtilityWeights] = None) -> dict[str, Optional[float]]:
    """The comparable objective vector for one measured state."""
    components = utility(metrics, weights=weights).get("components") or {}
    return {
        name: (float(components[name]) if components.get(name) is not None else None)
        for name in OBJECTIVES
    }


def dominates(
    left: Mapping[str, Optional[float]],
    right: Mapping[str, Optional[float]],
) -> bool:
    """True when at least two objectives are comparable, `left` is no worse, and better on one."""
    comparable = [
        name for name in OBJECTIVES
        if left.get(name) is not None and right.get(name) is not None
    ]
    if len(comparable) < 2:
        return False
    better = False
    for name in comparable:
        a, b = left.get(name), right.get(name)
        direction = OBJECTIVES[name]
        if direction == "max":
            if a < b:
                return False
            if a > b:
                better = True
        else:
            if a > b:
                return False
            if a < b:
                better = True
    return better


def frontier(
    states: Iterable[Mapping[str, Any]],
    *,
    weights: Optional[UtilityWeights] = None,
) -> dict[str, Any]:
    """Return the non-dominated states plus the dominator of every other row."""
    rows: list[dict[str, Any]] = []
    for state in states:
        rows.append({
            "id": state.get("id"),
            "scope": state.get("scope"),
            "status": state.get("status"),
            "utility": state.get("utility"),
            "vector": vector(state.get("metrics") or state, weights=weights),
        })

    front: list[str] = []
    dominated: dict[str, str] = {}
    for row in rows:
        conqueror = next(
            (
                other["id"] for other in rows
                if other is not row and other.get("id") != row.get("id")
                and dominates(other["vector"], row["vector"])
            ),
            None,
        )
        if conqueror is None:
            front.append(str(row.get("id")))
        else:
            dominated[str(row.get("id"))] = str(conqueror)

    return {
        "objectives": dict(OBJECTIVES),
        "frontier": front,
        "dominated": dominated,
        "states": rows,
    }


__all__ = ["OBJECTIVES", "dominates", "frontier", "vector"]
