"""Zulip provider: self-echo filter, queue lifecycle, basic auth, stream sends."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.zulip import ZulipProvider
from harness.channels.transport import OutboundMessage

BOT = "eclipse-bot@example.com"


def _provider(**kw) -> ZulipProvider:
    base = dict(site="https://chat.example.com", bot_email=BOT, api_key="k-1",
                default_stream="trading")
    base.update(kw)
    return ZulipProvider(**base)


def _msg(text="hello", chat="trading"):
    return OutboundMessage(kind="zulip", external_chat=chat, text=text)


def _event(*, sender="@alice@example.com", body="hi", event_id=1, kind="stream", stream="trading"):
    message = {
        "id": event_id,
        "sender_id": 42,
        "sender_email": sender,
        "sender_full_name": "Alice",
        "type": kind,
        "content": body,
    }
    if kind == "stream":
        message["display_recipient"] = stream
        message["subject"] = "nvda"
    return {"id": event_id, "type": "message", "message": message}


# -- spec / factory ---------------------------------------------------------


def test_the_spec_is_a_pull_provider_with_three_required_fields():
    spec = R.spec_for("zulip")
    assert spec is not None
    assert spec.inbound_mode == "poll"
    assert set(spec.required_keys) == {"site", "botEmail", "apiKey"}
    assert "zulip" in R.KINDS and "zulip" in R.POLL_KINDS
    assert "zulip" not in R.OUTBOUND_KINDS


def test_build_provider_needs_all_three_credentials():
    def ctx(values):
        return ProviderContext(kind="zulip", config={}, secret=lambda key: values.get(key, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"site": "https://x", "botEmail": BOT})) is None
    provider = R.build_provider(
        ctx({"site": "https://x", "botEmail": BOT, "apiKey": "k"}))
    assert isinstance(provider, ZulipProvider)


# -- inbound ----------------------------------------------------------------


def test_a_stream_message_becomes_inbound_with_the_stream_as_the_chat():
    messages = _provider()._to_inbound([_event(body="how is NVDA?")])
    assert len(messages) == 1
    message = messages[0]
    assert message.kind == "zulip"
    assert message.external_chat == "trading"
    assert message.text == "how is NVDA?"
    assert message.platform_message_id == "1"
    assert message.raw["topic"] == "nvda"


def test_the_bot_ignores_its_own_messages():
    assert _provider()._to_inbound([_event(sender=BOT)]) == []


def test_a_direct_message_is_labelled_direct():
    messages = _provider()._to_inbound([_event(kind="private")])
    assert messages[0].external_chat == "direct"


def test_non_message_and_empty_events_are_dropped():
    provider = _provider()
    assert provider._to_inbound([{"type": "heartbeat", "id": 2}]) == []
    assert provider._to_inbound([_event(body="   ")]) == []
    assert provider._to_inbound([]) == []


# -- outbound ---------------------------------------------------------------


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"result": "success", "id": 7}

    def json(self):
        return self._body


class _Client:
    def __init__(self, status, record, body=None):
        self._status = status
        self._record = record
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, auth=None):
        self._record.append(("POST", url, data, auth))
        return _Resp(self._status, self._body)

    async def get(self, url, params=None, auth=None):
        self._record.append(("GET", url, params, auth))
        return _Resp(200, {"result": "success", "events": []})


def test_send_posts_to_the_stream_topic_with_basic_auth(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg())) is True
    method, url, data, auth = record[0]
    assert method == "POST"
    assert url == "https://chat.example.com/api/v1/messages"
    assert data["type"] == "stream" and data["to"] == "trading"
    assert data["topic"] == "eclipse"
    assert auth == (BOT, "k-1")


def test_the_message_stream_overrides_the_default(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    asyncio.run(_provider().send(_msg(chat="research")))
    assert record[0][2]["to"] == "research"


def test_an_empty_send_posts_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg(text="  "))) is False
    assert asyncio.run(_provider(default_stream="").send(_msg(chat=""))) is False
    assert record == []


def test_an_error_result_or_http_status_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(400, record))
    assert asyncio.run(_provider().send(_msg())) is False
    monkeypatch.setattr("httpx.AsyncClient",
                        lambda **kw: _Client(200, record, {"result": "error", "msg": "bad topic"}))
    assert asyncio.run(_provider().send(_msg())) is False


# -- queue lifecycle --------------------------------------------------------


def test_registering_stores_the_queue_and_position(monkeypatch):
    class _Client2(_Client):
        async def post(self, url, data=None, auth=None):
            return _Resp(200, {"result": "success", "queue_id": "q-1", "last_event_id": 5})

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client2(200, []))
    provider = _provider()

    async def scenario():
        await provider._register()
        assert provider._queue_id == "q-1"
        assert provider._last_event_id == 5

    asyncio.run(scenario())


def test_events_advance_the_last_event_id(monkeypatch):
    record: list = []

    class _Client3(_Client):
        async def get(self, url, params=None, auth=None):
            record.append(params)
            return _Resp(200, {"result": "success", "events": [
                {"id": 9, "type": "message"}, {"id": 11, "type": "message"}]})

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client3(200, []))
    provider = _provider()
    provider._queue_id = "q-1"

    async def scenario():
        events = await provider._events()
        assert len(events) == 2
        assert provider._last_event_id == 11
        assert record[0]["queue_id"] == "q-1"

    asyncio.run(scenario())


def test_a_dead_queue_is_dropped_so_the_poller_re_registers(monkeypatch):
    class _Client4(_Client):
        async def get(self, url, params=None, auth=None):
            return _Resp(400, {"result": "error", "msg": "bad event queue id"})

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client4(400, []))
    provider = _provider()
    provider._queue_id = "q-dead"

    async def scenario():
        await provider._events()
        assert provider._queue_id == ""

    asyncio.run(scenario())


def test_an_incomplete_provider_never_starts_polling():
    provider = _provider(api_key="")

    async def scenario():
        await asyncio.wait_for(provider.run(lambda m: None), timeout=1)

    asyncio.run(scenario())
