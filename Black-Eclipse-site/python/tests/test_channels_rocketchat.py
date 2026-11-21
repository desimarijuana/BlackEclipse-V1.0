"""Rocket.Chat provider: watermark polling, self-echo drop, two-header auth."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.rocketchat import RocketChatProvider
from harness.channels.transport import OutboundMessage

BOT = "bot-id"
ROOM = "room-1"


def _provider(**kw) -> RocketChatProvider:
    base = dict(base_url="https://chat.example.com", auth_token="tok",
                user_id=BOT, room_id=ROOM, poll_seconds=1)
    base.update(kw)
    return RocketChatProvider(**base)


def _msg(text="hello", chat=ROOM):
    return OutboundMessage(kind="rocketchat", external_chat=chat, text=text)


def _message(*, sender="alice-id", text="hi", message_id="m1",
             ts="2026-11-01T12:00:00.000Z", room=ROOM):
    return {"_id": message_id, "msg": text, "rid": room, "ts": ts,
            "u": {"_id": sender, "username": "alice"}}


# -- spec / factory ---------------------------------------------------------


def test_the_spec_is_a_pull_provider_with_three_required_fields():
    spec = R.spec_for("rocketchat")
    assert spec is not None
    assert spec.inbound_mode == "poll"
    assert set(spec.required_keys) == {"baseUrl", "authToken", "userId"}
    assert "rocketchat" in R.KINDS and "rocketchat" in R.POLL_KINDS
    assert "rocketchat" not in R.OUTBOUND_KINDS


def test_build_provider_needs_the_three_identity_fields():
    def ctx(values):
        return ProviderContext(kind="rocketchat", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"baseUrl": "https://x", "authToken": "t"})) is None
    provider = R.build_provider(
        ctx({"baseUrl": "https://x", "authToken": "t", "userId": BOT}))
    assert isinstance(provider, RocketChatProvider)


# -- inbound ----------------------------------------------------------------


def test_a_message_becomes_inbound_with_the_room_as_the_chat():
    messages = _provider()._to_inbound([_message(text="how is NVDA?")])
    assert len(messages) == 1
    inbound = messages[0]
    assert inbound.kind == "rocketchat"
    assert inbound.external_chat == ROOM
    assert inbound.external_id == "alice-id"
    assert inbound.text == "how is NVDA?"
    assert inbound.platform_message_id == "m1"


def test_the_bot_ignores_its_own_posts():
    assert _provider()._to_inbound([_message(sender=BOT)]) == []


def test_the_same_message_id_is_delivered_once():
    provider = _provider()
    assert len(provider._to_inbound([_message(message_id="m9")])) == 1
    assert provider._to_inbound([_message(message_id="m9")]) == []


def test_empty_and_malformed_messages_are_dropped():
    provider = _provider()
    assert provider._to_inbound([_message(text="   ")]) == []
    assert provider._to_inbound([{"_id": "x", "msg": "hi"}]) == []   # no author
    assert provider._to_inbound([]) == []


# -- outbound ---------------------------------------------------------------


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"success": True}

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

    async def post(self, url, headers=None, json=None):
        self._record.append(("POST", url, headers, json))
        return _Resp(self._status, self._body)

    async def get(self, url, headers=None, params=None):
        self._record.append(("GET", url, headers, params))
        return _Resp(200, {"success": True, "messages": []})


def test_send_posts_with_the_two_auth_headers(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg())) is True
    method, url, headers, body = record[0]
    assert url == "https://chat.example.com/api/v1/chat.postMessage"
    assert headers["X-Auth-Token"] == "tok"
    assert headers["X-User-Id"] == BOT
    assert body == {"roomId": ROOM, "text": "hello"}


def test_the_message_room_overrides_the_default(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    asyncio.run(_provider().send(_msg(chat="room-2")))
    assert record[0][3]["roomId"] == "room-2"


def test_an_empty_send_posts_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg(text=" "))) is False
    assert asyncio.run(_provider(room_id="").send(_msg(chat=""))) is False
    assert record == []


def test_an_http_error_or_success_false_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(401, record))
    assert asyncio.run(_provider().send(_msg())) is False
    monkeypatch.setattr("httpx.AsyncClient",
                        lambda **kw: _Client(200, record, {"success": False}))
    assert asyncio.run(_provider().send(_msg())) is False


# -- polling ----------------------------------------------------------------


def test_history_advances_the_watermark_to_the_newest_timestamp(monkeypatch):
    record: list = []

    class _Client2(_Client):
        async def get(self, url, headers=None, params=None):
            record.append(params)
            return _Resp(200, {"success": True, "messages": [
                _message(message_id="a", ts="2026-11-01T12:00:05.000Z"),
                _message(message_id="b", ts="2026-11-01T12:00:01.000Z"),
            ]})

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client2(200, []))
    provider = _provider()
    provider._oldest = "2026-11-01T12:00:00.000Z"

    async def scenario():
        await provider._history()
        assert provider._oldest == "2026-11-01T12:00:05.000Z"
        assert record[0]["oldest"] == "2026-11-01T12:00:00.000Z"

    asyncio.run(scenario())


def test_the_first_poll_starts_from_now_not_from_history(monkeypatch):
    # Replaying a room's whole history into the agent would answer questions
    # nobody asked, so the watermark is initialised to "now" before polling.
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, []))
    provider = _provider()

    async def scenario():
        task = asyncio.create_task(provider.run(lambda m: None))
        await asyncio.sleep(0.05)
        await provider.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert provider._oldest.endswith("Z")


def test_a_provider_without_a_room_reads_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    provider = _provider(room_id="")

    async def scenario():
        assert await provider._history() == []

    asyncio.run(scenario())
    assert record == []


def test_an_incomplete_provider_never_starts_polling():
    provider = _provider(user_id="")

    async def scenario():
        await asyncio.wait_for(provider.run(lambda m: None), timeout=1)

    asyncio.run(scenario())
