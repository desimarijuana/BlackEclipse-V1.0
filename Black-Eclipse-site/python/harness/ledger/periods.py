"""Fiscal calendar and period control.

Phase 1 uses **monthly periods**. That is a deliberate, documented scope: the
close is month-end, a period is one calendar month, and the fiscal year starts on
`fiscal_year_start_month`. Quarterly/annual reporting is a *view over* monthly
periods (see `statements.py`), not a second calendar.

Period status is the lock:
  * `OPEN`   — postings accepted.
  * `CLOSED` — postings refused; an operator may reopen it.
  * `LOCKED` — postings refused; permanently closed (no reopen).

Nothing here reads a wall clock except `today()`; every other function takes the
date it should reason about, so a test (and a replay) is deterministic.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from .errors import (
    INVALID_DATE,
    PERIOD_CLOSED,
    PERIOD_LOCKED,
    PERIOD_NOT_CLOSED,
    PERIOD_NOT_FOUND,
    LedgerError,
)
from .models import Period

_ISO = "%Y-%m-%d"


def today() -> date:
    return date.today()


def parse_date(value: object, *, field: str = "date") -> date:
    """Accept an ISO date/datetime string or a `date`; refuse anything else."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise LedgerError(INVALID_DATE, f"`{field}` is required (YYYY-MM-DD)", {"field": field})
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise LedgerError(
            INVALID_DATE,
            f"`{field}` must be an ISO date (YYYY-MM-DD); got {value!r}",
            {"field": field, "value": str(value)},
        ) from exc


def iso(value: date) -> str:
    return value.strftime(_ISO)


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def fiscal_position(fiscal_year_start_month: int, when: date) -> tuple[int, int]:
    """`(fiscal_year, period_no)` for a date under a monthly fiscal calendar."""
    start = _clamp_start_month(fiscal_year_start_month)
    offset = (when.month - start) % 12
    fiscal_year = when.year if when.month >= start else when.year - 1
    return fiscal_year, offset + 1


def period_bounds(fiscal_year_start_month: int, fiscal_year: int, period_no: int) -> tuple[date, date]:
    start = _clamp_start_month(fiscal_year_start_month)
    if not 1 <= int(period_no) <= 12:
        raise LedgerError(INVALID_DATE, f"period_no must be 1-12; got {period_no}", {"period": period_no})
    year, month = _add_months(fiscal_year, start, int(period_no) - 1)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def period_bounds_for(fiscal_year_start_month: int, when: date) -> tuple[int, int, date, date]:
    fiscal_year, period_no = fiscal_position(fiscal_year_start_month, when)
    start, end = period_bounds(fiscal_year_start_month, fiscal_year, period_no)
    return fiscal_year, period_no, start, end


def _clamp_start_month(value: object) -> int:
    try:
        month = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise LedgerError(
            INVALID_DATE, f"fiscal_year_start_month must be 1-12; got {value!r}",
            {"value": str(value)},
        ) from exc
    if not 1 <= month <= 12:
        raise LedgerError(
            INVALID_DATE, f"fiscal_year_start_month must be 1-12; got {month}", {"value": month}
        )
    return month


def period_id(ledger_id: str, fiscal_year: int, period_no: int) -> str:
    return f"{ledger_id}:{int(fiscal_year):04d}-{int(period_no):02d}"


def build_period(ledger_id: str, fiscal_year_start_month: int,
                 fiscal_year: int, period_no: int) -> Period:
    start, end = period_bounds(fiscal_year_start_month, fiscal_year, period_no)
    return Period(
        id=period_id(ledger_id, fiscal_year, period_no),
        ledger_id=ledger_id,
        fiscal_year=int(fiscal_year),
        period_no=int(period_no),
        start_date=iso(start),
        end_date=iso(end),
        status="OPEN",
    )


def require_open(period: Optional[Period], *, when: date) -> Period:
    """A posting may only land in an OPEN period."""
    if period is None:
        raise LedgerError(
            PERIOD_NOT_FOUND,
            f"no fiscal period exists for {iso(when)}",
            {"date": iso(when)},
        )
    if period.status == "LOCKED":
        raise LedgerError(
            PERIOD_LOCKED,
            f"period {period.start_date}..{period.end_date} is LOCKED; postings are refused",
            {"periodId": period.id, "status": period.status},
        )
    if period.status != "OPEN":
        raise LedgerError(
            PERIOD_CLOSED,
            f"period {period.start_date}..{period.end_date} is {period.status}; "
            "reopen it before posting",
            {"periodId": period.id, "status": period.status},
        )
    return period


def require_closed(period: Optional[Period]) -> Period:
    if period is None:
        raise LedgerError(PERIOD_NOT_FOUND, "period not found", {})
    if period.status == "OPEN":
        raise LedgerError(
            PERIOD_NOT_CLOSED,
            f"period {period.start_date}..{period.end_date} is still OPEN",
            {"periodId": period.id},
        )
    return period


def label(period: Period) -> str:
    return f"{period.start_date}..{period.end_date}"


__all__ = [
    "build_period",
    "fiscal_position",
    "iso",
    "label",
    "parse_date",
    "period_bounds",
    "period_bounds_for",
    "period_id",
    "require_closed",
    "require_open",
    "today",
]
