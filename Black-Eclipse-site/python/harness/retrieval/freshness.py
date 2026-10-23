"""Cadence-aware freshness policy (D4).

A global freshness window is wrong for periodic data: a daily Treasury series is
legitimately one business day old, a weekly series one week, a monthly series a
month plus release lag. This registry keys tolerance by
``(provider, series, native cadence)`` and consults the trading calendar already
in the harness, so a weekend or market holiday never counts as staleness.

Intraday cadences keep their tight windows; only periodic data gets business-day
tolerance.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

_DAY = 24 * 3600

# Base tolerance per native cadence. Daily/weekly/monthly are expressed in
# wall-clock seconds that already absorb the normal weekend gap; the business-day
# helper below can widen them further for a holiday.
_DEFAULT_BY_CADENCE: dict[str, float] = {
    "realtime": 60.0,
    "intraday": 15 * 60.0,
    "hourly": 3600.0,
    "daily": 3 * _DAY,       # 1 business day + a weekend
    "weekly": 9 * _DAY,      # 7 days + a weekend
    "monthly": 35 * _DAY,    # 1 calendar month + 5 business days
    "quarterly": 100 * _DAY,
    "annual": 548 * _DAY,
    "any": 10 * 365 * _DAY,
}

# Explicit route overrides: provider + series -> cadence. Unknown series fall back
# to their declared cadence, never to a global window.
POLICY_REGISTRY: dict[tuple[str, str], str] = {
    ("treasury", "DGS10"): "daily",
    ("fred", "DGS10"): "daily",
    ("fred", "CPIAUCSL"): "monthly",
    ("fred", "FEDFUNDS"): "monthly",
    ("fred", "UNRATE"): "monthly",
}


def resolve_cadence(provider: Optional[str], series: Optional[str],
                    declared: Optional[str]) -> str:
    key = ((provider or "").strip().lower(), (series or "").strip().upper())
    if key in POLICY_REGISTRY:
        return POLICY_REGISTRY[key]
    cadence = (declared or "").strip().lower()
    return cadence if cadence in _DEFAULT_BY_CADENCE else "any"


def cadence_tolerance_seconds(
    provider: Optional[str],
    series: Optional[str],
    native_cadence: Optional[str],
    *,
    now: Optional[_dt.datetime] = None,
    observation: Optional[str] = None,
) -> float:
    """Allowed age in seconds for one route's native cadence.

    When ``observation`` is supplied, a daily/weekly/monthly observation is
    measured in BUSINESS days so a weekend or holiday is not counted as
    staleness.
    """
    cadence = resolve_cadence(provider, series, native_cadence)
    base = _DEFAULT_BY_CADENCE.get(cadence, _DEFAULT_BY_CADENCE["any"])
    if cadence not in ("daily", "weekly", "monthly") or not observation:
        return base
    now = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(_dt.timezone.utc)
    obs = _parse(observation)
    if obs is None:
        return base
    business_days = _business_days_between(obs.date(), now.date())
    # One business day is the minimum tolerance; each extra business day is
    # covered explicitly (weekly/monthly cadences keep their own base).
    if cadence == "daily":
        return max(base, (max(1, business_days) + 1) * _DAY)
    return base


def _parse(value: str) -> Optional[_dt.datetime]:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = _dt.datetime.combine(_dt.date.fromisoformat(text[:10]), _dt.time())
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


def _business_days_between(start: _dt.date, end: _dt.date) -> int:
    """Count business days from ``start`` to ``end`` (holidays excluded)."""
    if end <= start:
        return 0
    try:
        from ..market.calendar import is_trading_day  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - no calendar => weekday counting
        def is_trading_day(day: _dt.date) -> bool:
            return day.weekday() < 5
    count = 0
    day = start
    while day < end:
        if is_trading_day(day):
            count += 1
        day += _dt.timedelta(days=1)
    return count


__all__ = [
    "POLICY_REGISTRY",
    "cadence_tolerance_seconds",
    "resolve_cadence",
]
