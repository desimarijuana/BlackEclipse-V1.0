"""Lark / Feishu provider — event webhook inbound + IM API outbound.

The adapter mirrors the behavior of Minara's Lark channel: tenant access token
caching, domain switching (`open.feishu.cn` vs `open.larksuite.com`), text
messages, and event verification/decryption.

Inbound currently uses the HTTP event subscription. Minara additionally uses
Lark's WebSocket long connection; that can be layered on later via the optional
`lark-oapi` package without changing the normalized contract here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

import httpx

from ..attachments import read_attachment, sanitize_filename
from ..model import Attachment, InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.lark")

_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_MAX_TEXT = 4000
_DOMAINS = {
    "feishu": "https://open.feishu.cn",
    "larksuite": "https://open.larksuite.com",
}


class LarkProvider:
    kind = "lark"

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        default_chat_id: str = "",
        domain: str = "open.feishu.cn",
        use_websocket: bool = True,
    ) -> None:
        self._app_id = str(app_id or "").strip()
        self._app_secret = str(app_secret or "").strip()
        self._default_chat = str(default_chat_id or "").strip()
        self._base = _resolve_domain(domain)
        self._use_websocket = bool(use_websocket)
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._lock = asyncio.Lock()
        self._stopped = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_message: Any = None
        self._thread: Optional[threading.Thread] = None
        self._thread_stop = threading.Event()
        self._ws_client: Any = None

    # ── outbound ──────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        chat_id = message.external_chat or self._default_chat
        if not chat_id:
            return False
        token = await self._tenant_token()
        if not token:
            return False
        ok = True
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for attachment in message.attachments:
                if not await self._send_attachment(client, token, chat_id, attachment):
                    ok = False
            text = str(message.text or "")
            if text and not await self._send_message(
                client, token, chat_id, "text", {"text": text[:_MAX_TEXT]}
            ):
                ok = False
        return ok

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        msg_type: str,
        content: dict[str, Any],
    ) -> bool:
        body = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        try:
            res = await client.post(
                f"{self._base}/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = res.json() if res.content else {}
        except Exception:  # noqa: BLE001 - delivery failure is reported, not raised
            log.warning("lark send failed", exc_info=True)
            return False
        if res.status_code >= 300 or data.get("code") not in (0, None):
            log.warning("lark send rejected: HTTP %s code=%s msg=%s", res.status_code, data.get("code"), data.get("msg"))
            return False
        return True

    async def _send_attachment(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        attachment: Attachment,
    ) -> bool:
        data = await read_attachment(attachment)
        if not data:
            log.warning("lark attachment has no readable bytes")
            return False
        filename = sanitize_filename(attachment.name)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            if str(attachment.mime_type or "").startswith("image/"):
                res = await client.post(
                    f"{self._base}/open-apis/im/v1/images",
                    data={"image_type": "message"},
                    files={"image": (filename, data, attachment.mime_type or "application/octet-stream")},
                    headers=headers,
                )
                payload = res.json() if res.content else {}
                key = (payload.get("data") or {}).get("image_key")
                if res.status_code >= 300 or payload.get("code") not in (0, None) or not key:
                    log.warning("lark image upload rejected: %s", payload.get("msg"))
                    return False
                return await self._send_message(client, token, chat_id, "image", {"image_key": key})
            res = await client.post(
                f"{self._base}/open-apis/im/v1/files",
                data={"file_type": "stream", "file_name": filename},
                files={"file": (filename, data, attachment.mime_type or "application/octet-stream")},
                headers=headers,
            )
            payload = res.json() if res.content else {}
            key = (payload.get("data") or {}).get("file_key")
            if res.status_code >= 300 or payload.get("code") not in (0, None) or not key:
                log.warning("lark file upload rejected: %s", payload.get("msg"))
                return False
            return await self._send_message(client, token, chat_id, "file", {"file_key": key})
        except Exception:  # noqa: BLE001
            log.warning("lark attachment upload error", exc_info=True)
            return False

    async def _tenant_token(self) -> Optional[str]:
        now = time.monotonic()
        if self._token and now < self._token_expires_at - 30:
            return self._token
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - 30:
                return self._token
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    res = await client.post(
                        f"{self._base}/open-apis/auth/v3/tenant_access_token/internal",
                        json={"app_id": self._app_id, "app_secret": self._app_secret},
                    )
                    data = res.json() if res.content else {}
            except Exception:  # noqa: BLE001
                log.warning("lark tenant token request failed", exc_info=True)
                return None
            token = data.get("tenant_access_token")
            if not token:
                log.warning("lark tenant token rejected: code=%s msg=%s", data.get("code"), data.get("msg"))
                return None
            self._token = str(token)
            self._token_expires_at = time.monotonic() + float(data.get("expire") or 7200)
            return self._token

    # ── inbound (WebSocket long connection) ───────────────────────────────
    async def run(self, on_message: Any) -> None:
        """Run Lark's WebSocket long connection when `lark-oapi` is installed.

        WebSocket inbound needs no public URL, matching Minara's behavior. The
        HTTP event webhook remains available; if the optional SDK is absent the
        provider simply does not start a stream.
        """
        if not self._use_websocket or not self._app_id or not self._app_secret:
            return
        try:
            import lark_oapi  # noqa: F401, PLC0415
        except Exception:  # noqa: BLE001
            log.info("lark WebSocket not started (install the optional lark-oapi package)")
            return
        self._loop = asyncio.get_running_loop()
        self._on_message = on_message
        self._thread = threading.Thread(target=self._ws_main, name="lark-ws", daemon=True)
        self._thread.start()
        await self._stopped.wait()

    async def stop(self) -> None:
        self._stopped.set()
        self._thread_stop.set()
        client = self._ws_client
        if client is not None:
            try:
                # lark-oapi's ws client has no public stop(); its `start()` owns
                # a module-level loop, so disconnect on that loop.
                from lark_oapi.ws import client as ws_module  # noqa: PLC0415

                if getattr(ws_module.loop, "is_running", lambda: False)():
                    future = asyncio.run_coroutine_threadsafe(client._disconnect(), ws_module.loop)  # noqa: SLF001
                    await asyncio.to_thread(future.result, 2.0)
            except Exception:  # noqa: BLE001
                log.debug("lark WebSocket stop failed", exc_info=True)
        if self._thread is not None and self._thread.is_alive():
            try:
                await asyncio.to_thread(self._thread.join, 2.0)
            except Exception:  # noqa: BLE001
                pass

    def _ws_main(self) -> None:
        backoff = 1.0
        while not self._thread_stop.is_set():
            try:
                import lark_oapi as lark  # noqa: PLC0415

                handler = (
                    lark.EventDispatcherHandler.builder("", "")
                    .register_p2_im_message_receive_v1(self._on_ws_event)
                    .build()
                )
                self._ws_client = lark.ws.Client(
                    self._app_id,
                    self._app_secret,
                    event_handler=handler,
                    log_level=lark.LogLevel.INFO,
                    auto_reconnect=False,
                )
                backoff = 1.0
                self._ws_client.start()
            except Exception:  # noqa: BLE001 - a stream crash must not kill the runtime
                log.warning("lark WebSocket connection failed", exc_info=True)
            finally:
                self._ws_client = None
            if self._thread_stop.wait(backoff):
                return
            backoff = min(backoff * 2, 60.0)

    def _on_ws_event(self, data: Any) -> None:
        event = getattr(data, "event", None)
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        sender_id = getattr(sender, "sender_id", None)
        message_data = {
            "message_type": getattr(message, "message_type", ""),
            "content": getattr(message, "content", ""),
        }
        text = _message_text(message_data)
        attachments = _message_attachments(message_data)
        chat_id = getattr(message, "chat_id", None)
        open_id = getattr(sender_id, "open_id", None) or getattr(sender_id, "user_id", None)
        message_id = getattr(message, "message_id", None)
        if (
            (not text and not attachments)
            or not chat_id
            or not open_id
            or self._loop is None
            or self._on_message is None
        ):
            return
        inbound = InboundMessage(
            kind="lark",
            external_id=str(open_id),
            external_chat=str(chat_id),
            text=text[:4000],
            platform_message_id=str(message_id or ""),
            raw={"eventType": "im.message.receive_v1", "source": "websocket"},
            metadata={"chat_id": chat_id, "message_id": message_id},
            attachments=attachments,
        )
        future = asyncio.run_coroutine_threadsafe(self._on_message(inbound), self._loop)
        future.add_done_callback(_log_ws_failure)

    # ── inbound (HTTP event subscription) ─────────────────────────────────
    def parse_event(self, payload: dict[str, Any]) -> Optional[InboundMessage]:
        return parse_event(payload)


def parse_event(payload: dict[str, Any]) -> Optional[InboundMessage]:
    """Normalize a Lark `im.message.receive_v1` event (v2 schema). Pure."""
    if not isinstance(payload, dict):
        return None
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    text = _message_text(message)
    attachments = _message_attachments(message)
    chat_id = message.get("chat_id")
    open_id = sender_id.get("open_id") or sender_id.get("user_id")
    message_id = message.get("message_id")
    if (not text and not attachments) or not chat_id or not open_id:
        return None
    return InboundMessage(
        kind="lark",
        external_id=str(open_id),
        external_chat=str(chat_id),
        text=text[:4000],
        platform_message_id=str(message_id or ""),
        display_name=str(sender.get("sender_type") or ""),
        raw={"eventType": header.get("event_type"), "messageType": message.get("message_type")},
        metadata={"chat_id": chat_id, "message_id": message_id},
        attachments=attachments,
    )


def _log_ws_failure(future: Any) -> None:
    try:
        exc = future.exception()
    except Exception:  # noqa: BLE001
        return
    if exc is not None:
        log.warning("lark WebSocket message handling failed", exc_info=exc)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or "{}"
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    if message.get("message_type") == "text":
        return str(parsed.get("text") or "").strip()
    # Post/rich text: flatten the title and text runs.
    if isinstance(parsed.get("content"), list):
        parts: list[str] = []
        for block in parsed.get("content") or []:
            for run in block or []:
                if isinstance(run, dict) and run.get("tag") == "text":
                    parts.append(str(run.get("text") or ""))
        return "".join(parts).strip()
    return ""


def _message_attachments(message: dict[str, Any]) -> list[Attachment]:
    message_type = str(message.get("message_type") or "")
    if message_type not in ("file", "image", "audio", "media"):
        return []
    content = message.get("content") or "{}"
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []
    file_key = parsed.get("file_key")
    image_key = parsed.get("image_key")
    key = file_key or image_key or ""
    if not key:
        return []
    name = parsed.get("file_name") or key
    return [
        Attachment(
            id=str(key),
            name=str(name),
            mime_type=str(parsed.get("mime_type") or ""),
            size=int(parsed["file_size"]) if str(parsed.get("file_size") or "").isdigit() else None,
            provider_data={
                "message_id": message.get("message_id"),
                "file_key": file_key,
                "image_key": image_key,
                "message_type": message_type,
            },
        )
    ]


def _resolve_domain(domain: str) -> str:
    raw = str(domain or "").strip().rstrip("/")
    if not raw:
        return _DOMAINS["feishu"]
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if "larksuite" in raw:
        return _DOMAINS["larksuite"]
    return _DOMAINS["feishu"]


__all__ = ["LarkProvider", "parse_event"]
