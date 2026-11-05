"""The playbook envelope: what the loop may change, and in which direction.

The operator owns **bounds**; the loop owns **steps**. A transition is legal only
when it moves a knob toward "tighter" and stays inside the bounds. A change that
widens risk is refused here, in the runtime, regardless of what a graph asked
for — the node cannot grant itself authority.

This module is pure: it decides legality, it does not persist.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .model import DEFAULT_LIMITS, KNOBS, Playbook, _normalise_limit


class PlaybookRefused(ValueError):
    """A transition with a stable reason code (never a bare ValueError)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def _is_off(value: Any) -> bool:
    return value is None or value is False or value == 0 or value == "" or value == []


def is_tighter(name: str, old: Any, new: Any) -> bool:
    """True only when `new` reduces risk relative to `old`."""
    meta = KNOBS[name]
    direction = meta["direction"]
    if direction == "boolean":
        return bool(new) is True and bool(old) is False
    if direction == "lower":
        old_value, new_value = float(old or 0), float(new or 0)
        if new_value == 0 and old_value != 0:
            return False  # removing a limit is a loosening
        if old_value == 0:
            return new_value > 0  # enabling a limit is a tightening
        return new_value < old_value
    if direction == "higher":
        old_value, new_value = float(old or 0), float(new or 0)
        if new_value == 0 and old_value != 0:
            return False
        if old_value == 0:
            return new_value > 0
        return new_value > old_value
    if direction == "longer":
        return set(new or []) > set(old or [])
    if direction == "narrower":
        old_set, new_set = set(old or []), set(new or [])
        return bool(new_set) and new_set < old_set
    return False


def _within_bounds(name: str, value: Any, bounds: dict[str, Any]) -> bool:
    meta = KNOBS[name]
    bound = bounds.get(name)
    if bound is None:
        return False  # absent bounds = "not authorised to change this knob"
    kind = meta["kind"]
    if kind == "boolean":
        return bool(bound.get("allow", True)) is True and bool(value) is True
    if kind in ("number", "integer"):
        low = bound.get("min")
        high = bound.get("max")
        if low is not None and float(value) < float(low):
            return False
        if high is not None and float(value) > float(high):
            return False
        return True
    if kind == "list":
        cap = int(bound.get("max", 0) or 0)
        return cap <= 0 or len(value or []) <= cap
    return False


def validate_limits(
    limits: dict[str, Any],
    *,
    bounds: dict[str, Any],
    current: Optional[Playbook] = None,
    enforce_direction: bool = True,
) -> dict[str, Any]:
    """Normalise and validate a full limits snapshot against bounds + direction.

    `enforce_direction=False` is only for the FIRST version an operator creates:
    there is no prior state to tighten against, so only the bounds apply.

    Returns the normalised limits. Raises `PlaybookRefused` with one of
    `UNKNOWN_KNOB`, `OUT_OF_BOUNDS`, `NOT_A_TIGHTENING`.
    """
    unknown = [name for name in limits if name not in KNOBS]
    if unknown:
        raise PlaybookRefused("UNKNOWN_KNOB", ", ".join(sorted(unknown)))
    normalised = dict(DEFAULT_LIMITS)
    for name in KNOBS:
        if name in limits:
            normalised[name] = _normalise_limit(name, limits[name])
    # A caller may construct a Playbook with a partial limits dict; an absent
    # knob means its default, never "different from everything".
    base = {**DEFAULT_LIMITS, **((current.limits if current is not None else {}) or {})}
    for name, value in normalised.items():
        if value == base.get(name):
            continue
        if not _within_bounds(name, value, bounds):
            raise PlaybookRefused("OUT_OF_BOUNDS", name)
        if enforce_direction and not is_tighter(name, base.get(name), value):
            raise PlaybookRefused(
                "NOT_A_TIGHTENING",
                f"{name}: {base.get(name)!r} → {value!r} widens risk",
            )
    return normalised


def tightened_values(
    name: str,
    current: Any,
    bounds: dict[str, Any],
    *,
    additions: Optional[Iterable[str]] = None,
) -> list[Any]:
    """The one-step values this knob may move to, inside its bounds.

    A numeric knob moves by its declared step; a list knob appends the offending
    values named by evidence. No value is produced when the bounds do not
    authorise a change.
    """
    meta = KNOBS[name]
    bound = bounds.get(name)
    if bound is None:
        return []
    kind = meta["kind"]
    direction = meta["direction"]
    if kind == "boolean":
        return [True] if bool(bound.get("allow", True)) and not bool(current) else []
    if kind in ("number", "integer"):
        step = float(meta.get("step") or 0)
        low = float(bound.get("min", 0) or 0)
        high = float(bound.get("max", 0) or 0)
        values: list[Any] = []
        if direction == "lower":
            now = float(current or 0)
            if now == 0:
                value = max(low, 1.0 if kind == "integer" else step)
            else:
                value = now - step
            if value > 0 and value >= low and (high <= 0 or value <= high):
                if kind == "integer":
                    value = int(round(value))
                    if value < 1:
                        value = 0
                if value != current:
                    values.append(value)
        elif direction == "higher":
            now = float(current or 0)
            value = (now + step) if now > 0 else max(step, 0.25)
            if high > 0 and value <= high and value != current:
                values.append(int(value) if kind == "integer" else round(value, 6))
        return values
    if kind == "list":
        existing = list(current or [])
        cap = int(bound.get("max", 0) or 0)
        values = []
        for item in additions or ():
            clean = str(item).strip()
            if not clean or clean in existing:
                continue
            if cap > 0 and len(existing) + 1 > cap:
                break
            existing = existing + [clean]
            values.append(sorted(existing))
        return values
    return []


def candidate_limits(
    playbook: Playbook,
    name: str,
    *,
    additions: Optional[Iterable[str]] = None,
) -> list[dict[str, Any]]:
    """Every legal next snapshot after tightening one knob."""
    results: list[dict[str, Any]] = []
    for value in tightened_values(name, playbook.limits.get(name), playbook.bounds,
                                  additions=additions):
        limits = dict(playbook.limits)
        limits[name] = value
        try:
            results.append(validate_limits(limits, bounds=playbook.bounds, current=playbook))
        except PlaybookRefused:
            continue
    return results


def mutable_knobs(playbook: Playbook) -> list[str]:
    return sorted(name for name in KNOBS if name in playbook.bounds)


__all__ = [
    "PlaybookRefused",
    "candidate_limits",
    "is_tighter",
    "mutable_knobs",
    "tightened_values",
    "validate_limits",
]
