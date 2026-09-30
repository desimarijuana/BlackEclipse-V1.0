"""Local stdio MCP client (Phase 5B).

One persistent MCP server subprocess per enabled server, driven through the
maintained MCP Python SDK (`mcp`) over stdio. The SDK's transport already:

  * launches an argv list with no shell (never a command string);
  * inherits only a small safe default environment and merges the server's
    explicitly scoped env over it;
  * terminates the whole process tree cleanly, shielded against cancellation.

This module adds the host controls the slice requires: bounded startup, catalog
and call timeouts; cancellation propagation; serialized session access from one
owner task (anyio streams are task-affine, so all session I/O happens in the
runner task); and structured, redacted errors.

A connection is inert until `start()` is awaited. Nothing here decides whether a
tool may run — that is the manager/registry's job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp import types as mcp_types

from .config import MCPServerConfig, redact_secrets

log = logging.getLogger("harness.mcp.client")

# Sentinels that let us classify an error for events/tests without leaking text.
class MCPError(Exception):
    """Base for MCP client errors. `code` is a stable, safe category."""

    code = "mcp_error"

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class MCPStartupError(MCPError):
    code = "mcp_startup_failed"


class MCPTimeoutError(MCPError):
    code = "mcp_timeout"


class MCPCallError(MCPError):
    code = "mcp_call_failed"


class MCPProtocolError(MCPError):
    code = "mcp_protocol_error"


class MCPClosedError(MCPError):
    code = "mcp_closed"


class MCPSessionError(MCPError):
    """A mid-call session/transport expiry (safe to replay a READ once)."""

    code = "mcp_session_expired"


@dataclass
class MCPDiscoveredTool:
    """A tool as advertised by a server — UNTRUSTED and not yet activatable."""

    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: Any = None
    output_schema: Optional[dict[str, Any]] = None


@dataclass
class MCPCallOutcome:
    """A normalized call result. `ok=False` means the server reported an error."""

    ok: bool
    text: str
    data: Optional[dict[str, Any]] = None
    is_error: bool = False
    # True when a non-read call hit a session expiry and was NOT replayed, so the
    # effect may or may not have happened; the caller must verify.
    outcome_uncertain: bool = False


@dataclass
class _Request:
    name: str
    arguments: dict[str, Any]
    timeout_s: float
    kind: str = "call"  # "call" | "ping"
    future: "asyncio.Future[MCPCallOutcome]" = field(default_factory=asyncio.Future)


class MCPConnection:
    """A single stdio/http/sse server connection with bounded, serialized operations."""

    def __init__(
        self,
        config: MCPServerConfig,
        secret_resolver: Any = None,
        resolved: Any = None,
        bridge_fetch: Any = None,
    ) -> None:
        self.config = config
        # An optional async `(name) -> value | None` resolver for vault secret
        # references. The value is used ONLY to populate the child environment at
        # spawn and is never stored on the connection, logged, or emitted.
        self._secret_resolver = secret_resolver
        # An optional async `(capability, params) -> dict` bridge for OAuth token
        # storage. Used only for remote `auth.kind == "oauth"` servers.
        self._bridge_fetch = bridge_fetch
        # Connection-defining fields after `${VAR}` interpolation (or None, in
        # which case they are resolved here). Kept in memory only.
        self._resolved = resolved
        self.limits = config.limits()
        self._secrets = config.secret_values()
        self._runner: Optional[asyncio.Task[None]] = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._requests: "asyncio.Queue[Optional[_Request]]" = asyncio.Queue()
        self._state = "new"  # new | starting | ready | failed | closed
        self._error: Optional[str] = None
        self._error_code: Optional[str] = None
        self._tools: list[MCPDiscoveredTool] = []
        self._protocol_version: Optional[str] = None
        self._server_info: Optional[dict[str, Any]] = None
        self._capabilities: dict[str, bool] = {}
        self._resources: list[dict[str, Any]] = []
        self._prompts: list[dict[str, Any]] = []
        # Optional server-initiated interaction callbacks (Milestone 5), injected
        # by the manager. None means the server gets nothing.
        self._sampling_callback: Any = None
        self._elicitation_callback: Any = None
        # Optional async `(kind) -> None` callback invoked when the server signals
        # a catalog change (`notifications/tools/list_changed` etc.). Injected by
        # the manager; None = notifications are ignored. It is scheduled as its
        # own task so the SDK's read loop is never blocked.
        self._catalog_changed: Any = None
        self._notifications_seen: int = 0
        self._last_notification_kind: Optional[str] = None
        self._catalog_refresh_in_flight: bool = False
        self._call_count = 0
        self._connected_at: Optional[float] = None
        self._last_activity: Optional[float] = None
        # Auth secret resolved in memory for an http connection (never persisted).
        self._resolved_auth: dict[str, Any] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Spawn and initialize the server. Bounded; raises on failure."""
        if self._state == "ready":
            return
        if self._state in ("failed", "closed"):
            raise MCPClosedError(f"MCP server {self.config.id!r} is not startable in state {self._state!r}")
        self._state = "starting"
        self._runner = asyncio.create_task(self._run(), name=f"mcp-{self.config.id}")
        try:
            await asyncio.wait_for(
                self._ready.wait(), timeout=self.limits["startupTimeoutMs"] / 1000
            )
        except asyncio.TimeoutError as exc:
            await self._hard_close()
            self._state, self._error, self._error_code = "failed", "startup timed out", MCPTimeoutError.code
            raise MCPTimeoutError(
                f"MCP server {self.config.id!r} did not start within "
                f"{self.limits['startupTimeoutMs']}ms"
            ) from exc
        if self._state != "ready":
            raise MCPStartupError(
                redact_secrets(self._error or "server failed to start", self._secrets),
                code=self._error_code or MCPStartupError.code,
            )

    @property
    def ready(self) -> bool:
        return self._state == "ready"

    @property
    def state(self) -> str:
        return self._state

    @property
    def tools(self) -> list[MCPDiscoveredTool]:
        return list(self._tools)

    @property
    def protocol_version(self) -> Optional[str]:
        return self._protocol_version

    @property
    def server_info(self) -> Optional[dict[str, Any]]:
        return self._server_info

    @property
    def capabilities(self) -> dict[str, bool]:
        return dict(self._capabilities)

    @property
    def resources(self) -> list[dict[str, Any]]:
        return list(self._resources)

    @property
    def prompts(self) -> list[dict[str, Any]]:
        return list(self._prompts)

    async def read_resource(self, uri: str, *, timeout_ms: Optional[int] = None) -> MCPCallOutcome:
        """Read one resource, bounded; capability-aware (callers check first)."""
        if self._state != "ready":
            raise MCPClosedError(f"MCP server {self.config.id!r} is not connected (state={self._state!r})")
        if not self._capabilities.get("resources"):
            raise MCPCallError(
                f"MCP server {self.config.id!r} does not advertise resources",
                code="mcp_resource_unsupported",
            )
        effective = self.limits["callTimeoutMs"] if timeout_ms is None else max(1, min(int(timeout_ms), self.limits["callTimeoutMs"]))
        request = _Request(name=uri, arguments={}, timeout_s=effective / 1000, kind="read_resource")
        return await self._dispatch(request, effective)

    async def get_prompt(self, name: str, arguments: dict[str, Any], *, timeout_ms: Optional[int] = None) -> MCPCallOutcome:
        if self._state != "ready":
            raise MCPClosedError(f"MCP server {self.config.id!r} is not connected (state={self._state!r})")
        if not self._capabilities.get("prompts"):
            raise MCPCallError(
                f"MCP server {self.config.id!r} does not advertise prompts",
                code="mcp_prompt_unsupported",
            )
        effective = self.limits["callTimeoutMs"] if timeout_ms is None else max(1, min(int(timeout_ms), self.limits["callTimeoutMs"]))
        request = _Request(name=name, arguments=arguments or {}, timeout_s=effective / 1000, kind="get_prompt")
        return await self._dispatch(request, effective)

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def connected_at(self):
        return self._connected_at

    @property
    def last_activity(self):
        return self._last_activity

    @property
    def error_code(self):
        return self._error_code

    @property
    def error_message(self):
        return self._error

    @property
    def redaction_values(self) -> list[str]:
        """In-memory secret values to scrub from output (declared + resolved).

        Includes values resolved from the vault at spawn, so a server that echoes
        its own credential cannot leak it through a result or diagnostic.
        """
        return list(self._secrets)

    async def close(self) -> None:
        """Signal shutdown and wait for the runner to finish (bounded)."""
        self._stop.set()
        try:
            self._requests.put_nowait(None)
        except asyncio.QueueFull:  # pragma: no cover - unbounded queue
            pass
        runner = self._runner
        if runner is not None:
            try:
                await asyncio.wait_for(asyncio.shield(runner), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                runner.cancel()
        self._state = "closed"

    async def _hard_close(self) -> None:
        self._stop.set()
        runner = self._runner
        if runner is not None and not runner.done():
            try:
                self._requests.put_nowait(None)
            except asyncio.QueueFull:  # pragma: no cover
                pass

    # -- operations ----------------------------------------------------------

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout_ms: Optional[int] = None
    ) -> MCPCallOutcome:
        """Call one tool. Bounded by the configured call timeout (or override)."""
        if self._state != "ready":
            raise MCPClosedError(f"MCP server {self.config.id!r} is not connected (state={self._state!r})")
        ceiling = self.limits["callTimeoutMs"]
        effective = ceiling if timeout_ms is None else max(1, min(int(timeout_ms), ceiling))
        request = _Request(name=name, arguments=arguments or {}, timeout_s=effective / 1000)
        return await self._dispatch(request, effective)

    async def ping(self, *, timeout_ms: Optional[int] = None) -> bool:
        """Send an MCP ping on the live session; True when it answers.

        Used by keepalive: a failure is the signal to route into reconnect.
        """
        if self._state != "ready":
            raise MCPClosedError(f"MCP server {self.config.id!r} is not connected (state={self._state!r})")
        ceiling = self.limits["callTimeoutMs"]
        effective = ceiling if timeout_ms is None else max(1, min(int(timeout_ms), ceiling))
        request = _Request(name="", arguments={}, timeout_s=effective / 1000, kind="ping")
        self._touch()
        outcome = await self._dispatch(request, effective)
        return outcome.ok

    def _dispatch(self, request: _Request, effective: int) -> Any:
        self._call_count += 1
        self._touch()
        self._requests.put_nowait(request)
        return self._await_request(request, effective)

    async def _await_request(self, request: _Request, effective: int) -> MCPCallOutcome:
        try:
            return await asyncio.wait_for(
                asyncio.shield(request.future), timeout=(effective / 1000) + 1.0
            )
        except asyncio.TimeoutError as exc:
            request.future.cancel()
            raise MCPTimeoutError(
                f"MCP tool {request.name!r} on {self.config.id!r} timed out after {effective}ms"
            ) from exc
        except asyncio.CancelledError:
            # Propagate cancellation to the in-flight request, then re-raise so
            # the caller's run is cancelled (never retried).
            request.future.cancel()
            raise

    def _touch(self) -> None:
        """Record activity for keepalive/idle decisions."""
        import time as _time

        self._last_activity = _time.monotonic()

    # -- runner --------------------------------------------------------------

    async def _run(self) -> None:
        # Resolve vault secret references at connect time (never persisted).
        resolved_secrets = await self._resolve_env_secrets()
        await self._resolve_auth_secret()
        try:
            transport_cm = self._transport(resolved_secrets)
            async with transport_cm as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(
                    read_stream,
                    write_stream,
                    sampling_callback=self._sampling_callback,
                    elicitation_callback=self._elicitation_callback,
                    message_handler=self._on_session_message,
                ) as session:
                    init = await asyncio.wait_for(
                        session.initialize(),
                        timeout=self.limits["startupTimeoutMs"] / 1000,
                    )
                    self._protocol_version = getattr(init, "protocol_version", None)
                    info = getattr(init, "server_info", None)
                    self._server_info = {
                        "name": getattr(info, "name", None),
                        "version": getattr(info, "version", None),
                    }
                    self._capabilities = _read_capabilities(init)
                    await self._discover(session)
                    await self._discover_capabilities(session)
                    self._state = "ready"
                    import time as _time

                    self._connected_at = _time.monotonic()
                    self._last_activity = self._connected_at
                    self._ready.set()
                    await self._serve(session)
        except asyncio.CancelledError:
            self._state = "closed"
            raise
        except MCPError as exc:
            self._fail(str(exc), exc.code)
        except BaseException as exc:  # noqa: BLE001 - every failure must be a safe category
            nested = _first_mcp_error(exc)
            if nested is not None:
                self._fail(str(nested), nested.code)
            else:
                self._fail(_safe_message(exc), _classify_exception(exc))
        finally:
            if self._state == "starting":
                # Failed before ready without going through _fail (e.g. cancel).
                self._state = "failed"
            self._ready.set()
            self._fail_pending()
            self._state = "closed" if self._state != "failed" else "failed"

    async def _resolve_env_secrets(self) -> dict[str, str]:
        """Resolve `secret_refs` at spawn/connect; add values to redaction."""
        resolved: dict[str, str] = {}
        if self._secret_resolver is None or not self.config.secret_refs:
            return resolved
        for env_name, secret_name in self.config.secret_refs.items():
            value = await self._safe_resolve(secret_name)
            if value:
                resolved[env_name] = value
                if value not in self._secrets:
                    self._secrets = [*self._secrets, value]
        return resolved

    async def _safe_resolve(self, secret_name: str) -> Optional[str]:
        try:
            return await self._secret_resolver(secret_name)
        except Exception:  # noqa: BLE001 - a resolver failure is never authorization
            return None

    async def _resolve_auth_secret(self) -> None:
        """Resolve the configured auth secret into memory (never persisted)."""
        auth = self.config.auth if isinstance(self.config.auth, dict) else None
        if not auth or self._secret_resolver is None:
            return
        ref = auth.get("secretRef")
        if not ref:
            return
        value = await self._safe_resolve(str(ref))
        self._resolved_auth = {"kind": auth.get("kind"), "name": auth.get("name"), "value": value}
        if value and value not in self._secrets:
            self._secrets = [*self._secrets, value]

    def _transport(self, resolved_secrets: dict[str, str]):
        """Return the async context manager yielding `(read, write)` streams.

        stdio launches a local subprocess; http connects to a remote
        Streamable-HTTP endpoint; sse connects to a remote SSE endpoint. All
        yield the same stream pair, so the session lifecycle, discovery, serving,
        and error handling above are shared.
        """
        if self.config.transport == "http":
            return self._http_transport()
        if self.config.transport == "sse":
            return self._sse_transport()
        resolved = self._resolved or self.config.resolved_connection()
        params = StdioServerParameters(
            command=resolved.command,
            args=list(resolved.args),
            env=self.config.resolve_environment(resolved_secrets),
            cwd=self.config.resolve_cwd(),
        )
        return stdio_client(params)

    def _http_client(self, headers: dict[str, str]):
        """Build an httpx2 client honoring the TLS controls (verify/CA/mTLS)."""
        from mcp.client.streamable_http import create_mcp_http_client

        resolved = self._resolved or self.config.resolved_connection()
        kwargs: dict[str, Any] = {}
        verify = resolved.ssl_verify
        if verify is False:
            kwargs["verify"] = False
        elif isinstance(verify, str) and verify:
            if not os.path.isfile(verify):
                raise MCPStartupError(f"CA bundle not found: {verify}", code="mcp_tls_error")
            kwargs["verify"] = verify
        cert = self._client_cert_args()
        if cert is not None:
            kwargs["cert"] = cert
        # OAuth: the SDK's provider is an httpx2 auth flow. Only when this server
        # is configured for oauth AND a bridge is available.
        auth = self._oauth_provider()
        if auth is not None:
            kwargs["auth"] = auth
        # Always build the client for a remote transport so the redirect guard is
        # installed on every hop (a bare client would follow redirects unchecked).
        client = create_mcp_http_client(headers=headers or None, **kwargs)
        from .redirect_guard import make_redirect_hook

        client.event_hooks["response"].append(make_redirect_hook(self.config.url or ""))
        return client

    def _oauth_provider(self):
        """Build the SDK OAuth provider for an `oauth`-auth remote server."""
        auth = self._resolved.auth if self._resolved is not None else (
            self.config.auth if isinstance(self.config.auth, dict) else None
        )
        if not auth or auth.get("kind") != "oauth" or self._bridge_fetch is None:
            return None
        from .oauth import build_oauth_provider

        redirect = str(auth.get("redirectUri") or "http://127.0.0.1:8765/callback")
        return build_oauth_provider(self.config.id, self.config.url or "", self._bridge_fetch, redirect)

    def _client_cert_args(self):
        """mTLS `cert` argument: combined PEM, `[cert, key]`, or `[cert, key, pass]`."""
        cert = self.config.client_cert
        key = self.config.client_key
        if not cert:
            return None
        cert = os.path.expanduser(cert)
        if not os.path.isfile(cert):
            raise MCPStartupError(f"client certificate not found: {cert}", code="mcp_tls_error")
        if isinstance(key, list):
            parts = [str(p) for p in key]
            if parts and not os.path.isfile(parts[0]):
                raise MCPStartupError(f"client certificate not found: {parts[0]}", code="mcp_tls_error")
            return tuple(parts) if len(parts) > 1 else parts[0]
        key_path = os.path.expanduser(key) if isinstance(key, str) and key else None
        if key_path and not os.path.isfile(key_path):
            raise MCPStartupError(f"client key not found: {key_path}", code="mcp_tls_error")
        return (cert, key_path) if key_path else cert

    def _auth_headers_and_query(self) -> tuple[dict[str, str], dict[str, str]]:
        auth = self._resolved.auth if self._resolved is not None else (
            self.config.auth if isinstance(self.config.auth, dict) else None
        )
        headers: dict[str, str] = {}
        query: dict[str, str] = {}
        if auth:
            token = self._resolved_auth.get("value")
            if token:
                kind = auth.get("kind")
                if kind == "query":
                    query[str(auth.get("name"))] = token
                elif kind == "oauth":
                    # A pre-obtained OAuth access token (vault) is sent as a
                    # bearer; Milestone 3 wires the full OAuth flow.
                    headers["Authorization"] = f"Bearer {token}"
                else:
                    headers[str(auth.get("name"))] = f"{auth.get('prefix') or ''}{token}"
                if token not in self._secrets:
                    self._secrets = [*self._secrets, token]
        return headers, query

    def _http_transport(self):
        """A Streamable-HTTP transport with vault-backed header/query auth."""
        from mcp.client.streamable_http import streamable_http_client

        resolved = self._resolved or self.config.resolved_connection()
        url = resolved.url or ""
        headers, query = self._auth_headers_and_query()
        if query:
            url = f"{url}{'&' if '?' in url else '?'}" + "&".join(f"{k}={v}" for k, v in query.items())
        http_client = self._http_client(headers)
        # https-only / private-host refusal is enforced before this call (manager).
        return streamable_http_client(url, http_client=http_client)

    def _sse_transport(self):
        """An SSE transport sharing the same SSRF pre-check and lifecycle."""
        from mcp.client.sse import sse_client

        resolved = self._resolved or self.config.resolved_connection()
        url = resolved.url or ""
        headers, query = self._auth_headers_and_query()
        if query:
            url = f"{url}{'&' if '?' in url else '?'}" + "&".join(f"{k}={v}" for k, v in query.items())
        http_client = self._http_client(headers)
        if http_client is not None:
            return sse_client(url, httpx_client_factory=lambda **_: http_client)
        return sse_client(url)


    async def _list_resources(self, session: ClientSession) -> None:
        """Fetch `resources/list` and replace `_resources`.

        Shared by initial discovery and a `resources/list_changed` refresh. A list
        failure is not fatal: it leaves the previous list empty (discovery) or in
        place (refresh).
        """
        try:
            result = await asyncio.wait_for(
                session.list_resources(), timeout=self.limits["catalogTimeoutMs"] / 1000
            )
            rows = []
            for res in getattr(result, "resources", []) or []:
                rows.append({
                    "uri": str(getattr(res, "uri", "")),
                    "name": str(getattr(res, "name", "") or ""),
                    "mimeType": getattr(res, "mime_type", None),
                    "description": str(getattr(res, "description", "") or ""),
                })
            self._resources = rows
        except Exception:  # noqa: BLE001 - a resource list failure is not fatal
            self._resources = []

    async def _list_prompts(self, session: ClientSession) -> None:
        """Fetch `prompts/list` and replace `_prompts` (shared by discovery/refresh)."""
        try:
            result = await asyncio.wait_for(
                session.list_prompts(), timeout=self.limits["catalogTimeoutMs"] / 1000
            )
            rows = []
            for prompt in getattr(result, "prompts", []) or []:
                rows.append({
                    "name": str(getattr(prompt, "name", "") or ""),
                    "description": str(getattr(prompt, "description", "") or ""),
                    "arguments": [
                        {
                            "name": str(getattr(a, "name", "") or ""),
                            "required": bool(getattr(a, "required", False)),
                            "description": str(getattr(a, "description", "") or ""),
                        }
                        for a in (getattr(prompt, "arguments", None) or [])
                    ],
                })
            self._prompts = rows
        except Exception:  # noqa: BLE001
            self._prompts = []

    async def _discover_capabilities(self, session: ClientSession) -> None:
        """List resources/prompts only when the server advertises the capability."""
        if self._capabilities.get("resources"):
            await self._list_resources(session)
        if self._capabilities.get("prompts"):
            await self._list_prompts(session)

    async def _list_tools(self, session: ClientSession) -> None:
        """Fetch `tools/list` and replace `_tools`. Shared by discovery and refresh."""
        try:
            result = await asyncio.wait_for(
                session.list_tools(), timeout=self.limits["catalogTimeoutMs"] / 1000
            )
        except asyncio.TimeoutError as exc:
            raise MCPTimeoutError(
                f"MCP server {self.config.id!r} catalog did not return within "
                f"{self.limits['catalogTimeoutMs']}ms"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise MCPProtocolError(redact_secrets(str(exc), self._secrets)) from exc

        tools: list[MCPDiscoveredTool] = []
        for tool in getattr(result, "tools", []) or []:
            tools.append(
                MCPDiscoveredTool(
                    name=str(getattr(tool, "name", "")),
                    description=str(getattr(tool, "description", "") or ""),
                    input_schema=getattr(tool, "input_schema", None) or {},
                    annotations=getattr(tool, "annotations", None),
                    output_schema=getattr(tool, "output_schema", None),
                )
            )
        self._tools = tools

    async def _discover(self, session: ClientSession) -> None:
        await self._list_tools(session)

    async def _on_session_message(self, message: Any) -> None:
        """SDK `message_handler`: react to a declared inbound notification.

        We act ONLY on list-changed notifications for capabilities the server
        actually advertises (per the initialize handshake). A transport-level
        `Exception` (the other thing the SDK surfaces here) is ignored — the read
        loop owns failure handling. A catalog-change callback is dispatched in a
        separate task so this handler never blocks the dispatcher.
        """
        if isinstance(message, BaseException):
            return
        method = getattr(message, "method", None)
        caps = self._capabilities or {}
        kind: Optional[str] = None
        if method == "notifications/tools/list_changed" and caps.get("tools"):
            kind = "tools"
        elif method in ("notifications/resources/list_changed",) and caps.get("resources"):
            kind = "resources"
        elif method in ("notifications/prompts/list_changed",) and caps.get("prompts"):
            kind = "prompts"
        if kind is None:
            return
        self._notifications_seen += 1
        self._last_notification_kind = kind
        if self._catalog_changed is not None:
            # Fire-and-forget: the callback does its own locking and its own
            # bounded discovery. A raising callback must not fail the read loop.
            asyncio.ensure_future(self._safe_catalog_changed(kind))

    async def _safe_catalog_changed(self, kind: str) -> None:
        try:
            await self._catalog_changed(kind)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a notification must never break the session
            log.warning("MCP catalog-change callback failed for %s", self.config.id, exc_info=True)

    async def refresh_listing(self, kind: str) -> None:
        """Re-run one listing (`tools`/`resources`/`prompts`) on the live session.

        All session I/O is task-affine with the runner task, so the re-list is
        dispatched as a request and this coroutine awaits its result. The fresh
        listing replaces the cached one on the connection.
        """
        if kind not in ("tools", "resources", "prompts"):
            raise ValueError(f"unknown listing kind {kind!r}")
        if self._state != "ready":
            raise MCPClosedError(f"MCP server {self.config.id!r} is not connected (state={self._state!r})")
        request = _Request(
            name="",
            arguments={},
            timeout_s=self.limits["catalogTimeoutMs"] / 1000,
            kind=f"list_{kind}",
        )
        outcome = await self._dispatch(request, self.limits["catalogTimeoutMs"])
        if not outcome.ok:
            raise MCPProtocolError(f"{kind}/list failed on {self.config.id!r}")

    async def refresh_tools(self) -> list[MCPDiscoveredTool]:
        """Re-run `tools/list` and return the fresh tool list (back-compat wrapper)."""
        await self.refresh_listing("tools")
        return list(self._tools)

    async def _serve(self, session: ClientSession) -> None:
        """Process queued calls in this task (session I/O must be task-affine)."""
        stop_wait = asyncio.ensure_future(self._stop.wait())
        try:
            while not self._stop.is_set():
                get_task = asyncio.ensure_future(self._requests.get())
                done, _pending = await asyncio.wait(
                    {get_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
                )
                if get_task not in done:
                    get_task.cancel()
                    if stop_wait in done:
                        break
                    continue
                request = get_task.result()
                if request is None:
                    break
                if request.future.cancelled():
                    continue
                try:
                    outcome = await self._invoke(session, request)
                except asyncio.CancelledError:
                    raise
                except (MCPTimeoutError, MCPProtocolError, MCPSessionError) as exc:
                    if not request.future.done():
                        request.future.set_exception(exc)
                    continue
                except Exception as exc:  # noqa: BLE001
                    if not request.future.done():
                        request.future.set_exception(
                            MCPCallError(redact_secrets(str(exc), self._secrets))
                        )
                    continue
                if not request.future.done():
                    request.future.set_result(outcome)
        finally:
            stop_wait.cancel()

    async def _invoke(self, session: ClientSession, request: _Request) -> MCPCallOutcome:
        if request.kind == "ping":
            try:
                await asyncio.wait_for(session.send_ping(), timeout=request.timeout_s)
            except asyncio.TimeoutError as exc:
                raise MCPTimeoutError(
                    f"MCP ping on {self.config.id!r} timed out after {int(request.timeout_s * 1000)}ms"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - a ping failure is a session signal
                raise MCPSessionError(redact_secrets(str(exc), self._secrets)) from exc
            return MCPCallOutcome(ok=True, text="")
        if request.kind in ("list_tools", "list_resources", "list_prompts"):
            # Re-list the catalog/listing on the live session; the result is stored
            # on the connection (`_tools`/`_resources`/`_prompts`) and the outcome
            # only signals success.
            lister = {
                "list_tools": self._list_tools,
                "list_resources": self._list_resources,
                "list_prompts": self._list_prompts,
            }[request.kind]
            try:
                await lister(session)
            except MCPError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise MCPProtocolError(redact_secrets(str(exc), self._secrets)) from exc
            return MCPCallOutcome(ok=True, text="")
        if request.kind == "read_resource":
            return await self._invoke_resource(session, request)
        if request.kind == "get_prompt":
            return await self._invoke_prompt(session, request)
        try:
            result = await asyncio.wait_for(
                session.call_tool(request.name, request.arguments),
                timeout=request.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise MCPTimeoutError(
                f"MCP tool {request.name!r} on {self.config.id!r} timed out after "
                f"{int(request.timeout_s * 1000)}ms"
            ) from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = redact_secrets(str(exc), self._secrets)
            from .lifecycle import is_session_error

            if is_session_error(message) or _looks_like_session_exception(exc):
                raise MCPSessionError(message) from exc
            raise MCPCallError(message) from exc
        return _normalize_result(result, self.config.id, request.name)

    async def _invoke_resource(self, session: ClientSession, request: _Request) -> MCPCallOutcome:
        try:
            result = await asyncio.wait_for(session.read_resource(request.name), timeout=request.timeout_s)
        except asyncio.TimeoutError as exc:
            raise MCPTimeoutError(f"MCP resource {request.name!r} on {self.config.id!r} timed out") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = redact_secrets(str(exc), self._secrets)
            from .lifecycle import is_session_error

            if is_session_error(message) or _looks_like_session_exception(exc):
                raise MCPSessionError(message) from exc
            raise MCPCallError(message) from exc
        return _normalize_resource(result, self.config.id, request.name)

    async def _invoke_prompt(self, session: ClientSession, request: _Request) -> MCPCallOutcome:
        try:
            result = await asyncio.wait_for(
                session.get_prompt(request.name, request.arguments), timeout=request.timeout_s
            )
        except asyncio.TimeoutError as exc:
            raise MCPTimeoutError(f"MCP prompt {request.name!r} on {self.config.id!r} timed out") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = redact_secrets(str(exc), self._secrets)
            from .lifecycle import is_session_error

            if is_session_error(message) or _looks_like_session_exception(exc):
                raise MCPSessionError(message) from exc
            raise MCPCallError(message) from exc
        return _normalize_prompt(result, self.config.id, request.name)

    def _fail(self, message: str, code: str) -> None:
        self._error = redact_secrets(message, self._secrets)
        self._error_code = code
        if self._state != "failed":
            self._state = "failed"

    def _fail_pending(self) -> None:
        error = MCPClosedError(
            redact_secrets(self._error or "server connection closed", self._secrets),
            code=self._error_code or MCPClosedError.code,
        )
        while True:
            try:
                request = self._requests.get_nowait()
            except asyncio.QueueEmpty:
                break
            if request is not None and not request.future.done():
                request.future.set_exception(error)


def _read_capabilities(init: Any) -> dict[str, bool]:
    """Read the advertised server capabilities from an initialize result."""
    caps = getattr(init, "capabilities", None) or getattr(init, "server_capabilities", None)
    return {
        "tools": getattr(caps, "tools", None) is not None,
        "resources": getattr(caps, "resources", None) is not None,
        "prompts": getattr(caps, "prompts", None) is not None,
        "notifications": getattr(caps, "resources", None) is not None,
    }


def _looks_like_session_exception(exc: BaseException) -> bool:
    """Whether an SDK exception type names a session/transport problem."""
    name = type(exc).__name__.lower()
    return any(t in name for t in ("closed", "eof", "disconnect", "session", "transport", "broken"))


def _first_mcp_error(exc: BaseException) -> Optional[MCPError]:
    """Find a nested MCPError inside an SDK ExceptionGroup, if any.

    The SDK transports raise inside anyio task groups, which wrap the real cause
    in an `ExceptionGroup`. Surfacing the inner structured error keeps a startup
    timeout/crash a safe, specific category instead of an opaque group repr.
    """
    if isinstance(exc, MCPError):
        return exc
    for inner in getattr(exc, "exceptions", []) or []:
        found = _first_mcp_error(inner)
        if found is not None:
            return found
    return None


def _safe_message(exc: BaseException) -> str:
    """A bounded, secret-free message for a failure with no structured cause."""
    if isinstance(exc, BaseExceptionGroup):  # type: ignore[name-defined]
        first = exc.exceptions[0] if exc.exceptions else exc
        return _safe_message(first)
    return str(exc) or type(exc).__name__


def _classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text:
        return MCPTimeoutError.code
    if "closed" in name or "eof" in name or "broken" in name:
        return MCPClosedError.code
    if "json" in name or "validation" in name or "decode" in name:
        return MCPProtocolError.code
    return MCPStartupError.code


def _normalize_resource(result: Any, server_id: str, uri: str) -> MCPCallOutcome:
    """Flatten a ReadResourceResult. Resource text is UNTRUSTED data."""
    contents = getattr(result, "contents", None) or []
    parts: list[str] = []
    mime: Optional[str] = None
    for item in contents:
        text = getattr(item, "text", None)
        mime = getattr(item, "mime_type", None) or mime
        if text is not None:
            parts.append(str(text))
        else:
            parts.append("[binary resource content omitted]")
    text = "\n".join(p for p in parts if p)
    data = {
        "source": {"kind": "mcp", "serverId": server_id, "uri": uri},
        "isError": False,
        "contentKinds": ["resource"],
        "mimeType": mime,
    }
    return MCPCallOutcome(ok=True, text=text, data=data, is_error=False)


def _normalize_prompt(result: Any, server_id: str, name: str) -> MCPCallOutcome:
    """Flatten a GetPromptResult. Prompt text is UNTRUSTED, never instructions."""
    messages = getattr(result, "messages", None) or []
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                if getattr(block, "type", None) == "text":
                    parts.append(str(getattr(block, "text", "")))
        elif content is not None:
            parts.append(str(getattr(content, "text", content)))
    text = "\n".join(p for p in parts if p)
    description = getattr(result, "description", None)
    data = {
        "source": {"kind": "mcp", "serverId": server_id, "prompt": name},
        "isError": False,
        "contentKinds": ["prompt"],
        "description": description,
    }
    return MCPCallOutcome(ok=True, text=text, data=data, is_error=False)


def _normalize_result(
    result: Any, server_id: str, tool_name: str
) -> MCPCallOutcome:
    """Flatten an MCP CallToolResult into bounded text + structured data.

    Source identity (server, original tool name) and the upstream structured
    payload are preserved. Content is UNTRUSTED: it cannot change permissions or
    instructions, and it is never labelled Eclipse-verified.
    """
    is_error = bool(getattr(result, "is_error", False))
    blocks = getattr(result, "content", None) or []
    parts: list[str] = []
    kinds: list[str] = []
    content_meta: list[dict[str, Any]] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(str(getattr(block, "text", "")))
            kinds.append("text")
        elif block_type in ("image", "audio"):
            # The run's result path carries text + structured JSON only, so a
            # non-text block cannot be handed to the model as bytes. Rather than
            # an opaque "[image content omitted]", report the MIME type and the
            # DECODED byte size so the model and UI can honestly say what was
            # returned. (A binary transport for this content is a documented
            # non-goal of this phase — see the progress doc.)
            mime = str(getattr(block, "mime_type", None) or getattr(block, "mimeType", None) or "application/octet-stream")
            raw = getattr(block, "data", None)
            size = _decoded_size(raw)
            size_note = f", ~{size} bytes" if size is not None else ""
            parts.append(
                f"[This tool returned {block_type} content ({mime}{size_note}) that was NOT shown here. "
                "The agent runtime cannot carry binary content; the data exists on the server but is not "
                "in this result.]"
            )
            kinds.append(block_type)
            content_meta.append({"type": block_type, "mimeType": mime, "bytes": size})
        elif block_type == "resource":
            resource = getattr(block, "resource", None)
            text = getattr(resource, "text", None)
            parts.append(str(text) if text is not None else "[embedded resource omitted]")
            kinds.append("resource")
        else:
            parts.append(f"[{block_type or 'unknown'} content omitted]")
            kinds.append(block_type or "unknown")
    text = "\n".join(p for p in parts if p)
    # A server may report success (`isError=false`) while the payload is a
    # provider-side error (e.g. Notion returns HTTP 401 as a normal text block).
    # Eclipse must not hand that to the model as retrieved data.
    provider_error = None if is_error else looks_like_provider_error(text)
    if provider_error is not None:
        is_error = True
    structured = getattr(result, "structured_content", None)
    data: dict[str, Any] = {
        "source": {
            "kind": "mcp",
            "serverId": server_id,
            "tool": tool_name,
        },
        "isError": is_error,
        "contentKinds": kinds,
    }
    if provider_error is not None:
        # The raw body is preserved verbatim in `text`; this only records the
        # classification so a caller can render an explicit failure.
        data["providerError"] = provider_error
    if content_meta:
        # Metadata-only: MIME type + byte size, never the bytes themselves.
        data["nonTextContent"] = content_meta
    if structured is not None:
        data["structuredContent"] = structured
    return MCPCallOutcome(ok=not is_error, text=text, data=data, is_error=is_error)


# Status codes that unambiguously denote an error rather than a normal result.
_ERROR_STATUSES = {400, 401, 403, 404, 405, 409, 410, 422, 429, 500, 501, 502, 503, 504}
# Keys whose mere presence may signal a provider error, but only alongside a
# status/message (a bare `code` is far too common in legitimate payloads).
_ERROR_CODES = {
    "unauthorized", "forbidden", "not_found", "invalid_request", "invalid_request_error",
    "rate_limited", "rate_limit_exceeded", "server_error", "internal_error", "conflict",
}


def looks_like_provider_error(text: str) -> Optional[dict[str, Any]]:
    """Classify a successful-looking text body as a provider-side error.

    Conservative by design: a legitimate payload that merely carries a `code`
    field must NOT be misread as an error. The exact rule (all parts must hold):

      * the *entire* trimmed body parses as a JSON object (never an array or
        scalar, and never JSON embedded in prose); and
      * it has an unambiguous error signal: an explicit ``"error"`` key (present
        and truthy, or a non-null object/string), OR
      * an HTTP ``status``/``statusCode`` in a known 4xx/5xx error set, OR
      * a string ``code`` in a known error-code vocabulary **together with** a
        ``status``/``statusCode`` number or a non-empty ``message`` string.

    Returns ``{"code": ..., "status": ...}`` (either may be omitted) when the
    body is an error, else ``None``. It never rewrites the provider's words; the
    caller keeps the raw body verbatim.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped or stripped[0] != "{":
        return None
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None

    status = parsed.get("status")
    if status is None:
        status = parsed.get("statusCode")
    status_int: Optional[int] = None
    if isinstance(status, bool):
        status_int = None
    elif isinstance(status, int):
        status_int = status
    elif isinstance(status, str) and status.strip().isdigit():
        status_int = int(status.strip())

    message = parsed.get("message")
    code = parsed.get("code")
    code_str = code.strip().lower() if isinstance(code, str) else None

    has_error_key = "error" in parsed and bool(parsed.get("error"))
    status_is_error = status_int is not None and (
        status_int in _ERROR_STATUSES or status_int >= 400
    )
    code_matches = code_str in _ERROR_CODES

    is_error = (
        has_error_key
        or status_is_error
        or (code_matches and (status_int is not None or (isinstance(message, str) and message.strip())))
    )
    if not is_error:
        return None

    record: dict[str, Any] = {}
    if code_str:
        record["code"] = code_str
    if status_int is not None:
        record["status"] = status_int
    if not record:  # only the bare "error" key was present
        record["code"] = "provider_error"
    return record


def _decoded_size(data: Any) -> Optional[int]:
    """The decoded byte size of a base64 image/audio payload, or None.

    Best-effort and content-free: on a malformed/absent payload it returns None
    rather than guessing. The bytes are never retained.
    """
    import base64

    if not isinstance(data, str) or not data:
        return None
    try:
        return len(base64.b64decode(data, validate=False))
    except Exception:  # noqa: BLE001 - an unreadable size is simply unknown
        return None


__all__ = [
    "MCPConnection",
    "MCPDiscoveredTool",
    "MCPCallOutcome",
    "MCPError",
    "MCPStartupError",
    "MCPTimeoutError",
    "MCPCallError",
    "MCPProtocolError",
    "MCPClosedError",
    "MCPSessionError",
    "looks_like_provider_error",
]
