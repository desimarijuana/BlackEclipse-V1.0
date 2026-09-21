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


def validate_object(obj: NormalizedFinancialObject) -> QualityStatus:
    """Classify a single object on VALUE STRUCTURE only.

    Staleness is deliberately NOT checked per object: an old observation inside
    a time series is the whole point of history, not a defect. Dataset freshness
    is checked once, against the series' newest timestamp, in `validate_objects`.
    Unknown beats a false accusation.
    """
    if obj.value is None:
        return "warning"

    name = obj.name
    value = obj.value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value != value:  # NaN
            return "invalid"
        if name in _NON_NEGATIVE and value < 0:
            return "warning"
        # A negative value on a metric that permits it (e.g. negative earnings)
        # is VALID — that was the whole point of the check list.
        if value < 0 and name not in _NEGATIVE_OK:
            return "warning"
    return "valid"


def _newest_timestamp(objects: list[NormalizedFinancialObject]) -> Optional[str]:
    stamps = [o.dataTimestamp for o in objects if o.dataTimestamp]
    return max(stamps) if stamps else None


def validate_objects(
    objects: list[NormalizedFinancialObject], freshness: str = "any"
) -> tuple[list[NormalizedFinancialObject], list[str]]:
    """Validate in place; return (objects, warnings).

    Warnings are specific: they name the metric and WHY it is suspect. A blanket
    "possible quality issue" on every field is not a quality check — it is noise
    that trains the reader to ignore the signal.
    """
    warnings: list[str] = []
    for obj in objects:
        status = validate_object(obj)
        obj.quality = status
        if status == "warning":
            if obj.value is None:
                warnings.append(f"{obj.name}: value is missing")
            elif isinstance(obj.value, (int, float)) and obj.value < 0 and obj.name in _NON_NEGATIVE:
                warnings.append(f"{obj.name}: negative value for a metric that must be non-negative ({obj.value})")
            else:
                warnings.append(f"{obj.name}: unexpected negative value ({obj.value})")
        elif status == "invalid":
            warnings.append(f"{obj.name}: invalid value ({obj.value!r})")

    # Freshness is a DATASET property: is the most recent observation inside the
    # requested window? This is where "stale" belongs — once, not per row.
    newest = _newest_timestamp(objects)
    if newest:
        age = _age_seconds(newest)
        limit = max_age_seconds(freshness)
        if age is not None and age > limit:
            days = int(age // 86_400)
            warnings.append(
                f"data is stale: newest observation is {days} days old "
                f"(freshness requirement '{freshness}' allows {int(limit // 86_400)} days)"
            )
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
