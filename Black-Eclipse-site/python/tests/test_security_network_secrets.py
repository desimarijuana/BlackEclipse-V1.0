"""Network policy + secrets manager behavior."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-net-"), "agent-memory.db"),
)

from harness.security.models import Decision
from harness.security.network import NetworkPolicyEngine, NetworkRule
from harness.security.secrets import (
    SecretAccessDenied,
    SecretGrant,
    SecretsManager,
    StaticSecretProvider,
    build_default_secrets_manager,
)


# ── network ──────────────────────────────────────────────────────────────────
def test_default_deny():
    engine = NetworkPolicyEngine()
    assert engine.check("https://api.github.com/") is Decision.DENY


def test_explicit_allow_and_subdomain():
    engine = NetworkPolicyEngine([NetworkRule(host="github.com", verdict="allow")])
    assert engine.check("https://github.com/x") is Decision.ALLOW
    assert engine.check("https://api.github.com/x") is Decision.ALLOW  # subdomain
    assert engine.check("https://evil.com/x") is Decision.DENY


def test_cidr_rule_and_private_address_refused_by_ssrf():
    # An allow rule for a private CIDR still cannot make a private target reachable
    # because the SSRF guard runs first.
    engine = NetworkPolicyEngine([NetworkRule(host="10.0.0.0/8", verdict="allow")])
    assert engine.check("http://10.0.0.5/") is Decision.DENY


def test_method_and_path_rules_and_scheme():
    engine = NetworkPolicyEngine([
        NetworkRule(host="api.github.com", protocol="https", method="GET", path="/repos/*", verdict="allow"),
    ])
    assert engine.check("https://api.github.com/repos/x", method="GET") is Decision.ALLOW
    assert engine.check("http://api.github.com/repos/x", method="GET") is Decision.DENY  # scheme
    assert engine.check("https://api.github.com/other", method="GET") is Decision.DENY  # path
    assert engine.check("https://api.github.com/repos/x", method="POST") is Decision.DENY  # method


def test_metadata_and_loopback_always_denied():
    engine = NetworkPolicyEngine([NetworkRule(host="*", verdict="allow")])
    assert engine.check("http://169.254.169.254/") is Decision.DENY
    assert engine.check("http://127.0.0.1/") is Decision.DENY


def test_redirect_revalidation():
    engine = NetworkPolicyEngine([NetworkRule(host="github.com", verdict="allow")])
    assert engine.check_redirect("https://github.com/a", "https://evil.com/b") is Decision.DENY


# ── secrets ──────────────────────────────────────────────────────────────────
def test_secret_ref_parsing():
    assert SecretsManager.parse_ref("secret://env/GITHUB_TOKEN") == ("env", "GITHUB_TOKEN")
    assert SecretsManager.parse_ref("secret://GITHUB_TOKEN") == (None, "GITHUB_TOKEN")
    assert SecretsManager.parse_ref("not-a-ref") == (None, "")


def test_secret_scoped_to_consumer_and_action():
    manager = SecretsManager()
    manager.register_provider(StaticSecretProvider({"TOKEN": "abcdef123456"}))
    manager.grant(SecretGrant(ref="secret://static/TOKEN", consumer="github", actions=("network.request",)))
    assert manager.resolve("secret://static/TOKEN", consumer="github", action="network.request")
    with_secret = manager.resolve_optional("secret://static/TOKEN", consumer="github", action="network.request")
    assert with_secret == "abcdef123456"
    # Wrong consumer or wrong action → denied.
    assert manager.resolve_optional("secret://static/TOKEN", consumer="shell", action="network.request") is None
    assert manager.resolve_optional("secret://static/TOKEN", consumer="github", action="shell.execute") is None


def test_secret_grant_expiry():
    manager = SecretsManager()
    manager.register_provider(StaticSecretProvider({"K": "value-value"}))
    manager.grant(SecretGrant(ref="secret://static/K", consumer="app", expires_at=time.time() - 1))
    with pytest.raises(SecretAccessDenied):
        manager.resolve("secret://static/K", consumer="app")


def test_inject_env_only_named_refs():
    manager = SecretsManager()
    manager.register_provider(StaticSecretProvider({"A": "aaa-value", "B": "bbb-value"}))
    manager.grant(SecretGrant(ref="secret://static/A", consumer="proc"))
    env = manager.inject_env({"A_KEY": "secret://static/A", "B_KEY": "secret://static/B"}, consumer="proc")
    assert env == {"A_KEY": "aaa-value"}  # B had no grant → omitted


def test_build_default_manager_has_env_and_local():
    manager = build_default_secrets_manager()
    assert "env" in manager.providers()
    assert "local" in manager.providers()
