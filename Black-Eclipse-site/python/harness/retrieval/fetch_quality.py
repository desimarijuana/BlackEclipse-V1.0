"""Research-fetch quality: bounded retry, body cache, success rate (D9).

The observed 61% historical fetch success was not a provider outage: transient
timeouts were treated like definitive failures and successful bodies were
re-fetched on every request. This module owns the ONE retry/cache policy used by
research retrieval:

* retry ONLY timeout / transport / 5xx / 429 - never a definitive 4xx;
* cache a successful body per URL for a declared window and report a cache hit
  distinctly from a live fetch;
* escalate to the browser path when static extraction yields no text AND the
  page is known client-rendered;
* report the achieved success rate per route, so degradation is measurable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

FetchFn = Callable[[str], Awaitable[dict[str, Any]]]


def retryable_failure(payload: dict[str, Any]) -> bool:
    """Whether a failed fetch payload is worth retrying."""
    status = str(payload.get("status") or "").upper()
    if status == "OK":
        return False
    diagnostics = payload.get("diagnostics")
    for diag in diagnostics if isinstance(diagnostics, list) else []:
        if not isinstance(diag, dict):
            continue
        http = diag.get("httpStatus")
        if isinstance(http, int) and 400 <= http < 500 and http != 429:
            return False  # definitive 4xx: never retry
        if diag.get("retryable"):
            return True
        if str(diag.get("category")) in ("timeout", "transport_error", "rate_limited"):
            return True
    error = str(payload.get("error") or "").lower()
    if any(token in error for token in ("timeout", "timed out", "connection", "socket", "5xx")):
        return True
    if any(token in error for token in ("403", "404", "401", "400", "forbidden", "not found")):
        return False
    return False


def looks_client_rendered(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("clientRendered")
        or payload.get("javascriptOnly")
        or str(payload.get("rendering") or "").lower() in ("client", "spa", "javascript")
    )


@dataclass
class FetchQuality:
    url_window_s: float = 900.0
    max_retries: int = 2
    base_delay_s: float = 0.2
    max_delay_s: float = 2.0
    # URL -> (expires_at, payload)
    _cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: {
        "liveFetches": 0, "cacheHits": 0, "successes": 0, "failures": 0,
        "retries": 0, "browserEscalations": 0, "emptyExtractions": 0,
    })

    def cached(self, url: str, *, now: Optional[float] = None) -> Optional[dict[str, Any]]:
        entry = self._cache.get(url)
        if entry is None:
            return None
        expires, payload = entry
        if (now or time.time()) >= expires:
            self._cache.pop(url, None)
            return None
        self.counters["cacheHits"] += 1
        return {**payload, "cached": True, "cacheHit": True}

    async def fetch(self, url: str, fetch: FetchFn, *,
                    browser: Optional[FetchFn] = None) -> dict[str, Any]:
        cached = self.cached(url)
        if cached is not None:
            self.counters["successes"] += 1
            return cached

        attempt = 0
        payload: dict[str, Any] = {}
        while True:
            self.counters["liveFetches"] += 1
            payload = await fetch(url)
            if payload.get("status") == "OK":
                break
            if attempt >= max(0, self.max_retries) or not retryable_failure(payload):
                break
            delay = min(self.max_delay_s, self.base_delay_s * (2 ** attempt))
            attempt += 1
            self.counters["retries"] += 1
            import asyncio

            await asyncio.sleep(delay)

        if payload.get("status") != "OK":
            self.counters["failures"] += 1
            return payload

        text = str(payload.get("text") or "").strip()
        if not text:
            self.counters["emptyExtractions"] += 1
            if browser is not None and looks_client_rendered(payload):
                self.counters["browserEscalations"] += 1
                escalated = await browser(url)
                if escalated.get("status") == "OK" and str(escalated.get("text") or "").strip():
                    payload = escalated
                    text = str(payload.get("text") or "").strip()
            if not text:
                # Fetched but unreadable: never a successful empty extraction.
                self.counters["failures"] += 1
                return {
                    **payload,
                    "status": "UNAVAILABLE",
                    "failureClass": "unsupported_document",
                    "error": "fetched but no extractable text",
                    "documentStatus": "IMAGE_ONLY",
                }

        self._cache[url] = (time.time() + self.url_window_s, payload)
        self.counters["successes"] += 1
        return {**payload, "cached": False, "cacheHit": False}

    def stats(self) -> dict[str, Any]:
        attempts = self.counters["successes"] + self.counters["failures"]
        rate = (self.counters["successes"] / attempts) if attempts else 0.0
        return {
            **self.counters,
            "attempts": attempts,
            "successRate": round(rate, 4),
        }


__all__ = ["FetchQuality", "looks_client_rendered", "retryable_failure"]
