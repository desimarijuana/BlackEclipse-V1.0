"""Failure taxonomy — the shared cross-subsystem vocabulary (pure)."""

from __future__ import annotations

from harness.recovery.taxonomy import (
    FailureKind,
    Retryability,
    classify,
    normalize_failure,
    retryability_for,
)


def test_structured_code_wins_over_message_text():
    # A message that *looks* like a network error must not override the code.
    kind = classify("authentication_error", "connection reset by peer")
    assert kind == FailureKind.AUTHENTICATION


def test_message_rules_when_no_code():
    assert classify(None, "request timed out after 30s") == FailureKind.TIMEOUT
    assert classify(None, "ModuleNotFoundError: no module named 'foo'") == FailureKind.DEPENDENCY
    assert classify(None, "some completely novel thing") == FailureKind.UNKNOWN


def test_retryability_conservative():
    assert retryability_for("timeout", FailureKind.TIMEOUT) == Retryability.RETRYABLE
    assert retryability_for("authentication_error", FailureKind.AUTHENTICATION) == Retryability.NON_RETRYABLE
    # Unknown kind defaults to UNKNOWN, never a guessed retry.
    assert retryability_for(None, FailureKind.UNKNOWN) == Retryability.UNKNOWN
    # A known non-retryable code overrides a retryable-looking kind.
    assert retryability_for("tool_budget_exceeded", FailureKind.RESOURCE_EXHAUSTION) == Retryability.NON_RETRYABLE


def test_signature_is_stable_across_volatile_tokens():
    a = normalize_failure(code="TOOL_TIMEOUT", message="tool timed out after 1201ms", subsystem="tools", source="tool", location="search")
    b = normalize_failure(code="TOOL_TIMEOUT", message="tool timed out after 1198ms", subsystem="tools", source="tool", location="search")
    assert a.signature == b.signature
    assert "1201" not in a.signature


def test_signature_differs_by_kind_and_location():
    a = normalize_failure(code="TOOL_TIMEOUT", message="x", source="tool", location="a")
    b = normalize_failure(code="TOOL_TIMEOUT", message="x", source="tool", location="b")
    c = normalize_failure(code="NETWORK_ERROR", message="x", source="tool", location="a")
    assert a.signature != b.signature
    assert a.signature != c.signature


def test_message_is_truncated():
    failure = normalize_failure(code="TOOL_ERROR", message="z" * 5000)
    assert len(failure.message) == 500


def test_to_dict_is_json_safe():
    failure = normalize_failure(code="TOOL_ERROR", message="boom", details={"a": 1})
    view = failure.to_dict()
    assert view["kind"] == "runtime"
    assert view["retryable"] is True
    assert view["details"] == {"a": 1}
