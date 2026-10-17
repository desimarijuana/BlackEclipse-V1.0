"""The response-mode routing benchmark — a quality floor, not a vibe.

Phase 6 asks whether the orchestrator picked the RIGHT presentation. This scores
the shipped deterministic classifier against the labelled `DEFAULT_CASES` set and
asserts a floor, so a change that regresses routing (a forced widget on a simple
turn, a missed simulation) fails CI. The benchmark runs the SAME classifier the
runtime uses, so it cannot drift from production.
"""

from __future__ import annotations

from harness.response_mode_benchmark import (
    BENCHMARK_VERSION,
    DEFAULT_CASES,
    evaluate_routing,
    format_report,
)

# Floors are set just below the measured result (100% at v1) so a NEW case that
# is hard but correct does not fail the suite, while a regression does.
ACCURACY_FLOOR = 0.95
PER_MODE_RECALL_FLOOR = 0.9
ALL_MODES = {"text", "explanation", "visualization", "simulation", "workflow", "composite"}


def test_the_case_set_covers_every_mode() -> None:
    covered = {case.expected for case in DEFAULT_CASES}
    assert covered == ALL_MODES


def test_routing_accuracy_meets_the_floor() -> None:
    report = evaluate_routing()
    assert report.accuracy >= ACCURACY_FLOOR, format_report(report)


def test_every_mode_recalls_above_the_floor() -> None:
    report = evaluate_routing()
    for mode in report.modes():
        assert report.recall(mode) >= PER_MODE_RECALL_FLOOR, format_report(report)


def test_no_forced_widget_on_a_plain_turn() -> None:
    # The failure that matters most: a simple question must NOT be dressed up.
    report = evaluate_routing()
    assert report.mismatches == [], format_report(report)


def test_report_renders_the_accuracy_line() -> None:
    text = format_report(evaluate_routing())
    assert "accuracy:" in text
    assert BENCHMARK_VERSION in text
