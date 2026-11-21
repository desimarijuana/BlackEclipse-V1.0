"""Matrix provider — `/sync` long-poll inbound + `m.room.message` sends.

Matrix is the open, federated one: any homeserver (Synapse, Dendrite, matrix.org,
a self-hosted box) speaks the same client-server API, so like Mattermost it keeps
the operator in control of where messages live. It is a **pull** provider — the
runtime long-polls `/sync` from the local machine — so it needs no public
endpoint and does not widen the attack surface.

Two details that are easy to get wrong, and are therefore explicit:

  * **The bot must ignore itself.** Matrix delivers the bot's own sends back
    through `/sync`; without a sender filter every reply would re-trigger the
    agent. `userId` (the bot's own MXID) is what makes that filter possible, and
    it is required, not optional.
  * **Events are re-delivered on reconnect.** `since` prevents most of it, but a
    bounded seen-set makes duplicate handling impossible rather than unlikely.

Config:
  homeserverUrl  e.g. https://matrix.example.org (required)
  accessToken    bot access token (secret, required)
  userId         the bot's own MXID, e.g. @eclipse:example.org (required)
  defaultRoomId  room to post to when the caller does not name one
  pollTimeoutMs  /sync long-poll window (default 30000)
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
import uuid
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.matrix")

_TIMEOUT_S = 30
_MAX_TEXT = 32_000
_SEEN_LIMIT = 2_000

#: Event types that carry human text we will hand to the agent.
_TEXT_TYPES = frozenset({"m.text", "m.notice", "m.emote"})


class MatrixProvider:
    kind = "matrix"

    def __init__(
        self,
        *,
        homeserver_url: str,
        access_token: str,
        user_id: str,
        default_room_id: str = "",
        poll_timeout_ms: int = 30_000,
    ) -> None:
        self._base = str(homeserver_url or "").rstrip("/")
        self._token = str(access_token or "")
        self._user = str(user_id or "")        # the bot's own MXID
        self._room = str(default_room_id or "")
        self._poll_ms = max(1_000, int(poll_timeout_ms))
        self._since: Optional[str] = None
        self._seen: dict[str, None] = {}       # insertion-ordered, bounded
        self._stopped = asyncio.Event()
        self._timeout = httpx.Timeout(
            connect=10.0, read=self._poll_ms / 1000.0 + 10.0, write=10.0, pool=10.0
        )

    # ── shared ───────────────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        return f"{self._base}/_matrix/client/v3{path}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _remember(self, event_id: str) -> bool:
        """True the first time an event id is seen; False for a replay."""
        if not event_id:
            return True
        if event_id in self._seen:
            return False
        self._seen[event_id] = None
        while len(self._seen) > _SEEN_LIMIT:
            self._seen.pop(next(iter(self._seen)))
        return True

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        room = str(message.external_chat or self._room or "").strip()
        text = str(message.text or "").strip()
        if not self._base or not self._token or not room or not text:
            return False
        # Room ids contain `!` and `:`; the path segment must be escaped whole.
        room_path = urllib.parse.quote(room, safe="")
        url = self._url(f"/rooms/{room_path}/send/m.room.message/{uuid.uuid4().hex}")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.put(
                    url,
                    headers=self._headers,
                    json={"msgtype": "m.text", "body": text[:_MAX_TEXT]},
                )
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("matrix send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("matrix rejected the message: HTTP %s", res.status_code)
            return False
        event_id = ""
        try:
            event_id = str((res.json() or {}).get("event_id") or "")
        except Exception:  # noqa: BLE001 - the body is advisory
            event_id = ""
        # Our own event must not come back through /sync as inbound work.
        self._remember(event_id)
        return True

    # ── inbound ──────────────────────────────────────────────────────────────
    async def run(self, on_message: MessageHandler) -> None:
        if not self._base or not self._token or not self._user:
            log.warning("matrix provider is incomplete; poller not started")
            return
        log.info("matrix channel poller started")
        while not self._stopped.is_set():
            try:
                sync = await self._sync()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a transient poll error retries
                log.debug("matrix poll error", exc_info=True)
                await self._sleep(3.0)
                continue
            for message in self._to_inbound(sync):
                try:
                    await on_message(message)
                except Exception:  # noqa: BLE001 - one bad message never kills the poller
                    log.warning("matrix message handling failed", exc_info=True)

    async def stop(self) -> None:
        self._stopped.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _sync(self) -> dict[str, Any]:
        params: dict[str, Any] = {"timeout": self._poll_ms}
        if self._since:
            params["since"] = self._since
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.get(self._url("/sync"), headers=self._headers, params=params)
            if res.status_code != 200:
                return {}
            data = res.json()
        if not isinstance(data, dict):
            return {}
        self._since = str(data.get("next_batch") or self._since or "") or None
        return data

    def _to_inbound(self, sync: dict[str, Any]) -> list[InboundMessage]:
        rooms = sync.get("rooms") if isinstance(sync, dict) else None
        joined = rooms.get("join") if isinstance(rooms, dict) else None
        out: list[InboundMessage] = []
        for room_id, room in (joined or {}).items():
            timeline = room.get("timeline") if isinstance(room, dict) else None
            for event in (timeline or {}).get("events") or []:
                message = self._event_to_inbound(room_id, event)
                if message is not None:
                    out.append(message)
        return out

    def _event_to_inbound(self, room_id: str, event: Any) -> Optional[InboundMessage]:
        if not isinstance(event, dict) or event.get("type") != "m.room.message":
            return None
        sender = str(event.get("sender") or "")
        # Never treat our own sends (or any bridge bot echo) as user input.
        if not sender or sender == self._user:
            return None
        content = event.get("content") if isinstance(event.get("content"), dict) else {}
        if str(content.get("msgtype") or "") not in _TEXT_TYPES:
            return None
        text = str(content.get("body") or "").strip()
        if not text:
            return None
        event_id = str(event.get("event_id") or "")
        if not self._remember(event_id):
            return None
        return InboundMessage(
            kind=self.kind,
            external_id=sender,
            external_chat=str(room_id),
            text=text[:_MAX_TEXT],
            platform_message_id=event_id,
            display_name=sender,
            raw={"roomId": room_id, "sender": sender, "eventId": event_id},
        )


__all__ = ["MatrixProvider"]
