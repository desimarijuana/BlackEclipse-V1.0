"""Microsoft Teams adapter tests: activity parsing, JWT verification, send."""

from __future__ import annotations

import json

from harness.channels import verify
from harness.channels.providers import teams as teams_mod
from harness.channels.providers.teams import TeamsProvider, _safe_service_url, parse_activity
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
    token_calls = 0
    message_calls: list[dict] = []

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def post(self, url, **kwargs):  # noqa: ANN003
        if "login.microsoftonline.com" in url:
            _Client.token_calls += 1
            return _Resp({"access_token": "tok", "expires_in": 3600})
        _Client.message_calls.append({"url": url, **kwargs})
        if url.endswith("/attachments"):
            return _Resp({"id": "att-1"})
        return _Resp({"id": "a1"})


def _activity(text: str = "hello") -> dict:
    return {
        "type": "message",
        "id": "a1",
        "text": text,
        "from": {"id": "29:user", "aadObjectId": "aad-1", "name": "Sam"},
        "recipient": {"id": "28:bot"},
        "conversation": {"id": "conv-1", "tenantId": "tenant-1"},
        "channelId": "msteams",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
    }


def test_parse_activity():
    msg = parse_activity(_activity())
    assert msg is not None
    assert msg.external_id == "aad-1"
    assert msg.external_chat == "conv-1"
    assert msg.text == "hello"
    assert msg.platform_message_id == "a1"
    assert msg.metadata["serviceUrl"] == "https://smba.trafficmanager.net/emea/"


def test_parse_ignores_bot_and_non_message():
    own = _activity()
    own["from"]["id"] = "28:bot"
    assert parse_activity(own) is None
    assert parse_activity({"type": "conversationUpdate"}) is None
    assert parse_activity({"type": "message", "text": ""}) is None


def test_service_url_allowlist():
    assert _safe_service_url("https://smba.trafficmanager.net/emea/")
    assert _safe_service_url("https://foo.botframework.com/x")
    assert _safe_service_url("http://smba.trafficmanager.net/emea/") == ""
    assert _safe_service_url("https://evil.example.com/x") == ""
    assert _safe_service_url("https://trafficmanager.net.evil.com/x") == ""


async def test_send_uses_service_url_and_caches_token(monkeypatch):
    monkeypatch.setattr(teams_mod.httpx, "AsyncClient", _Client)
    _Client.token_calls = 0
    _Client.message_calls = []
    provider = TeamsProvider(app_id="app", app_password="pw")
    message = OutboundMessage(
        kind="teams",
        external_chat="conv-1",
        text="hi",
        metadata={"serviceUrl": "https://smba.trafficmanager.net/emea/"},
    )
    assert await provider.send(message) is True
    assert await provider.send(message) is True
    assert _Client.token_calls == 1
    assert len(_Client.message_calls) == 2
    first = _Client.message_calls[0]
    assert first["url"] == "https://smba.trafficmanager.net/emea/v3/conversations/conv-1/activities"
    assert first["json"] == {"type": "message", "text": "hi"}
    assert first["headers"]["Authorization"] == "Bearer tok"


def test_verify_teams_signature_and_audience():
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "k1"
    claims = {
        "aud": "app-id",
        "iss": "https://api.botframework.com",
        "exp": int(time.time()) + 600,
        "nbf": int(time.time()) - 10,
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "k1"})
    assert verify.verify_teams(
        token,
        app_id="app-id",
        jwks={"keys": [jwk]},
        issuer="https://api.botframework.com",
    )
    assert not verify.verify_teams(
        token,
        app_id="other-app",
        jwks={"keys": [jwk]},
        issuer="https://api.botframework.com",
    )
    assert not verify.verify_teams("not-a-jwt", app_id="app-id", jwks={"keys": [jwk]})

def test_parse_attachment_only_message():
    activity = _activity()
    activity["text"] = ""
    activity["attachments"] = [{"contentType": "application/pdf", "contentUrl": "https://x/y", "name": "a.pdf"}]
    msg = parse_activity(activity)
    assert msg is not None and msg.text == ""
    assert msg.attachments[0].name == "a.pdf"
    assert msg.attachments[0].url == "https://x/y"

async def test_send_attachment_uploads_and_links(monkeypatch):
    from harness.channels.model import Attachment

    monkeypatch.setattr(teams_mod.httpx, "AsyncClient", _Client)
    _Client.token_calls = 0
    _Client.message_calls = []
    provider = TeamsProvider(app_id="app", app_password="pw")
    ok = await provider.send(
        OutboundMessage(
            kind="teams",
            external_chat="conv-1",
            text="see attached",
            metadata={"serviceUrl": "https://smba.trafficmanager.net/emea/"},
            attachments=[Attachment(name="a.pdf", mime_type="application/pdf", data=b"pdf")],
        )
    )
    assert ok is True
    upload = next(call for call in _Client.message_calls if call["url"].endswith("/attachments"))
    assert upload["files"]["attachment"][0] == "a.pdf"
    activity = next(call for call in _Client.message_calls if call["url"].endswith("/activities"))
    assert activity["json"]["attachments"][0]["contentUrl"].endswith("/v3/attachments/att-1/views/original")
