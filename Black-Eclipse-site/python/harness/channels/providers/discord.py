"""Discord provider — bot Gateway WebSocket (inbound) + REST (outbound).

Like Telegram, Discord needs NO public endpoint: the bot connects outward to the
Discord Gateway and receives messages over that WebSocket. A user links by
messaging the bot (`/link <code>`); the bot must share a server with the user (or
be user-installed) to receive DMs — the ordinary Discord constraint.

The bot token comes from the channel config and is never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.discord")

_API = "https://discord.com/api/v10"
_GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"

# GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT — enough to read
# server-channel + DM text (Discord requires MESSAGE_CONTENT to see message text).
_INTENTS = (1 << 0) | (1 << 9) | (1 << 12) | (1 << 15)

# Discord's hard per-message content limit; longer replies are split.
_MAX_CONTENT = 2000


class DiscordProvider:
    kind = "discord"

    def __init__(self, *, bot_token: str) -> None:
        self._token = str(bot_token or "").strip()
        self._stopped = asyncio.Event()
        self._timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        if not self._token:
            return False
        url = f"{_API}/channels/{message.external_chat}/messages"
        headers = {"Authorization": f"Bot {self._token}", "Content-Type": "application/json"}
        for chunk in _chunk(message.text, _MAX_CONTENT):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    res = await client.post(
                        url,
                        headers=headers,
                        json={"content": chunk, "allowed_mentions": {"parse": []}},
                    )
                    if res.status_code >= 300:
                        log.warning("discord send failed: HTTP %s", res.status_code)
                        return False
            except Exception:  # noqa: BLE001 - a delivery failure is reported, not raised
                log.warning("discord send error", exc_info=True)
                return False
        return True

    # ── inbound ──────────────────────────────────────────────────────────────
    async def stop(self) -> None:
        self._stopped.set()

    async def run(self, on_message: MessageHandler) -> None:
        if not self._token:
            log.warning("discord provider has no bot token; gateway not started")
            return
        try:
            import websockets  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - a missing dependency is an honest no-op
            log.warning("discord provider unavailable (websockets not installed)")
            return
        log.info("discord channel gateway started")
        backoff = 1.0
        while not self._stopped.is_set():
            heartbeat: Optional[asyncio.Task[Any]] = None
            try:
                async with websockets.connect(_GATEWAY, max_size=2**20) as ws:
                    hello = json.loads(await ws.recv())
                    interval = float((hello.get("d") or {}).get("heartbeat_interval", 41250)) / 1000.0
                    seq = [None]
                    await self._identify(ws)
                    heartbeat = asyncio.create_task(self._heartbeat(ws, interval, seq))
                    backoff = 1.0
                    while not self._stopped.is_set():
                        raw = await ws.recv()
                        frame = json.loads(raw)
                        op = frame.get("op")
                        if op == 0:
                            seq[0] = frame.get("s")
                            if frame.get("t") == "MESSAGE_CREATE":
                                message = self._to_inbound(frame.get("d") or {})
                                if message is not None:
                                    try:
                                        await on_message(message)
                                    except Exception:  # noqa: BLE001 - one bad message never kills the gateway
                                        log.warning("discord message handling failed", exc_info=True)
                        elif op == 1:
                            await self._send_heartbeat(ws, seq[0])
                        elif op in (7, 9):
                            break  # reconnect
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the gateway reconnects with backoff
                log.debug("discord gateway error", exc_info=True)
            finally:
                if heartbeat is not None:
                    heartbeat.cancel()
            if not self._stopped.is_set():
                await self._sleep(min(backoff, 30.0))
                backoff = min(backoff * 2, 30.0)

    def _identify_payload(self) -> dict[str, Any]:
        return {
            "op": 2,
            "d": {
                "token": self._token,
                "intents": _INTENTS,
                "properties": {"os": "win32", "browser": "eclipse", "device": "eclipse"},
            },
        }

    async def _identify(self, ws: Any) -> None:
        await ws.send(json.dumps(self._identify_payload()))

    async def _heartbeat(self, ws: Any, interval: float, seq: list[Any]) -> None:
        try:
            await asyncio.sleep(interval * 0.5)  # jitter per Discord spec
            while True:
                await self._send_heartbeat(ws, seq[0])
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the connection loop owns recovery
            return

    async def _send_heartbeat(self, ws: Any, seq: Any) -> None:
        try:
            await ws.send(json.dumps({"op": 1, "d": seq}))
        except Exception:  # noqa: BLE001
            pass

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _to_inbound(self, data: dict[str, Any]) -> Optional[InboundMessage]:
        if not isinstance(data, dict):
            return None
        author = data.get("author") or {}
        if author.get("bot"):
            return None
        content = str(data.get("content") or "").strip()
        channel_id = data.get("channel_id")
        author_id = author.get("id")
        if not content or not channel_id or not author_id:
            return None
        return InboundMessage(
            kind=self.kind,
            external_id=str(author_id),
            external_chat=str(channel_id),
            text=content[:4000],
            platform_message_id=str(data.get("id") or ""),
            display_name=str(author.get("global_name") or author.get("username") or ""),
            raw={"guildId": data.get("guild_id")},
        )


def _chunk(text: str, size: int) -> list[str]:
    """Split a reply into <=`size` pieces (empty/blank text yields nothing)."""
    body = str(text or "")
    if not body:
        return []
    return [body[i : i + size] for i in range(0, len(body), size)]


__all__ = ["DiscordProvider"]
