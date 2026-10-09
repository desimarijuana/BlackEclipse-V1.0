"""Security core — floor, policy, risk, permission and capability behavior.

These lock the decision semantics: the Security Floor is terminal, the Risk Engine
is ordered by severity (not lexicographically), policy composes restrict-only, and
capabilities can never be delegated into a widening.
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-core-"), "agent-memory.db"),
)

from harness.security.capabilities import CapabilityEngine, CapabilityError
from harness.security.floor import FloorRule, SecurityFloor, default_floor
from harness.security.gateway import SecurityGateway
from harness.security.models import (
    AuthorizationRequest,
    Decision,
    Environment,
    PolicyProfile,
    RiskLevel,
    Verdict,
)
from harness.security.permissions import (
    PermissionGrant,
    PermissionSet,
    canonicalize_resource,
    resource_matches,
)
from harness.security.policy import PolicyDocument, PolicyEngine, PolicyError
from harness.security.risk import RiskEngine


# ── risk ordering ────────────────────────────────────────────────────────────
def test_risk_level_ordering_is_by_severity_not_spelling():
    assert RiskLevel.LOW < RiskLevel.HIGH
    assert RiskLevel.HIGH > RiskLevel.LOW
    assert RiskLevel.CRITICAL >= RiskLevel.HIGH
    assert not (RiskLevel.LOW >= RiskLevel.HIGH)
    assert RiskLevel.NONE < RiskLevel.LOW


def test_risk_engine_is_deterministic_and_monotonic():
    engine = RiskEngine()
    assert engine.evaluate(action="filesystem.read", resource="src/a.py") is RiskLevel.LOW
    assert engine.evaluate(action="filesystem.write", resource="src/a.py") is RiskLevel.MEDIUM
    assert engine.evaluate(action="filesystem.delete", resource="src/a.py") is RiskLevel.HIGH
    assert engine.evaluate(action="financial.withdraw", resource="acct") is RiskLevel.CRITICAL
    assert engine.evaluate(action="deploy.production", resource="svc") is RiskLevel.CRITICAL


def test_risk_private_network_destination_raises():
    engine = RiskEngine()
    risk = engine.evaluate(action="network.request", resource="http://10.0.0.5/x",
                           network_destination="http://10.0.0.5/x")
    assert risk >= RiskLevel.HIGH


def test_risk_hint_can_only_raise():
    engine = RiskEngine()
    low = engine.evaluate(action="filesystem.read", resource="x", hint="critical")
    assert low is RiskLevel.CRITICAL
    high = engine.evaluate(action="filesystem.delete", resource="x", hint="none")
    assert high is RiskLevel.HIGH  # hint did not lower it


# ── permissions ──────────────────────────────────────────────────────────────
def test_resource_glob_matching():
    assert resource_matches("/workspace/project/**", "/workspace/project/a/b.py")
    assert not resource_matches("/workspace/project/*", "/workspace/project/a/b.py")
    assert resource_matches("**/.env", "/srv/app/.env")
    assert resource_matches("*", "anything")


def test_canonicalize_blocks_traversal_smuggling():
    assert canonicalize_resource("a/../b") == "b"
    assert canonicalize_resource("/root/sub/../etc/passwd") == "/root/etc/passwd"
    # A traversal underneath an allowed prefix still lands outside it.
    assert not resource_matches("/workspace/project/**", "/workspace/project/../../etc/passwd")


def test_permission_set_requires_scope_and_expiry():
    ps = PermissionSet()
    grant = ps.grant_text("write:/workspace/**", environment=Environment.DEVELOPMENT,
                          scope="ws1")
    assert ps.allows("write", "/workspace/a.py", environment=Environment.DEVELOPMENT, scope="ws1")
    assert not ps.allows("write", "/workspace/a.py", environment=Environment.DEVELOPMENT, scope="ws2")
    assert not ps.allows("write", "/workspace/a.py", environment=Environment.PRODUCTION, scope="ws1")
    ps.revoke(grant.grant_id)
    assert not ps.allows("write", "/workspace/a.py", environment=Environment.DEVELOPMENT, scope="ws1")


# ── floor ────────────────────────────────────────────────────────────────────
def test_floor_hard_denies_sensitive_paths_for_read_and_write():
    floor = default_floor()
    for action in ("filesystem.read", "filesystem.write", "filesystem.delete"):
        verdict = floor.evaluate(action=action, resource="/home/u/.ssh/id_rsa")
        assert verdict is not None and verdict.verdict is Verdict.HARD_DENY
        env = floor.evaluate(action=action, resource="project/.env")
        assert env is not None and env.verdict is Verdict.HARD_DENY


def test_floor_protects_security_config_and_keys():
    floor = default_floor()
    for path in (".black-eclipse/security/policy.json", "src/keys/server.pem", "secrets.yaml"):
        verdict = floor.evaluate(action="filesystem.write", resource=path)
        assert verdict is not None and verdict.verdict is Verdict.HARD_DENY, path


def test_floor_mandates_approval_for_dangerous_classes():
    floor = default_floor()
    for action in ("deploy.production", "financial.live_trade", "database.write"):
        verdict = floor.evaluate(action=action, resource="x", environment=Environment.DEVELOPMENT)
        assert verdict is not None
        assert verdict.verdict in (Verdict.MANDATORY_APPROVAL, Verdict.HARD_DENY)


def test_floor_cannot_be_weakened_without_admin():
    floor = SecurityFloor([])
    with pytest.raises(PermissionError):
        floor.add_rule(FloorRule("x", Verdict.HARD_ALLOW), admin=False)
    floor.add_rule(FloorRule("x", Verdict.HARD_ALLOW, actions=("a.b",)), admin=True)
    assert floor.version == 2


# ── policy ───────────────────────────────────────────────────────────────────
def test_policy_inheritance_restrict_only():
    engine = PolicyEngine(PolicyProfile.DEVELOPER)
    # A higher layer denies a database write; a lower layer tries to allow it.
    engine.reload({
        "organization": {"defaults": {"database": "approval"}},
        "agent": {"defaults": {"database": "allow"}, "rules": [
            {"action": "database.write", "verdict": "allow"},
        ]},
    })
    match = engine.evaluate(action="database.write", resource="db", environment=Environment.DEVELOPMENT)
    assert match.verdict == "approval"  # the stricter org layer wins


def test_policy_reload_is_atomic_invalid_never_replaces_good():
    engine = PolicyEngine(PolicyProfile.SECURE)
    before = engine.version
    with pytest.raises(PolicyError):
        engine.reload({"agent": {"rules": [{"action": "x", "verdict": "bogus"}]}})
    assert engine.version == before  # unchanged


def test_policy_profile_defaults():
    lock = PolicyEngine(PolicyProfile.LOCKDOWN)
    assert lock.evaluate(action="shell.execute", resource="echo").verdict == "deny"
    dev = PolicyEngine(PolicyProfile.DEVELOPER)
    assert dev.evaluate(action="filesystem.write", resource="a").verdict == "allow"


def test_autonomous_profile_keeps_dangerous_classes_gated():
    engine = PolicyEngine(PolicyProfile.AUTONOMOUS)
    assert engine.evaluate(action="filesystem.write", resource="a").verdict == "allow"
    assert engine.evaluate(action="deploy.production", resource="a").verdict != "allow"
    assert engine.evaluate(action="credential.access", resource="x").verdict == "deny"


# ── capabilities ─────────────────────────────────────────────────────────────
def test_capability_lifecycle_and_no_escalation():
    engine = CapabilityEngine()
    parent = engine.issue(subject="agent", action="filesystem.write",
                          resource="/workspace/**", scope="ws1", ttl_seconds=60)
    assert engine.validate(parent.id)
    # Delegation that widens the resource is refused.
    with pytest.raises(CapabilityError):
        engine.delegate(parent.id, subject="agent", resource="/**")
    # Delegation that widens the action is refused.
    with pytest.raises(CapabilityError):
        engine.delegate(parent.id, subject="agent", action="filesystem.delete")
    # A narrower delegation succeeds.
    child = engine.delegate(parent.id, subject="child", resource="/workspace/sub/**")
    assert engine.validate(child.id)
    assert engine.permits(child.id, subject="child", action="filesystem.write",
                          resource="/workspace/sub/a.py", scope="ws1")
    # Revocation is immediate.
    engine.revoke(child.id)
    assert not engine.validate(child.id)


def test_capability_expiry():
    engine = CapabilityEngine()
    cap = engine.issue(subject="a", action="shell.execute", resource="echo", expires_at=1.0)
    assert not cap.active


# ── gateway end to end ───────────────────────────────────────────────────────
@pytest.fixture()
def gateway():
    store_path = os.path.join(tempfile.mkdtemp(prefix="be-sec-gw-"), "agent-memory.db")
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(store_path)
    gw = SecurityGateway(store=store, profile=PolicyProfile.DEVELOPER)
    try:
        yield gw
    finally:
        pass


def test_gateway_allows_low_risk_under_developer(gateway):
    decision = gateway.authorize(AuthorizationRequest(action="filesystem.read", resource="src/a.py"))
    assert decision.decision is Decision.ALLOW
    assert decision.audit_reference


def test_gateway_hard_denies_credentials(gateway):
    decision = gateway.authorize(AuthorizationRequest(action="filesystem.write", resource="/home/u/.aws/credentials"))
    assert decision.decision is Decision.DENY
    assert any("floor" in rule for rule in decision.matched_rules)


def test_gateway_requires_approval_then_allows_after_decision(gateway):
    # Without an approval store the gateway fails closed.
    decision = gateway.authorize(AuthorizationRequest(action="filesystem.delete", resource="src/a.py"))
    assert decision.decision is Decision.DENY


def test_gateway_require_raises():
    from harness.security.models import SecurityDenied

    gw = SecurityGateway(profile=PolicyProfile.LOCKDOWN)
    with pytest.raises(SecurityDenied):
        gw.require(AuthorizationRequest(action="shell.execute", resource="rm -rf /"))


def test_gateway_capability_satisfies_approval():
    from harness.security.models import ACTION_FS_DELETE

    gw = SecurityGateway(profile=PolicyProfile.SECURE)
    cap = gw.issue_capability(
        subject="agent", action=ACTION_FS_DELETE, resource="src/build/**",
        scope="ws1", ttl_seconds=60,
    )
    decision = gw.authorize(AuthorizationRequest(
        action=ACTION_FS_DELETE, resource="src/build/tmp", workspace="ws1",
        actor="agent",
    ))
    assert decision.decision is Decision.ALLOW
    assert decision.capability_id == cap.id
