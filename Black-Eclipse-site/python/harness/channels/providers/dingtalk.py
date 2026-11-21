"""DingTalk provider — outbound-only via a custom-robot webhook.

A DingTalk custom robot accepts one signed HTTPS POST. There is no inbound
transport here: DingTalk's *Stream Mode* needs its own SDK and a long-lived
websocket, so this provider advertises `inbound_mode="none"` rather than pretending
to receive. That makes it an **alerts/notifications** channel: scheduled briefs,
risk alerts, bot results.

Signing (DingTalk's documented algorithm): with a robot secret,

    string_to_sign = f"{timestamp_ms}\\n{secret}"
    sign           = base64(hmac_sha256(secret, string_to_sign))

and both `timestamp` and `sign` go in the query string. A webhook with no secret
is sent unsigned (DingTalk allows that, more weakly).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any, Optional

import httpx

from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.dingtalk")

_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_MAX_TEXT = 4000


def sign_webhook(url: str, secret: str, *, timestamp_ms: Optional[int] = None) -> str:
    """Return `url` with DingTalk's `timestamp`/`sign` query parameters.

    No secret means the URL is returned unchanged (unsigned POST). Pure, so the
    exact signing input is testable without a network.
    """
    if not secret:
        return url
    stamp = str(int(timestamp_ms if timestamp_ms is not None else time.time() * 1000))
    to_sign = f"{stamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), to_sign, hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest).decode("utf-8"))
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}timestamp={stamp}&sign={sign}"


class DingTalkProvider:
    kind = "dingtalk"

    def __init__(self, *, webhook_url: str, sign_secret: str = "") -> None:
        self._url = str(webhook_url or "").strip()
        self._secret = str(sign_secret or "").strip()
        self._stop = asyncio.Event()

    async def send(self, message: OutboundMessage) -> bool:
        text = str(message.text or "").strip()
        if not self._url or not text:
            return False
        body: dict[str, Any] = {"msgtype": "text", "text": {"content": text[:_MAX_TEXT]}}
        try:
            url = sign_webhook(self._url, self._secret)
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(url, json=body)
            data = res.json() if res.content else {}
        except Exception as exc:  # noqa: BLE001 - a delivery failure is a False, never a crash
            log.warning("dingtalk send failed: %s", exc)
            return False
        if res.status_code >= 400:
            log.warning("dingtalk rejected the message: HTTP %s %s", res.status_code, data)
            return False
        # DingTalk answers HTTP 200 with `errcode != 0` on an application error.
        if isinstance(data, dict) and int(data.get("errcode") or 0) != 0:
            log.warning("dingtalk application error: %s", data.get("errmsg"))
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """No inbound transport: wait until the gateway stops this provider."""
        await self._stop.wait()

    async def stop(self) -> None:
        self._stop.set()


__all__ = ["DingTalkProvider", "sign_webhook"]
