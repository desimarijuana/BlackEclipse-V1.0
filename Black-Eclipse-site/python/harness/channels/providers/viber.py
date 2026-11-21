"""Viber provider: hex body HMAC inbound, callbacks REST outbound."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.viber")

_SEND = "https://chatapi.viber.com/pa/send_message"
_MAX_TEXT = 7_000


def signature_for(auth_token: str, body: bytes) -> str:
    """`X-Viber-Content-Signature`: hex HMAC-SHA256(auth token, raw body)."""
    return hmac.new(str(auth_token).encode("utf-8"), body or b"",
                    hashlib.sha256).hexdigest()


def verify(auth_token: str, *, body: bytes, signature: Optional[str]) -> bool:
    if not auth_token or not signature:
        return False
    return hmac.compare_digest(signature_for(auth_token, body), signature)


def parse_webhook(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """A `message` event with text becomes one inbound message."""
    if not isinstance(payload, dict) or str(payload.get("event") or "") != "message":
        return None
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    sender_id = str(sender.get("id") or "")
    if not sender_id or str(message.get("type") or "text") != "text":
        return None
    text = str(message.get("text") or "").strip()
    if not text:
        return None
    return InboundMessage(
        kind="viber",
        external_id=sender_id,
        external_chat=sender_id,
        text=text[:_MAX_TEXT],
        platform_message_id=str(payload.get("message_token") or ""),
        display_name=str(sender.get("name") or sender_id),
        raw={"messageToken": payload.get("message_token"), "senderName": sender.get("name")},
    )


class ViberProvider:
    kind = "viber"

    def __init__(self, *, auth_token: str, sender_name: str = "Eclipse") -> None:
        self._token = str(auth_token or "")
        self._name = str(sender_name or "Eclipse")

    async def send(self, message: OutboundMessage) -> bool:
        receiver = str(message.external_chat or "").strip()
        text = str(message.text or "").strip()
        if not self._token or not receiver or not text:
            return False
        body = {
            "receiver": receiver,
            "type": "text",
            "text": text[:_MAX_TEXT],
            "sender": {"name": self._name[:28]},
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(
                    connect=10.0, read=20.0, write=20.0, pool=10.0)) as client:
                res = await client.post(_SEND, json=body,
                                        headers={"X-Viber-Auth-Token": self._token})
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("viber send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("viber rejected the message: HTTP %s", res.status_code)
            return False
        try:
            payload = res.json() or {}
        except Exception:  # noqa: BLE001 - the body is advisory
            return True
        return int(payload.get("status") or 0) == 0

    async def run(self, on_message: Any) -> None:
        """Inbound arrives by webhook; there is no transport to await here."""
        return None

    async def stop(self) -> None:
        return None


__all__ = ["ViberProvider", "parse_webhook", "signature_for", "verify"]
