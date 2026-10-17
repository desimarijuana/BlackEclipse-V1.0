"""Telegram provider — long-poll `getUpdates` + `sendMessage`.

Telegram is the zero-config-friendly first provider precisely because inbound
delivery needs NO public endpoint: the runtime long-polls Telegram from the local
machine. A user links their account by sending `/link <code>` to the bot.

The bot token comes from the channel config (a literal or a `secret://` reference
resolved by the service). It is never logged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.telegram")

_API_BASE = "https://api.telegram.org"
_DEFAULT_POLL_TIMEOUT_S = 30


class TelegramProvider:
    kind = "telegram"

    def __init__(self, *, bot_token: str, poll_timeout_s: int = _DEFAULT_POLL_TIMEOUT_S) -> None:
        self._token = str(bot_token or "").strip()
        self._poll_timeout = max(1, int(poll_timeout_s))
        self._offset = 0
        self._stopped = asyncio.Event()
        # A read timeout must exceed the long-poll window, or every poll aborts.
        self._timeout = httpx.Timeout(
            connect=10.0, read=float(self._poll_timeout) + 10.0, write=10.0, pool=10.0
        )

    def _url(self, method: str) -> str:
        return f"{_API_BASE}/bot{self._token}/{method}"

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        if not self._token:
            return False
        payload = {"chat_id": message.external_chat, "text": message.text[:4000]}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(self._url("sendMessage"), json=payload)
                if res.status_code != 200:
                    log.warning("telegram sendMessage failed: HTTP %s", res.status_code)
                    return False
                return True
        except Exception:  # noqa: BLE001 - a delivery failure is reported, not raised
            log.warning("telegram sendMessage error", exc_info=True)
            return False

    # ── inbound ──────────────────────────────────────────────────────────────
    async def run(self, on_message: MessageHandler) -> None:
        if not self._token:
            log.warning("telegram provider has no bot token; poller not started")
            return
        log.info("telegram channel poller started")
        while not self._stopped.is_set():
            try:
                updates = await self._get_updates()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a transient poll error retries
                log.debug("telegram poll error", exc_info=True)
                await self._sleep(3.0)
                continue
            for update in updates:
                message = self._to_inbound(update)
                if message is None:
                    continue
                try:
                    await on_message(message)
                except Exception:  # noqa: BLE001 - one bad message never kills the poller
                    log.warning("telegram message handling failed", exc_info=True)

    async def stop(self) -> None:
        self._stopped.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _get_updates(self) -> list[dict[str, Any]]:
        params = {
            "offset": self._offset,
            "timeout": self._poll_timeout,
            "allowed_updates": '["message"]',
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.get(self._url("getUpdates"), params=params)
            if res.status_code != 200:
                return []
            data = res.json()
        if not isinstance(data, dict) or not data.get("ok"):
            return []
        out: list[dict[str, Any]] = []
        for update in data.get("result") or []:
            if isinstance(update, dict):
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                out.append(update)
        return out

    def _to_inbound(self, update: dict[str, Any]) -> Optional[InboundMessage]:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return None
        text = message.get("text") or message.get("caption") or ""
        if not str(text).strip():
            return None
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        sender_id = sender.get("id")
        if chat_id is None:
            return None
        name_parts = [sender.get("first_name"), sender.get("last_name")]
        display = " ".join(p for p in name_parts if p).strip() or str(sender.get("username") or "")
        return InboundMessage(
            kind=self.kind,
            external_id=str(sender_id if sender_id is not None else chat_id),
            external_chat=str(chat_id),
            text=str(text)[:4000],
            platform_message_id=str(update.get("update_id")),
            display_name=display,
            raw={"updateId": update.get("update_id"), "chatId": chat_id, "fromId": sender_id},
        )


__all__ = ["TelegramProvider"]
