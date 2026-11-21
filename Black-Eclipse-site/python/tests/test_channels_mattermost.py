"""Mattermost provider: outbound-only posts, credential probe, no false inbound."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.mattermost import MattermostProvider
from harness.channels.transport import OutboundMessage


def _msg(text="hello", chat="chan-1"):
    return OutboundMessage(kind="mattermost", external_chat=chat, text=text)


class _Resp:
    def __init__(self, status=201):
        self.status_code = status


class _Client:
    def __init__(self, status, record):
        self._status = status
        self._record = record

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self._record.append((url, headers, json))
        return _Resp(self._status)


def _provider(**kw):
    base = dict(base_url="https://chat.example.com", bot_token="tok", channel_id="chan-1")
    base.update(kw)
    return MattermostProvider(**base)


def test_the_spec_is_outbound_only_and_requires_three_fields():
    spec = R.spec_for("mattermost")
    assert spec is not None
    assert spec.inbound_mode == "none"
    assert set(spec.required_keys) == {"baseUrl", "botToken", "channelId"}
    assert "mattermost" in R.KINDS


def test_send_posts_to_the_channel_with_a_bearer_token(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    ok = asyncio.run(_provider().send(_msg()))
    assert ok is True
    url, headers, body = record[0]
    assert url == "https://chat.example.com/api/v4/posts"
    assert headers["Authorization"] == "Bearer tok"
    assert body == {"channel_id": "chan-1", "message": "hello"}


def test_the_message_channel_overrides_the_default(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    asyncio.run(_provider().send(_msg(chat="other")))
    assert record[0][2]["channel_id"] == "other"


def test_a_blank_message_or_channel_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    assert asyncio.run(_provider().send(_msg(text="   "))) is False
    # no default channel and no per-message channel -> nothing to post to
    assert asyncio.run(_provider(channel_id="").send(_msg(chat=""))) is False
    assert record == []


def test_an_http_error_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(403, record))
    assert asyncio.run(_provider().send(_msg())) is False


def test_a_transport_error_is_a_false(monkeypatch):
    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("connection reset")

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Boom())
    assert asyncio.run(_provider().send(_msg())) is False


def test_run_blocks_until_stopped():
    provider = _provider()

    async def scenario():
        task = asyncio.create_task(provider.run(lambda m: None))
        await asyncio.sleep(0.01)
        assert not task.done()
        await provider.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())


def test_build_provider_requires_all_three_fields():
    def ctx(values):
        return ProviderContext(kind="mattermost", config={}, secret=lambda key: values.get(key, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"baseUrl": "https://x", "botToken": "t"})) is None
    provider = R.build_provider(ctx({"baseUrl": "https://x", "botToken": "t", "channelId": "c"}))
    assert isinstance(provider, MattermostProvider)
