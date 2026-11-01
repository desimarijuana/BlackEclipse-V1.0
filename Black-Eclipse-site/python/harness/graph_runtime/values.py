"""Shared value helpers for graph nodes.

One dotted-path rule, one numeric coercion rule and one join-key identity rule
serve every node that reads into a payload (the Template node and the tabular
transforms). Keeping them here is what stops `a.b` meaning different things in
`transform.select` and `transform.join`.

Nothing in this module has side effects or state: it is pure data plumbing.
"""

from __future__ import annotations

import json
import math
from typing import Any


class _MissingType:
    """Sentinel for "this path does not exist", distinct from a null value."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"

    def __bool__(self) -> bool:
        return False


MISSING = _MissingType()


def resolve_path(value: Any, path: str) -> Any:
    """Resolve a dotted path through objects and array indices.

    Returns `MISSING` when a segment is absent, so callers can tell a missing
    column from a column whose value is legitimately null.
    """
    current = value
    for part in [segment for segment in str(path).split(".") if segment]:
        if isinstance(current, dict):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(part)
            except ValueError:
                return MISSING
            if index < 0 or index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def coerce_number(value: Any) -> float | None:
    """A finite float, or None when the value is not unambiguously a number.

    Booleans are deliberately excluded (``True`` is not a price) and non-finite
    floats are rejected rather than poisoning a sort or an aggregate.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def key_part(value: Any, *, case_insensitive: bool = False) -> tuple[str, Any]:
    """A hashable identity part for a join key.

    Numbers, numeric strings and ints/floats compare equal, so a provider that
    sends ``"123.0"`` matches a row that sends ``123``. Text compares exactly
    unless `case_insensitive` is on, and null only matches null.
    """
    if value is None or value is MISSING:
        return ("null", None)
    if isinstance(value, bool):
        return ("number", 1.0 if value else 0.0)
    number = coerce_number(value)
    if number is not None:
        return ("number", number)
    if isinstance(value, str):
        text = value.strip()
        return ("string", text.casefold() if case_insensitive else text)
    return ("json", json.dumps(value, sort_keys=True, default=str))


__all__ = ["MISSING", "resolve_path", "coerce_number", "key_part"]
