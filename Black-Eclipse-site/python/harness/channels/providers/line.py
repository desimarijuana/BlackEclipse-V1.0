"""LINE Messaging API provider — signed webhook inbound + push outbound.

LINE signs the **raw body only** (no timestamp, no URL), so the check is simple and
absolute: `X-Line-Signature` must equal `base64(HMAC-SHA256(channel secret, body))`.
Because there is no timestamp there is no replay window either, which is why the
gateway's message-level dedupe (by `webhookEventId`) is the only thing standing
between a redelivery and a duplicate turn — LINE retries failed deliveries.

Two payload facts this module honours rather than flattens:

  * an event's **source** can be a user, a group or a room; the chat id is whichever
    of those the event carries, and the *sender* stays the user id. Collapsing them
    would make every group member share one conversation.
  * `message.type` is only `text` here: a sticker or image carries no text to answer,
    so it is dropped rather than described.

Config:
  channelAccessToken  the bot's channel access token (secret, required for sends)
  channelSecret       the channel secret that signs inbound bodies (secret, required)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.line")

_PUSH = "https://api.line.me/v2/bot/message/push"
_MAX_TEXT = 5_000   # one LINE text message


def signature_for(channel_secret: str, body: bytes) -> str:
    """`X-Line-Signature`: base64(HMAC-SHA256(channel secret, raw body))."""
    digest = hmac.new(str(channel_secret).encode("utf-8"), body or b"",
                      hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify(channel_secret: str, *, body: bytes, signature: Optional[str]) -> bool:
    if not channel_secret or not signature:
        return False
    return hmac.compare_digest(signature_for(channel_secret, body), signature)


def _source_ids(source: Any) -> tuple[str, str]:
    """(sender id, chat id) from a LINE source of any type."""
    if not isinstance(source, dict):
        return "", ""
    user = str(source.get("userId") or "")
    group = str(source.get("groupId") or "")
    room = str(source.get("roomId") or "")
    return user, (group or room or user)


def parse_webhook(payload: dict[str, Any]) -> list[InboundMessage]:
    """Every text message event in one webhook delivery."""
    events = payload.get("events") if isinstance(payload, dict) else None
    out: list[InboundMessage] = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict) or event.get("type") != "message":
            continue
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        if str(message.get("type") or "") != "text":
            continue
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        sender, chat = _source_ids(event.get("source"))
        if not chat:
            continue
        out.append(InboundMessage(
            kind="line",
            external_id=sender or chat,
            external_chat=chat,
            text=text[:_MAX_TEXT],
            platform_message_id=str(event.get("webhookEventId") or message.get("id") or ""),
            display_name=str((event.get("source") or {}).get("userId") or "")
            if isinstance(event.get("source"), dict) else "",
            raw={
                "replyToken": event.get("replyToken"),
                "messageId": message.get("id"),
                "sourceType": (event.get("source") or {}).get("type")
                if isinstance(event.get("source"), dict) else None,
            },
        ))
    return out


class LineProvider:
    kind = "line"

    def __init__(self, *, channel_access_token: str, channel_secret: str) -> None:
        self._token = str(channel_access_token or "")
        self._secret = str(channel_secret or "")

    async def send(self, message: OutboundMessage) -> bool:
        to = str(message.external_chat or "").strip()
        text = str(message.text or "").strip()
        if not self._token or not to or not text:
            return False
        body = {"to": to, "messages": [{"type": "text", "text": text[:_MAX_TEXT]}]}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(
                    connect=10.0, read=20.0, write=20.0, pool=10.0)) as client:
                res = await client.post(
                    _PUSH, headers={"Authorization": f"Bearer {self._token}"}, json=body)
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("line push failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("line rejected the message: HTTP %s", res.status_code)
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """Inbound arrives by webhook; there is no transport to await here."""
        return None

    async def stop(self) -> None:
        return None


__all__ = ["LineProvider", "parse_webhook", "signature_for", "verify"]
