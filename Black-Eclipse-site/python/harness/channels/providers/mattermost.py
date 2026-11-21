"""Mattermost provider — outbound notifications over the REST API.

Mattermost is self-hosted, so it is a genuinely different deployment from every
cloud channel here: the operator supplies a base URL, a bot token and a channel
id, and nothing leaves their network except the post itself.

`inbound_mode="none"`: this provider only writes. Mattermost's *outgoing* webhook
posts to us, which needs a per-kind signature check the gateway does not yet do;
declaring `push` without that check would accept unverified traffic, so the
honest declaration is "send only" until that verification exists.

Config:
  baseUrl     e.g. https://chat.example.com (required)
  botToken    bot account token (secret, required)
  channelId   default channel to post to (required)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.mattermost")

_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_MAX_TEXT = 16_000  # Mattermost's default post limit


class MattermostProvider:
    kind = "mattermost"

    def __init__(self, *, base_url: str, bot_token: str, channel_id: str) -> None:
        self._base = str(base_url or "").rstrip("/")
        self._token = str(bot_token or "")
        self._channel = str(channel_id or "")
        self._stop = asyncio.Event()

    async def send(self, message: OutboundMessage) -> bool:
        text = str(message.text or "").strip()
        channel = str(message.external_chat or self._channel or "").strip()
        if not self._base or not self._token or not channel or not text:
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(
                    f"{self._base}/api/v4/posts",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={"channel_id": channel, "message": text[:_MAX_TEXT]},
                )
        except Exception as exc:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("mattermost send failed: %s", exc)
            return False
        if res.status_code >= 400:
            log.warning("mattermost rejected the post: HTTP %s", res.status_code)
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """No inbound transport: wait until the gateway stops this provider."""
        await self._stop.wait()

    async def stop(self) -> None:
        self._stop.set()


__all__ = ["MattermostProvider"]
