"""Push-provider adapters: WhatsApp (Cloud API) and a generic webhook.

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

from ..attachments import read_attachment, sanitize_filename
from ..model import Attachment, InboundMessage
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


class WhatsappProvider:
    kind = "whatsapp"

    def __init__(self, *, access_token: str, phone_number_id: str, api_version: str = "v21.0") -> None:
        self._token = str(access_token or "").strip()
        self._phone = str(phone_number_id or "").strip()
        self._version = str(api_version or "v21.0")

    async def send(self, message: OutboundMessage) -> bool:
        if not self._token or not self._phone:
            return False
        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"https://graph.facebook.com/{self._version}/{self._phone}/messages"
        text = str(message.text or "")
        ok = True
        captioned = False
        for attachment in message.attachments:
            data = await read_attachment(attachment)
            if not data:
                log.warning("whatsapp attachment has no readable bytes")
                ok = False
                continue
            media_id = await self._upload_media(data, attachment)
            if not media_id:
                ok = False
                continue
            caption = text if not captioned else ""
            captioned = True
            if str(attachment.mime_type or "").startswith("image/"):
                body = {
                    "messaging_product": "whatsapp",
                    "to": message.external_chat,
                    "type": "image",
                    "image": {"id": media_id, **({"caption": caption[:1024]} if caption else {})},
                }
            else:
                body = {
                    "messaging_product": "whatsapp",
                    "to": message.external_chat,
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": sanitize_filename(attachment.name),
                        **({"caption": caption[:1024]} if caption else {}),
                    },
                }
            if not await _post(url, body, headers):
                ok = False
        if text and not captioned:
            ok = await _post(
                url,
                {
                    "messaging_product": "whatsapp",
                    "to": message.external_chat,
                    "type": "text",
                    "text": {"body": text[:4000]},
                },
                headers,
            ) and ok
        return ok

    async def _upload_media(self, data: bytes, attachment: Attachment) -> Optional[str]:
        url = f"https://graph.facebook.com/{self._version}/{self._phone}/media"
        filename = sanitize_filename(attachment.name)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(
                    url,
                    data={"messaging_product": "whatsapp"},
                    files={
                        "file": (
                            filename,
                            data,
                            attachment.mime_type or "application/octet-stream",
                        )
                    },
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                payload = res.json() if res.content else {}
        except Exception:  # noqa: BLE001
            log.warning("whatsapp media upload failed", exc_info=True)
            return None
        if res.status_code >= 300 or not payload.get("id"):
            log.warning("whatsapp media upload rejected: %s", payload.get("error", {}).get("message"))
            return None
        return str(payload["id"])


class WebhookProvider:
    kind = "webhook"

    def __init__(self, *, reply_url: str, token: Optional[str] = None) -> None:
        self._url = str(reply_url or "").strip()
        self._token = str(token or "").strip()

    async def send(self, message: OutboundMessage) -> bool:
        if not self._url:
            return False
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        body: dict[str, Any] = {"text": message.text}
        if message.attachments:
            import base64  # noqa: PLC0415

            body["attachments"] = [
                {
                    "name": item.name,
                    "mimeType": item.mime_type,
                    "size": item.size,
                    "url": item.url,
                    **(
                        {"contentBase64": base64.b64encode(item.data).decode("ascii")}
                        if item.data is not None
                        else {}
                    ),
                }
                for item in message.attachments
            ]
        return await _post(self._url, body, headers)


# ── pure inbound parsers ─────────────────────────────────────────────────────
def parse_slack(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a Slack Events API `event_callback` message. None for anything
    else (including `url_verification` and bot/edited messages)."""
    if not isinstance(payload, dict) or payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "message":
        return None
    if event.get("bot_id") or event.get("subtype") in (
        "bot_message",
        "message_changed",
        "message_deleted",
        "channel_join",
        "channel_leave",
    ):
        return None
    text = str(event.get("text") or "").strip()
    channel = event.get("channel")
    user = event.get("user")
    attachments = [
        Attachment(
            id=str(item.get("id") or ""),
            name=str(item.get("name") or item.get("title") or ""),
            mime_type=str(item.get("mimetype") or ""),
            size=int(item["size"]) if isinstance(item.get("size"), (int, float)) else None,
            url=str(item.get("url_private") or item.get("permalink") or ""),
            provider_data={"file_id": item.get("id"), "filetype": item.get("filetype")},
        )
        for item in (event.get("files") or [])
        if isinstance(item, dict)
    ]
    if (not text and not attachments) or not channel or not user:
        return None
    thread_ts = event.get("thread_ts")
    return InboundMessage(
        kind="slack",
        external_id=str(user),
        external_chat=str(channel),
        text=text[:4000],
        platform_message_id=str(event.get("client_msg_id") or event.get("ts") or ""),
        display_name=str(event.get("username") or ""),
        thread_id=str(thread_ts) if thread_ts else None,
        raw={"team": (payload.get("team_id"))},
        metadata={"team": payload.get("team_id"), "thread_ts": thread_ts},
        attachments=attachments,
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
                if not isinstance(message, dict):
                    continue
                sender = message.get("from")
                if not sender:
                    continue
                text, attachments = _whatsapp_content(message)
                if not text and not attachments:
                    continue
                out.append(
                    InboundMessage(
                        kind="whatsapp",
                        external_id=str(sender),
                        external_chat=str(sender),
                        text=str(text)[:4000],
                        platform_message_id=str(message.get("id") or ""),
                        display_name=str(contacts.get(sender) or ""),
                        attachments=attachments,
                    )
                )
    return out


def _whatsapp_content(message: dict[str, Any]) -> tuple[str, list[Attachment]]:
    message_type = str(message.get("type") or "")
    if message_type == "text":
        return str((message.get("text") or {}).get("body") or ""), []
    if message_type not in ("image", "document", "audio", "video", "sticker"):
        return "", []
    media = message.get(message_type) or {}
    media_id = str(media.get("id") or "")
    name = str(media.get("filename") or media.get("caption") or f"{message_type}-{media_id}")
    text = str(media.get("caption") or media.get("filename") or f"[{message_type}]")
    attachment = Attachment(
        id=media_id,
        name=name,
        mime_type=str(media.get("mime_type") or ""),
        provider_data={"media_id": media_id, "type": message_type},
    )
    return text, [attachment]


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
    "WebhookProvider",
    "WhatsappProvider",
    "parse_generic",
    "parse_slack",
    "parse_whatsapp",
]
