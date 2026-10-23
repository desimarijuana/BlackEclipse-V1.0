"""Metaproductivity: how much a state's descendants actually improved.

A state can be a weak performer and still be the best place to explore from.
The Darwin Gödel Machine keeps such states in an archive; the Huxley-Gödel
Machine showed that ranking a state by its own benchmark score is not the same
as ranking it by its *potential* for further improvement.

This module estimates that potential from the recorded descendants:

    lift = mean(utility(descendant) - utility(state))

with a depth discount (a child is closer evidence than a grandchild). It is a
sampling signal only. It never enters `utility.acceptance`, so a high-lift state
cannot promote itself or its children.

Cold start is explicit: a state with too few measured descendants reports
`coldStart: true` and a `lift` that callers must not treat as a measured zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from .sampler import state_utility

ChildrenFn = Callable[[str], Sequence[Mapping[str, Any]]]

MAX_DESCENDANTS = 50


@dataclass(frozen=True)
class CMPConfig:
    """Bounded settings for the descendant-lift estimate."""

    horizon: int = 3
    discount: float = 0.8
    min_samples: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizon", max(1, min(6, int(self.horizon))))
        object.__setattr__(
            self, "discount", max(0.0, min(1.0, float(self.discount)))
        )
        object.__setattr__(
            self, "min_samples", max(1, min(50, int(self.min_samples)))
        )


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def collect_descendants(
    state_id: str,
    children: ChildrenFn,
    *,
    horizon: int = 3,
) -> list[tuple[int, dict[str, Any]]]:
    """Breadth-first descendants up to `horizon`, with their depth."""
    if not state_id:
        return []
    limit = max(1, min(6, int(horizon)))
    seen: set[str] = {state_id}
    frontier: list[tuple[str, int]] = [(state_id, 0)]
    found: list[tuple[int, dict[str, Any]]] = []
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= limit:
            continue
        try:
            rows = children(current) or []
        except Exception:  # noqa: BLE001 - an unreadable child is no evidence
            rows = []
        for row in rows:
            data = dict(row)
            child_id = str(data.get("id") or "")
            if not child_id or child_id in seen:
                continue
            seen.add(child_id)
            found.append((depth + 1, data))
            frontier.append((child_id, depth + 1))
    return found


def descendant_lift(
    state: Mapping[str, Any],
    *,
    children: ChildrenFn,
    config: Optional[CMPConfig] = None,
) -> dict[str, Any]:
    """Estimate one state's metaproductivity from its measured descendants.

    `lift` is the discounted mean of `utility(descendant) - utility(state)`.
    A state with no usable descendants is `coldStart` and carries `lift: None`;
    an unmeasured state is also cold start, because a missing number is not
    evidence of potential.
    """
    settings = config or CMPConfig()
    base = state_utility(state)
    rows = collect_descendants(
        str(state.get("id") or ""), children, horizon=settings.horizon,
    )
    points: list[dict[str, Any]] = []
    weights: list[float] = []
    if base is not None:
        for depth, child in rows:
            utility = state_utility(child)
            if utility is None:
                continue
            weight = settings.discount ** depth
            points.append({
                "id": child.get("id"),
                "depth": depth,
                "utility": utility,
                "lift": round(utility - base, 6),
                "weight": round(weight, 6),
            })
            weights.append(weight)

    samples = len(points)
    cold_start = base is None or samples < settings.min_samples
    lift: Optional[float] = None
    std: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    if samples:
        total = sum(weights)
        lift = round(
            sum(point["lift"] * point["weight"] for point in points) / total, 6,
        )
        if samples > 1:
            variance = (
                sum(
                    point["weight"] * (point["lift"] - lift) ** 2
                    for point in points
                )
                / total
            )
            std = round(math.sqrt(max(0.0, variance)), 6)
            # An approximate normal interval, labelled as such in the report;
            # it is a sampling aid, never an acceptance test.
            margin = 1.96 * std / math.sqrt(samples)
            ci_low = round(lift - margin, 6)
            ci_high = round(lift + margin, 6)
    return {
        "stateId": state.get("id"),
        "lift": lift,
        "samples": samples,
        "coldStart": bool(cold_start),
        "std": std,
        "ciLow": ci_low,
        "ciHigh": ci_high,
        "horizon": settings.horizon,
        "discount": settings.discount,
        "descendants": points[:MAX_DESCENDANTS],
    }


def metaproductivity(
    state: Mapping[str, Any],
    *,
    children: ChildrenFn,
    config: Optional[CMPConfig] = None,
) -> dict[str, Any]:
    """Alias for the estimate, named for the property it estimates."""
    return descendant_lift(state, children=children, config=config)


__all__ = [
    "CMPConfig",
    "ChildrenFn",
    "MAX_DESCENDANTS",
    "collect_descendants",
    "descendant_lift",
    "metaproductivity",
]
