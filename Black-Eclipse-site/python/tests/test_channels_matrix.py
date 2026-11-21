"""Matrix provider: self-echo filter, replay dedupe, room-id escaping, /sync."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.matrix import MatrixProvider
from harness.channels.transport import OutboundMessage

BOT = "@eclipse:example.org"
ROOM = "!abc:example.org"


def _provider(**kw) -> MatrixProvider:
    base = dict(
        homeserver_url="https://matrix.example.org",
        access_token="tok",
        user_id=BOT,
        default_room_id=ROOM,
    )
    base.update(kw)
    return MatrixProvider(**base)


def _msg(text="hello", chat=ROOM):
    return OutboundMessage(kind="matrix", external_chat=chat, text=text)


def _event(*, sender="@alice:example.org", body="hi", event_id="$e1",
           msgtype="m.text", room=ROOM):
    return room, {
        "type": "m.room.message",
        "event_id": event_id,
        "sender": sender,
        "content": {"msgtype": msgtype, "body": body},
    }


def _sync(*events, next_batch="s1"):
    rooms: dict = {}
    for room, event in events:
        rooms.setdefault(room, {"timeline": {"events": []}})["timeline"]["events"].append(event)
    return {"next_batch": next_batch, "rooms": {"join": rooms}}


# -- spec / factory ---------------------------------------------------------


def test_the_spec_polls_and_requires_the_bot_identity():
    spec = R.spec_for("matrix")
    assert spec is not None
    assert spec.inbound_mode == "poll"
    assert set(spec.required_keys) == {"homeserverUrl", "accessToken", "userId"}
    assert "matrix" in R.KINDS and "matrix" in R.POLL_KINDS
    assert "matrix" not in R.OUTBOUND_KINDS


def test_build_provider_requires_the_bot_user_id():
    def ctx(values):
        return ProviderContext(kind="matrix", config={}, secret=lambda key: values.get(key, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"homeserverUrl": "https://x", "accessToken": "t"})) is None
    provider = R.build_provider(
        ctx({"homeserverUrl": "https://x", "accessToken": "t", "userId": BOT})
    )
    assert isinstance(provider, MatrixProvider)


# -- inbound normalization --------------------------------------------------


def test_a_text_message_becomes_an_inbound_message():
    messages = _provider()._to_inbound(_sync(_event(body="how is NVDA?")))
    assert len(messages) == 1
    message = messages[0]
    assert message.kind == "matrix"
    assert message.external_id == "@alice:example.org"
    assert message.external_chat == ROOM
    assert message.text == "how is NVDA?"
    assert message.platform_message_id == "$e1"


def test_the_bot_ignores_its_own_messages():
    # Without this filter every reply would re-trigger the agent.
    assert _provider()._to_inbound(_sync(_event(sender=BOT))) == []


def test_a_replayed_event_is_delivered_once():
    provider = _provider()
    event = _event(event_id="$same")
    assert len(provider._to_inbound(_sync(event, next_batch="s1"))) == 1
    assert provider._to_inbound(_sync(event, next_batch="s2")) == []


def test_non_message_and_empty_events_are_dropped():
    provider = _provider()
    assert provider._to_inbound({"rooms": {"join": {ROOM: {"timeline": {"events": [
        {"type": "m.room.member", "event_id": "$m", "sender": "@a:x", "content": {}},
    ]}}}}}) == []
    assert provider._to_inbound(_sync(_event(body="   "))) == []
    assert provider._to_inbound(_sync(_event(msgtype="m.image"))) == []
    assert provider._to_inbound({}) == []


def test_events_in_several_rooms_are_all_normalized():
    provider = _provider()
    other = "!other:example.org"
    messages = provider._to_inbound(_sync(
        _event(event_id="$a"), _event(event_id="$b", room=other),
    ))
    assert sorted(m.external_chat for m in messages) == sorted([ROOM, other])


# -- outbound ---------------------------------------------------------------


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {"event_id": "$sent"}

    def json(self):
        return self._body


class _Client:
    def __init__(self, status, record):
        self._status = status
        self._record = record

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def put(self, url, headers=None, json=None):
        self._record.append((url, headers, json))
        return _Resp(self._status)

    async def get(self, url, headers=None, params=None):
        self._record.append((url, headers, params))
        return _Resp(200, {"next_batch": "s9", "rooms": {}})


def test_send_escapes_the_room_id_and_uses_the_bearer_token(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg())) is True
    url, headers, body = record[0]
    assert url.startswith(
        "https://matrix.example.org/_matrix/client/v3/rooms/%21abc%3Aexample.org/send/m.room.message/"
    )
    assert headers["Authorization"] == "Bearer tok"
    assert body["msgtype"] == "m.text" and body["body"] == "hello"


def test_the_message_room_overrides_the_default(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    asyncio.run(_provider().send(_msg(chat="!other:example.org")))
    assert "%21other%3Aexample.org" in record[0][0]


def test_a_send_with_nothing_to_say_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg(text="  "))) is False
    assert asyncio.run(_provider(default_room_id="").send(_msg(chat=""))) is False
    assert record == []


def test_an_http_error_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(403, record))
    assert asyncio.run(_provider().send(_msg())) is False


def test_our_own_sent_event_is_not_echoed_back(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    provider = _provider()
    asyncio.run(provider.send(_msg()))
    echo = _event(event_id="$sent", sender="@other:example.org", body="hello")
    assert provider._to_inbound(_sync(echo)) == []


# -- /sync driving ----------------------------------------------------------


def test_sync_advances_the_batch_token(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))

    async def scenario():
        provider = _provider()
        await provider._sync()
        assert provider._since == "s9"
        await provider._sync()
        assert record[1][2]["since"] == "s9"   # the second poll resumes

    asyncio.run(scenario())


def test_run_delivers_then_stops(monkeypatch):
    received: list = []

    async def fake_sync():
        # Yield to the loop: a coroutine that never suspends would starve the
        # scenario task and deadlock the test (and hide a spinning poller).
        await asyncio.sleep(0)
        return _sync(_event(body="ping"))

    monkeypatch.setattr(MatrixProvider, "_sync", lambda self: fake_sync())

    async def scenario():
        provider = _provider()
        task = asyncio.create_task(provider.run(lambda m: _collect(received, m)))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if received:
                break
        await provider.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert [m.text for m in received] == ["ping"]


async def _collect(bucket: list, message):
    bucket.append(message)


def test_an_incomplete_provider_never_starts_polling():
    provider = _provider(user_id="")

    async def scenario():
        await asyncio.wait_for(provider.run(lambda m: None), timeout=1)

    asyncio.run(scenario())
