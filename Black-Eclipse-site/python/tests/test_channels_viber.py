"""Viber provider: hex body HMAC, message parsing, send_message, route."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers import viber
from harness.channels.transport import OutboundMessage
from harness.routers import channels as channels_router

TOKEN = "viber-token"


def _payload(*, text="hi", sender="U1", event="message", message_type="text",
             token="mt-1"):
    return {
        "event": event,
        "timestamp": 1700000000000,
        "message_token": token,
        "sender": {"id": sender, "name": "Alice", "language": "en"},
        "message": {"type": message_type, "text": text},
    }


# -- signature --------------------------------------------------------------


def test_the_signature_is_hex_hmac_sha256_of_the_body():
    body = json.dumps(_payload()).encode()
    expected = hmac.new(TOKEN.encode(), body, hashlib.sha256).hexdigest()
    assert viber.signature_for(TOKEN, body) == expected
    assert len(expected) == 64           # hex, unlike LINE's base64


def test_a_bad_body_token_or_missing_signature_is_refused():
    body = json.dumps(_payload()).encode()
    good = viber.signature_for(TOKEN, body)
    assert viber.verify(TOKEN, body=body, signature=good) is True
    assert viber.verify(TOKEN, body=body + b" ", signature=good) is False
    assert viber.verify("other", body=body, signature=good) is False
    assert viber.verify(TOKEN, body=body, signature=None) is False


# -- parsing ----------------------------------------------------------------


def test_a_text_message_becomes_inbound():
    message = viber.parse_webhook(_payload(text="how is NVDA?"))
    assert message is not None
    assert message.kind == "viber"
    assert message.external_chat == "U1"
    assert message.text == "how is NVDA?"
    assert message.platform_message_id == "mt-1"
    assert message.display_name == "Alice"


def test_non_message_and_non_text_events_are_dropped():
    assert viber.parse_webhook(_payload(event="subscribed")) is None
    assert viber.parse_webhook(_payload(message_type="picture")) is None
    assert viber.parse_webhook(_payload(text="   ")) is None
    assert viber.parse_webhook({}) is None


def test_a_missing_sender_is_dropped():
    payload = _payload()
    payload["sender"] = {}
    assert viber.parse_webhook(payload) is None


# -- outbound ---------------------------------------------------------------


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"status": 0}

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

    async def post(self, url, json=None, headers=None):
        self._record.append((url, headers, json))
        return _Resp(self._status, self._body)


def test_send_posts_the_bot_payload_with_the_auth_header(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    provider = viber.ViberProvider(auth_token=TOKEN, sender_name="Eclipse")
    import asyncio

    assert asyncio.run(provider.send(
        OutboundMessage(kind="viber", external_chat="U1", text="hi"))) is True
    url, headers, body = record[0]
    assert url == "https://chatapi.viber.com/pa/send_message"
    assert headers["X-Viber-Auth-Token"] == TOKEN
    assert body["receiver"] == "U1" and body["type"] == "text"
    assert body["sender"]["name"] == "Eclipse"


def test_a_non_zero_status_or_http_error_is_a_false(monkeypatch):
    record: list = []
    provider = viber.ViberProvider(auth_token=TOKEN)
    import asyncio

    message = OutboundMessage(kind="viber", external_chat="U1", text="hi")
    monkeypatch.setattr("httpx.AsyncClient",
                        lambda **kw: _Client(200, record, {"status": 1}))
    assert asyncio.run(provider.send(message)) is False
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(500, record))
    assert asyncio.run(provider.send(message)) is False


def test_an_empty_target_or_token_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    import asyncio

    provider = viber.ViberProvider(auth_token=TOKEN)
    assert asyncio.run(provider.send(
        OutboundMessage(kind="viber", external_chat="", text="hi"))) is False
    assert asyncio.run(viber.ViberProvider(auth_token="").send(
        OutboundMessage(kind="viber", external_chat="U1", text="hi"))) is False
    assert record == []


# -- spec + route -----------------------------------------------------------


def test_the_spec_is_push_with_one_required_secret():
    spec = R.spec_for("viber")
    assert spec is not None
    assert spec.inbound_mode == "push"
    assert set(spec.required_keys) == {"authToken"}
    assert "viber" in R.KINDS and "viber" in R.PUSH_KINDS
    assert "viber" not in R.POLL_KINDS and "viber" not in R.OUTBOUND_KINDS


def test_build_provider_needs_the_token():
    def ctx(values):
        return ProviderContext(kind="viber", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    assert isinstance(R.build_provider(ctx({"authToken": TOKEN})), viber.ViberProvider)


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


def test_the_route_accepts_a_signed_webhook():
    service = _FakeChannels({"authToken": TOKEN})
    body = json.dumps(_payload()).encode()
    original = channels_router._enqueue
    channels_router._enqueue = lambda svc, message, background: svc.handle_inbound(message)
    app = FastAPI()
    app.include_router(channels_router.router)
    channels_router._channels = lambda: service
    try:
        res = TestClient(app).post(
            "/channels/webhook/viber", content=body,
            headers={"X-Viber-Content-Signature": viber.signature_for(TOKEN, body),
                     "Content-Type": "application/json"})
    finally:
        channels_router._enqueue = original
    assert res.status_code == 200
    assert [m.text for m in service.accepted] == ["hi"]


def test_the_route_refuses_an_unsigned_body():
    service = _FakeChannels({"authToken": TOKEN})
    body = json.dumps(_payload()).encode()
    app = FastAPI()
    app.include_router(channels_router.router)
    channels_router._channels = lambda: service
    res = TestClient(app).post("/channels/webhook/viber", content=body,
                               headers={"X-Viber-Content-Signature": "nope"})
    assert res.status_code == 403
