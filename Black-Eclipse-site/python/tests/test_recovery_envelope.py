"""The Autonomy Envelope — the permission that makes unattended action safe."""

from __future__ import annotations

from harness.recovery.envelope import (
    ActionClass,
    AutonomyEnvelope,
    EnvelopeOutcome,
    STRATEGY_TO_CLASS,
    default_envelope,
    from_dict,
)
from harness.recovery.policy import RecoveryStrategy


def test_default_envelope_allows_reversible_low_risk():
    env = default_envelope()
    decision = env.check(RecoveryStrategy.RETRY, reversible=True, risk="low")
    assert decision.allowed
    assert decision.action_class == ActionClass.RETRY


def test_default_envelope_denies_effectful_classes():
    env = default_envelope()
    assert env.check(RecoveryStrategy.FIX_DEPENDENCY, reversible=False).outcome == EnvelopeOutcome.APPROVAL
    assert env.check(RecoveryStrategy.SUBSTITUTE_PROVIDER).outcome == EnvelopeOutcome.APPROVAL
    assert env.check(RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION).outcome == EnvelopeOutcome.APPROVAL


def test_kill_switch_revokes_everything():
    env = AutonomyEnvelope(enabled=False)
    decision = env.check(RecoveryStrategy.RETRY)
    assert decision.outcome == EnvelopeOutcome.DENY
    assert env.revoked() is True


def test_expiry_revokes():
    env = AutonomyEnvelope(expires_at="2000-01-01T00:00:00Z")
    assert env.revoked() is True
    assert env.check(RecoveryStrategy.RETRY).outcome == EnvelopeOutcome.DENY


def test_bad_expiry_fails_closed():
    env = AutonomyEnvelope(expires_at="not-a-date")
    assert env.revoked() is True


def test_irreversible_action_requires_approval_when_required():
    env = AutonomyEnvelope(require_reversible=True, action_classes=frozenset(ActionClass))
    assert env.check(RecoveryStrategy.ROLLBACK, reversible=False).outcome == EnvelopeOutcome.APPROVAL
    assert env.check(RecoveryStrategy.ROLLBACK, reversible=True).allowed


def test_risk_ceiling_blocks_higher_risk():
    env = AutonomyEnvelope(action_classes=frozenset({ActionClass.FIX_DEPENDENCY}), risk_ceiling="low")
    assert env.check(RecoveryStrategy.FIX_DEPENDENCY, risk="medium").outcome == EnvelopeOutcome.APPROVAL


def test_caps_block_over_budget_actions():
    env = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.FIX_DEPENDENCY}),
        max_files_changed=2,
        max_cost_usd=0.5,
    )
    assert env.check(RecoveryStrategy.FIX_DEPENDENCY, files_changed=3).outcome == EnvelopeOutcome.APPROVAL
    assert env.check(RecoveryStrategy.FIX_DEPENDENCY, cost_usd=5.0).outcome == EnvelopeOutcome.APPROVAL
    assert env.check(RecoveryStrategy.FIX_DEPENDENCY, files_changed=1, cost_usd=0.1).allowed


def test_network_allowlist():
    env = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.ALTERNATIVE_IMPLEMENTATION}),
        allowed_network=("example.com",),
        risk_ceiling="high", require_reversible=False,
    )
    assert env.check(RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION, network=("api.example.com",)).allowed
    assert env.check(RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION, network=("evil.test",)).outcome == EnvelopeOutcome.APPROVAL


def test_from_dict_round_trip_and_fail_closed():
    env = from_dict({
        "enabled": True,
        "actionClasses": ["retry", "fix_dependency"],
        "riskCeiling": "medium",
        "maxFilesChanged": 3,
    })
    assert ActionClass.FIX_DEPENDENCY in env.action_classes
    assert env.risk_ceiling == "medium"
    assert env.max_files_changed == 3
    # An unknown class name drops the whole class set back to the default.
    fallback = from_dict({"actionClasses": ["nonsense"]})
    assert fallback.action_classes
    # An unknown risk ceiling falls back.
    assert from_dict({"riskCeiling": "extreme"}).risk_ceiling == "low"


def test_strategy_to_class_covers_every_strategy():
    for strategy in RecoveryStrategy:
        if strategy in (RecoveryStrategy.SUSPEND, RecoveryStrategy.STOP_AND_REPORT):
            continue  # terminal, not an action class
        assert strategy in STRATEGY_TO_CLASS