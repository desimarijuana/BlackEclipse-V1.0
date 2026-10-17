"""Channel provider tests: signature verification, payload parsing, and the
Discord/Email normalizers (pure, no network)."""

from __future__ import annotations

import hashlib
import hmac
import time

from harness.channels import verify
from harness.channels.providers.discord import DiscordProvider
from harness.channels.providers.email import EmailProvider
from harness.channels.providers.webhooks import parse_generic, parse_slack, parse_whatsapp


# ── signature verification ────────────────────────────────────────────────────
def _slack_sig(secret: str, ts: int, body: bytes) -> str:
    base = f"v0:{ts}:".encode() + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def test_verify_slack_ok_and_replay():
    secret = "s3cr3t"
    body = b'{"type":"event_callback"}'
    ts = int(time.time())
    assert verify.verify_slack(secret, timestamp=str(ts), body=body, signature=_slack_sig(secret, ts, body))
    # stale timestamp is refused (replay window)
    old = ts - 10_000
    assert not verify.verify_slack(
        secret, timestamp=str(old), body=body, signature=_slack_sig(secret, old, body)
    )
    assert not verify.verify_slack(secret, timestamp=str(ts), body=body, signature="v0=deadbeef")
    assert not verify.verify_slack("", timestamp=str(ts), body=body, signature=_slack_sig(secret, ts, body))


def test_verify_whatsapp_and_generic():
    body = b'{"entry":[]}'
    wa = "appsecret"
    sig = "sha256=" + hmac.new(wa.encode(), body, hashlib.sha256).hexdigest()
    assert verify.verify_whatsapp(wa, body=body, signature=sig)
    assert not verify.verify_whatsapp(wa, body=body, signature="sha256=00")
    assert not verify.verify_whatsapp("", body=body, signature=sig)

    secret = "generic"
    gsig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify.verify_generic(secret, body=body, signature=gsig)
    assert not verify.verify_generic(secret, body=body, signature="nope")


# ── parsers ───────────────────────────────────────────────────────────────────
def test_parse_slack():
    payload = {
        "type": "event_callback",
        "team_id": "T1",
        "event": {"type": "message", "channel": "C1", "user": "U1", "text": "hi", "client_msg_id": "m1"},
    }
    msg = parse_slack(payload)
    assert msg and msg.external_id == "U1" and msg.external_chat == "C1" and msg.text == "hi"
    assert parse_slack({"type": "url_verification", "challenge": "x"}) is None
    assert parse_slack({"type": "event_callback", "event": {"type": "message", "bot_id": "B", "text": "x"}}) is None


def test_parse_whatsapp():
    payload = {
        "entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": "1555", "profile": {"name": "Sam"}}],
            "messages": [{"from": "1555", "id": "wamid.1", "type": "text", "text": {"body": "hello"}}],
        }}]}],
    }
    messages = parse_whatsapp(payload)
    assert len(messages) == 1
    assert messages[0].external_id == "1555" and messages[0].text == "hello"
    assert messages[0].display_name == "Sam"
    assert parse_whatsapp({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []


def test_parse_generic():
    msg = parse_generic({"externalId": "9", "text": "yo"})
    assert msg and msg.external_chat == "9"
    assert parse_generic({"externalId": "9"}) is None


# ── discord normalization ─────────────────────────────────────────────────────
def test_discord_to_inbound():
    provider = DiscordProvider(bot_token="x")
    msg = provider._to_inbound({  # noqa: SLF001
        "content": "hello", "channel_id": "C", "id": "M",
        "author": {"id": "U", "username": "sam", "bot": False},
    })
    assert msg and msg.external_id == "U" and msg.external_chat == "C" and msg.text == "hello"
    assert provider._to_inbound({"content": "x", "channel_id": "C", "author": {"id": "B", "bot": True}}) is None  # noqa: SLF001
    assert provider._to_inbound({"content": "", "channel_id": "C", "author": {"id": "U"}}) is None  # noqa: SLF001


# ── email normalization ───────────────────────────────────────────────────────
def _raw_email(frm="user@example.com", body="hello", subject="Hi") -> bytes:
    return (
        f"From: {frm}\r\nTo: eclipse@example.com\r\nSubject: {subject}\r\n"
        f"Message-ID: <m1@example.com>\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode("utf-8")


def test_email_to_inbound_and_link():
    provider = EmailProvider(imap_host="imap.example.com", imap_user="eclipse@example.com", imap_pass="x")
    msg = provider._to_inbound(_raw_email())  # noqa: SLF001
    assert msg and msg.external_id == "user@example.com" and msg.text == "hello"
    assert msg.platform_message_id == "<m1@example.com>"

    link = provider._to_inbound(_raw_email(body="/link ABC123\n> quoted reply"))  # noqa: SLF001
    assert link and link.text == "/link ABC123"


def test_email_ignores_own_and_bulk():
    provider = EmailProvider(
        imap_host="h", imap_user="eclipse@example.com", imap_pass="x", from_address="eclipse@example.com"
    )
    assert provider._to_inbound(_raw_email(frm="eclipse@example.com")) is None  # noqa: SLF001
    raw = _raw_email() + b""
    bulk = b"From: a@b.com\r\nPrecedence: bulk\r\nMessage-ID: <m2>\r\n\r\nx\r\n"
    assert provider._to_inbound(bulk) is None  # noqa: SLF001
