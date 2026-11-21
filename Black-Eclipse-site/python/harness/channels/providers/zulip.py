"""Zulip provider — event-queue long-poll inbound + stream sends.

Zulip is an open-source, self-hosted team chat, so like Matrix and Mattermost the
operator keeps the data. Its API is unusually explicit:

    POST /api/v1/register            -> queue_id, last_event_id
    GET  /api/v1/events?queue_id=…   -> the next events (long-poll)
    POST /api/v1/messages            -> send

Two consequences, stated rather than hidden:

  * **The bot must ignore itself.** Zulip delivers the bot's own sends back
    through the event queue, so every event whose `sender_email` is the bot's own
    address is dropped — without that, each reply re-triggers the agent.
  * **Replies go to one configured stream + topic.** Zulip requires a topic for a
    stream message; per-thread reply routing is not implemented, so `topic` is
    config with a documented default rather than a guess from the payload.

Auth is HTTP Basic with `bot_email:api_key`, which is what Zulip expects (not a
Bearer token).

Config:
  site         e.g. https://chat.example.com (required)
  botEmail     the bot's Zulip address (required)
  apiKey       bot API key (secret, required)
  defaultStream  stream to reply into when a message names none
  topic        topic for replies (default "eclipse")
  pollSeconds  event long-poll window (default 30)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.zulip")

_MAX_TEXT = 10_000


class ZulipProvider:
    kind = "zulip"

    def __init__(
        self,
        *,
        site: str,
        bot_email: str,
        api_key: str,
        default_stream: str = "",
        topic: str = "eclipse",
        poll_seconds: int = 30,
    ) -> None:
        self._site = str(site or "").rstrip("/")
        self._email = str(bot_email or "").strip()
        self._key = str(api_key or "")
        self._stream = str(default_stream or "").strip()
        self._topic = str(topic or "eclipse").strip() or "eclipse"
        self._poll = max(1, int(poll_seconds))
        self._queue_id = ""
        self._last_event_id = -1
        self._stopped = asyncio.Event()
        # The long-poll read timeout must exceed the server's window.
        self._timeout = httpx.Timeout(
            connect=10.0, read=float(self._poll) + 10.0, write=10.0, pool=10.0
        )

    def _url(self, path: str) -> str:
        return f"{self._site}/api/v1{path}"

    @property
    def _auth(self) -> tuple[str, str]:
        return (self._email, self._key)

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        stream = str(message.external_chat or self._stream or "").strip()
        text = str(message.text or "").strip()
        if not self._site or not self._key or not stream or not text:
            return False
        data = {
            "type": "stream",
            "to": stream,
            "topic": self._topic,
            "content": text[:_MAX_TEXT],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(self._url("/messages"), data=data, auth=self._auth)
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("zulip send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("zulip rejected the message: HTTP %s", res.status_code)
            return False
        try:
            body = res.json() or {}
        except Exception:  # noqa: BLE001 - the body is advisory
            return True
        if body.get("result") == "error":
            log.warning("zulip refused the message: %s", str(body.get("msg") or "")[:200])
            return False
        return True

    # ── inbound ──────────────────────────────────────────────────────────────
    async def run(self, on_message: MessageHandler) -> None:
        if not self._site or not self._email or not self._key:
            log.warning("zulip provider is incomplete; poller not started")
            return
        log.info("zulip channel poller started")
        while not self._stopped.is_set():
            try:
                if not self._queue_id:
                    await self._register()
                    continue
                events = await self._events()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a transient poll error retries
                log.debug("zulip poll error", exc_info=True)
                self._queue_id = ""     # a dead queue is re-registered
                await self._sleep(3.0)
                continue
            for message in self._to_inbound(events):
                try:
                    await on_message(message)
                except Exception:  # noqa: BLE001 - one bad message never kills the poller
                    log.warning("zulip message handling failed", exc_info=True)

    async def stop(self) -> None:
        self._stopped.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _register(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.post(
                self._url("/register"),
                data={"event_types": '["message"]'},
                auth=self._auth,
            )
            if res.status_code != 200:
                return
            body = res.json() or {}
        if body.get("result") != "success" or not body.get("queue_id"):
            return
        self._queue_id = str(body["queue_id"])
        self._last_event_id = int(body.get("last_event_id") or -1)

    async def _events(self) -> list[dict[str, Any]]:
        params = {
            "queue_id": self._queue_id,
            "last_event_id": self._last_event_id,
            "dont_block": "false",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.get(self._url("/events"), params=params, auth=self._auth)
            if res.status_code != 200:
                # A queue we cannot read (expired, or the server restarted) is
                # dropped so the poller registers a fresh one.
                self._queue_id = ""
                return []
            body = res.json() or {}
        if body.get("result") != "success":
            self._queue_id = ""
            return []
        events = [e for e in body.get("events") or [] if isinstance(e, dict)]
        for event in events:
            try:
                self._last_event_id = max(self._last_event_id, int(event.get("id", -1)))
            except (TypeError, ValueError):
                continue
        return events

    def _to_inbound(self, events: list[dict[str, Any]]) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        for event in events:
            message = self._event_to_inbound(event)
            if message is not None:
                out.append(message)
        return out

    def _event_to_inbound(self, event: dict[str, Any]) -> Optional[InboundMessage]:
        if not isinstance(event, dict) or event.get("type") != "message":
            return None
        message = event.get("message")
        if not isinstance(message, dict):
            return None
        sender = str(message.get("sender_email") or "")
        # Never treat the bot's own sends as user input.
        if not sender or sender == self._email:
            return None
        text = str(message.get("content") or "").strip()
        if not text:
            return None
        kind = str(message.get("type") or "")
        stream = str(message.get("display_recipient") or "") if kind == "stream" else ""
        chat = stream or "direct"
        return InboundMessage(
            kind=self.kind,
            external_id=str(message.get("sender_id") or sender),
            external_chat=chat,
            text=text[:_MAX_TEXT],
            platform_message_id=str(message.get("id") or ""),
            display_name=str(message.get("sender_full_name") or sender),
            raw={
                "messageId": message.get("id"),
                "senderEmail": sender,
                "stream": stream,
                "topic": message.get("subject"),
            },
        )


__all__ = ["ZulipProvider"]
