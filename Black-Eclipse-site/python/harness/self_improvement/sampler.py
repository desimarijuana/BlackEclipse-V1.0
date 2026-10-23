"""Deterministic archive sampling for the bounded hill climb.

The greedy climb always proposed from the current champion, which discards the
"stepping stone" states that make open-ended search work. This module chooses an
exploration parent from a pool of measured states.

It is a pure function of the pool, a seeded `random.Random` and the mode, so the
same inputs always produce the same parent. It never changes acceptance: the
archive decides *where to look*, `utility.acceptance` still decides *what may
replace the champion*.

Modes:
- `uniform`  — every state equally likely (a diversity floor).
- `weighted` — softmax over utility, metaproductivity and novelty.
- `uct`      — the same score plus an exploration bonus for under-sampled states.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Optional, Sequence

MODES: tuple[str, ...] = ("uniform", "weighted", "uct")

# The relative pull of each signal. Utility dominates; archive-only signals
# (CMP, novelty, exploration) steer but never outvote a measured score.
UTILITY_WEIGHT = 0.55
CMP_WEIGHT = 0.30
NOVELTY_WEIGHT = 0.15
EXPLORATION_WEIGHT = 0.50


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def state_utility(state: Mapping[str, Any]) -> Optional[float]:
    """The measured ranking signal for a state, or None when unmeasured."""
    direct = _number(state.get("utility"))
    if direct is not None:
        return direct
    metrics = state.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    aggregates = metrics.get("aggregates")
    if isinstance(aggregates, Mapping):
        return _number(aggregates.get("task_success"))
    return _number(metrics.get("task_success"))


def _visits(state: Mapping[str, Any]) -> int:
    try:
        return max(0, int(state.get("visitCount") or 0))
    except (TypeError, ValueError):
        return 0


def _ops(state: Mapping[str, Any]) -> set[str]:
    raw = state.get("ops") or state.get("proposedOps") or ()
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item) for item in raw if str(item)}


def novelty(state: Mapping[str, Any], pool: Sequence[Mapping[str, Any]]) -> float:
    """How different a state is from the pool, in [0, 1].

    A new snapshot identity is maximally novel. A repeated identity is novel
    only in the operations it does not share with the earlier occurrence. The
    archived row itself is excluded from the comparison.
    """
    digest = str(state.get("snapshotDigest") or "")
    if not digest:
        return 0.0
    same = [
        other for other in pool
        if str(other.get("snapshotDigest") or "") == digest
        and str(other.get("id") or "") != str(state.get("id") or "")
    ]
    if not same:
        return 1.0
    ops = _ops(state)
    if not ops:
        return 0.0
    shared: set[str] = set()
    for other in same:
        shared |= _ops(other)
    return len(ops - shared) / len(ops)


def _normalised(values: Sequence[Optional[float]]) -> list[float]:
    present = [value for value in values if value is not None]
    if not present:
        return [0.0 for _ in values]
    low, high = min(present), max(present)
    if high <= low:
        return [0.5 if value is not None else 0.0 for value in values]
    return [
        0.0 if value is None else (value - low) / (high - low)
        for value in values
    ]


def scores(
    states: Sequence[Mapping[str, Any]],
    *,
    mode: str = "weighted",
) -> list[float]:
    """One transparent score per state; exposed for the operator digest."""
    if not states:
        return []
    total = len(states)
    utilities = _normalised([state_utility(state) for state in states])
    cmps = _normalised([_number(state.get("cmpScore")) for state in states])
    output: list[float] = []
    for index, state in enumerate(states):
        recorded = _number(state.get("novelty"))
        value = novelty(state, states) if recorded is None else float(recorded)
        score = (
            UTILITY_WEIGHT * utilities[index]
            + CMP_WEIGHT * cmps[index]
            + NOVELTY_WEIGHT * value
        )
        if mode == "uct":
            visits = _visits(state)
            score += EXPLORATION_WEIGHT * math.sqrt(
                math.log(total + 1.0) / (visits + 1.0)
            )
        output.append(score)
    return output


def _softmax_pick(
    states: Sequence[Mapping[str, Any]],
    weights: Sequence[float],
    rng: random.Random,
    temperature: float,
) -> Mapping[str, Any]:
    if temperature <= 0:
        best = max(range(len(states)), key=lambda i: (weights[i], -i))
        return states[best]
    peak = max(weights) if weights else 0.0
    expo = [math.exp(min(50.0, (weight - peak) / temperature)) for weight in weights]
    total = sum(expo)
    if total <= 0:
        return states[rng.randrange(len(states))]
    target = rng.random() * total
    running = 0.0
    for state, weight in zip(states, expo):
        running += weight
        if target <= running:
            return state
    return states[-1]


def sample(
    states: Sequence[Mapping[str, Any]],
    *,
    rng: Optional[random.Random] = None,
    mode: str = "weighted",
    temperature: float = 1.0,
    exclude_digests: Sequence[str] = (),
) -> Optional[dict[str, Any]]:
    """Choose one exploration parent, or None for an empty pool.

    `exclude_digests` drops already-evaluated identities (a tabu list). The
    caller owns persistence and the visit counter.
    """
    generator = rng or random.Random(0)
    chosen_mode = mode if mode in MODES else "weighted"
    excluded = {str(item) for item in exclude_digests if str(item)}
    pool = [
        dict(state) for state in states
        if str(state.get("snapshotDigest") or "") not in excluded
    ]
    if not pool:
        return None
    if chosen_mode == "uniform":
        return pool[generator.randrange(len(pool))]
    weights = scores(pool, mode=chosen_mode)
    picked = _softmax_pick(pool, weights, generator, float(temperature))
    return dict(picked)


__all__ = [
    "MODES",
    "novelty",
    "sample",
    "scores",
    "state_utility",
]
