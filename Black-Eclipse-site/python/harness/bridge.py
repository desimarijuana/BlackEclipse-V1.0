"""The thin HTTP data bridge (Python → Next front door).

Extracted from `service.py` so that module stays within its size ratchet. This is
the ONE read-only transport the finance/retrieval/market tools use to reach JDdS
through the TS accessor; it is deliberately small and dependency-light (`httpx`
is imported lazily).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from typing import Any, Optional

from .tools import DataBridge

log = logging.getLogger("harness.service")


class HttpDataBridge(DataBridge):
    """Reads JDdS data through the thin TS bridge.

    Two timeout classes. A STRUCTURED/vault read (market snapshot, quote,
    fundamentals, provider adapters) must fail BEFORE the tool budget
    (`graph.py`: `toolTimeoutMs or 20_000`) so the tool returns a structured
    UNAVAILABLE instead of being killed as TOOL_TIMEOUT. A capability that fetches
    the public web
    (search/extract/education/image) may legitimately take longer and gets the
    slower class — still under the 30s research-tool budget.

    Retry: exactly ONE retry, and only on `ConnectError` — the dev-server-restart
    case, which fails instantly (observed as `All connection attempts failed` in
    `retrieval.source_unavailable`). Retrying a TIMEOUT would double the wait past
    the caller's budget, so it is never retried; the tool reports UNAVAILABLE and
    the agent can route elsewhere. A hung-but-listening server is therefore
    bounded by one per-class timeout, never by two.
    """

    #: The slowest structured read measured on this machine is
    #: `financial_statements` at 8.56 s (cold), so 8.0 s could never return it.
    #: 15 s covers that plus queueing and still fails well before the 20 s tool
    #: budget, keeping UNAVAILABLE distinguishable from TOOL_TIMEOUT.
    _TIMEOUT_S = 15.0
    _NETWORK_TIMEOUT_S = 20.0
    _RETRY_DELAY_S = 0.4
    #: A read that is safe to serve from the last successful response when the
    #: live route times out. Price history is the one that can be slow enough to
    #: cross the budget (the live `price_history` ReadTimeout); a stale series
    #: with an explicit `STALE` status is more useful than UNAVAILABLE, and the
    #: agent is told it is stale.
    _CACHE_CAPABILITIES = frozenset({"price_history"})
    _CACHE_SIZE = 32
    _NETWORK_CAPABILITIES = frozenset({
        "web_search", "web_fetch", "web_collect", "academic_search", "news_search",
        "image_search", "video_search", "playlist_search", "video_metadata",
        "transcript_fetch", "course_search", "github_search",
        # Collection routes reach a public source (SEC, the operator's REST
        # endpoint) through the front door's own guarded transport, which can
        # legitimately take longer than a vault read.
        "sec_filing_list", "custom_dataset_records",
    })

    def __init__(self, base_url: str, token: Optional[str]) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

    @staticmethod
    def _cache_key(capability: str, params: dict[str, Any]) -> str:
        return f"{capability}|{json.dumps(params, sort_keys=True, default=str)}"

    def _timeout_for(self, capability: str) -> float:
        return self._NETWORK_TIMEOUT_S if capability in self._NETWORK_CAPABILITIES else self._TIMEOUT_S

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        payload = {"capability": capability, "params": params}
        timeout = self._timeout_for(capability)
        cache_key = (
            self._cache_key(capability, params)
            if capability in self._CACHE_CAPABILITIES else None
        )
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
                data = response.json()
                if (
                    cache_key
                    and isinstance(data, dict)
                    and data.get("status") in (None, "OK")
                ):
                    self._cache[cache_key] = data
                    self._cache.move_to_end(cache_key)
                    while len(self._cache) > self._CACHE_SIZE:
                        self._cache.popitem(last=False)
                return data
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                # Both are "the connection was not usable": ConnectError is a
                # refused/absent listener, RemoteProtocolError is a peer that
                # accepted and then dropped the request. The second form carries
                # no `str()`, which is why it used to log as an empty line. Both
                # are safe to retry exactly once; a timeout never is.
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(self._RETRY_DELAY_S)
                    continue
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                break
        # A slow but previously successful read is served from the last good
        # response, explicitly marked STALE. This is the one place a timeout does
        # not become UNAVAILABLE: the series (and its retrievedAt) is real, and
        # the agent is told it is cached so it can label it.
        if cache_key and cache_key in self._cache:
            log.warning("data bridge stale (%s): serving the cached read", capability)
            return {
                **self._cache[cache_key],
                "status": "STALE",
                "stale": True,
                "cached": True,
            }
        # An exception whose `str()` is empty is undiagnosable - that is exactly
        # how three load-time failures were logged as `data bridge failed (...):`
        # with nothing after the colon. The TYPE is the only thing that separates
        # a timeout from a dropped connection, so it is always logged and always
        # returned.
        detail = f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown"
        log.warning("data bridge failed (%s): %s", capability, detail)
        return {"status": "UNAVAILABLE", "error": detail}

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON body to a front-door route that WRITES.

        The read bridge above is read-only by design. The scraper lane is the
        one place the runtime hands collected rows back to the front door (which
        owns the vault), so it gets its own explicit, narrow seam rather than a
        write-capable `/api/harness/data`.
        """
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        url = f"{self._base}/{str(path).lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self._NETWORK_TIMEOUT_S) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                return {"ok": False, "error": f"the front door refused the rows (HTTP {response.status_code})"}
            body = response.json()
        except Exception as exc:  # noqa: BLE001 - a transport failure is an honest failure
            log.warning("bridge write failed (%s): %s", path, exc)
            return {"ok": False, "error": str(exc)}
        return body if isinstance(body, dict) else {"ok": False, "error": "unreadable answer"}


__all__ = ["HttpDataBridge"]
