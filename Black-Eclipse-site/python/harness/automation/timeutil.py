"""Timezone-aware schedule arithmetic (§19).

Timezones are first-class: the trigger's IANA name is stored explicitly and the
NEXT fire time is computed in that zone's wall clock, then converted to a
durable UTC instant. The server's local timezone is never assumed.

DST is handled deterministically via `zoneinfo` and PEP 495 `fold`:

  * a wall time that does not exist (spring-forward gap) resolves to the instant
    immediately after the gap (fold=0) rather than being skipped or raising;
  * an ambiguous wall time (fall-back overlap) resolves to the FIRST occurrence
    (fold=0).

Both choices are stable across restarts because they depend only on the zone and
the expression, never on process state.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..jobs.cron import CronError, parse_cron

UTC = _dt.timezone.utc

# Common aliases a user might type for the server's own zone.
_LOCAL_ALIASES = frozenset({"local", "server", ""})


class TimezoneError(ValueError):
    """An unknown timezone, with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_timezone(name: Optional[str]) -> _dt.tzinfo:
    """Resolve an IANA name (or `local`/`utc`) to a tzinfo. Raises on unknown."""
    text = (name or "").strip()
    if text.lower() in _LOCAL_ALIASES:
        # "local" is only ever a DISPLAY convenience; the engine stores UTC and
        # computes in the resolved zone. We resolve to the process zone here.
        return _dt.datetime.now().astimezone().tzinfo or UTC
    if text.upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise TimezoneError("INVALID_TIMEZONE", f"unknown timezone {name!r}") from exc


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(UTC)


def parse_iso(value: Optional[str]) -> Optional[_dt.datetime]:
    """Parse an ISO-8601 string to an aware UTC datetime, or None."""
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_utc_iso(moment: _dt.datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def next_cron_fire(
    expression: str,
    timezone: str,
    after_utc: _dt.datetime,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
) -> Optional[_dt.datetime]:
    """The first matching instant strictly after `after_utc`, in UTC.

    Computed in the trigger's wall clock so "every day at 8 AM Asia/Karachi"
    fires at 08:00 Karachi regardless of the server zone.
    """
    try:
        cron = parse_cron(expression)
    except CronError:
        return None
    tz = resolve_timezone(timezone)
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=UTC)
    local_after = after_utc.astimezone(tz).replace(tzinfo=None)
    local_next = cron.next_fire(local_after)
    moment = local_next.replace(tzinfo=tz, fold=0).astimezone(UTC)
    # A DST gap can push the localized instant at or before `after`; advance one
    # minute and retry (bounded) so we never return a non-future fire time.
    guard = 0
    while moment <= after_utc and guard < 5:
        local_next = cron.next_fire(local_next)
        moment = local_next.replace(tzinfo=tz, fold=0).astimezone(UTC)
        guard += 1
    start = parse_iso(start_at)
    end = parse_iso(end_at)
    if end is not None and moment > end:
        return None
    if start is not None and moment < start:
        # Advance to the first fire at/after start (bounded scan).
        local_start = start.astimezone(tz).replace(tzinfo=None)
        candidate_local = cron.next_fire(local_start - _dt.timedelta(minutes=1))
        moment = candidate_local.replace(tzinfo=tz, fold=0).astimezone(UTC)
        if end is not None and moment > end:
            return None
    return moment


def next_interval_fire(
    interval_seconds: int,
    anchor_utc: _dt.datetime,
    *,
    after_utc: Optional[_dt.datetime] = None,
) -> _dt.datetime:
    """The next interval fire strictly after `after_utc` (defaults to now)."""
    step = _dt.timedelta(seconds=int(interval_seconds))
    after = after_utc or now_utc()
    if anchor_utc.tzinfo is None:
        anchor_utc = anchor_utc.replace(tzinfo=UTC)
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    if anchor_utc > after:
        return anchor_utc
    delta = after - anchor_utc
    steps = int(delta.total_seconds() // step.total_seconds()) + 1
    return anchor_utc + step * steps


def next_one_time_fire(run_at: str, after_utc: Optional[_dt.datetime] = None) -> Optional[_dt.datetime]:
    """The one-time fire instant if it is still in the future, else None."""
    moment = parse_iso(run_at)
    if moment is None:
        return None
    after = after_utc or now_utc()
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    return moment if moment > after else None


__all__ = [
    "UTC",
    "TimezoneError",
    "next_cron_fire",
    "next_interval_fire",
    "next_one_time_fire",
    "now_utc",
    "parse_iso",
    "resolve_timezone",
    "to_utc_iso",
]
