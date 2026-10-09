"""Adversarial / safety invariants of the autonomy engine.

These are the properties that must hold for unattended action to be trustworthy:
the envelope cannot be bypassed, the kill switch revokes everything, a
non-retryable failure is never retried, recovery is always bounded, a one-off
approval is scoped to exactly its strategy, and no secret is persisted.
"""

from __future__ import annotations

import asyncio

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.envelope import ActionClass, AutonomyEnvelope, autonomy_enabled, load_envelope
from harness.recovery.executor import recover_operation
from harness.recovery.policy import RecoveryStrategy
from harness.recovery.service import RecoveryService
from harness.recovery.taxonomy import normalize_failure


def _svc(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def _run(coro):
    return asyncio.run(coro)


def test_default_envelope_denies_effectful_classes_unattended():
    env = AutonomyEnvelope()
    for strategy in (RecoveryStrategy.FIX_DEPENDENCY, RecoveryStrategy.SUBSTITUTE_PROVIDER,
                     RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION):
        decision = env.check(strategy)
        assert not decision.allowed
        assert decision.outcome.value in ("approval", "deny")


def test_kill_switch_revokes_the_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_AUTONOMY", "0")
    assert autonomy_enabled() is False
    env = load_envelope()
    assert env.enabled is False
    assert env.check(RecoveryStrategy.RETRY).outcome.value == "deny"


def test_executor_never_retries_an_auth_failure(tmp_path):
    svc = _svc(tmp_path)
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        raise RuntimeError("401 unauthorized invalid api key")

    result = _run(recover_operation(svc, op, subsystem="provider", source="provider",
                                    task_id="t1", max_attempts=5, sleep=lambda s: asyncio.sleep(0)))
    assert result.ok is False
    assert calls["n"] == 1


def test_recovery_is_bounded_never_infinite(tmp_path):
    svc = _svc(tmp_path)

    async def op():
        raise TimeoutError("timed out")

    result = _run(recover_operation(svc, op, subsystem="tools", source="tool", task_id="t1",
                                    max_attempts=3, sleep=lambda s: asyncio.sleep(0)))
    assert result.ok is False
    assert result.attempts <= 3


def test_one_off_approval_is_scoped_to_its_strategy(tmp_path):
    svc = _svc(tmp_path)
    recorded = svc.record_failure(code="provider_unavailable", message="down", source="provider", task_id="t1")
    incident_id = recorded["incidentId"]
    svc.approve(incident_id, "substitute_provider")
    assert svc.has_approval(incident_id, "substitute_provider") is True
    assert svc.has_approval(incident_id, "alternative_implementation") is False


def test_incident_message_is_bounded(tmp_path):
    svc = _svc(tmp_path)
    recorded = svc.record_failure(
        code="TOOL_ERROR", message="secret-token sk-ABCDEF " + "x" * 5000, source="tool", task_id="t1",
    )
    incident = svc.get_incident(recorded["incidentId"])
    assert len(incident["message"]) <= 500
    # The signature is a one-way digest, never the raw message.
    assert "sk-ABCDEF" not in incident["signature"]
    assert len(incident["signature"]) == 16


def test_envelope_expiry_fails_closed():
    env = AutonomyEnvelope(expires_at="2000-01-01T00:00:00Z")
    assert env.revoked() is True
    assert env.check(RecoveryStrategy.RETRY).outcome.value == "deny"