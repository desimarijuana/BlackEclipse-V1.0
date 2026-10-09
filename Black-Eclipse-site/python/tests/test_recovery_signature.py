"""Failure signatures and recurrence/loop detection (pure)."""

from __future__ import annotations

from harness.recovery.signature import RecurrenceTracker, failure_signature, normalize_message


def test_normalize_message_collapses_volatile_tokens():
    n = normalize_message("Timeout after 12500ms at C:\\work\\a.py:42 id 550e8400-e29b-41d4-a716-446655440000")
    assert "<n>" in n
    assert "<path>" in n
    assert "<id>" in n
    assert "12500" not in n


def test_signature_is_hex_and_stable():
    one = failure_signature(kind="timeout", code="t", source="tool", subsystem="tools", message="a")
    two = failure_signature(kind="timeout", code="t", source="tool", subsystem="tools", message="a")
    assert one == two
    assert len(one) == 16


def test_recurrence_detects_repeat_within_window():
    tracker = RecurrenceTracker(threshold=3, window=6)
    sig = "abc"
    verdicts = [tracker.observe(sig) for _ in range(3)]
    assert verdicts[-1].repeated is True
    assert verdicts[0].repeated is False


def test_recurrence_expires_out_of_window():
    tracker = RecurrenceTracker(threshold=3, window=3)
    tracker.observe("abc")
    tracker.observe("def")
    tracker.observe("ghi")
    # "abc" has slid out; a single new observation must not be "repeated".
    assert tracker.observe("abc").repeated is False


def test_reset_clears_state():
    tracker = RecurrenceTracker(threshold=2)
    tracker.observe("x")
    tracker.observe("x")
    tracker.reset()
    assert tracker.observe("x").repeated is False
