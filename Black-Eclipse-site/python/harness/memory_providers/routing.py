"""Native-first memory routing with explicit external fencing.

The rule (data, not prose):

    search native first
      → if external search is enabled AND the caller allowed it AND native
        results are insufficient
      → search selected external providers
      → label every result
      → NEVER auto-promote an external result to native truth

Routing is deterministic and explainable: every decision is recorded so the
caller can see WHY a provider was or was not consulted. An external result can
never be merged into the native list as if it were native; it is fenced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .protocol import (
    DEFAULT_EXTERNAL_PROVENANCE,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
)
from .registry import MemoryProviderRegistry

# The number of native results below which external search may be attempted.
DEFAULT_NATIVE_SUFFICIENCY = 3


def fence_external(provider_name: str, content: str) -> str:
    """Wrap external content in the explicit, machine-visible fence.

    External memory is UNVERIFIED CONTEXT. The fence is deliberately loud so the
    model and any UI can never mistake it for native, verified memory.
    """
    return (
        f"[EXTERNAL MEMORY — PROVIDER: {provider_name} — UNVERIFIED CONTEXT]\n"
        f"{content}\n"
        "[END EXTERNAL MEMORY]"
    )


@dataclass
class RoutedMemory:
    native: MemorySearchResponse
    external: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "native": self.native.to_dict(),
            "external": self.external,
            "decisions": self.decisions,
        }

    def fenced_external_blocks(self) -> list[str]:
        blocks: list[str] = []
        for entry in self.external:
            response = entry.get("response") or {}
            for result in response.get("results", []) or []:
                blocks.append(fence_external(entry.get("provider", "external"), result.get("content", "")))
        return blocks


class MemoryRouter:
    """Deterministic native-first router over the provider registry."""

    def __init__(
        self,
        registry: MemoryProviderRegistry,
        *,
        native_sufficiency: int = DEFAULT_NATIVE_SUFFICIENCY,
    ) -> None:
        self._registry = registry
        self._native_sufficiency = max(1, int(native_sufficiency))

    async def search(
        self,
        request: MemorySearchRequest,
        *,
        allow_external: bool = False,
    ) -> RoutedMemory:
        decisions: list[dict[str, Any]] = []
        native = await self._registry.search_native(request)
        decisions.append({
            "provider": "native",
            "consulted": True,
            "resultCount": len(native.results),
            "reason": "native is always the first source",
        })

        external: list[dict[str, Any]] = []
        if not allow_external or not self._registry.external_enabled or not request.allow_external:
            decisions.append({
                "provider": "external",
                "consulted": False,
                "reason": "external search not enabled/allowed for this request",
            })
            return RoutedMemory(native=native, external=external, decisions=decisions)

        if len(native.results) >= self._native_sufficiency:
            decisions.append({
                "provider": "external",
                "consulted": False,
                "reason": f"native returned {len(native.results)} result(s) (sufficient)",
            })
            return RoutedMemory(native=native, external=external, decisions=decisions)

        responses = await self._registry.search_external(request)
        for response in responses:
            external.append({"provider": response.provider, "response": response.to_dict()})
            decisions.append({
                "provider": response.provider,
                "consulted": True,
                "resultCount": len(response.results),
                "degraded": response.degraded,
                "reason": "native results were insufficient",
                # External results are never promoted.
                "promoted": False,
            })
        return RoutedMemory(native=native, external=external, decisions=decisions)


def build_memory_router(
    service: Any,
    *,
    mcp_manager: Any = None,
    external_enabled: bool = False,
    native_sufficiency: int = DEFAULT_NATIVE_SUFFICIENCY,
) -> MemoryRouter:
    """Convenience factory used by the service and the tools."""
    registry = MemoryProviderRegistry(
        native_service=service, mcp_manager=mcp_manager, external_enabled=external_enabled
    )
    return MemoryRouter(registry, native_sufficiency=native_sufficiency)


__all__ = [
    "DEFAULT_NATIVE_SUFFICIENCY",
    "MemoryRouter",
    "RoutedMemory",
    "build_memory_router",
    "fence_external",
]
