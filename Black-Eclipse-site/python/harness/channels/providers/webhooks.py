"""Push-provider adapters: Slack, WhatsApp (Cloud API) and a generic webhook.

These channels share one shape — inbound arrives at the public
`/channels/webhook/{kind}` route (signature-verified by `channels/verify.py`) and
outbound is a single authenticated HTTP POST. The PURE `parse_*` functions
normalize a provider payload into `InboundMessage`s and are unit-tested directly;
the provider classes implement only `send`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.webhooks")

_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)


async def _post(url: str, body: Any, headers: Optional[dict[str, str]] = None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            res = await client.post(url, json=body, headers=headers or {})
            if res.status_code >= 300:
                log.warning("webhook reply failed: HTTP %s", res.status_code)
                return False
            return True
    except Exception:  # noqa: BLE001 - a delivery failure is reported, not raised
        log.warning("webhook reply error", exc_info=True)
        return False


class SlackProvider:
    kind = "slack"

    def __init__(self, *, bot_token: str) -> None:
        self._token = str(bot_token or "").strip()
        self._base = "https://slack.com/api"

    async def send(self, message: OutboundMessage) -> bool:
        if not self._token:
            return False
        return await _post(
            f"{self._base}/chat.postMessage",
            {"channel": message.external_chat, "text": message.text[:4000]},
            {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json; charset=utf-8"},
        )


class WhatsappProvider:
    kind = "whatsapp"

    def __init__(self, *, access_token: str, phone_number_id: str, api_version: str = "v21.0") -> None:
        self._token = str(access_token or "").strip()
        self._phone = str(phone_number_id or "").strip()
        self._version = str(api_version or "v21.0")

    async def send(self, message: OutboundMessage) -> bool:
        if not self._token or not self._phone:
            return False
        url = f"https://graph.facebook.com/{self._version}/{self._phone}/messages"
        return await _post(
            url,
            {
                "messaging_product": "whatsapp",
                "to": message.external_chat,
                "type": "text",
                "text": {"body": message.text[:4000]},
            },
            {"Authorization": f"Bearer {self._token}"},
        )


class WebhookProvider:
    kind = "webhook"

    def __init__(self, *, reply_url: str, token: Optional[str] = None) -> None:
        self._url = str(reply_url or "").strip()
        self._token = str(token or "").strip()

    async def send(self, message: OutboundMessage) -> bool:
        if not self._url:
            return False
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return await _post(self._url, {"text": message.text}, headers)


# ── pure inbound parsers ─────────────────────────────────────────────────────
def parse_slack(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a Slack Events API `event_callback` message. None for anything
    else (including `url_verification` and bot/edited messages)."""
    if not isinstance(payload, dict) or payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "message":
        return None
    if event.get("bot_id") or event.get("subtype"):
        return None
    text = str(event.get("text") or "").strip()
    channel = event.get("channel")
    user = event.get("user")
    if not text or not channel or not user:
        return None
    return InboundMessage(
        kind="slack",
        external_id=str(user),
        external_chat=str(channel),
        text=text[:4000],
        platform_message_id=str(event.get("client_msg_id") or event.get("ts") or ""),
        display_name=str(event.get("username") or ""),
        raw={"team": (payload.get("team_id"))},
    )


def parse_whatsapp(payload: dict[str, Any]) -> list[InboundMessage]:
    """Normalize Meta WhatsApp webhook messages (statuses are ignored)."""
    out: list[InboundMessage] = []
    if not isinstance(payload, dict):
        return out
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in (value.get("contacts") or [])}
            for message in value.get("messages") or []:
                if (message or {}).get("type") != "text":
                    continue
                body = (message.get("text") or {}).get("body") or ""
                sender = message.get("from")
                if not sender or not str(body).strip():
                    continue
                out.append(
                    InboundMessage(
                        kind="whatsapp",
                        external_id=str(sender),
                        external_chat=str(sender),
                        text=str(body)[:4000],
                        platform_message_id=str(message.get("id") or ""),
                        display_name=str(contacts.get(sender) or ""),
                    )
                )
    return out


def parse_generic(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a generic signed webhook body.

    Expected shape: `{"externalId": "...", "externalChat": "...", "text": "...",
    "messageId": "...", "displayName": "..."}`. `externalChat` defaults to
    `externalId` (reply to the sender). `messageId` is required for idempotency.
    """
    if not isinstance(payload, dict):
        return None
    external_id = payload.get("externalId")
    text = str(payload.get("text") or "").strip()
    if not external_id or not text:
        return None
    return InboundMessage(
        kind="webhook",
        external_id=str(external_id),
        external_chat=str(payload.get("externalChat") or external_id),
        text=text[:4000],
        platform_message_id=str(payload.get("messageId") or ""),
        display_name=str(payload.get("displayName") or ""),
    )


__all__ = [
    "SlackProvider",
    "WebhookProvider",
    "WhatsappProvider",
    "parse_generic",
    "parse_slack",
    "parse_whatsapp",
]
