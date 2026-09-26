"""An MCP server exposed as a memory provider.

This does NOT add a second MCP client. It reuses the existing `MCPManager`
connection lifecycle (`_ServerRuntime`, `MCPConnection`, approval gate) and
adapts a configured server into the uniform `MemoryProvider` shape so the router
can offer it side-by-side with native memory.

Rollout levels (implemented here, gated by config):

  * **L1 search-only (default):** the provider calls ONLY read-effect tools. A
    server with no read tool is `unavailable`, honestly — never emulated.
  * **L2 explicit external writes:** a `write` call requires BOTH
    `explicit_user_request` and `approved`; it is audited and never touches
    native memory. Disabled unless the operator opted the server's write effect
    in (`enabled_effects`), which the existing manager already enforces.
  * **L3 automatic writes:** deliberately NOT implemented. The provider declares
    `write=False` for automatic use, so the router can never auto-write.

Every result carries `provenance=external_provider` and `verified=false`; the
manager's secret redaction, output bounding and per-call re-checks still apply.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..mcp.client import MCPClosedError, MCPError, MCPTimeoutError
from .protocol import (
    DEFAULT_EXTERNAL_PROVENANCE,
    MAX_RESULT_CHARS,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemoryExportRequest,
    MemoryExportResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryWriteRequest,
    MemoryWriteResponse,
    ProviderCapabilities,
    ProviderHealth,
)

# Tool-name hints for a generic memory MCP server. A server may not follow them;
# discovery still requires an explicit operator selection.
_SEARCH_HINTS = ("search", "recall", "retrieve", "query", "find", "lookup")
_WRITE_HINTS = ("save", "write", "remember", "add", "store", "create")
_READ_EFFECT = "read"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _pick_tool(descriptors: dict[str, Any], hints: tuple[str, ...]) -> Optional[str]:
    """Deterministically choose a tool whose name matches a hint, else None."""
    for name in sorted(descriptors):
        lowered = name.lower()
        if any(hint in lowered for hint in hints):
            return name
    return None


class MCPMemoryProvider:
    """Read-only-first memory provider backed by one configured MCP server."""

    def __init__(self, manager: Any, server_id: str, *, version: str = "1") -> None:
        self._manager = manager
        self._server_id = server_id
        self.name = f"mcp:{server_id}"
        self.version = version

    # -- internal -----------------------------------------------------------

    def _runtime(self) -> Any:
        return getattr(self._manager, "_runtimes", {}).get(self._server_id)

    def _search_tool(self) -> Optional[str]:
        rt = self._runtime()
        if rt is None:
            return None
        activatable = {
            d.original_name: d
            for d in rt.descriptors.values()
            if d.activatable and d.effect == _READ_EFFECT
        }
        return _pick_tool(activatable, _SEARCH_HINTS)

    def _write_tool(self) -> Optional[str]:
        rt = self._runtime()
        if rt is None:
            return None
        enabled = set(rt.config.enabled_effects or ["read"])
        candidates = {
            d.original_name: d
            for d in rt.descriptors.values()
            if d.activatable and d.effect in enabled and d.effect != _READ_EFFECT
        }
        return _pick_tool(candidates, _WRITE_HINTS)

    # -- contract -----------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        search = self._search_tool() is not None
        # L2 is only possible when the operator opted a write effect in AND a
        # write-shaped tool exists; automatic writes are never declared.
        write = self._write_tool() is not None
        return ProviderCapabilities(
            search=search, write=write, delete=False, export=False, read_only=not write
        )

    async def health(self) -> ProviderHealth:
        started = time.monotonic()
        rt = self._runtime()
        if rt is None:
            return ProviderHealth(ok=False, state="unavailable", detail="server not configured", version=self.version)
        if not rt.config.enabled:
            return ProviderHealth(ok=False, state="unavailable", detail="server disabled", version=self.version)
        if rt.state != "connected" or rt.connection is None:
            return ProviderHealth(
                ok=False, state="degraded",
                detail=rt.diagnostic or f"server state={rt.state}", version=self.version,
            )
        latency = int((time.monotonic() - started) * 1000)
        if not self.capabilities().search:
            return ProviderHealth(
                ok=False, state="degraded",
                detail="no selected read-effect tool matches a memory-search hint",
                latency_ms=latency, version=self.version,
            )
        return ProviderHealth(ok=True, state="available", latency_ms=latency, version=self.version)

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        if not request.allow_external:
            return MemorySearchResponse(
                provider=self.name, degraded=True,
                detail="external search not allowed for this request",
            )
        rt = self._runtime()
        if rt is None or rt.state != "connected" or rt.connection is None:
            return MemorySearchResponse(provider=self.name, degraded=True, detail="server unavailable")
        tool = self._search_tool()
        if tool is None:
            return MemorySearchResponse(provider=self.name, degraded=True, detail="no search tool available")
        descriptor = rt.descriptors[tool]
        req = request.bounded()
        arguments: dict[str, Any] = {"query": req.query}
        if req.limit:
            arguments["limit"] = req.limit
        try:
            outcome = await rt.connection.call_tool(tool, arguments, timeout_ms=rt.limits["callTimeoutMs"])
        except MCPTimeoutError:
            return MemorySearchResponse(provider=self.name, degraded=True, detail="search timed out")
        except (MCPClosedError, MCPError) as exc:
            return MemorySearchResponse(provider=self.name, degraded=True, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - an external failure never crashes the caller
            return MemorySearchResponse(provider=self.name, degraded=True, detail=str(exc))

        text = rt.redact((outcome.text or "")[:MAX_RESULT_CHARS])
        result = MemorySearchResult(
            record_id=f"{self._server_id}:{tool}",
            content=text,
            scope=request.scope or "general",
            scope_id=request.scope_id,
            memory_type="external",
            provider=self.name,
            provenance=DEFAULT_EXTERNAL_PROVENANCE,
            verified=False,
            retrieved_at=_now(),
            metadata={"serverId": self._server_id, "tool": tool, "isError": outcome.is_error},
        )
        return MemorySearchResponse(provider=self.name, results=[result] if text else [])

    async def write(self, request: MemoryWriteRequest) -> MemoryWriteResponse:
        # An external write requires BOTH explicit user intent and a matching
        # operator approval; otherwise it is refused. It never mutates native
        # memory and is audited by the caller.
        if not request.explicit_user_request or not request.approved:
            return MemoryWriteResponse(
                provider=self.name, ok=False,
                detail="external write requires an explicit user request AND an approval",
            )
        rt = self._runtime()
        tool = self._write_tool()
        if rt is None or rt.state != "connected" or tool is None:
            return MemoryWriteResponse(provider=self.name, ok=False, detail="no approved write tool available")
        try:
            outcome = await rt.connection.call_tool(
                tool, {"content": request.content}, timeout_ms=rt.limits["callTimeoutMs"]
            )
        except Exception as exc:  # noqa: BLE001
            return MemoryWriteResponse(provider=self.name, ok=False, detail=str(exc))
        return MemoryWriteResponse(
            provider=self.name, ok=bool(outcome.ok),
            detail=None if outcome.ok else rt.redact(outcome.text or "external write failed"),
            audited=True,
        )

    async def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResponse:
        # External deletes are not enabled in this slice — refuse honestly rather
        # than emulate a delete.
        return MemoryDeleteResponse(provider=self.name, ok=False, detail="external delete is not enabled")

    async def export(self, request: MemoryExportRequest) -> MemoryExportResponse:
        return MemoryExportResponse(provider=self.name, ok=False, detail="external export is not enabled")


__all__ = ["MCPMemoryProvider"]
