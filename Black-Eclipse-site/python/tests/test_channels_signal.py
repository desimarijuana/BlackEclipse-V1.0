"""Signal provider: send-only by declaration, with an honest inbound story."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.signal import SignalProvider
from harness.channels.transport import OutboundMessage

BOT = "+15550001111"


def _provider(**kw) -> SignalProvider:
    base = dict(base_url="http://127.0.0.1:8080", number=BOT)
    base.update(kw)
    return SignalProvider(**base)


def _msg(text="fill confirmed", chat="+15552223333"):
    return OutboundMessage(kind="signal", external_chat=chat, text=text)


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


def test_the_spec_is_send_only_and_requires_two_fields():
    spec = R.spec_for("signal")
    assert spec is not None
    assert spec.inbound_mode == "none"
    assert set(spec.required_keys) == {"baseUrl", "number"}
    assert "signal" in R.KINDS and "signal" in R.OUTBOUND_KINDS
    assert "signal" not in R.POLL_KINDS and "signal" not in R.PUSH_KINDS


def test_send_posts_the_bridge_payload(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    assert asyncio.run(_provider().send(_msg())) is True
    url, headers, body = record[0]
    assert url == "http://127.0.0.1:8080/v2/send"
    assert body == {"message": "fill confirmed", "number": BOT,
                    "recipients": ["+15552223333"]}
    assert "Authorization" not in headers


def test_a_bridge_token_is_sent_when_configured(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    asyncio.run(_provider(api_token="tok").send(_msg()))
    assert record[0][1]["Authorization"] == "Bearer tok"


def test_an_empty_recipient_or_message_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(201, record))
    assert asyncio.run(_provider().send(_msg(chat=""))) is False
    assert asyncio.run(_provider().send(_msg(text="   "))) is False
    assert asyncio.run(_provider(number="").send(_msg())) is False
    assert record == []


def test_an_http_error_or_transport_failure_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(400, record))
    assert asyncio.run(_provider().send(_msg())) is False

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("bridge down")

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Boom())
    assert asyncio.run(_provider().send(_msg())) is False


def test_run_returns_without_claiming_inbound():
    # A send-only provider must not leave a task alive that can never deliver.
    async def scenario():
        await asyncio.wait_for(_provider().run(lambda m: None), timeout=1)

    asyncio.run(scenario())


def test_build_provider_needs_a_url_and_a_number():
    def ctx(values):
        return ProviderContext(kind="signal", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    assert R.build_provider(ctx({"baseUrl": "http://x"})) is None
    provider = R.build_provider(ctx({"baseUrl": "http://x", "number": BOT}))
    assert isinstance(provider, SignalProvider)
