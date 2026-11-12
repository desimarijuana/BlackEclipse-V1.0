"""Release gating: a strong average must not hide a critical failure."""

from __future__ import annotations

from harness.evaluation.scoring import release_ready, weighted_composite


def _all_required(**overrides):
    dims = {
        "task_success": 1.0,
        "safety_score": 1.0,
        "delivery": 1.0,
        "provenance": 1.0,
        "financial_accuracy": 0.95,
    }
    dims.update(overrides)
    return dims


def test_all_required_measured_and_passing_is_releasable():
    ok, failures = release_ready(_all_required())
    assert ok is True
    assert failures == []


def test_a_failed_delivery_blocks_even_with_a_high_average():
    dims = _all_required(delivery=0.4, financial_accuracy=1.0, task_success=1.0)
    ok, failures = release_ready(dims)
    assert ok is False
    assert any("delivery" in f for f in failures)
    # The weighted mean can still look healthy; that is exactly why the gate is
    # separate.
    assert weighted_composite(dims) is not None


def test_an_unmeasured_required_dimension_blocks():
    dims = _all_required()
    dims.pop("provenance")
    ok, failures = release_ready(dims)
    assert ok is False
    assert any("provenance: unmeasured" in f for f in failures)


def test_safety_failure_blocks():
    ok, failures = release_ready(_all_required(safety_score=0.0))
    assert ok is False
    assert any("safety_score" in f for f in failures)
