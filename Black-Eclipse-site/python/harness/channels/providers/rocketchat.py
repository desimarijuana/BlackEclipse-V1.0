"""Rocket.Chat provider — channel-history poll inbound + `chat.postMessage` sends.

Rocket.Chat is self-hosted, so like Mattermost, Matrix and Zulip the operator keeps
the data. Its REST API is small and explicit:

    GET  /api/v1/me                              -> the bot's own `_id`
    GET  /api/v1/channels.history?roomId=…       -> messages, newest first
    POST /api/v1/chat.postMessage                -> {roomId, text}

Auth is two headers (`X-Auth-Token`, `X-User-Id`), not a bearer token.

Three rules, and why each is explicit:

  * **The bot must ignore itself.** History returns its own posts; the bot's
    `_id` is fetched once at start and every message from it is dropped.
  * **History is polled with a watermark.** `oldest` is a message timestamp, and
    the newest seen `ts` advances it, so a restart does not replay the room. The
    first poll deliberately starts from *now* — replaying a room's history into
    the agent would answer questions nobody asked.
  * **Messages are de-duplicated by `_id`.** Two polls can overlap at the
    boundary; a bounded seen-set makes that harmless rather than merely unlikely.

Config:
  baseUrl      e.g. https://chat.example.com (required)
  authToken    personal access token (secret, required)
  userId       the bot's user id (required — it is also what X-User-Id carries)
  roomId       default room to post to
  pollSeconds  history poll interval (default 5)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.rocketchat")

_MAX_TEXT = 5_000
_SEEN_LIMIT = 2_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RocketChatProvider:
    kind = "rocketchat"

    def __init__(
        self,
        *,
        base_url: str,
        auth_token: str,
        user_id: str,
        room_id: str = "",
        poll_seconds: int = 5,
    ) -> None:
        self._base = str(base_url or "").rstrip("/")
        self._token = str(auth_token or "")
        self._user = str(user_id or "")
        self._room = str(room_id or "")
        self._poll = max(1, int(poll_seconds))
        self._oldest = ""            # set to "now" on the first poll
        self._seen: dict[str, None] = {}
        self._stopped = asyncio.Event()
        self._timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)

    def _url(self, path: str) -> str:
        return f"{self._base}/api/v1{path}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self._token, "X-User-Id": self._user}

    def _remember(self, message_id: str) -> bool:
        if not message_id:
            return True
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        while len(self._seen) > _SEEN_LIMIT:
            self._seen.pop(next(iter(self._seen)))
        return True

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        room = str(message.external_chat or self._room or "").strip()
        text = str(message.text or "").strip()
        if not self._base or not self._token or not self._user or not room or not text:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(
                    self._url("/chat.postMessage"),
                    headers=self._headers,
                    json={"roomId": room, "text": text[:_MAX_TEXT]},
                )
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("rocketchat send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("rocketchat rejected the message: HTTP %s", res.status_code)
            return False
        try:
            body = res.json() or {}
        except Exception:  # noqa: BLE001 - the body is advisory
            return True
        return bool(body.get("success", True))

    # ── inbound ──────────────────────────────────────────────────────────────
    async def run(self, on_message: MessageHandler) -> None:
        if not self._base or not self._token or not self._user:
            log.warning("rocketchat provider is incomplete; poller not started")
            return
        if not self._oldest:
            # Start from now: history before the bot existed is not a conversation.
            self._oldest = _now_iso()
        log.info("rocketchat channel poller started")
        while not self._stopped.is_set():
            try:
                messages = await self._history()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a transient poll error retries
                log.debug("rocketchat poll error", exc_info=True)
                await self._sleep(float(self._poll))
                continue
            for message in self._to_inbound(messages):
                try:
                    await on_message(message)
                except Exception:  # noqa: BLE001 - one bad message never kills the poller
                    log.warning("rocketchat message handling failed", exc_info=True)
            await self._sleep(float(self._poll))

    async def stop(self) -> None:
        self._stopped.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _history(self) -> list[dict[str, Any]]:
        room = self._room
        if not room:
            return []
        params = {"roomId": room, "count": 50, "oldest": self._oldest}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.get(self._url("/channels.history"),
                                   headers=self._headers, params=params)
            if res.status_code != 200:
                return []
            body = res.json() or {}
        if body.get("success") is False:
            return []
        messages = [m for m in body.get("messages") or [] if isinstance(m, dict)]
        # History is newest-first; the watermark is the newest timestamp seen.
        for message in messages:
            stamp = str(message.get("ts") or "")
            if stamp > self._oldest:
                self._oldest = stamp
        return messages

    def _to_inbound(self, messages: list[dict[str, Any]]) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        for message in messages:
            inbound = self._event_to_inbound(message)
            if inbound is not None:
                out.append(inbound)
        return out

    def _event_to_inbound(self, message: dict[str, Any]) -> Optional[InboundMessage]:
        if not isinstance(message, dict):
            return None
        author = message.get("u") if isinstance(message.get("u"), dict) else {}
        sender_id = str(author.get("_id") or "")
        # Never treat the bot's own posts as user input.
        if not sender_id or sender_id == self._user:
            return None
        text = str(message.get("msg") or "").strip()
        if not text:
            return None
        message_id = str(message.get("_id") or "")
        if not self._remember(message_id):
            return None
        return InboundMessage(
            kind=self.kind,
            external_id=sender_id,
            external_chat=str(message.get("rid") or self._room),
            text=text[:_MAX_TEXT],
            platform_message_id=message_id,
            display_name=str(author.get("username") or sender_id),
            raw={"messageId": message_id, "roomId": message.get("rid"), "ts": message.get("ts")},
        )


__all__ = ["RocketChatProvider"]
