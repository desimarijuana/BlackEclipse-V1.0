"""Slack provider — Socket Mode inbound + Web API outbound.

Socket Mode is the preferred inbound mode for a local-first app: it needs no
public URL. The HTTP Events API path remains available for deployments that
already expose `/channels/webhook/slack`; both normalize to the same
`InboundMessage`.

Credentials:
  * `botToken`      (xoxb-...) — Web API, required for outbound
  * `appToken`      (xapp-...) — Socket Mode, required for local inbound
  * `signingSecret`            — HTTP webhook only
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from ..attachments import read_attachment, sanitize_filename
from ..model import Attachment, InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.slack")

_API = "https://slack.com/api"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=20.0, pool=10.0)
_MAX_TEXT = 3900
_IGNORED_SUBTYPES = {"bot_message", "message_changed", "message_deleted", "channel_join", "channel_leave"}


class SlackProvider:
    kind = "slack"

    def __init__(
        self,
        *,
        bot_token: str,
        app_token: str = "",
        signing_secret: str = "",
        default_channel: str = "",
    ) -> None:
        self._token = str(bot_token or "").strip()
        self._app_token = str(app_token or "").strip()
        self._signing_secret = str(signing_secret or "").strip()
        self._default_channel = str(default_channel or "").strip()
        self._stopped = asyncio.Event()
        self._ws: Any = None

    # ── outbound ──────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        if not self._token:
            return False
        channel = message.external_chat or self._default_channel
        if not channel:
            return False
        thread_ts = message.thread_id or message.metadata.get("thread_ts")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if message.attachments:
                return await self._send_files(client, message, channel)
            chunks = _chunks(message.text)
            if not chunks:
                return False
            ok = True
            for chunk in chunks:
                body: dict[str, Any] = {"channel": channel, "text": _to_mrkdwn(chunk)}
                if thread_ts:
                    body["thread_ts"] = thread_ts
                try:
                    res = await client.post(f"{_API}/chat.postMessage", json=body, headers=headers)
                    data = res.json() if res.content else {}
                    if res.status_code >= 300 or not data.get("ok", False):
                        log.warning("slack chat.postMessage failed: HTTP %s %s", res.status_code, data.get("error"))
                        ok = False
                except Exception:  # noqa: BLE001 - delivery failure is reported, not raised
                    log.warning("slack chat.postMessage error", exc_info=True)
                    ok = False
            return ok

    async def _send_files(
        self,
        client: httpx.AsyncClient,
        message: OutboundMessage,
        channel: str,
    ) -> bool:
        auth = {"Authorization": f"Bearer {self._token}"}
        uploaded: list[dict[str, str]] = []
        for attachment in message.attachments:
            data = await read_attachment(attachment)
            if not data:
                log.warning("slack attachment has no readable bytes")
                continue
            filename = sanitize_filename(attachment.name)
            try:
                start = await client.post(
                    f"{_API}/files.getUploadURLExternal",
                    data={"filename": filename, "length": str(len(data))},
                    headers=auth,
                )
                info = start.json() if start.content else {}
                if start.status_code >= 300 or not info.get("ok"):
                    log.warning("slack upload URL rejected: %s", info.get("error"))
                    continue
                upload = await client.post(
                    info["upload_url"],
                    content=data,
                    headers={"Content-Type": "application/octet-stream"},
                )
                if upload.status_code >= 300:
                    log.warning("slack file upload failed: HTTP %s", upload.status_code)
                    continue
                uploaded.append({"id": str(info["file_id"]), "title": filename})
            except Exception:  # noqa: BLE001
                log.warning("slack file upload error", exc_info=True)
        if not uploaded:
            return False
        try:
            payload: dict[str, Any] = {
                "files": json.dumps(uploaded),
                "channel_id": channel,
            }
            if message.text:
                payload["initial_comment"] = message.text[:_MAX_TEXT]
            res = await client.post(
                f"{_API}/files.completeUploadExternal",
                data=payload,
                headers=auth,
            )
            info = res.json() if res.content else {}
            if res.status_code >= 300 or not info.get("ok"):
                log.warning("slack completeUploadExternal rejected: %s", info.get("error"))
                return False
            return True
        except Exception:  # noqa: BLE001
            log.warning("slack completeUploadExternal error", exc_info=True)
            return False

    # ── inbound (Socket Mode) ─────────────────────────────────────────────
    async def run(self, on_message: MessageHandler) -> None:
        if not self._app_token:
            log.info("slack Socket Mode not started (no app-level token)")
            return
        try:
            import websockets  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            log.warning("slack Socket Mode unavailable (websockets not installed)")
            return

        backoff = 1.0
        log.info("slack Socket Mode poller started")
        while not self._stopped.is_set():
            try:
                url = await self._open_socket()
                if not url:
                    await self._sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue
                backoff = 1.0
                async with websockets.connect(
                    url, max_size=2**21, ping_interval=20, ping_timeout=20
                ) as ws:
                    self._ws = ws
                    async for raw in ws:
                        await self._handle_frame(ws, raw, on_message)
                        if self._stopped.is_set():
                            break
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a dropped socket reconnects
                log.warning("slack Socket Mode connection lost", exc_info=True)
                await self._sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            finally:
                self._ws = None

    async def stop(self) -> None:
        self._stopped.set()
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def _handle_frame(self, ws: Any, raw: Any, on_message: MessageHandler) -> None:
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            return
        frame_type = frame.get("type")
        if frame_type == "hello":
            return
        if frame_type == "disconnect":
            log.info("slack requested disconnect (%s)", frame.get("reason"))
            return
        if frame_type != "events_api":
            return
        # Acknowledge within Slack's 3s window before any agent work.
        envelope_id = frame.get("envelope_id")
        if envelope_id:
            try:
                await ws.send(json.dumps({"envelope_id": envelope_id}))
            except Exception:  # noqa: BLE001
                log.debug("slack envelope ack failed", exc_info=True)
        message = self._to_inbound(frame.get("payload") or {})
        if message is not None:
            try:
                await on_message(message)
            except Exception:  # noqa: BLE001 - one bad event never kills the socket
                log.warning("slack message handling failed", exc_info=True)

    async def _open_socket(self) -> Optional[str]:
        if not self._app_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(
                    f"{_API}/apps.connections.open",
                    headers={"Authorization": f"Bearer {self._app_token}"},
                )
                data = res.json() if res.content else {}
        except Exception:  # noqa: BLE001
            log.warning("slack apps.connections.open failed", exc_info=True)
            return None
        if not data.get("ok"):
            log.warning("slack apps.connections.open rejected: %s", data.get("error"))
            return None
        return data.get("url")

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # ── normalization ─────────────────────────────────────────────────────
    def _to_inbound(self, payload: dict[str, Any]) -> Optional[InboundMessage]:
        """Normalize an Events API payload (`event_callback`). Pure and testable."""
        if not isinstance(payload, dict) or payload.get("type") != "event_callback":
            return None
        event = payload.get("event")
        if not isinstance(event, dict):
            return None
        if event.get("type") not in ("message", "app_mention"):
            return None
        if event.get("bot_id") or event.get("subtype") in _IGNORED_SUBTYPES:
            return None
        text = str(event.get("text") or "").strip()
        channel = event.get("channel")
        user = event.get("user")
        attachments = [_slack_attachment(item) for item in (event.get("files") or []) if isinstance(item, dict)]
        if (not text and not attachments) or not channel or not user:
            return None
        thread_ts = event.get("thread_ts")
        return InboundMessage(
            kind=self.kind,
            external_id=str(user),
            external_chat=str(channel),
            text=text[:4000],
            platform_message_id=str(event.get("client_msg_id") or event.get("ts") or ""),
            display_name=str(event.get("username") or ""),
            thread_id=str(thread_ts) if thread_ts else None,
            raw={"team": payload.get("team_id"), "threadTs": thread_ts},
            metadata={"team": payload.get("team_id"), "thread_ts": thread_ts},
            attachments=attachments,
        )


def _slack_attachment(item: dict[str, Any]) -> Attachment:
    raw_size = item.get("size")
    return Attachment(
        id=str(item.get("id") or ""),
        name=str(item.get("name") or item.get("title") or ""),
        mime_type=str(item.get("mimetype") or ""),
        size=int(raw_size) if isinstance(raw_size, (int, float)) else None,
        url=str(item.get("url_private") or item.get("permalink") or ""),
        provider_data={"file_id": item.get("id"), "filetype": item.get("filetype")},
    )


def _chunks(text: str, limit: int = _MAX_TEXT) -> list[str]:
    if not text:
        return []
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _to_mrkdwn(text: str) -> str:
    """Conservative Markdown → Slack mrkdwn for the common cases."""
    # **bold** -> *bold*; leave code fences and links alone.
    import re  # noqa: PLC0415

    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)


__all__ = ["SlackProvider"]
