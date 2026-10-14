"""The thin HTTP data bridge (Python → Next front door).

Extracted from `service.py` so that module stays within its size ratchet. This is
the ONE read-only transport the finance/retrieval/market tools use to reach JDdS
through the TS accessor; it is deliberately small and dependency-light (`httpx`
is imported lazily).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .tools import DataBridge

log = logging.getLogger("harness.service")


class HttpDataBridge(DataBridge):
    """Reads JDdS data through the thin TS bridge.

    Two timeout classes. A STRUCTURED/vault read (market snapshot, quote,
    fundamentals, provider adapters) must fail BEFORE the smallest market-tool
    budget (10s) so the tool returns a structured UNAVAILABLE instead of being
    killed as TOOL_TIMEOUT. A capability that fetches the public web
    (search/extract/education/image) may legitimately take longer and gets the
    slower class — still under the 30s research-tool budget.

    Retry: exactly ONE retry, and only on `ConnectError` — the dev-server-restart
    case, which fails instantly (observed as `All connection attempts failed` in
    `retrieval.source_unavailable`). Retrying a TIMEOUT would double the wait past
    the caller's budget, so it is never retried; the tool reports UNAVAILABLE and
    the agent can route elsewhere. A hung-but-listening server is therefore
    bounded by one per-class timeout, never by two.
    """

    _TIMEOUT_S = 8.0
    _NETWORK_TIMEOUT_S = 20.0
    _RETRY_DELAY_S = 0.4
    _NETWORK_CAPABILITIES = frozenset({
        "web_search", "web_fetch", "web_collect", "academic_search", "news_search",
        "image_search", "video_search", "playlist_search", "video_metadata",
        "transcript_fetch", "course_search", "github_search",
    })

    def __init__(self, base_url: str, token: Optional[str]) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def _timeout_for(self, capability: str) -> float:
        return self._NETWORK_TIMEOUT_S if capability in self._NETWORK_CAPABILITIES else self._TIMEOUT_S

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        payload = {"capability": capability, "params": params}
        timeout = self._timeout_for(capability)
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self._base}/api/harness/data",
                        headers=headers,
                        json=payload,
                    )
                if response.status_code >= 400:
                    return {"status": "UNAVAILABLE", "error": f"bridge HTTP {response.status_code}"}
                return response.json()
            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(self._RETRY_DELAY_S)
                    continue
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                break
        log.warning("data bridge failed (%s): %s", capability, last_exc)
        return {"status": "UNAVAILABLE", "error": str(last_exc)}


__all__ = ["HttpDataBridge"]
