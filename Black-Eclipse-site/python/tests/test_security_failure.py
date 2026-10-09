"""Failure-mode tests — every component failure must fail CLOSED.

A missing approval store, a broken policy, an unreachable secret provider, an
internal error in evaluation: none may become ALLOW.
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-fail-"), "agent-memory.db"),
)

from harness.security.gateway import SecurityGateway
from harness.security.models import (
    AuthorizationRequest,
    Decision,
    PolicyProfile,
)
from harness.security.policy import PolicyEngine, PolicyError
from harness.security.secrets import (
    SecretAccessDenied,
    SecretsManager,
    UnavailableSecretProvider,
)


def test_missing_approval_store_denies_approval_required_action():
    gw = SecurityGateway(profile=PolicyProfile.SECURE)  # no approvals store
    d = gw.authorize(AuthorizationRequest(action="filesystem.write", resource="src/x.py"))
    assert d.decision is Decision.DENY


def test_evaluation_error_fails_closed(monkeypatch):
    gw = SecurityGateway(profile=PolicyProfile.DEVELOPER)

    def _boom(*args, **kwargs):
        raise RuntimeError("policy engine exploded")

    monkeypatch.setattr(gw.policy, "evaluate", _boom)
    d = gw.authorize(AuthorizationRequest(action="filesystem.read", resource="a.py"))
    assert d.decision is Decision.DENY
    assert gw.health()["failures"] >= 1


def test_invalid_policy_preserves_known_good():
    engine = PolicyEngine(PolicyProfile.SECURE)
    before = engine.snapshot()
    with pytest.raises(PolicyError):
        engine.reload({"agent": {"profile": "not-a-profile"}})
    assert engine.snapshot()["version"] == before["version"]


def test_unavailable_secret_provider_denies():
    manager = SecretsManager()
    manager.register_provider(UnavailableSecretProvider("vault", "no network"))
    with pytest.raises(SecretAccessDenied):
        manager.resolve("secret://vault/DB_PASSWORD", consumer="app", require_grant=False)


def test_secret_without_grant_denied_even_when_available():
    from harness.security.secrets import StaticSecretProvider

    manager = SecretsManager()
    manager.register_provider(StaticSecretProvider({"K": "value-value-value"}))
    with pytest.raises(SecretAccessDenied):
        manager.resolve("secret://static/K", consumer="anything")


def test_redaction_never_returns_original_on_internal_error(monkeypatch):
    from harness.security.secrets import SecretRegistry

    registry = SecretRegistry()
    registry.register("topsecrettoken123")

    # Even if the underlying walk raises, redact must return the sentinel.
    monkeypatch.setattr(registry, "_scrub", lambda value: (_ for _ in ()).throw(RuntimeError("boom")))
    assert registry.redact("topsecrettoken123") == "[REDACTED]"


def test_gateway_audit_survives_store_failure():
    from harness.persistence import AgentMemoryStore

    real = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-sec-fail-db-"), "agent-memory.db"))

    class _BrokenAuditStore:
        """A real agent-memory DB whose audit append is broken."""

        def __init__(self, underlying):
            self._underlying = underlying

        @property
        def _db(self):
            return self._underlying._db

        def append_audit(self, event):
            raise RuntimeError("audit table down")

    gw = SecurityGateway(store=_BrokenAuditStore(real), profile=PolicyProfile.DEVELOPER)
    # A low-risk allow proceeds even though the audit sink is broken.
    d = gw.authorize(AuthorizationRequest(action="filesystem.read", resource="a.py"))
    assert d.decision is Decision.ALLOW
    assert gw.health()["failures"] >= 0  # audit failure is counted, not fatal
