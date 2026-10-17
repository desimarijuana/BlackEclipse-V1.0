"""Discord provider tests: message normalization, reply chunking/REST call and
service provider construction (no live Gateway connection)."""

from __future__ import annotations

import pytest

from harness.channels.providers import discord as discord_mod
from harness.channels.providers.discord import DiscordProvider
from harness.channels.service import ChannelService
from harness.channels.transport import OutboundMessage
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
def env(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store, None, _StubService(store).channels
    store.close()


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status


class _FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def post(self, url, headers=None, json=None):  # noqa: ANN001, A002
        _FakeAsyncClient.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(200)


def test_to_inbound_maps_fields():
    provider = DiscordProvider(bot_token="tok")
    message = provider._to_inbound({  # noqa: SLF001
        "id": "m1",
        "channel_id": "c1",
        "content": "hello",
        "author": {"id": "u1", "username": "neo", "global_name": "Neo"},
    })
    assert message is not None
    assert message.external_id == "u1"
    assert message.external_chat == "c1"
    assert message.text == "hello"
    assert message.platform_message_id == "m1"
    assert message.display_name == "Neo"


def test_to_inbound_skips_empty_content():
    provider = DiscordProvider(bot_token="tok")
    assert provider._to_inbound({"id": "m", "channel_id": "c", "content": "  ", "author": {"id": "u"}}) is None  # noqa: SLF001


def test_identify_payload_has_token_and_intents():
    provider = DiscordProvider(bot_token="tok")
    payload = provider._identify_payload()  # noqa: SLF001
    assert payload["op"] == 2
    assert payload["d"]["token"] == "tok"
    # GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT
    assert payload["d"]["intents"] == 37377


async def test_send_chunks_and_authorizes(monkeypatch):
    monkeypatch.setattr(discord_mod.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []
    provider = DiscordProvider(bot_token="tok")
    ok = await provider.send(OutboundMessage(kind="discord", external_chat="123", text="x" * 2500))
    assert ok is True
    assert len(_FakeAsyncClient.calls) == 2  # 2000 + 500
    first = _FakeAsyncClient.calls[0]
    assert first["headers"]["Authorization"] == "Bot tok"
    assert first["url"].endswith("/channels/123/messages")
    assert first["json"]["allowed_mentions"] == {"parse": []}


async def test_send_failure_reports_false(monkeypatch):
    class _Fail(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):  # noqa: ANN001, A002
            return _FakeResponse(403)

    monkeypatch.setattr(discord_mod.httpx, "AsyncClient", _Fail)
    provider = DiscordProvider(bot_token="tok")
    assert await provider.send(OutboundMessage(kind="discord", external_chat="1", text="hi")) is False


def test_service_builds_discord_provider(env):
    _, _, service = env
    service.configure("discord", enabled=True, config={"botToken": "tok"})
    assert service._is_configured("discord", {"botToken": "tok"})  # noqa: SLF001
    provider = service._build_provider("discord")  # noqa: SLF001
    assert provider is not None and provider.kind == "discord"
