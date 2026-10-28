"""Google Chat provider — HTTP event webhook inbound + Chat API outbound.

Google Chat pushes events to a public HTTPS endpoint and authenticates each
request with a Google-signed JWT. Outbound messages use a service account (or
Application Default Credentials) with the `chat.bot` scope.

Credentials:
  * `credentialsJson` — service-account JSON (inline or a file path)
  * `useAdc`          — use Application Default Credentials instead
  * `projectNumber`   — expected JWT audience for inbound verification
  * `defaultSpaceId`  — optional proactive-send target (`spaces/...`)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..attachments import read_attachment, sanitize_filename
from ..model import Attachment, InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.google_chat")

_API = "https://chat.googleapis.com/v1"
_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_SCOPES = ("https://www.googleapis.com/auth/chat.bot",)
_MAX_TEXT = 4000


class GoogleChatProvider:
    kind = "google_chat"

    def __init__(
        self,
        *,
        credentials_json: str = "",
        use_adc: bool = False,
        default_space_id: str = "",
    ) -> None:
        self._credentials_json = str(credentials_json or "").strip()
        self._use_adc = bool(use_adc)
        self._default_space = str(default_space_id or "").strip()
        self._creds: Any = None
        self._lock = asyncio.Lock()

    # ── outbound ──────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        space = _space(message.external_chat or self._default_space)
        text = str(message.text or "")
        if not space or (not text and not message.attachments):
            return False
        token = await self._get_token()
        if not token:
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                refs: list[dict[str, Any]] = []
                for attachment in message.attachments:
                    ref = await self._upload_attachment(client, token, space, attachment)
                    if ref:
                        refs.append(ref)
                body: dict[str, Any] = {}
                if text:
                    body["text"] = text[:_MAX_TEXT]
                if message.thread_id:
                    body["thread"] = {"name": message.thread_id}
                if refs:
                    body["attachment"] = refs
                res = await client.post(
                    f"{_API}/{space}/messages",
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = res.json() if res.content else {}
        except Exception:  # noqa: BLE001 - delivery failure is reported, not raised
            log.warning("google chat send failed", exc_info=True)
            return False
        if res.status_code >= 300:
            log.warning("google chat send rejected: HTTP %s %s", res.status_code, data.get("error", {}).get("message"))
            return False
        return True

    async def _upload_attachment(
        self,
        client: httpx.AsyncClient,
        token: str,
        space: str,
        attachment: Attachment,
    ) -> Optional[dict[str, Any]]:
        data = await read_attachment(attachment)
        if not data:
            log.warning("google chat attachment has no readable bytes")
            return None
        filename = sanitize_filename(attachment.name)
        try:
            res = await client.post(
                f"https://chat.googleapis.com/upload/v1/{space}/attachments",
                params={"uploadType": "multipart"},
                files={
                    "metadata": (None, json.dumps({"filename": filename}), "application/json"),
                    "media": (filename, data, attachment.mime_type or "application/octet-stream"),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            payload = res.json() if res.content else {}
        except Exception:  # noqa: BLE001
            log.warning("google chat attachment upload failed", exc_info=True)
            return None
        ref = payload.get("attachmentDataRef") if isinstance(payload, dict) else None
        if res.status_code >= 300 or not isinstance(ref, dict) or not ref.get("resourceName"):
            log.warning("google chat attachment upload rejected: HTTP %s", res.status_code)
            return None
        return {"attachmentDataRef": {"resourceName": ref["resourceName"]}}

    async def _get_token(self) -> Optional[str]:
        async with self._lock:
            try:
                if self._creds is None:
                    self._creds = await asyncio.to_thread(self._load_credentials)
                if self._creds is None:
                    return None
                if not getattr(self._creds, "valid", False):
                    await asyncio.to_thread(self._refresh)
                token = getattr(self._creds, "token", None)
                expiry = getattr(self._creds, "expiry", None)
                if token and expiry and expiry <= datetime.now(timezone.utc):
                    await asyncio.to_thread(self._refresh)
                    token = getattr(self._creds, "token", None)
                return token
            except Exception:  # noqa: BLE001 - an unavailable credential is honest
                log.warning("google chat credentials unavailable", exc_info=True)
                return None

    def _load_credentials(self) -> Any:
        from google.auth import default as google_default  # noqa: PLC0415
        from google.oauth2 import service_account  # noqa: PLC0415

        if self._use_adc or not self._credentials_json:
            creds, _ = google_default(scopes=_SCOPES)
            return creds
        raw = self._credentials_json
        if raw.lstrip().startswith("{"):
            info = json.loads(raw)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        return service_account.Credentials.from_service_account_file(raw, scopes=_SCOPES)

    def _refresh(self) -> None:
        from google.auth.transport.requests import Request  # noqa: PLC0415

        self._creds.refresh(Request())

    # ── inbound ───────────────────────────────────────────────────────────
    def parse_event(self, payload: dict[str, Any]) -> Optional[InboundMessage]:
        return parse_event(payload)


def parse_event(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a Google Chat MESSAGE event. Pure and testable."""
    if not isinstance(payload, dict):
        return None
    if str(payload.get("type") or "").upper() != "MESSAGE":
        return None
    message = payload.get("message") or {}
    user = payload.get("user") or {}
    space = payload.get("space") or {}
    text = str(message.get("argumentText") or message.get("text") or "").strip()
    user_id = user.get("name")
    space_id = space.get("name")
    attachments = [
        _google_chat_attachment(item)
        for item in (message.get("attachment") or [])
        if isinstance(item, dict)
    ]
    if (not text and not attachments) or not user_id or not space_id:
        return None
    thread = (message.get("thread") or {}).get("name")
    return InboundMessage(
        kind="google_chat",
        external_id=str(user_id),
        external_chat=str(space_id),
        text=text[:4000],
        platform_message_id=str(message.get("name") or ""),
        display_name=str(user.get("displayName") or ""),
        thread_id=str(thread) if thread else None,
        raw={"type": payload.get("type"), "spaceType": space.get("type")},
        metadata={"space": space_id, "thread": thread},
        attachments=attachments,
    )


def _google_chat_attachment(item: dict[str, Any]) -> Attachment:
    data_ref = item.get("attachmentDataRef") or {}
    return Attachment(
        id=str(item.get("name") or ""),
        name=str(item.get("contentName") or item.get("name") or "attachment"),
        mime_type=str(item.get("contentType") or ""),
        url=str(item.get("downloadUri") or ""),
        provider_data={
            "resource_name": data_ref.get("resourceName"),
            "attachment_name": item.get("name"),
        },
    )


def _space(space: str) -> str:
    value = str(space or "").strip()
    if not value:
        return ""
    return value if value.startswith("spaces/") else f"spaces/{value}"


__all__ = ["GoogleChatProvider", "parse_event"]
