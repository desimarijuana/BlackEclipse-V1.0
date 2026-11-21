"""Signal provider — outbound messages through a self-hosted signal-cli bridge.

Signal has no bot API and no server a harness can join: the only supported way to
send as a number is a local `signal-cli` (here, its REST wrapper
`bregman-arie/signal-cli-rest-api`), which the operator runs themselves. That is
the same deployment shape as Mattermost, Matrix and Zulip — the messages never
touch a third party.

    POST {baseUrl}/v2/send   {"message": "...", "number": "<bot number>",
                              "recipients": ["+15551234567"]}

**Declared limit — outbound only.** The bridge's receive endpoint is a streaming
socket with reconnect and de-duplication semantics this gateway does not yet
implement, and inventing a poll over it would produce a provider that looks
bidirectional and silently misses messages. So `inbound_mode="none"`: Signal is an
alerts surface (trade fills, risk breaches, job failures) until that receive path
is built properly.

Config:
  baseUrl    e.g. http://127.0.0.1:8080 (required)
  number     the bot's registered Signal number (required)
  apiToken   optional bearer token when the bridge is behind an authenticating proxy
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.signal")

_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)
_MAX_TEXT = 2_000   # Signal's practical message ceiling for a single frame


class SignalProvider:
    kind = "signal"

    def __init__(self, *, base_url: str, number: str, api_token: str = "") -> None:
        self._base = str(base_url or "").rstrip("/")
        self._number = str(number or "").strip()
        self._token = str(api_token or "")

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def send(self, message: OutboundMessage) -> bool:
        recipient = str(message.external_chat or "").strip()
        text = str(message.text or "").strip()
        if not self._base or not self._number or not recipient or not text:
            return False
        payload: dict[str, Any] = {
            "message": text[:_MAX_TEXT],
            "number": self._number,
            "recipients": [recipient],
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(f"{self._base}/v2/send", headers=self._headers,
                                        json=payload)
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("signal send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("signal bridge rejected the message: HTTP %s", res.status_code)
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """No inbound transport: nothing to await, so return immediately.

        A provider that claimed inbound would keep a task alive that can never
        deliver; returning says the truth, and the gateway does not start a poller
        for `inbound_mode="none"` anyway.
        """
        return None

    async def stop(self) -> None:
        return None


__all__ = ["SignalProvider"]
