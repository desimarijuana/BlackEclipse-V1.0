"""DingTalk provider: signing, spec, offline send, and honest inbound=none."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import urllib.parse

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.dingtalk import DingTalkProvider, sign_webhook
from harness.channels.transport import OutboundMessage


def test_the_spec_declares_an_outbound_only_channel():
    spec = R.spec_for("dingtalk")
    assert spec is not None
    assert spec.inbound_mode == "none"
    assert spec.required_keys == ("webhookUrl",)
    assert "dingtalk" in R.KINDS


def test_signing_matches_dingtalks_documented_algorithm():
    url = "https://oapi.dingtalk.com/robot/send?access_token=abc"
    signed = sign_webhook(url, "SEC000", timestamp_ms=1_700_000_000_000)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(signed).query)
    assert query["timestamp"] == ["1700000000000"]
    expected = base64.b64encode(hmac.new(
        b"SEC000", b"1700000000000\nSEC000", hashlib.sha256).digest()).decode()
    assert query["sign"] == [expected]


def test_without_a_secret_the_url_is_unchanged():
    url = "https://example.com/robot"
    assert sign_webhook(url, "") == url


def test_configured_requires_the_webhook_url():
    ctx = ProviderContext(kind="dingtalk", config={}, secret=lambda key: "")
    assert R.spec_for("dingtalk").is_configured(lambda key: "") is False
    assert R.spec_for("dingtalk").is_configured(
        lambda key: "https://x" if key == "webhookUrl" else "") is True


def test_build_provider_returns_one_only_when_configured():
    class _Ctx(ProviderContext):
        pass

    def ctx(value: str) -> ProviderContext:
        return ProviderContext(kind="dingtalk", config={}, secret=lambda key: value)

    assert R.build_provider(ctx("")) is None
    provider = R.build_provider(ctx("https://oapi.dingtalk.com/robot/send?access_token=x"))
    assert isinstance(provider, DingTalkProvider)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.content = b"{}"
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response, record):
        self._response = response
        self._record = record

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        self._record.append((url, json))
        return self._response


def _run_send(monkeypatch, response, *, text="hello", secret="SEC"):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient",
                        lambda **kw: _FakeClient(response, record))
    provider = DingTalkProvider(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=x",
                                sign_secret=secret)
    ok = asyncio.run(provider.send(
        OutboundMessage(kind="dingtalk", external_chat="robot", text=text)))
    return ok, record


def test_send_posts_a_signed_text_message(monkeypatch):
    ok, record = _run_send(monkeypatch, _FakeResponse(200, {"errcode": 0}))
    assert ok is True
    url, body = record[0]
    assert "timestamp=" in url and "sign=" in url
    assert body == {"msgtype": "text", "text": {"content": "hello"}}


def test_an_application_error_is_a_false_not_a_success(monkeypatch):
    ok, _ = _run_send(monkeypatch, _FakeResponse(200, {"errcode": 310000, "errmsg": "sign not match"}))
    assert ok is False


def test_an_http_error_is_a_false(monkeypatch):
    ok, _ = _run_send(monkeypatch, _FakeResponse(500, {}))
    assert ok is False


def test_empty_text_or_url_sends_nothing(monkeypatch):
    ok, record = _run_send(monkeypatch, _FakeResponse(200, {"errcode": 0}), text="  ")
    assert ok is False and record == []
    provider = DingTalkProvider(webhook_url="", sign_secret="")
    assert asyncio.run(provider.send(
        OutboundMessage(kind="dingtalk", external_chat="robot", text="hello"))) is False


def test_run_blocks_until_stop():
    provider = DingTalkProvider(webhook_url="https://x", sign_secret="")

    async def scenario():
        task = asyncio.create_task(provider.run(lambda m: None))
        await asyncio.sleep(0.01)
        assert not task.done()
        await provider.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())
