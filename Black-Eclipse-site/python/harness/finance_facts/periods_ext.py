"""Universal period model (Universal Financial Data Accuracy, §3).

Extends `research/periods.py` (which parses annual/quarter/date/range) with the
period TYPES the analysis must distinguish:

    current intraday daily mtd qtd ytd quarter half nine_month fy cy ttm ntm
    annualized reported estimated restated pro_forma

FY2025 EPS is NOT TTM EPS; H1 2026 earnings is NOT FY2026 earnings. The period
type is the guard against combining them. Duration helpers are pure arithmetic on
ISO dates.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

PeriodType = str

# The closed period-type vocabulary. A new type is a new entry.
PERIOD_TYPES: tuple[str, ...] = (
    "current", "intraday", "daily", "mtd", "qtd", "ytd",
    "quarter", "half", "nine_month", "fy", "cy",
    "ttm", "ntm",
    "annualized", "reported", "estimated", "restated", "pro_forma",
)

# Duration in months for the flow periods that have one (TTM = 12, H1 = 6, 9M = 9,
# quarter = 3). A point-in-time fact has no duration.
_MONTHS: dict[str, int] = {
    "quarter": 3, "half": 6, "nine_month": 9, "fy": 12, "cy": 12, "ttm": 12, "ntm": 12,
}

# Trailing-window period types: they END at their period_end and cover _MONTHS
# back. Point-in-time / open-ended types are not windows.
_TRAILING = {"quarter", "half", "nine_month", "fy", "cy", "ttm", "ntm"}


def months_for(period_type: str) -> Optional[int]:
    return _MONTHS.get(period_type)


def is_trailing(period_type: str) -> bool:
    return period_type in _TRAILING


def parse_iso(date: Optional[str]) -> Optional[_dt.date]:
    if not date:
        return None
    text = str(date).strip()
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _shift_months(d: _dt.date, months: int) -> _dt.date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return _dt.date(year, month, day)


def window_for(period_type: str, period_end: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(start, end) ISO dates for a trailing period, or (None, end) when unknown.

    TTM ending 2026-06-30 covers 2025-07-01..2026-06-30. Used to test overlap and
    to sum the right quarters; never to fabricate a start when the end is unknown.
    """
    end = parse_iso(period_end)
    months = months_for(period_type)
    if end is None or months is None:
        return None, (period_end or None)
    start = _shift_months(end, -months) + _dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


# ── Fiscal labels (`FY2025`, `Q2 2026`, `H1 2026`, `9M 2025`, `CY2024`, `TTM`) ──

_FY_RE = re.compile(r"\bFY\s*((?:19|20)\d{2})\b", re.IGNORECASE)
_CY_RE = re.compile(r"\bCY\s*((?:19|20)\d{2})\b", re.IGNORECASE)
_QUARTER_RE = re.compile(r"\b(?:Q([1-4])\s*(?:FY)?\s*((?:19|20)\d{2})|((?:19|20)\d{2})\s*[-/ ]?Q([1-4]))\b", re.IGNORECASE)
_HALF_RE = re.compile(r"\bH([12])\s*((?:19|20)\d{2})\b", re.IGNORECASE)
_NINE_RE = re.compile(r"\b(?:9M|9\s*M|nine[- ]month)\s*((?:19|20)\d{2})\b", re.IGNORECASE)
_TTM_RE = re.compile(r"\bTTM\b", re.IGNORECASE)
_NTM_RE = re.compile(r"\bNTM\b", re.IGNORECASE)


def parse_period_type(label: Optional[str]) -> Optional[str]:
    """Classify a fiscal label into a period TYPE, or None when unrecognised."""
    if not label:
        return None
    text = str(label)
    if _TTM_RE.search(text):
        return "ttm"
    if _NTM_RE.search(text):
        return "ntm"
    if _FY_RE.search(text):
        return "fy"
    if _CY_RE.search(text):
        return "cy"
    if _HALF_RE.search(text):
        return "half"
    if _NINE_RE.search(text):
        return "nine_month"
    if _QUARTER_RE.search(text):
        return "quarter"
    return None


def periods_comparable(a_type: str, b_type: str) -> bool:
    """May two facts of these period types be compared WITHOUT transformation?

    Only an exact type match is directly comparable. Everything else (FY vs TTM,
    H1 vs FY, quarter vs nine_month) needs an explicit transformation and is
    refused by default — the §3 rule.
    """
    return a_type == b_type


__all__ = [
    "PERIOD_TYPES",
    "PeriodType",
    "is_trailing",
    "months_for",
    "parse_iso",
    "parse_period_type",
    "periods_comparable",
    "window_for",
]
