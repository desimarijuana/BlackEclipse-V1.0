"""Data-quality validation (Milestone 2J).

Reusable checks over the normalized objects. The point is to DISTINGUISH
`valid` / `warning` / `invalid` / `unknown` — not to flag everything unusual.

Critically: legitimate financial values must not be misclassified. Negative
earnings, zero revenue, a loss quarter, a high P/E, a negative margin — all can
be legitimate. Only structural problems (missing, wrong order, incomplete
period, currency mismatch, stale) are warnings or invalid.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from .contract import NormalizedFinancialObject, QualityStatus
from .policies import format_age, max_age_seconds

# Metrics that are legitimately allowed to be negative.
_NEGATIVE_OK = ("netIncome", "eps", "changePct", "earnings", "freeCashFlow", "operatingCashFlow", "netDebt", "margin")

# Metrics that must never be negative when present.
_NON_NEGATIVE = ("price", "volume", "marketCap", "sharesOutstanding", "revenue", "totalAssets")


def _age_seconds(ts: Optional[str], *, now: Optional[float] = None) -> Optional[float]:
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
    ref = _dt.datetime.now(_dt.timezone.utc) if now is None else _dt.datetime.fromtimestamp(
        now, _dt.timezone.utc
    )
    return (ref - parsed).total_seconds()


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


# ── D2: truncation / partial-parse detection ────────────────────────────────
# A partially parsed numeric must never be emitted as a figure. These are the
# fingerprints of a truncated scrape/parse that reached us as a "value".

_TRUNCATED_NUMERIC_RE = re.compile(
    r"""
    ^\s*[+-]?                    # optional sign
    (?:
        \d{1,3}(?:[,\s]\d{3})*   # grouped thousands, possibly incomplete
        (?:\.[\d]*)?             # optional decimal, possibly empty ("12.")
      | \.[\d]+                  # leading-dot decimal
      | \d*\.\d*                 # bare decimal point
    )
    \s*$
    """,
    re.VERBOSE,
)

# A number ending in a separator or decimal point is a truncation artefact.
_TRUNCATION_TAIL_RE = re.compile(r"[.,]\s*$")


# A whole-string numeric shape: currency/sign, digits, separators, decimal,
# optional magnitude/percent. Anything with letters (other than a magnitude
# suffix) is NOT a numeric candidate and must never be flagged.
_NUMERICISH_RE = re.compile(r"^[($€£¥]?\s*[+-]?\s*[\d][\d,\s]*(?:\.\d*)?\s*(?:%|[KMBT])?\)?$", re.IGNORECASE)


def looks_truncated(value: Any) -> bool:
    """True when a value looks like a partial/truncated numeric parse.

    Catches the observed case (`1,23` from a cut-off `1,234.56`) and trailing
    separators (`12.`, `1,`). A well-formed number or any non-numeric string
    (a name, a date, a label) is never flagged.
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    # Only a numeric-looking string can be a truncated number.
    if not _NUMERICISH_RE.match(s):
        return False
    # Trailing separator/decimal ⇒ cut off mid-number.
    if _TRUNCATION_TAIL_RE.search(s):
        return True
    # Grouped thousands: check the integer part only (drop any decimal part),
    # where every group after the first separator must be exactly 3 digits.
    if "," in s:
        core = s.strip().strip("()").lstrip("+-").strip()
        integer_part = core.split(".", 1)[0].strip()
        head, _, rest = integer_part.partition(",")
        if not head.isdigit() or len(head) > 3:
            return True
        groups = rest.split(",")
        if any(len(g) != 3 for g in groups if g):
            return True
    return False


def detect_incomplete(objects: list[NormalizedFinancialObject]) -> list[str]:
    """Return warnings for objects whose value looks truncated/incomplete (D2).

    Such objects are marked `invalid` so they are never presented as figures.
    """
    warnings: list[str] = []
    for obj in objects:
        raw = obj.raw.get("value") if isinstance(obj.raw, dict) else None
        probe = raw if raw is not None else obj.value
        if isinstance(probe, str) and looks_truncated(probe):
            obj.quality = "invalid"
            warnings.append(
                f"{obj.name}: value {probe!r} looks truncated/partially parsed — withheld"
            )
    return warnings


def _newest_timestamp(objects: list[NormalizedFinancialObject]) -> Optional[str]:
    stamps = [o.dataTimestamp for o in objects if o.dataTimestamp]
    return max(stamps) if stamps else None


def validate_objects(
    objects: list[NormalizedFinancialObject], freshness: str = "any", source_cadence_seconds: Optional[int] = None
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
    #
    # Comparators are STRICT (`>`): data exactly at the tolerance is fresh. The
    # message is unit-aware so a sub-day age is never rounded to "0 days" — the
    # old whole-day formatting made a genuine 2-hour-old quote read as
    # "0 days old (allows 0 days)", indistinguishable from an off-by-one.
    newest = _newest_timestamp(objects)
    if newest:
        age = _age_seconds(newest)
        limit = max_age_seconds(freshness)
        # A source with a KNOWN native cadence slower than the requested window
        # is "delayed", not "stale": e.g. a source that only publishes a daily
        # close can never satisfy a `realtime` request, and flagging every such
        # quote `warning` destroys the signal. Only an age beyond BOTH the
        # request window AND the source's own cadence is a staleness warning.
        effective_limit = limit
        if source_cadence_seconds is not None:
            effective_limit = max(limit, source_cadence_seconds)
        if age is not None and age > effective_limit:
            warnings.append(
                f"data is stale: newest observation is {_fmt_duration(age)} old "
                f"(freshness requirement '{freshness}' allows {_fmt_duration(limit)})"
            )
        elif age is not None and limit > 0 and age > limit and source_cadence_seconds is not None:
            # Delayed, not stale. This is an informational transformation, NOT a
            # warning — attaching it to `warnings` would stamp the result
            # `quality=warning` and make every delayed quote look suspect.
            for obj in objects:
                obj.transformations.append(
                    f"delayed source: {_fmt_duration(age)} old on a "
                    f"{_fmt_duration(source_cadence_seconds)} publishing cadence"
                )
    return objects, warnings


def _fmt_duration(seconds: float) -> str:
    """Human duration with enough precision that a sub-day age is never '0 days'."""
    return format_age(seconds)


def validate_observations(
    objects: list[NormalizedFinancialObject],
    freshness: str,
    *,
    now: Optional[float] = None,
    window_s: Optional[int] = None,
) -> tuple[list[NormalizedFinancialObject], list[str]]:
    """Flag ONE stale observation inside an otherwise fresh payload.

    The dataset-level check (`validate_objects`) answers "is this batch current?";
    a payload of 40 rows where 3 are a month old passes it. This answers "is THIS
    value current?" and is the check that stops a stale row riding a fresh batch.

    A row dated by a SNAPSHOT WRITE (`observation_source == "snapshot_write"`) is
    never described as live: for a `realtime` request its transformations gain
    "saved snapshot, not a live reading" and its quality becomes `warning`.

    `window_s`, when given, is the caller's effective freshness ceiling (the
    stricter of the data type's own window and the request's). It is used in
    place of the request freshness window so the per-observation age and the
    arbitration eligibility agree.
    """
    warnings: list[str] = []
    limit = window_s if window_s is not None else max_age_seconds(freshness)
    for obj in objects:
        stamp = obj.observation_time or obj.dataTimestamp
        age = _age_seconds(stamp, now=now)

        if getattr(obj, "observation_source", "unknown") == "snapshot_write":
            note = "saved snapshot, not a live reading"
            if note not in obj.transformations:
                obj.transformations.append(note)
            if freshness == "realtime":
                if obj.quality != "invalid":
                    obj.quality = "warning"
                warnings.append(
                    f"{obj.name}: saved snapshot, not a live reading"
                )
                continue

        if age is not None and age > limit:
            if obj.quality != "invalid":
                obj.quality = "warning"
            warnings.append(
                f"{obj.name}: observation is {format_age(age)} old "
                f"(freshness requirement '{freshness}' allows {format_age(limit)})"
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
    "validate_observations",
    "check_ordering",
    "detect_duplicates",
    "insufficient_observations",
]
