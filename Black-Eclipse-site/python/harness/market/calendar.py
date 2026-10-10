"""Trading calendar + session-aware freshness.

A quote is not "stale" merely because its timestamp is old: when the market is
closed, the last legitimate observation before the close is the freshest value
that can exist. This module makes that distinction deterministic and
dependency-free (no `zoneinfo`/`tzdata` requirement), so freshness never
mislabels a correctly frozen market.

Sessions modelled:
  * US equity/ETF (weekday sessions 09:30–16:00 America/New_York, US holidays),
  * crypto (24/7),
  * FX (Sunday 17:00 ET → Friday 17:00 ET),
  * unknown (no session awareness — callers get `unknown`).

US DST is computed from the statutory rule (second Sunday in March →
first Sunday in November) rather than the tz database, so the result is stable
on any host.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

_UTC = _dt.timezone.utc


def _parse(value: Any) -> Optional[_dt.datetime]:
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_UTC)
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_UTC)


# ── US DST (statutory rule) ──────────────────────────────────────────────────
def _nth_sunday(year: int, month: int, n: int) -> _dt.date:
    first = _dt.date(year, month, 1)
    first_sunday = first + _dt.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + _dt.timedelta(weeks=n - 1)


def _us_dst(dt: _dt.datetime) -> bool:
    """True when the US Eastern zone is on daylight time at `dt` (UTC)."""
    year = dt.year
    start = _dt.datetime.combine(_nth_sunday(year, 3, 2), _dt.time(7, 0), tzinfo=_UTC)
    end = _dt.datetime.combine(_nth_sunday(year, 11, 1), _dt.time(6, 0), tzinfo=_UTC)
    return start <= dt < end


def to_eastern(dt: _dt.datetime) -> _dt.datetime:
    return dt.astimezone(_UTC) - _dt.timedelta(hours=4 if _us_dst(dt) else 5)


# ── US market holidays ───────────────────────────────────────────────────────
def _observed(day: _dt.date) -> _dt.date:
    if day.weekday() == 5:
        return day - _dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + _dt.timedelta(days=1)
    return day


def _easter(year: int) -> _dt.date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return _dt.date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    first = _dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + _dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> _dt.date:
    if month == 12:
        first_next = _dt.date(year + 1, 1, 1)
    else:
        first_next = _dt.date(year, month + 1, 1)
    last = first_next - _dt.timedelta(days=1)
    return last - _dt.timedelta(days=(last.weekday() - weekday) % 7)


def us_holidays(year: int) -> set[_dt.date]:
    return {
        _observed(_dt.date(year, 1, 1)),                # New Year's Day
        _nth_weekday(year, 1, 0, 3),                    # MLK
        _nth_weekday(year, 2, 0, 3),                    # Washington's Birthday
        _easter(year) - _dt.timedelta(days=2),          # Good Friday
        _last_weekday(year, 5, 0),                      # Memorial Day
        _observed(_dt.date(year, 6, 19)),               # Juneteenth
        _observed(_dt.date(year, 7, 4)),                # Independence Day
        _nth_weekday(year, 9, 0, 1),                    # Labor Day
        _nth_weekday(year, 11, 3, 4),                   # Thanksgiving
        _observed(_dt.date(year, 12, 25)),              # Christmas
    }


def is_trading_day(day: _dt.date) -> bool:
    return day.weekday() < 5 and day not in us_holidays(day.year)


# ── Market kind ──────────────────────────────────────────────────────────────
def market_kind(asset_type: Optional[str], market: Optional[str] = None) -> str:
    """Classify an instrument into a calendar kind."""
    at = (asset_type or "").strip().lower()
    mk = (market or "").strip().upper()
    if at in ("crypto", "cryptocurrency") or mk == "CRYPTO":
        return "crypto"
    if at in ("fx", "forex", "currency") or mk == "FX":
        return "fx"
    if at in ("equity", "etf", "fund", "index", "option", "future", "derivative", "bond"):
        return "us_equity"
    return "unknown"


def _session_bounds_et(day: _dt.date) -> tuple[_dt.datetime, _dt.datetime]:
    def et(hour: int, minute: int) -> _dt.datetime:
        offset = 4 if _us_dst(_dt.datetime.combine(day, _dt.time(hour, minute), tzinfo=_UTC)) else 5
        return _dt.datetime.combine(day, _dt.time(hour, minute), tzinfo=_UTC) + _dt.timedelta(hours=offset)
    return et(9, 30), et(16, 0)


def is_open(kind: str, at: _dt.datetime) -> bool:
    at = at.astimezone(_UTC)
    if kind == "crypto":
        return True
    if kind == "us_equity":
        et = to_eastern(at)
        if not is_trading_day(et.date()):
            return False
        open_utc, close_utc = _session_bounds_et(et.date())
        return open_utc <= at < close_utc
    if kind == "fx":
        et = to_eastern(at)
        wd = et.weekday()
        if wd == 5:
            return False
        if wd == 6 and et.time() < _dt.time(17, 0):
            return False
        if wd == 4 and et.time() >= _dt.time(17, 0):
            return False
        return True
    return False


def last_session_close(kind: str, at: _dt.datetime) -> Optional[_dt.datetime]:
    """The most recent session close at or before `at` (UTC), for the kind."""
    if kind == "crypto":
        return None  # never closes
    at = at.astimezone(_UTC)
    if kind == "us_equity":
        et = to_eastern(at)
        day = et.date()
        for _ in range(10):
            if is_trading_day(day):
                _, close_utc = _session_bounds_et(day)
                if close_utc <= at:
                    return close_utc
            day -= _dt.timedelta(days=1)
        return None
    if kind == "fx":
        et = to_eastern(at)
        day = et.date()
        for _ in range(10):
            if day.weekday() < 5:
                close_et = _dt.datetime.combine(day, _dt.time(17, 0), tzinfo=_UTC) + _dt.timedelta(hours=4 if _us_dst(at) else 5)
                if close_et <= at:
                    return close_et
            day -= _dt.timedelta(days=1)
        return None
    return None


def next_session_open(kind: str, at: _dt.datetime) -> Optional[_dt.datetime]:
    if kind == "crypto":
        return at.astimezone(_UTC)
    at = at.astimezone(_UTC)
    if kind == "us_equity":
        et = to_eastern(at)
        day = et.date()
        for _ in range(10):
            if is_trading_day(day):
                open_utc, close_utc = _session_bounds_et(day)
                if open_utc > at:
                    return open_utc
            day += _dt.timedelta(days=1)
        return None
    return None


# ── Session-aware freshness ──────────────────────────────────────────────────
def assess(
    asset_type: Optional[str],
    timestamp: Any,
    *,
    market: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
) -> dict[str, Any]:
    """Classify a timestamp against its market session.

    Returns a dict with `kind`, `state` (`open` | `closed_recent` | `stale` |
    `unknown`), `open` (bool), `ageSeconds`, `lastClose`, `nextOpen` and a
    human `reason`. A closed-market observation at/after the last close is
    `closed_recent` (the freshest value that can exist), never `stale`.
    """
    now = (now or _dt.datetime.now(_UTC)).astimezone(_UTC)
    kind = market_kind(asset_type, market)
    ts = _parse(timestamp)
    age = (now - ts).total_seconds() if ts else None
    if kind == "unknown" or ts is None:
        return {"kind": kind, "state": "unknown", "open": False, "ageSeconds": age,
                "lastClose": None, "nextOpen": None,
                "reason": "no session model or unusable timestamp"}
    open_now = is_open(kind, now)
    last_close = last_session_close(kind, now)
    result: dict[str, Any] = {
        "kind": kind, "open": open_now, "ageSeconds": age,
        "lastClose": last_close.isoformat() if last_close else None,
        "nextOpen": (next_session_open(kind, now).isoformat() if next_session_open(kind, now) else None),
    }
    if open_now or kind == "crypto":
        result["state"] = "open"
        result["reason"] = "market is open (or 24/7)"
        return result
    # Market closed: the last legitimate observation is the prior session close.
    if last_close is not None and ts >= last_close:
        result["state"] = "closed_recent"
        result["reason"] = "market closed; observation is the latest legitimate value"
    else:
        result["state"] = "stale"
        result["reason"] = "market closed and the observation predates the last session close"
    return result


__all__ = [
    "assess",
    "is_open",
    "is_trading_day",
    "last_session_close",
    "market_kind",
    "next_session_open",
    "to_eastern",
    "us_holidays",
]
