"""Twilio SMS: the signed push path, end to end and offline.

Twilio is the first push provider that is neither JSON nor header-signed, so these
cases pin what is easy to get wrong:

  * the signature is **HMAC-SHA1 over the public URL plus sorted form params**,
    base64 encoded;
  * it is only valid for the URL Twilio actually fetched — the harness sees an
    internal one, so `publicUrl` is required and its absence is a 503;
  * Twilio echoes the outbound leg back to the same webhook, so `From` equal to
    the bot's number is dropped rather than looped into the agent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.parse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers import twilio
from harness.channels.transport import OutboundMessage
from harness.routers import channels as channels_router

PUBLIC = "https://app.example.com/api/channels/webhook/twilio"
TOKEN = "tok-123"
BOT = "+15550001111"


def _sign(params: dict[str, str], *, token: str = TOKEN, url: str = PUBLIC) -> str:
    return twilio.signature_for(token, url, params)


# -- the signature ----------------------------------------------------------


def test_the_signature_is_hmac_sha1_base64_over_url_and_sorted_params():
    params = {"To": BOT, "From": "+15552223333", "Body": "hi", "MessageSid": "SM1"}
    joined = PUBLIC + "".join(f"{k}{params[k]}" for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(TOKEN.encode(), joined.encode(), hashlib.sha1).digest()
    ).decode()
    assert _sign(params) == expected


def test_param_order_does_not_change_the_signature_but_values_do():
    a = {"Body": "hi", "From": "x"}
    b = {"From": "x", "Body": "hi"}
    assert _sign(a) == _sign(b)
    assert _sign(a) != _sign({"Body": "ho", "From": "x"})


def test_a_wrong_url_token_or_missing_signature_is_a_refusal():
    params = {"Body": "hi", "From": "+15552223333"}
    good = _sign(params)
    assert twilio.verify(TOKEN, url=PUBLIC, params=params, signature=good) is True
    assert twilio.verify(TOKEN, url=PUBLIC + "/x", params=params, signature=good) is False
    assert twilio.verify("other", url=PUBLIC, params=params, signature=good) is False
    assert twilio.verify(TOKEN, url=PUBLIC, params=params, signature=None) is False
    assert twilio.verify("", url=PUBLIC, params=params, signature=good) is False


# -- inbound parsing --------------------------------------------------------


def test_a_text_message_becomes_inbound():
    message = twilio.parse_inbound({
        "From": "+15552223333", "To": BOT, "Body": "how is NVDA?",
        "MessageSid": "SM123", "NumMedia": "0",
    })
    assert message is not None
    assert message.kind == "twilio"
    assert message.external_chat == "+15552223333"
    assert message.text == "how is NVDA?"
    assert message.platform_message_id == "SM123"


def test_the_bot_ignores_its_own_outbound_echo():
    message = twilio.parse_inbound({"From": BOT, "Body": "echo"}, bot_number=BOT)
    assert message is None


def test_a_blank_body_is_dropped():
    assert twilio.parse_inbound({"From": "+15552223333", "Body": "  "}) is None
    assert twilio.parse_inbound({"To": BOT, "Body": "hi"}) is None


# -- outbound ---------------------------------------------------------------


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

    async def post(self, url, data=None, auth=None):
        self._record.append((url, data, auth))
        return _Resp(self._status)


def _provider(**kw) -> twilio.TwilioProvider:
    base = dict(account_sid="AC1", auth_token=TOKEN, from_number=BOT, public_url=PUBLIC)
    base.update(kw)
    return twilio.TwilioProvider(**base)


def test_send_posts_the_rest_payload_with_basic_auth(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    message = OutboundMessage(kind="twilio", external_chat="+15552223333", text="hi")
    import asyncio

    assert asyncio.run(_provider().send(message)) is True
    url, data, auth = record[0]
    assert url == "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json"
    assert data == {"From": BOT, "To": "+15552223333", "Body": "hi"}
    assert auth == ("AC1", TOKEN)


def test_an_incomplete_provider_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    message = OutboundMessage(kind="twilio", external_chat="+15552223333", text="hi")
    import asyncio

    assert asyncio.run(_provider(account_sid="").send(message)) is False
    assert asyncio.run(_provider().send(
        OutboundMessage(kind="twilio", external_chat="", text="hi"))) is False
    assert record == []


# -- the spec and the route -------------------------------------------------


def test_the_spec_is_a_push_provider_with_four_required_fields():
    spec = R.spec_for("twilio")
    assert spec is not None
    assert spec.inbound_mode == "push"
    assert set(spec.required_keys) == {"accountSid", "authToken", "fromNumber", "publicUrl"}
    assert "twilio" in R.KINDS and "twilio" in R.PUSH_KINDS
    assert "twilio" not in R.OUTBOUND_KINDS and "twilio" not in R.POLL_KINDS


def test_build_provider_needs_the_three_outbound_fields():
    def ctx(values):
        return ProviderContext(kind="twilio", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    provider = R.build_provider(ctx({
        "accountSid": "AC1", "authToken": TOKEN, "fromNumber": BOT, "publicUrl": PUBLIC,
    }))
    assert isinstance(provider, twilio.TwilioProvider)


class _FakeChannels:
    """Only what the webhook branch touches, plus a record of what it accepted."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.accepted: list = []

    def secret_value(self, kind: str, key: str) -> str:
        del kind
        return self._values.get(key, "")

    def handle_inbound(self, message):  # pragma: no cover - background path
        self.accepted.append(message)
        return True


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(channels_router.router)
    channels_router._channels = lambda: service
    return TestClient(app)


FORM = {"From": "+15552223333", "To": BOT, "Body": "how is NVDA?",
        "MessageSid": "SM999", "NumMedia": "0"}


def test_the_route_accepts_a_correctly_signed_form():
    service = _FakeChannels({"authToken": TOKEN, "publicUrl": PUBLIC, "fromNumber": BOT})
    # `_enqueue` runs the handler in a background task; patch it to be synchronous.
    original = channels_router._enqueue
    channels_router._enqueue = lambda svc, message, background: svc.handle_inbound(message)
    try:
        client = _client(service)
        res = client.post("/channels/webhook/twilio", data=FORM,
                          headers={"X-Twilio-Signature": _sign(FORM)})
    finally:
        channels_router._enqueue = original
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert [m.text for m in service.accepted] == ["how is NVDA?"]


def test_the_route_refuses_a_bad_signature():
    service = _FakeChannels({"authToken": TOKEN, "publicUrl": PUBLIC, "fromNumber": BOT})
    client = _client(service)
    res = client.post("/channels/webhook/twilio", data=FORM,
                      headers={"X-Twilio-Signature": "bogus"})
    assert res.status_code == 403


def test_the_route_refuses_to_guess_the_public_url():
    service = _FakeChannels({"authToken": TOKEN, "fromNumber": BOT})
    client = _client(service)
    res = client.post("/channels/webhook/twilio", data=FORM,
                      headers={"X-Twilio-Signature": _sign(FORM)})
    assert res.status_code == 503
    assert "publicUrl" in res.json()["detail"]
