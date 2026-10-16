"""Phase 6 G1 — the stdlib cron matcher is correct and refuses precisely.

`next_fire` is pure, so every case here injects a datetime. No sleeping, no clock.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from harness.jobs.cron import CronError, is_valid, parse_cron


def _dt_at(y, m, d, hh=0, mm=0):
    return _dt.datetime(y, m, d, hh, mm)


# ── Basic resolution ─────────────────────────────────────────────────────────


def test_every_minute():
    expr = parse_cron("* * * * *")
    assert expr.next_fire(_dt_at(2026, 9, 28, 6, 30)) == _dt_at(2026, 9, 28, 6, 31)


def test_step_minutes():
    expr = parse_cron("*/15 * * * *")
    assert expr.next_fire(_dt_at(2026, 9, 28, 6, 30)) == _dt_at(2026, 9, 28, 6, 45)
    assert expr.next_fire(_dt_at(2026, 9, 28, 6, 45)) == _dt_at(2026, 9, 28, 7, 0)


def test_weekday_morning():
    expr = parse_cron("30 7 * * 1-5")
    # Monday 2026-09-28 07:30 -> next weekday 07:30 is Tuesday.
    assert expr.next_fire(_dt_at(2026, 9, 28, 7, 30)) == _dt_at(2026, 9, 29, 7, 30)


def test_weekday_skips_weekend():
    expr = parse_cron("30 7 * * 1-5")
    # Friday after 07:30 -> Monday (skips Sat/Sun).
    assert expr.next_fire(_dt_at(2026, 10, 2, 7, 30)) == _dt_at(2026, 10, 5, 7, 30)


def test_exact_hour_list():
    expr = parse_cron("0 7,12,18 * * *")
    assert expr.next_fire(_dt_at(2026, 9, 28, 8, 0)) == _dt_at(2026, 9, 28, 12, 0)


def test_range_with_step():
    expr = parse_cron("0 8-18/6 * * *")
    # 8, 14, 18
    assert expr.next_fire(_dt_at(2026, 9, 28, 8, 0)) == _dt_at(2026, 9, 28, 14, 0)


def test_dom_or_dow_rule_both_restricted():
    # Vixie OR rule: fires on the 1st OR on a Monday.
    expr = parse_cron("0 0 1 * 1")
    # 2026-10-01 is a Thursday and is the 1st -> fires.
    assert expr.next_fire(_dt_at(2026, 9, 30, 0, 0)) == _dt_at(2026, 10, 1, 0, 0)


def test_dom_only_when_dow_is_star():
    expr = parse_cron("0 0 15 * *")
    assert expr.next_fire(_dt_at(2026, 9, 20, 0, 0)) == _dt_at(2026, 10, 15, 0, 0)


def test_leap_day():
    expr = parse_cron("0 0 29 2 *")
    assert expr.next_fire(_dt_at(2023, 3, 1, 0, 0)) == _dt_at(2024, 2, 29, 0, 0)


def test_leap_day_bound_is_bounded():
    # The next Feb 29 after 2024-02-29 is 2028-02-29.
    expr = parse_cron("0 0 29 2 *")
    assert expr.next_fire(_dt_at(2024, 2, 29, 0, 0)) == _dt_at(2028, 2, 29, 0, 0)


def test_dst_boundary_resolves():
    # A daily 02:30 in a DST-observing zone is still a wall-clock match; the
    # matcher is timezone-naive and resolves the next matching wall-clock minute.
    expr = parse_cron("30 2 * * *")
    assert expr.next_fire(_dt_at(2026, 3, 8, 3, 0)) == _dt_at(2026, 3, 9, 2, 30)


def test_impossible_expression_has_no_next_fire():
    # Feb 30 exists in no year: next_fire is None, never a phantom far-future date.
    expr = parse_cron("0 0 30 2 *")
    assert expr.next_fire(_dt_at(2026, 1, 1, 0, 0)) is None


def test_matches_reports_true_and_false():
    expr = parse_cron("30 7 * * 1-5")
    assert expr.matches(_dt_at(2026, 9, 28, 7, 30))
    assert not expr.matches(_dt_at(2026, 9, 28, 7, 31))


# ── Refusals, each with a specific code ──────────────────────────────────────


def test_refuses_six_field_seconds():
    with pytest.raises(CronError) as info:
        parse_cron("0 30 7 * * 1-5")
    assert info.value.code == "SECONDS_NOT_ALLOWED"


def test_refuses_macro():
    with pytest.raises(CronError) as info:
        parse_cron("@reboot")
    assert info.value.code == "MACRO_NOT_ALLOWED"


def test_refuses_name_alias():
    with pytest.raises(CronError) as info:
        parse_cron("0 7 * * MON")
    assert info.value.code == "NAME_NOT_ALLOWED"


def test_refuses_name_alias_in_month():
    with pytest.raises(CronError) as info:
        parse_cron("0 7 * JAN *")
    assert info.value.code == "NAME_NOT_ALLOWED"


def test_refuses_wrong_field_count():
    with pytest.raises(CronError) as info:
        parse_cron("0 7 * *")
    assert info.value.code == "FIELD_COUNT"


def test_refuses_out_of_range():
    with pytest.raises(CronError) as info:
        parse_cron("0 25 * * *")
    assert info.value.code == "OUT_OF_RANGE"


def test_refuses_empty():
    with pytest.raises(CronError) as info:
        parse_cron("   ")
    assert info.value.code == "EMPTY_EXPRESSION"


def test_refuses_bad_step():
    with pytest.raises(CronError) as info:
        parse_cron("*/0 * * * *")
    assert info.value.code == "INVALID_STEP"


def test_is_valid_never_raises():
    assert is_valid("30 7 * * 1-5")
    assert not is_valid("@reboot")
    assert not is_valid("garbage")
