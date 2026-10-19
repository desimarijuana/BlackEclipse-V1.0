"""Round 4 (W1.2) — a UI capability gap is a first-class failure incident.

The event is canonical (registered), maps to the shared failure vocabulary, and
is subscribed by the recovery engine. No new FailureKind and no second store.
"""

from __future__ import annotations

from harness.event_system.registry import EventRegistry, _build_default_specs
from harness.recovery.bootstrap import _FAILURE_TYPES
from harness.recovery.taxonomy import (
    FailureKind,
    Retryability,
    classify,
    retryability_for,
)


def test_the_event_is_registered_with_recovery_as_a_consumer():
    registry = EventRegistry()
    registry.register_all(_build_default_specs())
    spec = registry.get("ui.capability_gap")
    assert spec is not None
    assert "recovery" in spec.consumers
    assert "capability" in spec.required_fields


def test_recovery_subscribes_to_the_event():
    assert "ui.capability_gap" in _FAILURE_TYPES


def test_the_code_classifies_as_a_capability_failure():
    assert classify("ui_capability_gap", "") is FailureKind.CAPABILITY
    assert retryability_for("ui_capability_gap", FailureKind.CAPABILITY) is Retryability.NON_RETRYABLE


def test_the_message_alone_classifies_honestly():
    # A payload without a code still maps on the recorded reason.
    assert classify(None, "no registered component matches: clock") is FailureKind.CAPABILITY
    assert classify(None, "capability gap: world clock") is FailureKind.CAPABILITY
