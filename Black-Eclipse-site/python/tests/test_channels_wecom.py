"""WeCom group robot: errcode decides success, and it is honestly send-only."""

from __future__ import annotations

import asyncio

import pytest

from harness.channels import registry as R
from harness.channels.provider import ProviderContext
from harness.channels.providers.wecom import WecomProvider
from harness.channels.transport import OutboundMessage


def _provider(**kw) -> WecomProvider:
    base = dict(webhook_key="rob-key")
    base.update(kw)
    return WecomProvider(**base)


def _msg(text="fill confirmed", chat=""):
    return OutboundMessage(kind="wecom", external_chat=chat, text=text)


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"errcode": 0, "errmsg": "ok"}

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

    async def post(self, url, params=None, json=None):
        self._record.append((url, params, json))
        return _Resp(self._status, self._body)


def test_the_spec_is_outbound_only_and_requires_the_robot_key():
    spec = R.spec_for("wecom")
    assert spec is not None
    assert spec.inbound_mode == "none"
    assert set(spec.required_keys) == {"webhookKey"}
    assert "wecom" in R.KINDS and "wecom" in R.OUTBOUND_KINDS
    assert "wecom" not in R.POLL_KINDS and "wecom" not in R.PUSH_KINDS


def test_send_posts_the_robot_payload_with_the_key_in_the_query(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg())) is True
    url, params, body = record[0]
    assert url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
    assert params == {"key": "rob-key"}
    assert body == {"msgtype": "text", "text": {"content": "fill confirmed"}}


def test_an_empty_message_or_missing_key_sends_nothing(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(200, record))
    assert asyncio.run(_provider().send(_msg(text="  "))) is False
    assert asyncio.run(_provider(webhook_key="").send(_msg())) is False
    assert record == []


def test_a_non_zero_errcode_is_a_false_even_with_http_200(monkeypatch):
    # WeCom answers 200 with errcode 93000 for a bad key; the code decides.
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient",
                        lambda **kw: _Client(200, record, {"errcode": 93000,
                                                           "errmsg": "invalid webhook key"}))
    assert asyncio.run(_provider().send(_msg())) is False


def test_an_http_error_or_transport_failure_is_a_false(monkeypatch):
    record: list = []
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Client(500, record))
    assert asyncio.run(_provider().send(_msg())) is False

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _Boom())
    assert asyncio.run(_provider().send(_msg())) is False


def test_run_returns_without_claiming_inbound():
    async def scenario():
        await asyncio.wait_for(_provider().run(lambda m: None), timeout=1)

    asyncio.run(scenario())


def test_build_provider_needs_the_key():
    def ctx(values):
        return ProviderContext(kind="wecom", config={}, secret=lambda k: values.get(k, ""))

    assert R.build_provider(ctx({})) is None
    assert isinstance(R.build_provider(ctx({"webhookKey": "k"})), WecomProvider)
