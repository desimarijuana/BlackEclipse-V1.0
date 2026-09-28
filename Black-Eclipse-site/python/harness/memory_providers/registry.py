"""The memory-provider registry.

Holds the native provider and any configured external providers, and reports
their health/capabilities. Discovery is NOT activation: an MCP server is
registered as a *candidate* provider but the router only reaches it when the
caller explicitly allows external search AND the server is connected.

The registry never writes to native memory and never mutates a provider's
configuration — it only introspects.
"""

from __future__ import annotations

from typing import Any, Optional

from .mcp import MCPMemoryProvider
from .native import NativeMemoryProvider
from .protocol import (
    MemoryProvider,
    MemorySearchRequest,
    MemorySearchResponse,
    ProviderHealth,
)

NATIVE_NAME = "native"


class MemoryProviderRegistry:
    """Registration + enumeration of memory providers."""

    def __init__(
        self,
        native_service: Any = None,
        mcp_manager: Any = None,
        *,
        external_enabled: bool = False,
    ) -> None:
        self._providers: dict[str, MemoryProvider] = {}
        self._external_enabled = bool(external_enabled)
        self._native = NativeMemoryProvider(native_service)
        self._providers[NATIVE_NAME] = self._native
        self._mcp_manager = mcp_manager
        if mcp_manager is not None:
            # Register a candidate per configured server; candidates are inert
            # until connected + explicitly allowed at call time.
            for server_id in getattr(mcp_manager, "_runtimes", {}):
                provider = MCPMemoryProvider(mcp_manager, server_id)
                self._providers[provider.name] = provider

    # -- configuration ------------------------------------------------------

    @property
    def external_enabled(self) -> bool:
        return self._external_enabled

    def set_external_enabled(self, enabled: bool) -> None:
        self._external_enabled = bool(enabled)

    # -- access -------------------------------------------------------------

    def native(self) -> MemoryProvider:
        return self._native

    def get(self, name: str) -> Optional[MemoryProvider]:
        return self._providers.get(name)

    def external(self) -> list[MemoryProvider]:
        return [p for name, p in self._providers.items() if name != NATIVE_NAME]

    def names(self) -> list[str]:
        return list(self._providers)

    # -- introspection ------------------------------------------------------

    async def health(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, provider in self._providers.items():
            try:
                health: ProviderHealth = await provider.health()
            except Exception as exc:  # noqa: BLE001 - a failing provider is degraded
                health = ProviderHealth(ok=False, state="unavailable", detail=str(exc))
            out.append({
                "name": name,
                "version": getattr(provider, "version", None),
                "isNative": name == NATIVE_NAME,
                "capabilities": provider.capabilities().to_dict(),
                "health": health.to_dict(),
            })
        return out

    async def search_native(self, request: MemorySearchRequest) -> MemorySearchResponse:
        return await self._native.search(request)

    async def search_external(self, request: MemorySearchRequest) -> list[MemorySearchResponse]:
        """Explicit external-only search across allowed providers.

        Refuses unless the request explicitly allows external search; returns one
        response per provider, each labelled and independently bounded. A
        provider whose circuit is open is SKIPPED (reported, not called), so a
        repeatedly failing provider cannot stall every run. A transient failure
        is retried a bounded number of times. Native memory is never affected.
        """
        if not request.allow_external or not self._external_enabled:
            return []
        import time as _time  # noqa: PLC0415

        from .reliability import (  # noqa: PLC0415
            RETRY_BACKOFF_S,
            classify_failure,
            global_reliability,
            is_retryable,
        )

        reliability = global_reliability()
        responses: list[MemorySearchResponse] = []
        for provider in self.external():
            record = reliability.record_for(provider.name)
            if not record.allows_call():
                responses.append(MemorySearchResponse(
                    provider=provider.name, degraded=True,
                    detail="provider temporarily skipped (circuit open after repeated failures)",
                ))
                continue
            attempts = 0
            last_error: Optional[str] = None
            while attempts < 2:
                attempts += 1
                started = _time.monotonic()
                try:
                    response = await provider.search(request)
                    record.record_success((_time.monotonic() - started) * 1000)
                    responses.append(response)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - never let one provider break search
                    last_error = str(exc)
                    category = classify_failure(exc)
                    record.record_failure(category)
                    if is_retryable(category) and attempts < 2:
                        import asyncio  # noqa: PLC0415

                        await asyncio.sleep(RETRY_BACKOFF_S)
                        continue
                    responses.append(MemorySearchResponse(
                        provider=provider.name, degraded=True, detail=last_error,
                    ))
                    break
        return responses


__all__ = ["MemoryProviderRegistry", "NATIVE_NAME"]
