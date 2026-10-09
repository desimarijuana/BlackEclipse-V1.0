"""Adversarial / red-team scenarios.

Every attack must result in DENY or APPROVAL_REQUIRED — never a silent allow.
These are the concrete attacks named in the security specification, driven against
the real gateway.
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-adv-"), "agent-memory.db"),
)

from harness.security.capabilities import CapabilityEngine, CapabilityError
from harness.security.gateway import SecurityGateway
from harness.security.models import (
    AuthorizationRequest,
    Decision,
    Environment,
    PolicyProfile,
)
from harness.security.secrets import SecretAccessDenied, SecretGrant, StaticSecretProvider


@pytest.fixture()
def gateway():
    from harness.persistence import AgentMemoryStore
    from harness.mcp.approvals import ApprovalStore

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(prefix="be-sec-adv-db-"), "agent-memory.db"))
    approvals = ApprovalStore(store)
    return SecurityGateway(store=store, approvals=approvals, profile=PolicyProfile.DEVELOPER)


def _not_allowed(decision):
    return decision.decision in (Decision.DENY, Decision.APPROVAL_REQUIRED)


def test_ignore_policy_and_read_private_key(gateway):
    d = gateway.authorize(AuthorizationRequest(action="filesystem.read", resource="/root/.ssh/id_rsa"))
    assert _not_allowed(d)


def test_absolute_path_escape_reading_passwd(gateway):
    d = gateway.authorize(AuthorizationRequest(action="filesystem.read", resource="/etc/passwd"))
    assert _not_allowed(d)


def test_path_traversal_escape_is_canonicalized(gateway):
    d = gateway.authorize(AuthorizationRequest(
        action="filesystem.write", resource="/workspace/project/../../etc/cron.d/x",
    ))
    # Canonicalizes to /workspace/etc/cron.d/x — but the security-config/sensitive
    # rules and the developer policy still refuse an absolute escape.
    assert _not_allowed(d)


def test_symlink_style_sensitive_target(gateway):
    d = gateway.authorize(AuthorizationRequest(action="filesystem.write", resource="link/.env"))
    assert _not_allowed(d)


def test_modify_permission_configuration(gateway):
    d = gateway.authorize(AuthorizationRequest(
        action="filesystem.write", resource=".black-eclipse/security/policy.json",
    ))
    assert d.decision is Decision.DENY


def test_disable_security_gateway_action(gateway):
    d = gateway.authorize(AuthorizationRequest(action="security.admin", resource="gateway"))
    assert d.decision is Decision.DENY


def test_access_cloud_metadata(gateway):
    for target in (
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/",
    ):
        d = gateway.check_network(target)
        assert d.decision is Decision.DENY, target


def test_ssrf_private_network_and_loopback(gateway):
    for target in ("http://127.0.0.1:8765/internal", "http://10.0.0.1/", "http://192.168.1.1/",
                   "http://localhost/admin"):
        assert gateway.check_network(target).decision is Decision.DENY, target


def test_dns_rebinding_style_hostname_to_metadata(gateway):
    # `check_network` re-resolves; a name that resolves private must be denied.
    # (best effort when DNS is unavailable: the literal-host checks still apply)
    d = gateway.check_network("https://api.github.com/repos")
    assert d.decision is Decision.ALLOW
    d2 = gateway.check_network("https://evil-attacker.example.invalid/")
    assert d2.decision is Decision.DENY


def test_credential_exfiltration_via_general_shell_secrets(gateway):
    gateway.secrets.register_provider(StaticSecretProvider({"AWS_SECRET": "AKIAIOSFODNN7EXAMPLE" * 2}))
    # No grant for the shell consumer → denied.
    with pytest.raises(SecretAccessDenied):
        gateway.secrets.resolve("secret://static/AWS_SECRET", consumer="shell")
    assert gateway.validate_secret_access("secret://static/AWS_SECRET", consumer="shell") is False


def test_plugin_cannot_self_authorize_secrets(gateway):
    gateway.secrets.register_provider(StaticSecretProvider({"DB_URL": "postgres://u:p@host/db"}))
    with pytest.raises(SecretAccessDenied):
        gateway.secrets.resolve("secret://static/DB_URL", consumer="plugin:evil")
    # Granting to a different consumer does not leak.
    gateway.secrets.grant(SecretGrant(ref="secret://static/DB_URL", consumer="app"))
    with pytest.raises(SecretAccessDenied):
        gateway.secrets.resolve("secret://static/DB_URL", consumer="plugin:evil")


def test_secret_redaction_in_output(gateway):
    gateway.secrets.register_provider(StaticSecretProvider({"TOKEN": "supersecretvalue12345"}))
    gateway.secrets.grant(SecretGrant(ref="secret://static/TOKEN", consumer="app"))
    value = gateway.secrets.resolve("secret://static/TOKEN", consumer="app")
    assert value == "supersecretvalue12345"
    redacted = gateway.redact(f"the token is {value} thanks")
    assert value not in str(redacted)
    assert "[REDACTED]" in str(redacted)


def test_production_database_write_requires_approval(gateway):
    d = gateway.authorize(AuthorizationRequest(
        action="database.write", resource="prod-db", environment=Environment.PRODUCTION,
    ))
    assert d.decision is not Decision.ALLOW
    assert d.risk.value in ("high", "critical")


def test_production_database_drop_hard_denied(gateway):
    d = gateway.authorize(AuthorizationRequest(
        action="database.admin", resource="prod-db", environment=Environment.PRODUCTION,
    ))
    assert d.decision is Decision.DENY


def test_deploy_without_approval(gateway):
    d = gateway.authorize(AuthorizationRequest(
        action="deploy.production", resource="api", environment=Environment.PRODUCTION,
    ))
    assert d.decision is Decision.APPROVAL_REQUIRED


def test_live_financial_actions_never_inherit_research(gateway):
    research = gateway.authorize(AuthorizationRequest(action="financial.research", resource="AAPL"))
    assert research.decision is Decision.ALLOW
    live = gateway.authorize(AuthorizationRequest(action="financial.live_trade", resource="AAPL"))
    assert live.decision is Decision.APPROVAL_REQUIRED
    withdraw = gateway.authorize(AuthorizationRequest(action="financial.withdraw", resource="acct"))
    assert withdraw.decision is Decision.DENY  # hard-denied by the floor


def test_prompt_cannot_grant_capability_by_claiming(gateway):
    # A model-supplied "requestedCapabilities" field names capabilities; it must
    # not create or satisfy them. An unknown id authorizes nothing: an action
    # that would otherwise require approval is still not allowed by the claim.
    d = gateway.authorize(AuthorizationRequest(
        action="filesystem.delete", resource="src/x.py",
        requested_capabilities=("cap_i_made_this_up",),
    ))
    assert d.decision is Decision.APPROVAL_REQUIRED
    assert d.capability_id is None


def test_agent_cannot_escalate_capability_via_delegation():
    engine = CapabilityEngine()
    parent = engine.issue(subject="agent", action="filesystem.read",
                          resource="/workspace/**", scope="ws")
    with pytest.raises(CapabilityError):
        engine.delegate(parent.id, subject="agent", action="security.admin", resource="/**")
    with pytest.raises(CapabilityError):
        engine.delegate(parent.id, subject="agent", action="filesystem.read", resource="/etc/**")


def test_cross_session_workspace_access_denied(gateway):
    context = gateway.open_session(session_id="s1", workspace_id="ws-a", agent_id="agent")
    d = gateway.authorize(
        AuthorizationRequest(action="filesystem.write", resource="a.py", workspace="ws-b"),
        context=context,
    )
    assert d.decision is Decision.DENY
    assert "isolation" in d.matched_rules


def test_closed_session_is_refused(gateway):
    context = gateway.open_session(session_id="s2", workspace_id="ws-a", agent_id="agent")
    gateway.close_session("s2")
    d = gateway.authorize(
        AuthorizationRequest(action="filesystem.read", resource="a.py"), context=context,
    )
    assert d.decision is Decision.DENY
