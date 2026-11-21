"""WeCom (WeChat Work) provider — group-robot alerts, and why there is no inbound.

A WeCom **group robot** is one URL: `POST .../cgi-bin/webhook/send?key=...` with
`{"msgtype": "text", "text": {"content": "..."}}`, answering `{"errcode": 0,
"errmsg": "ok"}`. It is the cheapest way to reach a Chinese trading desk's group
chat, and it is **outbound-only by design**: WeCom's inbound path is an encrypted
callback (AES + SHA1 token check) on an app, not on a group robot, so declaring
`inbound_mode="none"` is the accurate contract rather than a limitation of effort.

The response is the important part: WeCom returns **HTTP 200 with a non-zero
`errcode`** for a bad key or a rate limit, so the code — not the status — decides
success.

Config:
  webhookKey  the robot's key from the group chat (secret, required)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.wecom")

_BASE = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
_MAX_TEXT = 2_000   # WeCom's text-message ceiling is 2048 bytes; stay under


class WecomProvider:
    kind = "wecom"

    def __init__(self, *, webhook_key: str) -> None:
        self._key = str(webhook_key or "")

    async def send(self, message: OutboundMessage) -> bool:
        text = str(message.text or "").strip()
        if not self._key or not text:
            return False
        payload = {"msgtype": "text", "text": {"content": text[:_MAX_TEXT]}}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(
                    connect=10.0, read=20.0, write=20.0, pool=10.0)) as client:
                res = await client.post(_BASE, params={"key": self._key}, json=payload)
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("wecom send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("wecom rejected the message: HTTP %s", res.status_code)
            return False
        try:
            body = res.json() or {}
        except Exception:  # noqa: BLE001 - the body is advisory
            return False
        if int(body.get("errcode") or 0) != 0:
            log.warning("wecom refused the message: %s", str(body.get("errmsg") or "")[:200])
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """Group robots have no inbound: return rather than hold an idle task."""
        return None

    async def stop(self) -> None:
        return None


__all__ = ["WecomProvider"]
