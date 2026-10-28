"""Lark adapter tests: event parsing, token caching, send payload, verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from harness.channels.providers import lark as lark_mod
from harness.channels.providers.lark import LarkProvider, parse_event
from harness.channels.transport import OutboundMessage
from harness.channels import verify


class _Resp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    @property
    def content(self) -> bytes:
        return b"x"

    def json(self) -> dict:
        return self._payload


class _Client:
    token_calls = 0
    message_calls: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def post(self, url, **kwargs):  # noqa: ANN003
        if url.endswith("/tenant_access_token/internal"):
            _Client.token_calls += 1
            return _Resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})
        _Client.message_calls.append({"url": url, **kwargs})
        if url.endswith("/im/v1/images"):
            return _Resp({"code": 0, "data": {"image_key": "ik-1"}})
        if url.endswith("/im/v1/files"):
            return _Resp({"code": 0, "data": {"file_key": "fk-1"}})
        return _Resp({"code": 0, "data": {"message_id": "om_1"}})


def _event(text: str = "hello", message_type: str = "text", content: dict | None = None) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "vt"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": message_type,
                "content": json.dumps(content if content is not None else {"text": text}),
            },
        },
    }


def test_parse_text_event():
    msg = parse_event(_event("hello"))
    assert msg is not None
    assert msg.kind == "lark"
    assert msg.external_id == "ou_1"
    assert msg.external_chat == "oc_1"
    assert msg.text == "hello"
    assert msg.platform_message_id == "om_1"


def test_parse_post_event_flattens_text_runs():
    payload = _event(
        message_type="post",
        content={"title": "", "content": [[{"tag": "text", "text": "a"}, {"tag": "text", "text": "b"}]]},
    )
    msg = parse_event(payload)
    assert msg is not None and msg.text == "ab"


def test_parse_ignores_other_events():
    payload = _event()
    payload["header"]["event_type"] = "im.chat.updated_v1"
    assert parse_event(payload) is None
    assert parse_event({"type": "url_verification"}) is None


async def test_send_caches_token_and_posts_text(monkeypatch):
    monkeypatch.setattr(lark_mod.httpx, "AsyncClient", _Client)
    _Client.token_calls = 0
    _Client.message_calls = []
    provider = LarkProvider(app_id="a", app_secret="s")
    assert await provider.send(OutboundMessage(kind="lark", external_chat="oc_1", text="hi")) is True
    assert await provider.send(OutboundMessage(kind="lark", external_chat="oc_1", text="again")) is True
    assert _Client.token_calls == 1
    assert len(_Client.message_calls) == 2
    first = _Client.message_calls[0]
    assert first["headers"]["Authorization"] == "Bearer t-1"
    assert first["params"] == {"receive_id_type": "chat_id"}
    assert json.loads(first["json"]["content"]) == {"text": "hi"}


async def test_send_reports_platform_error(monkeypatch):
    class _Bad(_Client):
        async def post(self, url, json=None, headers=None, params=None):  # noqa: ANN001, A002
            if url.endswith("/tenant_access_token/internal"):
                return _Resp({"code": 0, "tenant_access_token": "t", "expire": 7200})
            return _Resp({"code": 230002, "msg": "chat not found"}, status=400)

    monkeypatch.setattr(lark_mod.httpx, "AsyncClient", _Bad)
    provider = LarkProvider(app_id="a", app_secret="s")
    assert await provider.send(OutboundMessage(kind="lark", external_chat="oc_1", text="hi")) is False


def test_domain_switch():
    assert LarkProvider(app_id="a", app_secret="s", domain="open.larksuite.com")._base == "https://open.larksuite.com"  # noqa: SLF001
    assert LarkProvider(app_id="a", app_secret="s", domain="")._base == "https://open.feishu.cn"  # noqa: SLF001


def test_lark_verify_and_decrypt_roundtrip():
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = "ek"
    plaintext = json.dumps(_event("secret")).encode()
    iv = b"0" * 16
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(hashlib.sha256(key.encode()).digest()), modes.CBC(iv)).encryptor()
    ciphertext = base64.b64encode(iv + encryptor.update(padded) + encryptor.finalize()).decode()

    body = json.dumps({"encrypt": ciphertext}).encode()
    ts, nonce = "123", "n"
    signature = hashlib.sha256(f"{ts}{nonce}{key}".encode() + body).hexdigest()
    assert verify.verify_lark(key, timestamp=ts, nonce=nonce, body=body, signature=signature)
    assert not verify.verify_lark(key, timestamp=ts, nonce=nonce, body=body, signature="no")
    decrypted = verify.decrypt_lark(key, ciphertext)
    assert decrypted is not None and decrypted["header"]["event_type"] == "im.message.receive_v1"
    assert verify.decrypt_lark("wrong", ciphertext) is None

async def test_websocket_disabled_is_a_noop():
    import asyncio

    provider = LarkProvider(app_id="a", app_secret="s", use_websocket=False)
    await asyncio.wait_for(provider.run(lambda message: None), timeout=1)


async def test_websocket_event_normalizes():
    import asyncio
    from types import SimpleNamespace

    provider = LarkProvider(app_id="a", app_secret="s")
    seen = []

    async def on_message(message):
        seen.append(message)

    provider._loop = asyncio.get_running_loop()  # noqa: SLF001
    provider._on_message = on_message  # noqa: SLF001
    provider._on_ws_event(  # noqa: SLF001
        SimpleNamespace(
            event=SimpleNamespace(
                message=SimpleNamespace(
                    message_type="text",
                    content=json.dumps({"text": "hello"}),
                    chat_id="oc_1",
                    message_id="om_1",
                ),
                sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_1")),
            )
        )
    )
    await asyncio.sleep(0.05)
    assert len(seen) == 1
    assert seen[0].external_id == "ou_1"
    assert seen[0].external_chat == "oc_1"
    assert seen[0].text == "hello"

def test_parse_file_message():
    payload = _event(message_type="file", content={"file_key": "fk", "file_name": "a.pdf", "file_size": "12"})
    msg = parse_event(payload)
    assert msg is not None and msg.text == ""
    assert msg.attachments[0].id == "fk"
    assert msg.attachments[0].name == "a.pdf"
    assert msg.attachments[0].size == 12

async def test_send_file_attachment_uploads_then_sends(monkeypatch):
    from harness.channels.model import Attachment

    monkeypatch.setattr(lark_mod.httpx, "AsyncClient", _Client)
    _Client.token_calls = 0
    _Client.message_calls = []
    provider = LarkProvider(app_id="a", app_secret="s")
    ok = await provider.send(
        OutboundMessage(
            kind="lark",
            external_chat="oc_1",
            text="see attached",
            attachments=[Attachment(name="a.pdf", mime_type="application/pdf", data=b"pdf")],
        )
    )
    assert ok is True
    upload = next(call for call in _Client.message_calls if call["url"].endswith("/im/v1/files"))
    assert upload["files"]["file"][0] == "a.pdf"
    sent = next(call for call in _Client.message_calls if call["url"].endswith("/im/v1/messages"))
    assert json.loads(sent["json"]["content"]) == {"file_key": "fk-1"}
