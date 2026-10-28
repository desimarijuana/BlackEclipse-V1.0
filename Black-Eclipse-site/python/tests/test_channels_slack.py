"""Slack adapter tests: normalization, thread replies, chunking (no network)."""

from __future__ import annotations

from harness.channels.providers import slack as slack_mod
from harness.channels.providers.slack import SlackProvider, _chunks, _to_mrkdwn
from harness.channels.transport import OutboundMessage


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
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def post(self, url, **kwargs):  # noqa: ANN003
        _Client.calls.append({"url": url, **kwargs})
        if url.endswith("/files.getUploadURLExternal"):
            return _Resp({"ok": True, "upload_url": "https://upload.example/x", "file_id": "F1"})
        if url == "https://upload.example/x":
            return _Resp({"ok": True}, status=200)
        if url.endswith("/files.completeUploadExternal"):
            return _Resp({"ok": True})
        return _Resp({"ok": True})


def _payload(event: dict, team: str = "T1") -> dict:
    return {"type": "event_callback", "team_id": team, "event": event}


def test_to_inbound_top_level():
    provider = SlackProvider(bot_token="x")
    msg = provider._to_inbound(  # noqa: SLF001
        _payload({"type": "message", "channel": "C1", "user": "U1", "text": "hi", "ts": "1.2"})
    )
    assert msg is not None
    assert msg.external_id == "U1"
    assert msg.external_chat == "C1"
    assert msg.platform_message_id == "1.2"
    assert msg.thread_id is None


def test_to_inbound_thread_and_app_mention():
    provider = SlackProvider(bot_token="x")
    msg = provider._to_inbound(  # noqa: SLF001
        _payload({
            "type": "app_mention",
            "channel": "C1",
            "user": "U1",
            "text": "<@BOT> hello",
            "ts": "2.2",
            "thread_ts": "1.2",
        })
    )
    assert msg is not None and msg.thread_id == "1.2"
    assert msg.text == "<@BOT> hello"


def test_to_inbound_ignores_bots_and_edits():
    provider = SlackProvider(bot_token="x")
    assert provider._to_inbound(_payload({"type": "message", "bot_id": "B", "text": "x"})) is None  # noqa: SLF001
    assert provider._to_inbound(_payload({"type": "message", "subtype": "message_changed", "text": "x"})) is None  # noqa: SLF001
    assert provider._to_inbound({"type": "url_verification"}) is None  # noqa: SLF001


async def test_send_replies_in_thread_and_chunks(monkeypatch):
    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _Client)
    _Client.calls = []
    provider = SlackProvider(bot_token="xoxb")
    ok = await provider.send(
        OutboundMessage(
            kind="slack",
            external_chat="C1",
            text="x" * 8000,
            thread_id="1.2",
        )
    )
    assert ok is True
    assert len(_Client.calls) == 3  # 3900 + 3900 + 200
    assert _Client.calls[0]["json"]["thread_ts"] == "1.2"
    assert _Client.calls[0]["headers"]["Authorization"] == "Bearer xoxb"


async def test_send_reports_platform_error(monkeypatch):
    class _Bad(_Client):
        async def post(self, url, json=None, headers=None):  # noqa: ANN001, A002
            return _Resp({"ok": False, "error": "channel_not_found"})

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _Bad)
    provider = SlackProvider(bot_token="x")
    assert await provider.send(OutboundMessage(kind="slack", external_chat="C1", text="hi")) is False


def test_helpers():
    assert _chunks("") == []
    assert _chunks("a" * 4000)[0][:1] == "a"
    assert _to_mrkdwn("**bold**") == "*bold*"

def test_to_inbound_file_only():
    provider = SlackProvider(bot_token="x")
    msg = provider._to_inbound(  # noqa: SLF001
        _payload({
            "type": "message",
            "subtype": "file_share",
            "channel": "C1",
            "user": "U1",
            "ts": "3.3",
            "files": [{"id": "F1", "name": "report.pdf", "mimetype": "application/pdf", "size": 10, "url_private": "https://files/x"}],
        })
    )
    assert msg is not None and msg.text == ""
    assert len(msg.attachments) == 1
    assert msg.attachments[0].name == "report.pdf"
    assert msg.attachments[0].size == 10

async def test_send_attachment_upload_flow(monkeypatch):
    from harness.channels.model import Attachment

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", _Client)
    _Client.calls = []
    provider = SlackProvider(bot_token="xoxb")
    ok = await provider.send(
        OutboundMessage(
            kind="slack",
            external_chat="C1",
            text="see attached",
            attachments=[Attachment(name="a.pdf", mime_type="application/pdf", data=b"pdf")],
        )
    )
    assert ok is True
    urls = [call["url"] for call in _Client.calls]
    assert any(url.endswith("/files.getUploadURLExternal") for url in urls)
    assert "https://upload.example/x" in urls
    complete = next(call for call in _Client.calls if call["url"].endswith("/files.completeUploadExternal"))
    assert complete["data"]["channel_id"] == "C1"
    assert complete["data"]["initial_comment"] == "see attached"
