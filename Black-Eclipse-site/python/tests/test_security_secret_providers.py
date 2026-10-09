"""Production secret providers — CLI + OS keychain, with honest availability."""

from __future__ import annotations

import os
import sys
import tempfile

from harness.security.secrets import (
    CliSecretProvider,
    OsKeychainProvider,
    StaticSecretProvider,
    build_default_secrets_manager,
)


def test_cli_provider_resolves_via_configured_command():
    provider = CliSecretProvider({
        "TOKEN": [sys.executable, "-c", "print('resolved-value')"],
    })
    assert provider.available() is True
    assert provider.get("TOKEN") == "resolved-value"


def test_cli_provider_template_substitution():
    provider = CliSecretProvider({
        "DB_PASS": [sys.executable, "-c", "import sys; print('got:' + sys.argv[1])", "{name}"],
    })
    assert provider.get("DB_PASS") == "got:DB_PASS"


def test_cli_provider_failure_is_none_never_fabricated():
    provider = CliSecretProvider({"X": [sys.executable, "-c", "import sys; sys.exit(2)"]})
    assert provider.get("X") is None
    # Missing CLI → None, not an exception.
    assert provider.get("unknown") is None


def test_os_keychain_status_is_honest():
    status = OsKeychainProvider("eclipse").status()
    assert status["provider"] == "keychain"
    assert isinstance(status["available"], bool)


def test_default_manager_registers_env_local_and_keychain():
    manager = build_default_secrets_manager()
    providers = manager.providers()
    assert "env" in providers
    assert "local" in providers
    assert "keychain" in providers
    manager.register_provider(StaticSecretProvider({"K": "v"}))
    assert "static" in manager.providers()


def test_cli_provider_from_env_config_is_wired():
    os.environ["BLACK_ECLIPSE_SECRETS_CLI"] = (
        '{"*": ["' + sys.executable.replace("\\", "\\\\") + '", "-c", "print(1)"]}'
    )
    try:
        manager = build_default_secrets_manager()
        assert "cli" in manager.providers()
    finally:
        os.environ.pop("BLACK_ECLIPSE_SECRETS_CLI", None)


def test_malformed_cli_config_is_reported_not_trusted():
    os.environ["BLACK_ECLIPSE_SECRETS_CLI"] = "not-json"
    try:
        manager = build_default_secrets_manager()
        assert "cli" in manager.providers()
        assert manager._providers["cli"].status()["available"] is False  # noqa: SLF001
    finally:
        os.environ.pop("BLACK_ECLIPSE_SECRETS_CLI", None)
