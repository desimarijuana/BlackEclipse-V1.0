"""Trading-calendar tests — deterministic sessions, holidays, freshness."""

from __future__ import annotations

import datetime as dt

from harness.market.calendar import (
    assess,
    is_open,
    is_trading_day,
    last_session_close,
    market_kind,
    us_holidays,
)


def _utc(y, m, d, hh=0, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


def test_market_kind_classification():
    assert market_kind("equity", "US") == "us_equity"
    assert market_kind("crypto") == "crypto"
    assert market_kind("fx", "FX") == "fx"
    assert market_kind("weird") == "unknown"


def test_us_holidays_known_dates():
    hols = us_holidays(2026)
    assert dt.date(2026, 1, 1) in hols          # New Year's Day (Thu)
    assert dt.date(2026, 7, 3) in hols          # Jul 4 2026 is Sat → observed Fri
    assert dt.date(2026, 11, 26) in hols        # Thanksgiving (4th Thu Nov)
    assert dt.date(2026, 12, 25) in hols        # Christmas (Fri)


def test_trading_day_and_weekend():
    assert is_trading_day(dt.date(2026, 1, 2)) is True       # Friday
    assert is_trading_day(dt.date(2026, 1, 3)) is False      # Saturday
    assert is_trading_day(dt.date(2026, 1, 1)) is False      # holiday


def test_us_equity_session_open_and_closed():
    # 2026-01-02 15:00 UTC = 10:00 ET (EST) → open.
    assert is_open("us_equity", _utc(2026, 1, 2, 15, 0)) is True
    # 12:00 UTC = 07:00 ET → pre-market, closed.
    assert is_open("us_equity", _utc(2026, 1, 2, 12, 0)) is False
    # weekend closed.
    assert is_open("us_equity", _utc(2026, 1, 3, 15, 0)) is False


def test_crypto_always_open():
    assert is_open("crypto", _utc(2026, 1, 3, 3, 0)) is True


def test_last_session_close_is_prior_close_when_closed():
    close = last_session_close("us_equity", _utc(2026, 1, 3, 12, 0))  # Saturday
    assert close is not None
    # Friday 2026-01-02 16:00 ET = 21:00 UTC.
    assert close == _utc(2026, 1, 2, 21, 0)


def test_assess_closed_recent_is_not_stale():
    # Observation at Friday's close, evaluated Saturday → closed_recent.
    out = assess("equity", "2026-01-02T21:00:00Z", now=_utc(2026, 1, 3, 12, 0))
    assert out["state"] == "closed_recent"
    assert out["open"] is False


def test_assess_stale_when_predates_last_close():
    out = assess("equity", "2025-12-30T21:00:00Z", now=_utc(2026, 1, 3, 12, 0))
    assert out["state"] == "stale"


def test_assess_open_market():
    out = assess("equity", "2026-01-02T15:00:00Z", now=_utc(2026, 1, 2, 15, 5))
    assert out["state"] == "open"


def test_assess_unknown_kind():
    out = assess("weird", "2026-01-02T15:00:00Z")
    assert out["state"] == "unknown"
