"""Data-quality validation (Milestone 2J).

Reusable checks over the normalized objects. The point is to DISTINGUISH
`valid` / `warning` / `invalid` / `unknown` — not to flag everything unusual.

Critically: legitimate financial values must not be misclassified. Negative
earnings, zero revenue, a loss quarter, a high P/E, a negative margin — all can
be legitimate. Only structural problems (missing, wrong order, incomplete
period, currency mismatch, stale) are warnings or invalid.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .contract import NormalizedFinancialObject, QualityStatus
from .policies import max_age_seconds

# Metrics that are legitimately allowed to be negative.
_NEGATIVE_OK = ("netIncome", "eps", "changePct", "earnings", "freeCashFlow", "operatingCashFlow", "netDebt", "margin")

# Metrics that must never be negative when present.
_NON_NEGATIVE = ("price", "volume", "marketCap", "sharesOutstanding", "revenue", "totalAssets")


def _age_seconds(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    import datetime as _dt

    text = ts.strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return ( _dt.datetime.now(_dt.timezone.utc) - parsed ).total_seconds()


def validate_object(obj: NormalizedFinancialObject, freshness: str = "any") -> QualityStatus:
    """Classify a single object. Unknown beats a false accusation."""
    if obj.value is None:
        return "warning"

    name = obj.name
    value = obj.value

    # Numeric structural checks only apply to numbers.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value != value:  # NaN
            return "invalid"
        if name in _NON_NEGATIVE and value < 0:
            return "warning"
        # A negative value on a metric that permits it (e.g. negative earnings)
        # is VALID — that was the whole point of the check list.
        if value < 0 and name not in _NEGATIVE_OK:
            # Still not invalid: an unexpected negative is a warning to surface.
            return "warning"

    age = _age_seconds(obj.dataTimestamp)
    if age is not None and age > max_age_seconds(freshness):
        return "warning"
    return "valid"


def validate_objects(
    objects: list[NormalizedFinancialObject], freshness: str = "any"
) -> tuple[list[NormalizedFinancialObject], list[str]]:
    """Validate in place; return (objects, warnings)."""
    warnings: list[str] = []
    for obj in objects:
        status = validate_object(obj, freshness)
        obj.quality = status
        if status == "warning":
            warnings.append(f"{obj.name}: possible quality issue (value={obj.value!r})")
        elif status == "invalid":
            warnings.append(f"{obj.name}: invalid value ({obj.value!r})")
    return objects, warnings


def check_ordering(dated: list[dict[str, Any]], date_key: str = "date") -> list[str]:
    """Detect out-of-order date series (a real data-quality bug)."""
    dates = [row.get(date_key) for row in dated if isinstance(row, dict)]
    dates = [d for d in dates if d]
    for prev, curr in zip(dates, dates[1:]):
        if str(prev) > str(curr):
            return [f"series is not in ascending date order at {curr!r}"]
    return []


def detect_duplicates(dated: list[dict[str, Any]], date_key: str = "date") -> list[str]:
    seen: set[Any] = set()
    dupes: list[str] = []
    for row in dated:
        if not isinstance(row, dict):
            continue
        key = row.get(date_key)
        if key is None:
            continue
        if key in seen:
            dupes.append(str(key))
        seen.add(key)
    return [f"duplicate record(s) for {', '.join(sorted(set(dupes)))}"] if dupes else []


def insufficient_observations(count: int, minimum: int) -> Optional[str]:
    if count < minimum:
        return f"insufficient observations: {count} < required {minimum}"
    return None


__all__ = [
    "validate_object",
    "validate_objects",
    "check_ordering",
    "detect_duplicates",
    "insufficient_observations",
]
