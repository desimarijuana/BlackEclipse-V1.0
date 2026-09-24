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
import logging
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


@dataclass
class _Request:
    name: str
    arguments: dict[str, Any]
    timeout_s: float
    future: "asyncio.Future[MCPCallOutcome]" = field(default_factory=asyncio.Future)


class MCPConnection:
    """A single stdio server connection with bounded, serialized operations."""

    def __init__(self, config: MCPServerConfig, secret_resolver: Any = None) -> None:
        self.config = config
        # An optional async `(name) -> value | None` resolver for vault secret
        # references. The value is used ONLY to populate the child environment at
        # spawn and is never stored on the connection, logged, or emitted.
        self._secret_resolver = secret_resolver
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
        self._call_count = 0
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
    def call_count(self) -> int:
        return self._call_count

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
        self._requests.put_nowait(request)
        self._call_count += 1
        try:
            return await asyncio.wait_for(
                asyncio.shield(request.future), timeout=(effective / 1000) + 1.0
            )
        except asyncio.TimeoutError as exc:
            request.future.cancel()
            raise MCPTimeoutError(
                f"MCP tool {name!r} on {self.config.id!r} timed out after {effective}ms"
            ) from exc
        except asyncio.CancelledError:
            # Propagate cancellation to the in-flight request, then re-raise so
            # the caller's run is cancelled (never retried).
            request.future.cancel()
            raise

    # -- runner --------------------------------------------------------------

    async def _run(self) -> None:
        # Resolve vault secret references at connect time (never persisted).
        resolved_secrets = await self._resolve_env_secrets()
        await self._resolve_auth_secret()
        try:
            transport_cm = self._transport(resolved_secrets)
            async with transport_cm as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
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
                    await self._discover(session)
                    self._state = "ready"
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
        Streamable-HTTP endpoint. Both yield the same stream pair, so the session
        lifecycle, discovery, serving, and error handling above are shared.
        """
        if self.config.transport == "http":
            return self._http_transport()
        params = StdioServerParameters(
            command=self.config.command,
            args=list(self.config.args),
            env=self.config.resolve_environment(resolved_secrets),
            cwd=self.config.resolve_cwd(),
        )
        return stdio_client(params)

    def _http_transport(self):
        """A Streamable-HTTP transport with vault-backed header/query auth."""
        import httpx2
        from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client

        url = self.config.url or ""
        auth = self.config.auth if isinstance(self.config.auth, dict) else None
        headers: dict[str, str] = {}
        query: dict[str, str] = {}
        if auth:
            token = None
            # `_auth_secret` is resolved synchronously via the injected resolver
            # only in an async context; here we accept a pre-resolved value cached
            # on the connection by `_run`. See `_resolved_auth`.
            token = self._resolved_auth.get("value")
            if token:
                if auth.get("kind") == "query":
                    query[str(auth.get("name"))] = token
                else:
                    headers[str(auth.get("name"))] = f"{auth.get('prefix') or ''}{token}"
                if token not in self._secrets:
                    self._secrets = [*self._secrets, token]
        if query:
            url = f"{url}{'&' if '?' in url else '?'}" + "&".join(f"{k}={v}" for k, v in query.items())
        http_client = (
            create_mcp_http_client(headers=headers)
            if headers
            else None
        )
        # https-only / private-host refusal is enforced before this call (manager).
        return streamable_http_client(url, http_client=http_client)


    async def _discover(self, session: ClientSession) -> None:
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
                except (MCPTimeoutError, MCPProtocolError) as exc:
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
        except Exception as exc:  # noqa: BLE001
            raise MCPCallError(redact_secrets(str(exc), self._secrets)) from exc
        return _normalize_result(result, self.config.id, request.name)

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
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(str(getattr(block, "text", "")))
            kinds.append("text")
        elif block_type in ("image", "audio"):
            parts.append(f"[{block_type} content omitted]")
            kinds.append(block_type)
        elif block_type == "resource":
            resource = getattr(block, "resource", None)
            text = getattr(resource, "text", None)
            parts.append(str(text) if text is not None else "[embedded resource omitted]")
            kinds.append("resource")
        else:
            parts.append(f"[{block_type or 'unknown'} content omitted]")
            kinds.append(block_type or "unknown")
    text = "\n".join(p for p in parts if p)
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
    if structured is not None:
        data["structuredContent"] = structured
    return MCPCallOutcome(ok=not is_error, text=text, data=data, is_error=is_error)


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
]
