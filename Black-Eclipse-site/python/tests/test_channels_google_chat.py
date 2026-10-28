"""Google Chat adapter tests: event parsing and outbound payloads (no network)."""

from __future__ import annotations

from harness.channels.providers import google_chat as gc_mod
from harness.channels.providers.google_chat import GoogleChatProvider, parse_event
from harness.channels.transport import OutboundMessage


class _Resp:
    def __init__(self, payload: dict | None = None, status: int = 200) -> None:
        self._payload = payload or {}
        self.status_code = status

    @property
    def content(self) -> bytes:
        return b"x"

    def json(self) -> dict:
        return self._payload


class _Client:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def post(self, url, **kwargs):  # noqa: ANN003
        _Client.calls.append({"url": url, **kwargs})
        if "/upload/v1/" in url:
            return _Resp({"attachmentDataRef": {"resourceName": "spaces/AAAA/attachments/1"}})
        return _Resp({"name": "spaces/AAAA/messages/1"})


def _event(text: str = "hello") -> dict:
    return {
        "type": "MESSAGE",
        "user": {"name": "users/123", "displayName": "Sam"},
        "space": {"name": "spaces/AAAA", "type": "DM"},
        "message": {
            "name": "spaces/AAAA/messages/1",
            "text": f"<users/123> {text}",
            "argumentText": text,
            "thread": {"name": "spaces/AAAA/threads/T1"},
        },
    }


def test_parse_message_event():
    msg = parse_event(_event())
    assert msg is not None
    assert msg.external_id == "users/123"
    assert msg.external_chat == "spaces/AAAA"
    assert msg.text == "hello"
    assert msg.thread_id == "spaces/AAAA/threads/T1"
    assert msg.display_name == "Sam"


def test_parse_ignores_non_message():
    assert parse_event({"type": "ADDED_TO_SPACE"}) is None
    assert parse_event({"type": "MESSAGE", "message": {}}) is None


async def test_send_prefixes_space_and_sets_thread(monkeypatch):
    monkeypatch.setattr(gc_mod.httpx, "AsyncClient", _Client)
    _Client.calls = []
    provider = GoogleChatProvider(credentials_json='{"type":"service_account"}')
    monkeypatch.setattr(provider, "_get_token", _token)

    ok = await provider.send(
        OutboundMessage(
            kind="google_chat",
            external_chat="AAAA",
            text="hi",
            thread_id="spaces/AAAA/threads/T1",
        )
    )
    assert ok is True
    assert _Client.calls[0]["url"].endswith("/spaces/AAAA/messages")
    assert _Client.calls[0]["json"]["thread"]["name"] == "spaces/AAAA/threads/T1"
    assert _Client.calls[0]["headers"]["Authorization"] == "Bearer tok"


async def test_send_without_token_reports_false(monkeypatch):
    provider = GoogleChatProvider(credentials_json='{"type":"service_account"}')
    monkeypatch.setattr(provider, "_get_token", _no_token)
    assert await provider.send(OutboundMessage(kind="google_chat", external_chat="spaces/A", text="hi")) is False


async def _token():
    return "tok"


async def _no_token():
    return None

def test_parse_attachment_only_message():
    payload = _event()
    payload["message"]["argumentText"] = ""
    payload["message"]["text"] = ""
    payload["message"]["attachment"] = [{
        "name": "spaces/A/messages/1/attachments/1",
        "contentName": "a.pdf",
        "contentType": "application/pdf",
        "attachmentDataRef": {"resourceName": "spaces/A/messages/1/attachments/1"},
    }]
    msg = parse_event(payload)
    assert msg is not None and msg.text == ""
    assert msg.attachments[0].name == "a.pdf"
    assert msg.attachments[0].provider_data["resource_name"].endswith("/attachments/1")

async def test_send_attachment_uploads_and_links(monkeypatch):
    from harness.channels.model import Attachment

    monkeypatch.setattr(gc_mod.httpx, "AsyncClient", _Client)
    _Client.calls = []
    provider = GoogleChatProvider(credentials_json='{"type":"service_account"}')
    monkeypatch.setattr(provider, "_get_token", _token)
    ok = await provider.send(
        OutboundMessage(
            kind="google_chat",
            external_chat="spaces/AAAA",
            text="see attached",
            attachments=[Attachment(name="a.pdf", mime_type="application/pdf", data=b"pdf")],
        )
    )
    assert ok is True
    upload = next(call for call in _Client.calls if "/upload/v1/" in call["url"])
    assert upload["files"]["media"][0] == "a.pdf"
    message = next(call for call in _Client.calls if call["url"].endswith("/spaces/AAAA/messages"))
    assert message["json"]["attachment"][0]["attachmentDataRef"]["resourceName"].endswith("/attachments/1")
