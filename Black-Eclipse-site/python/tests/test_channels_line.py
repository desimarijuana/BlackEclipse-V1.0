"""LINE provider: body-only HMAC inbound, group/room chat ids, push outbound."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers import line
from harness.channels.transport import OutboundMessage
from harness.routers import channels as channels_router

SECRET = "chan-secret"


def _event(*, text="hi", user="U1", group="", room="", event_id="ev-1",
           message_type="text", kind="message"):
    source = {"type": "user", "userId": user}
    if group:
        source = {"type": "group", "groupId": group, "userId": user}
    elif room:
        source = {"type": "room", "roomId": room, "userId": user}
    return {
        "type": kind,
        "webhookEventId": event_id,
        "replyToken": "rt",
        "source": source,
        "message": {"type": message_type, "id": "m-1", "text": text},
    }


def _payload(*events):
    return {"destination": "Ubot", "events": list(events)}


# -- signature --------------------------------------------------------------


def test_the_signature_is_hmac_sha256_of_the_raw_body():
    body = json.dumps(_payload(_event())).encode()
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    assert line.signature_for(SECRET, body) == expected


def test_a_changed_body_or_secret_or_missing_signature_is_refused():
    body = json.dumps(_payload(_event())).encode()
    good = line.signature_for(SECRET, body)
    assert line.verify(SECRET, body=body, signature=good) is True
    assert line.verify(SECRET, body=body + b" ", signature=good) is False
    assert line.verify("other", body=body, signature=good) is False
    assert line.verify(SECRET, body=body, signature=None) is False
    assert line.verify("", body=body, signature=good) is False


# -- parsing ----------------------------------------------------------------


def test_a_user_text_message_becomes_inbound():
    messages = line.parse_webhook(_payload(_event(text="how is NVDA?")))
    assert len(messages) == 1
    message = messages[0]
    assert message.kind == "line"
    assert message.external_id == "U1"
    assert message.external_chat == "U1"
    assert message.text == "how is NVDA?"
    assert message.platform_message_id == "ev-1"


def test_a_group_message_keeps_the_group_as_the_chat_and_the_user_as_sender():
    messages = line.parse_webhook(_payload(_event(group="C-group")))
    assert messages[0].external_chat == "C-group"
    assert messages[0].external_id == "U1"


def test_a_room_message_uses_the_room_id():
    assert line.parse_webhook(_payload(_event(room="R-room")))[0].external_chat == "R-room"


def test_non_text_and_non_message_events_are_dropped():
    provider_events = [
        _event(message_type="sticker"),
        _event(kind="follow"),
        _event(kind="postback"),
    ]
    assert line.parse_webhook(_payload(*provider_events)) == []
    assert line.parse_webhook({}) == []


# -- outbound ---------------------------------------------------------------


class _Resp:
    def __init__(self, status=200):
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


def _provider(**kw) -> line.LineProvider:
    base = dict(channel_access_token="tok", channel_secret=SECRET)
    base.update(kw)
    return line.LineProvider(**base)


def test_push_sends_a_text_message_with_a_bearer_token(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    message = OutboundMessage(kind="line", external_chat="U1", text="hi")
    import asyncio

    assert asyncio.run(_provider().send(message)) is True
    url, headers, body = record[0]
    assert url == "https://api.line.me/v2/bot/message/push"
    assert headers["Authorization"] == "Bearer tok"
    assert body == {"to": "U1", "messages": [{"type": "text", "text": "hi"}]}


def test_an_empty_target_or_missing_token_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    import asyncio

    assert asyncio.run(_provider().send(
        OutboundMessage(kind="line", external_chat="", text="hi"))) is False
    assert asyncio.run(_provider(channel_access_token="").send(
        OutboundMessage(kind="line", external_chat="U1", text="hi"))) is False
    assert record == []


# -- spec + route -----------------------------------------------------------


def test_the_spec_is_push_with_two_required_secrets():
    spec = R.spec_for("line")
    assert spec is not None
    assert spec.inbound_mode == "push"
    assert set(spec.required_keys) == {"channelAccessToken", "channelSecret"}
    assert "line" in R.KINDS and "line" in R.PUSH_KINDS
    assert "line" not in R.POLL_KINDS and "line" not in R.OUTBOUND_KINDS


def test_build_provider_needs_both_secrets():
    def ctx(values):
        return ProviderContext(kind="line", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"channelAccessToken": "t"})) is None
    provider = R.build_provider(ctx({"channelAccessToken": "t", "channelSecret": SECRET}))
    assert isinstance(provider, line.LineProvider)


class _FakeChannels:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.accepted: list = []

    def secret_value(self, kind: str, key: str) -> str:
        del kind
        return self._values.get(key, "")

    def handle_inbound(self, message):
        self.accepted.append(message)
        return True


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(channels_router.router)
    channels_router._channels = lambda: service
    return TestClient(app)


def test_the_route_accepts_a_signed_webhook_and_enqueues_text():
    service = _FakeChannels({"channelSecret": SECRET})
    body = json.dumps(_payload(_event(text="hi"), _event(message_type="sticker"))).encode()
    original = channels_router._enqueue
    channels_router._enqueue = lambda svc, message, background: svc.handle_inbound(message)
    try:
        res = _client(service).post(
            "/channels/webhook/line", content=body,
            headers={"X-Line-Signature": line.signature_for(SECRET, body),
                     "Content-Type": "application/json"})
    finally:
        channels_router._enqueue = original
    assert res.status_code == 200
    assert res.json()["accepted"] == 1
    assert [m.text for m in service.accepted] == ["hi"]


def test_the_route_refuses_an_unsigned_body():
    service = _FakeChannels({"channelSecret": SECRET})
    body = json.dumps(_payload(_event())).encode()
    res = _client(service).post("/channels/webhook/line", content=body,
                                headers={"X-Line-Signature": "nope"})
    assert res.status_code == 403
