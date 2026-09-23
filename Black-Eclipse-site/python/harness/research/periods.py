"""Canonical financial-period parsing and matching (Phase 4 hardening).

Replaces the previous substring-of-digits test, which let an annual leg match an
arbitrary quarter or a malformed/adjacent year (e.g. `FY2024` matched `20244` or
`2019-Q4`). Every period is parsed into an explicit granularity — annual,
quarter, date, or range — and matching only succeeds when the granularities are
compatible:

  * annual  FY2024  matches annual FY2024, or a date/range inside 2024.
  * quarter FY2024-Q1 matches the same quarter, or a date inside that quarter.
  * date    matches the exact date, or a range containing it.
  * range   matches an overlapping range or a date inside it.

Cross-granularity matches (an annual leg vs a quarter row) are refused, and a
missing candidate period never matches. Legitimate aliases (`FY2024` vs `2024`,
`Q1 2024` vs `FY2024-Q1`) are preserved and covered by tests.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Literal, Optional

Granularity = Literal["annual", "quarter", "date", "range"]


@dataclass(frozen=True)
class Period:
    granularity: Granularity
    year: Optional[int] = None
    quarter: Optional[int] = None
    date: Optional[str] = None      # YYYY-MM-DD
    end: Optional[str] = None       # range end (YYYY-MM-DD)

    @property
    def key(self) -> str:
        if self.granularity == "annual":
            return f"FY{self.year}"
        if self.granularity == "quarter":
            return f"FY{self.year}-Q{self.quarter}"
        if self.granularity == "range":
            return f"{self.date}..{self.end}"
        return str(self.date)


# A 4-digit year that is NOT part of a longer digit run (rejects "20244").
_YEAR = r"((?:19|20)\d{2})"
_DIGITS_GUARD = r"(?<!\d)"
# Quarter forms: FY2024-Q1, 2024-Q1, Q1 2024, Q1FY2024, 1Q2024.
_QUARTER_PATTERNS = [
    re.compile(rf"{_DIGITS_GUARD}(?:FY\s*)?{_YEAR}\s*[-/ ]?\s*Q([1-4])(?!\d)", re.IGNORECASE),
    re.compile(rf"{_DIGITS_GUARD}Q([1-4])\s*(?:FY\s*)?{_YEAR}(?!\d)", re.IGNORECASE),
    re.compile(rf"{_DIGITS_GUARD}([1-4])Q\s*{_YEAR}(?!\d)", re.IGNORECASE),
]
_ANNUAL_RE = re.compile(rf"{_DIGITS_GUARD}(?:FY\s*)?{_YEAR}(?!\d)", re.IGNORECASE)
_DATE_RE = re.compile(rf"{_DIGITS_GUARD}((?:19|20)\d{{2}})-(\d{{2}})-(\d{{2}})(?!\d)")
_RANGE_RE = re.compile(
    rf"{_DIGITS_GUARD}((?:19|20)\d{{2}}-\d{{2}}-\d{{2}})\s*(?:\.\.|to|–|—)\s*((?:19|20)\d{{2}}-\d{{2}}-\d{{2}})(?!\d)",
    re.IGNORECASE,
)


def _valid_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        return _dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_period(value: Optional[str]) -> Optional[Period]:
    """Parse one period label into a canonical `Period`, or None if unknown.

    Returns None for anything that is not a recognisable period, so an unknown
    label can never become a wildcard match.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    match = _RANGE_RE.search(text)
    if match:
        return Period("range", date=match.group(1), end=match.group(2))

    match = _DATE_RE.search(text)
    if match:
        iso = _valid_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return Period("date", date=iso) if iso else None

    for pattern in _QUARTER_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            # The three patterns order year/quarter differently.
            if pattern is _QUARTER_PATTERNS[0]:
                year, quarter = int(groups[0]), int(groups[1])
            elif pattern is _QUARTER_PATTERNS[1]:
                quarter, year = int(groups[0]), int(groups[1])
            else:
                quarter, year = int(groups[0]), int(groups[1])
            return Period("quarter", year=year, quarter=quarter)

    match = _ANNUAL_RE.search(text)
    if match:
        return Period("annual", year=int(match.group(1)))
    return None


def _date_within(date: str, p: Period) -> bool:
    if p.granularity == "date":
        return date == p.date
    if p.granularity == "range":
        return bool(p.date and p.end and p.date <= date <= p.end)
    if p.granularity == "annual":
        return bool(p.year and date[:4] == f"{p.year:04d}")
    if p.granularity == "quarter":
        if not (p.year and p.quarter):
            return False
        try:
            d = _dt.date.fromisoformat(date)
        except ValueError:
            return False
        return d.year == p.year and (d.month - 1) // 3 + 1 == p.quarter
    return False


def periods_match(
    required: Optional[str],
    candidate: Optional[str],
    *,
    candidate_is_timestamp: bool = False,
) -> bool:
    """Do a required and a candidate period refer to the same period?

    `candidate_is_timestamp` marks a candidate derived from `dataTimestamp`
    (no explicit fiscal label): a date timestamp is then allowed to satisfy an
    annual/quarter leg it falls inside, since a fiscal period end is a valid
    realisation of that period. An explicit fiscal `period` label never
    cross-matches granularity.
    """
    if not required:
        return True  # no requirement → any period is admissible
    req = parse_period(required)
    cand = parse_period(candidate)
    if req is None:
        # An unparseable requirement cannot be validated → refuse (never a wildcard).
        return False
    if cand is None:
        return False

    if req.granularity == "annual":
        if cand.granularity == "annual":
            return req.year == cand.year
        if cand.granularity == "date" and candidate_is_timestamp:
            return bool(req.year and cand.date and cand.date[:4] == f"{req.year:04d}")
        if cand.granularity == "range" and candidate_is_timestamp:
            return bool(req.year and cand.date and cand.date[:4] == f"{req.year:04d}")
        return False

    if req.granularity == "quarter":
        if cand.granularity == "quarter":
            return req.year == cand.year and req.quarter == cand.quarter
        if cand.granularity == "date" and candidate_is_timestamp:
            return _date_within(cand.date or "", req)
        return False

    if req.granularity == "date":
        if cand.granularity == "date":
            return req.date == cand.date
        if cand.granularity == "range":
            return bool(cand.date and cand.end and cand.date <= (req.date or "") <= cand.end)
        return False

    if req.granularity == "range":
        if cand.granularity == "date":
            return _date_within(cand.date or "", req)
        if cand.granularity == "range":
            return bool(
                req.date and req.end and cand.date and cand.end
                and req.date <= cand.end and cand.date <= req.end
            )
        return False

    return False


__all__ = ["Granularity", "Period", "parse_period", "periods_match"]
