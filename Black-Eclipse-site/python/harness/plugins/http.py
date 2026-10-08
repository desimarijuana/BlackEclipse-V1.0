"""A controlled HTTP client for plugins.

Plugins never touch the network directly. Every request goes through this client,
which centralizes timeouts, retries with exponential backoff, per-host rate
limiting, a per-host circuit breaker, request IDs, telemetry and a metadata-IP
SSRF guard. The `network` permission is enforced on every call.

The client reuses the existing `mcp.circuit.CircuitBreaker` rather than inventing
a second breaker. It returns a small `HttpResponse` value object (status, headers,
text, `json()`), so a plugin never handles a raw transport object.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json as _json
import random
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional
from urllib.parse import urlparse

from ..mcp.circuit import CircuitBreaker
from .errors import PluginError
from .permissions import GrantedPermissions


class HttpError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


# Cloud instance-metadata endpoints. Always refused, even with `network`, because
# a plugin has no legitimate reason to fetch instance credentials.
_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}


@dataclass
class RateLimiter:
    """A token bucket. `rate` tokens/second, `burst` capacity."""

    rate: float = 10.0
    burst: float = 20.0
    _tokens: float = field(default=0.0, init=False)
    _last: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = self.burst
        self._last = time.monotonic()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / self.rate)


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    content: bytes
    url: str
    request_id: str

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return _json.loads(self.content.decode("utf-8"))

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "url": self.url,
            "requestId": self.request_id,
            "headers": self.headers,
            "body": self.text[:20_000],
        }


class PluginHttp:
    """Per-plugin HTTP access with mandatory permission + policy enforcement."""

    def __init__(
        self,
        plugin_id: str,
        permissions: GrantedPermissions,
        *,
        timeout_s: float = 20.0,
        retries: int = 2,
        rate: float = 10.0,
        burst: float = 20.0,
        allowed_hosts: Optional[list[str]] = None,
        on_telemetry: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._permissions = permissions
        self._timeout = timeout_s
        self._retries = max(0, retries)
        self._limiter = RateLimiter(rate=rate, burst=burst)
        self._allowed_hosts = {h.lower() for h in allowed_hosts} if allowed_hosts else None
        self._breakers: dict[str, CircuitBreaker] = {}
        self._telemetry = on_telemetry

    # ── policy ───────────────────────────────────────────────────────────────

    def _guard(self, method: str, url: str) -> None:
        self._permissions.require("network", f"http.{method.lower()}")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https", "ws", "wss"):
            raise HttpError("PLUGIN_HTTP_SCHEME", f"unsupported URL scheme: {parsed.scheme!r}")
        host = (parsed.hostname or "").lower()
        if not host:
            raise HttpError("PLUGIN_HTTP_URL", "URL has no host")
        if host in _METADATA_HOSTS:
            raise HttpError("PLUGIN_HTTP_BLOCKED", "requests to the instance metadata endpoint are refused")
        if self._allowed_hosts is not None and host not in self._allowed_hosts:
            raise HttpError(
                "PLUGIN_HTTP_HOST_NOT_ALLOWED",
                f"host {host!r} is not in this plugin's allowed-hosts list",
                detail={"host": host, "allowed": sorted(self._allowed_hosts)},
            )
        self._check_resolved_ip(host)

    @staticmethod
    def _check_resolved_ip(host: str) -> None:
        """Refuse a hostname that resolves to a metadata/link-local IP."""
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception:  # noqa: BLE001 - a DNS failure surfaces later as a transport error
            return
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if str(ip) in _METADATA_HOSTS or (ip.is_link_local and not ip.is_loopback):
                raise HttpError("PLUGIN_HTTP_BLOCKED", f"host {host!r} resolves to a blocked address")

    def _breaker(self, host: str) -> CircuitBreaker:
        if host not in self._breakers:
            self._breakers[host] = CircuitBreaker()
        return self._breakers[host]

    def _emit(self, name: str, data: dict[str, Any]) -> None:
        if self._telemetry is not None:
            try:
                self._telemetry(name, data)
            except Exception:  # noqa: BLE001 - telemetry must never break a request
                pass

    # ── core request ─────────────────────────────────────────────────────────

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        json: Any = None,
        data: Any = None,
        content: Optional[bytes] = None,
        timeout_s: Optional[float] = None,
    ) -> HttpResponse:
        import httpx  # noqa: PLC0415 - imported lazily to keep the module light

        self._guard(method, url)
        host = (urlparse(url).hostname or "").lower()
        breaker = self._breaker(host)
        if not breaker.allow():
            self._emit("plugin.http.circuit_open", {"host": host})
            raise HttpError(
                "PLUGIN_HTTP_CIRCUIT_OPEN",
                f"the circuit breaker for {host!r} is open; retry later",
                retryable=True,
            )

        request_id = uuid.uuid4().hex
        merged = {"User-Agent": "BlackEclipse-Plugin", "X-Plugin-Id": self._plugin_id,
                  "X-Request-Id": request_id}
        if headers:
            merged.update(headers)

        last_error: Optional[Exception] = None
        for attempt in range(self._retries + 1):
            await self._limiter.acquire()
            started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=timeout_s or self._timeout, follow_redirects=True) as client:
                    response = await client.request(
                        method.upper(), url, params=params, headers=merged,
                        json=json, data=data, content=content,
                    )
                duration = time.monotonic() - started
                if response.status_code >= 500 or response.status_code == 429:
                    last_error = HttpError(
                        "PLUGIN_HTTP_UPSTREAM", f"upstream returned {response.status_code}",
                        retryable=True,
                    )
                    if attempt < self._retries:
                        await self._backoff(attempt)
                        continue
                breaker.record_success()
                self._emit("plugin.http.request", {
                    "method": method.upper(), "host": host, "status": response.status_code,
                    "durationMs": round(duration * 1000, 1), "requestId": request_id,
                })
                return HttpResponse(
                    status=response.status_code,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    content=response.content,
                    url=str(response.url),
                    request_id=request_id,
                )
            except HttpError as exc:
                if not exc.retryable or attempt >= self._retries:
                    breaker.record_failure("plugin_http_failed")
                    raise
                last_error = exc
                await self._backoff(attempt)
            except Exception as exc:  # noqa: BLE001 - transport failures are data
                last_error = exc
                if attempt >= self._retries:
                    breaker.record_failure("plugin_http_transport")
                    self._emit("plugin.http.failed", {"host": host, "error": type(exc).__name__})
                    raise HttpError(
                        "PLUGIN_HTTP_TRANSPORT", f"request failed: {type(exc).__name__}: {exc}",
                        retryable=True,
                    ) from exc
                await self._backoff(attempt)
        raise HttpError("PLUGIN_HTTP_TRANSPORT", f"request failed: {last_error}")

    async def _backoff(self, attempt: int) -> None:
        delay = min(8.0, (0.25 * (2 ** attempt))) + random.uniform(0, 0.1)
        await asyncio.sleep(delay)

    async def stream(
        self, method: str, url: str, *, headers: Optional[dict[str, str]] = None,
        json: Any = None, timeout_s: Optional[float] = None,
    ) -> AsyncIterator[bytes]:
        """Stream response chunks (for SSE or a streaming HTTP body)."""
        import httpx  # noqa: PLC0415

        self._guard(method, url)
        request_headers = {"User-Agent": "BlackEclipse-Plugin", "X-Plugin-Id": self._plugin_id}
        if headers:
            request_headers.update(headers)
        async with httpx.AsyncClient(timeout=timeout_s or self._timeout) as client:
            async with client.stream(method.upper(), url, headers=request_headers, json=json) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def sse(
        self, url: str, *, headers: Optional[dict[str, str]] = None,
        timeout_s: Optional[float] = None, max_events: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Consume a Server-Sent Events stream, yielding `{event, data, id}`."""
        buffer = ""
        count = 0
        async for chunk in self.stream("GET", url, headers={**(headers or {}), "Accept": "text/event-stream"},
                                      timeout_s=timeout_s):
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                event = {"event": "message", "data": "", "id": None}
                for line in raw.splitlines():
                    if line.startswith("event:"):
                        event["event"] = line[6:].strip()
                    elif line.startswith("data:"):
                        event["data"] += line[5:].strip()
                    elif line.startswith("id:"):
                        event["id"] = line[3:].strip()
                count += 1
                yield event
                if max_events and count >= max_events:
                    return

    async def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self.request("DELETE", url, **kwargs)

    async def connect_ws(
        self, url: str, *, headers: Optional[dict[str, str]] = None,
        subprotocols: Optional[list[str]] = None, open_timeout: float = 10.0,
        ping_interval: float = 20.0, max_reconnect: int = 3,
    ) -> "PluginWebSocket":
        """Open a permission-checked WebSocket with reconnect + heartbeat."""
        self._guard("WS", url)
        return PluginWebSocket(
            self, url, headers=headers, subprotocols=subprotocols, open_timeout=open_timeout,
            ping_interval=ping_interval, max_reconnect=max_reconnect,
        )

    def breaker_status(self) -> dict[str, Any]:
        return {host: b.public() for host, b in self._breakers.items()}


class PluginWebSocket:
    """A reconnecting WebSocket connection. Use as an async context manager."""

    def __init__(
        self, http: "PluginHttp", url: str, *, headers: Optional[dict[str, str]] = None,
        subprotocols: Optional[list[str]] = None, open_timeout: float = 10.0,
        ping_interval: float = 20.0, max_reconnect: int = 3,
    ) -> None:
        self._http = http
        self._url = url
        self._headers = headers or {}
        self._subprotocols = subprotocols or []
        self._open_timeout = open_timeout
        self._ping_interval = ping_interval
        self._max_reconnect = max_reconnect
        self._conn: Any = None
        self._reconnects = 0

    async def __aenter__(self) -> "PluginWebSocket":
        await self._connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        await self.close()
        return False

    async def _connect(self) -> None:
        try:
            import websockets  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001 - a missing lib is an honest failure
            raise HttpError("PLUGIN_WS_UNAVAILABLE", "the 'websockets' package is not installed") from exc
        host = (urlparse(self._url).hostname or "").lower()
        breaker = self._http._breaker(host)  # noqa: SLF001 - same-plugin breaker reuse
        if not breaker.allow():
            raise HttpError("PLUGIN_WS_CIRCUIT_OPEN", f"the circuit breaker for {host!r} is open")
        kwargs = {"subprotocols": self._subprotocols or None, "open_timeout": self._open_timeout,
                  "ping_interval": self._ping_interval}
        try:
            self._conn = await websockets.connect(self._url, additional_headers=self._headers, **kwargs)
        except TypeError:  # older websockets uses `extra_headers`
            self._conn = await websockets.connect(self._url, extra_headers=self._headers, **kwargs)
        except Exception as exc:  # noqa: BLE001
            breaker.record_failure("plugin_ws_connect")
            raise HttpError("PLUGIN_WS_CONNECT", f"websocket connect failed: {exc}", retryable=True) from exc
        breaker.record_success()
        self._http._emit("plugin.ws.connected", {"url": self._url})  # noqa: SLF001

    async def send(self, data: Any) -> None:
        await self._attempt(lambda: self._conn.send(data))

    async def recv(self) -> Any:
        return await self._attempt(lambda: self._conn.recv())

    async def close(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass
            self._conn = None

    async def _attempt(self, op: Any) -> Any:
        try:
            return await op()
        except Exception as exc:  # noqa: BLE001 - a dropped socket reconnects (bounded)
            if self._reconnects >= self._max_reconnect:
                raise HttpError("PLUGIN_WS_DROPPED", f"websocket dropped: {exc}", retryable=True) from exc
            self._reconnects += 1
            await asyncio.sleep(min(8.0, 0.25 * (2 ** self._reconnects)))
            await self._connect()
            return await op()

    def __aiter__(self) -> "PluginWebSocket":
        return self

    async def __anext__(self) -> Any:
        try:
            return await self.recv()
        except HttpError:
            raise StopAsyncIteration


__all__ = ["PluginHttp", "HttpResponse", "HttpError", "RateLimiter", "PluginWebSocket"]
