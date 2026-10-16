"""Native Automation Engine — condition/timezone/lifecycle/validation units."""

from __future__ import annotations

import datetime as _dt

import pytest

from harness.automation.conditions import (
    ConditionContext,
    ConditionError,
    FALSE,
    TRUE,
    UNAVAILABLE,
    decide_edge,
    evaluate,
    extract_variables,
    parse_condition,
    validate_condition,
)
from harness.automation.lifecycle import (
    TransitionError,
    assert_execution_transition,
    assert_lifecycle_transition,
    can_transition_lifecycle,
)
from harness.automation.timeutil import (
    TimezoneError,
    next_cron_fire,
    next_interval_fire,
    next_one_time_fire,
    resolve_timezone,
)
from harness.automation.model import AutomationDefinition
from harness.automation.validation import is_valid, validate_automation


# ── DST (the module's most specific promise) ─────────────────────────────────


def test_dst_spring_forward_gap_resolves_deterministically():
    # 2026-03-08 America/New_York springs forward 02:00→03:00, so 02:30 does not
    # exist. It must still yield a concrete, future instant (fold=0 lands past the
    # gap), never None and never a non-future time.
    from datetime import timezone as _tz

    after = _dt.datetime(2026, 3, 8, 5, 0, tzinfo=_tz.utc)  # 00:00 EST
    nxt = next_cron_fire("30 2 * * *", "America/New_York", after)
    assert nxt == _dt.datetime(2026, 3, 8, 7, 30, tzinfo=_tz.utc)
    assert nxt > after


def test_dst_fall_back_overlap_resolves_to_first_occurrence():
    # 2026-11-01 America/New_York falls back 02:00→01:00, so 01:30 happens twice;
    # fold=0 must pick the FIRST (EDT, -04:00).
    from datetime import timezone as _tz

    after = _dt.datetime(2026, 11, 1, 4, 0, tzinfo=_tz.utc)  # 00:00 EDT
    nxt = next_cron_fire("30 1 * * *", "America/New_York", after)
    assert nxt == _dt.datetime(2026, 11, 1, 5, 30, tzinfo=_tz.utc)


# ── Conditions ───────────────────────────────────────────────────────────────


def test_comparison_and_logic():
    ctx = ConditionContext(values={"BTC.price": 89000, "BTC.volume": 150, "BTC.avg": 80})
    assert evaluate("BTC.price < 90000", ctx).state == TRUE
    assert evaluate("BTC.price > 90000", ctx).state == FALSE
    assert evaluate("BTC.price < 90000 AND BTC.volume > BTC.avg * 1.5", ctx).state == TRUE
    assert evaluate("BTC.price < 90000 OR BTC.price > 100000", ctx).state == TRUE
    assert evaluate("NOT BTC.price < 90000", ctx).state == FALSE


def test_unavailable_is_three_valued():
    ctx = ConditionContext(values={"BTC.price": 89000})
    # A missing operand is UNAVAILABLE, never silently false.
    assert evaluate("BTC.price < 90000 AND BTC.volume > 10", ctx).state == UNAVAILABLE
    assert evaluate("BTC.price < 90000 OR BTC.volume > 10", ctx).state == TRUE  # short-circuit
    assert evaluate("BTC.missing > 1", ctx).state == UNAVAILABLE


def test_membership_and_matching():
    ctx = ConditionContext(values={"sym": "AAPL", "tags": ["tech", "us"], "name": "Apple Inc"})
    assert evaluate("sym IN ['AAPL', 'MSFT']", ctx).state == TRUE
    assert evaluate("sym NOT_IN ['MSFT']", ctx).state == TRUE
    assert evaluate("name CONTAINS 'Apple'", ctx).state == TRUE
    assert evaluate("name MATCHES '^App'", ctx).state == TRUE


def test_domain_helpers():
    ctx = ConditionContext(values={"BTC.price": 89900}, history={"BTC.price": 90100})
    assert evaluate("crosses_below(BTC.price, 90000)", ctx).state == TRUE
    assert evaluate("crosses_above(BTC.price, 90000)", ctx).state == FALSE
    ctx2 = ConditionContext(values={"BTC.price": 105}, history={"BTC.price": 100})
    assert evaluate("increased_by(BTC.price, 3)", ctx2).state == TRUE
    assert evaluate("decreased_by(BTC.price, 3)", ctx2).state == FALSE
    ctx3 = ConditionContext(values={"BTC.price": 101}, history={"BTC.price": 100})
    assert evaluate("changed(BTC.price)", ctx3).state == TRUE


def test_edge_detection_semantics():
    assert decide_edge(TRUE, None) is True
    assert decide_edge(TRUE, FALSE) is True
    assert decide_edge(TRUE, TRUE) is False
    assert decide_edge(FALSE, TRUE) is False
    # UNAVAILABLE never manufactures a transition.
    assert decide_edge(UNAVAILABLE, TRUE) is False


def test_parser_rejects_unsafe_and_unknown():
    with pytest.raises(ConditionError):
        parse_condition("__import__('os').system('rm -rf /')")
    with pytest.raises(ConditionError):
        parse_condition("open('x')")
    with pytest.raises(ConditionError):
        parse_condition("BTC.price <")
    with pytest.raises(ConditionError):
        parse_condition("")
    assert set(extract_variables("BTC.price < 90000 AND ETH.price > 1")) == {"BTC.price", "ETH.price"}


def test_validate_condition_known_variables():
    assert validate_condition("BTC.price < 1", known_variables={"BTC.price"}) == ["BTC.price"]
    with pytest.raises(ConditionError):
        validate_condition("BTC.price < 1", known_variables={"ETH.price"})


# ── Timezones ────────────────────────────────────────────────────────────────


def test_cron_next_fire_is_timezone_aware():
    after = _dt.datetime(2026, 10, 8, 0, 0, tzinfo=_dt.timezone.utc)
    # 08:00 Asia/Karachi == 03:00 UTC.
    moment = next_cron_fire("0 8 * * *", "Asia/Karachi", after)
    assert moment == _dt.datetime(2026, 10, 8, 3, 0, tzinfo=_dt.timezone.utc)
    # 09:00 America/New_York (EDT, UTC-4) == 13:00 UTC.
    ny = next_cron_fire("0 9 * * *", "America/New_York", _dt.datetime(2026, 7, 1, 0, 0, tzinfo=_dt.timezone.utc))
    assert ny.hour == 13


def test_cron_weekday_and_start_end():
    after = _dt.datetime(2026, 10, 10, 0, 0, tzinfo=_dt.timezone.utc)  # Saturday
    monday = next_cron_fire("0 9 * * 1", "UTC", after)
    assert monday.weekday() == 0  # Monday
    assert next_cron_fire("0 9 * * *", "UTC", after, end_at="2026-10-09T00:00:00+00:00") is None


def test_interval_and_one_time():
    anchor = _dt.datetime(2026, 1, 1, 0, 0, tzinfo=_dt.timezone.utc)
    nxt = next_interval_fire(3600, anchor, after_utc=_dt.datetime(2026, 1, 1, 0, 30, tzinfo=_dt.timezone.utc))
    assert nxt == _dt.datetime(2026, 1, 1, 1, 0, tzinfo=_dt.timezone.utc)
    assert next_one_time_fire("2030-01-01T00:00:00+00:00", after_utc=anchor) is not None
    assert next_one_time_fire("2020-01-01T00:00:00+00:00", after_utc=anchor) is None


def test_unknown_timezone_raises():
    with pytest.raises(TimezoneError):
        resolve_timezone("Mars/Olympus")


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_lifecycle_transitions_are_validated():
    assert can_transition_lifecycle("draft", "active")
    assert can_transition_lifecycle("active", "paused")
    assert not can_transition_lifecycle("archived", "active")
    with pytest.raises(TransitionError):
        assert_lifecycle_transition("archived", "active")
    assert_execution_transition("running", "completed")
    with pytest.raises(TransitionError):
        assert_execution_transition("completed", "running")


# ── Validation ───────────────────────────────────────────────────────────────


def _definition(**overrides):
    base = dict(
        id="auto_x", name="Test", state="draft",
        trigger={"type": "cron", "cron": "0 8 * * *", "timezone": "UTC"},
        action={"type": "run_agent", "objective": "brief"},
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
    )
    base.update(overrides)
    return AutomationDefinition(**base)


def test_validation_catches_bad_cron_and_timezone():
    assert is_valid(validate_automation(_definition()))
    bad_cron = _definition(trigger={"type": "cron", "cron": "not a cron", "timezone": "UTC"})
    codes = {i.code for i in validate_automation(bad_cron)}
    assert "INVALID_CRON" in codes
    bad_tz = _definition(trigger={"type": "cron", "cron": "0 8 * * *", "timezone": "Mars/Olympus"})
    assert "INVALID_TIMEZONE" in {i.code for i in validate_automation(bad_tz)}


def test_validation_catches_embedded_secret_and_bad_action():
    secret = _definition(action={"type": "call_tool", "tool_name": "x", "tool_args": {"apiKey": "sk-123"}})
    assert "EMBEDDED_SECRET" in {i.code for i in validate_automation(secret)}
    bad_action = _definition(action={"type": "execute_workflow"})
    assert "INVALID_ACTION" in {i.code for i in validate_automation(bad_action)}
