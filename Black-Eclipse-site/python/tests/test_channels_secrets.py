"""Channel credential storage tests: encrypted at rest, redacted presence, and
the honest legacy fallback when the vault is unavailable."""

from __future__ import annotations

import pytest

from harness.channels.service import ChannelService
from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry


class _DummyGateway:
    secrets = None
    audit = None


class _StubService:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.security = _DummyGateway()
        self.registry = ToolRegistry()
        self.channels = ChannelService(self)

    async def run(self, request):  # noqa: ANN001
        raise NotImplementedError


@pytest.fixture()
def service(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    svc = _StubService(memory).channels
    # `store` is the ChannelStore (the persistence surface these tests exercise).
    yield svc.store, svc
    memory.close()


def test_credentials_are_encrypted_at_rest(service):
    store, svc = service  # store is AgentMemoryStore; svc.store is ChannelStore
    assert svc.secretbox.available  # cryptography is installed in this environment
    svc.configure("telegram", enabled=True, config={"botToken": "super-secret-token", "agentId": "eclipse-agent"})

    # The plaintext token is NOT in the config JSON...
    plain = store.get_config("telegram")["config"]
    assert "botToken" not in plain
    assert plain.get("agentId") == "eclipse-agent"

    # ...it is stored as ciphertext...
    ciphertext = store.get_secret_ciphertext("telegram", "botToken")
    assert ciphertext and ciphertext != "super-secret-token"

    # ...and only resolves back through the vault.
    assert svc.secret_value("telegram", "botToken") == "super-secret-token"


def test_describe_redacts_and_reports_presence(service):
    _, svc = service
    svc.configure("slack", enabled=True, config={"botToken": "xoxb-abc", "signingSecret": "sss"})
    described = svc.describe_config("slack")
    assert described["config"]["botToken"] == "***"
    assert described["config"]["signingSecret"] == "***"
    assert described["configured"] is True
    assert set(described["secrets"]) >= {"botToken", "signingSecret"}
    assert described["secretsEncrypted"] is True


def test_delete_config_purges_secrets(service):
    store, svc = service  # store is AgentMemoryStore; svc.store is ChannelStore
    svc.configure("telegram", enabled=True, config={"botToken": "t"})
    assert store.list_secret_names("telegram") == ["botToken"]
    svc.delete_config("telegram")
    assert store.list_secret_names("telegram") == []
    assert store.get_config("telegram") is None


def test_fallback_when_vault_unavailable(service):
    store, svc = service  # store is AgentMemoryStore; svc.store is ChannelStore
    # Simulate a missing crypto backend: the vault reports unavailable and a
    # sensitive value falls back to the config JSON (zero-config preserved).
    svc.secretbox._fernet = None  # noqa: SLF001
    svc.secretbox._reason = "cryptography unavailable"  # noqa: SLF001
    svc.configure("telegram", enabled=True, config={"botToken": "legacy-literal"})
    assert store.get_config("telegram")["config"]["botToken"] == "legacy-literal"
    assert svc.secret_value("telegram", "botToken") == "legacy-literal"
    assert svc.describe_config("telegram")["secretsEncrypted"] is False

