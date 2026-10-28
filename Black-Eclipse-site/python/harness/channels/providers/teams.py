"""Microsoft Teams provider — Bot Framework webhook inbound + connector outbound.

Teams delivers activities to a public HTTPS endpoint. Each request carries a
Bot Framework JWT, verified in `channels/verify.py`. Replies go to the
conversation's `serviceUrl` with a client-credentials token.

Credentials:
  * `appId` / `appPassword` — Azure Bot registration
  * `tenantId`             — "common" for multi-tenant (default)
  * `defaultConversationId`, `defaultServiceUrl` — proactive sends
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from ..attachments import read_attachment, sanitize_filename
from ..model import Attachment, InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.teams")

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SCOPE = "https://api.botframework.com/.default"
_DEFAULT_SERVICE_URL = "https://smba.trafficmanager.net/teams"
_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_MAX_TEXT = 4000
_ALLOWED_SUFFIXES = (
    ".botframework.com",
    ".trafficmanager.net",
    ".skype.com",
)


class TeamsProvider:
    kind = "teams"

    def __init__(
        self,
        *,
        app_id: str,
        app_password: str,
        tenant_id: str = "common",
        default_conversation_id: str = "",
        default_service_url: str = _DEFAULT_SERVICE_URL,
    ) -> None:
        self._app_id = str(app_id or "").strip()
        self._app_password = str(app_password or "").strip()
        self._tenant = str(tenant_id or "common").strip() or "common"
        self._default_conversation = str(default_conversation_id or "").strip()
        self._default_service_url = _safe_service_url(default_service_url) or _DEFAULT_SERVICE_URL
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._lock = asyncio.Lock()

    # ── outbound ──────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        conversation = message.external_chat or self._default_conversation
        service_url = _safe_service_url(
            str(message.metadata.get("serviceUrl") or self._default_service_url)
        )
        text = str(message.text or "")
        if not conversation or not service_url or (not text and not message.attachments):
            return False
        token = await self._access_token()
        if not token:
            return False
        base = service_url.rstrip("/")
        url = f"{base}/v3/conversations/{conversation}/activities"
        body: dict[str, Any] = {"type": "message", "text": text[:_MAX_TEXT]}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                attachments: list[dict[str, Any]] = []
                for attachment in message.attachments:
                    meta = await self._attachment_meta(client, token, base, conversation, attachment)
                    if meta:
                        attachments.append(meta)
                if attachments:
                    body["attachments"] = attachments
                res = await client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                data = res.json() if res.content else {}
        except Exception:  # noqa: BLE001 - delivery failure is reported, not raised
            log.warning("teams send failed", exc_info=True)
            return False
        if res.status_code >= 300:
            log.warning("teams send rejected: HTTP %s %s", res.status_code, data.get("error", {}).get("message"))
            return False
        return True

    async def _attachment_meta(
        self,
        client: httpx.AsyncClient,
        token: str,
        base: str,
        conversation: str,
        attachment: Attachment,
    ) -> Optional[dict[str, Any]]:
        name = sanitize_filename(attachment.name)
        if attachment.url.startswith("https://") and attachment.data is None:
            return {
                "contentType": attachment.mime_type or "application/octet-stream",
                "contentUrl": attachment.url,
                "name": name,
            }
        data = await read_attachment(attachment)
        if not data:
            log.warning("teams attachment has no readable bytes")
            return None
        try:
            res = await client.post(
                f"{base}/v3/conversations/{conversation}/attachments",
                files={
                    "attachment": (
                        name,
                        data,
                        attachment.mime_type or "application/octet-stream",
                    )
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            payload = res.json() if res.content else {}
        except Exception:  # noqa: BLE001
            log.warning("teams attachment upload failed", exc_info=True)
            return None
        resource_id = payload.get("id") if isinstance(payload, dict) else None
        if res.status_code >= 300 or not resource_id:
            log.warning("teams attachment upload rejected: HTTP %s", res.status_code)
            return None
        return {
            "contentType": attachment.mime_type or "application/octet-stream",
            "contentUrl": f"{base}/v3/attachments/{resource_id}/views/original",
            "name": name,
        }

    async def _access_token(self) -> Optional[str]:
        now = time.monotonic()
        if self._token and now < self._token_expires_at - 60:
            return self._token
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - 60:
                return self._token
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    res = await client.post(
                        _TOKEN_URL.format(tenant=self._tenant),
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self._app_id,
                            "client_secret": self._app_password,
                            "scope": _SCOPE,
                        },
                    )
                    data = res.json() if res.content else {}
            except Exception:  # noqa: BLE001
                log.warning("teams token request failed", exc_info=True)
                return None
            token = data.get("access_token")
            if not token:
                log.warning("teams token rejected: %s", data.get("error_description") or data.get("error"))
                return None
            self._token = str(token)
            self._token_expires_at = time.monotonic() + float(data.get("expires_in") or 3600)
            return self._token


def parse_activity(activity: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a Bot Framework `message` activity. Pure and testable."""
    if not isinstance(activity, dict) or activity.get("type") != "message":
        return None
    text = str(activity.get("text") or "").strip()
    sender = activity.get("from") or {}
    conversation = activity.get("conversation") or {}
    recipient = activity.get("recipient") or {}
    sender_id = sender.get("aadObjectId") or sender.get("id")
    conversation_id = conversation.get("id")
    attachments = [
        _teams_attachment(item)
        for item in (activity.get("attachments") or [])
        if isinstance(item, dict)
    ]
    if (not text and not attachments) or not sender_id or not conversation_id:
        return None
    if recipient.get("id") and (
        sender.get("id") == recipient.get("id") or sender_id == recipient.get("id")
    ):
        return None  # our own message
    service_url = activity.get("serviceUrl")
    return InboundMessage(
        kind="teams",
        external_id=str(sender_id),
        external_chat=str(conversation_id),
        text=text[:4000],
        platform_message_id=str(activity.get("id") or ""),
        display_name=str(sender.get("name") or ""),
        thread_id=str(conversation_id),
        raw={"channelId": activity.get("channelId"), "locale": activity.get("locale")},
        metadata={
            "serviceUrl": service_url,
            "tenantId": (conversation.get("tenantId") or activity.get("channelData", {}).get("tenant", {}).get("id")),
        },
        attachments=attachments,
    )


def _teams_attachment(item: dict[str, Any]) -> Attachment:
    content_type = str(item.get("contentType") or "")
    return Attachment(
        id=str(item.get("id") or ""),
        name=str(item.get("name") or content_type or "attachment"),
        mime_type=content_type,
        url=str(item.get("contentUrl") or ""),
        provider_data={"contentType": content_type},
    )


def _safe_service_url(url: str) -> str:
    """Only talk to Microsoft-operated Bot Framework endpoints (SSRF guard)."""
    raw = str(url or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    host = parsed.hostname.lower()
    if host == "smba.trafficmanager.net" or any(host.endswith(suffix) for suffix in _ALLOWED_SUFFIXES):
        return raw
    return ""


__all__ = ["TeamsProvider", "parse_activity"]
