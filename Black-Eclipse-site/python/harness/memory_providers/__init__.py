"""First-class external/native memory providers (Milestone 8).

A thin, explicit provider layer that joins the mature native Eclipse-Memory
subsystem and the mature MCP tool subsystem WITHOUT collapsing them into one
"generic memory". It owns:

  * `protocol.py`  — the `MemoryProvider` contract + request/response types;
  * `native.py`    — the native Eclipse-Memory provider (search/write/delete/export);
  * `mcp.py`       — an MCP server exposed as a search-only (then explicitly
                     write-gated) memory provider;
  * `registry.py`  — the provider registry (health + capability introspection);
  * `routing.py`   — native-first routing that labels and NEVER auto-promotes
                     external results;
  * `diagnostics.py` — bounded, content-free provider diagnostics.

Safety rules enforced by construction:

  * every result carries provider/scope/verification metadata; external results
    default to `provenance=external_provider`, `verified=false`;
  * external providers can never silently overwrite native memory;
  * no provider discovery activates a provider or a tool;
  * secrets never enter a result, a diagnostic, or a memory record.
"""

from __future__ import annotations

from .diagnostics import provider_diagnostics
from .mcp import MCPMemoryProvider
from .native import NativeMemoryProvider
from .protocol import (
    DEFAULT_EXTERNAL_PROVENANCE,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemoryExportRequest,
    MemoryExportResponse,
    MemoryProvider,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryWriteRequest,
    MemoryWriteResponse,
    ProviderCapabilities,
    ProviderHealth,
)
from .registry import MemoryProviderRegistry
from .routing import MemoryRouter, build_memory_router, fence_external

__all__ = [
    "DEFAULT_EXTERNAL_PROVENANCE",
    "MCPMemoryProvider",
    "MemoryDeleteRequest",
    "MemoryDeleteResponse",
    "MemoryExportRequest",
    "MemoryExportResponse",
    "MemoryProvider",
    "MemoryProviderRegistry",
    "MemoryRouter",
    "MemorySearchRequest",
    "MemorySearchResponse",
    "MemorySearchResult",
    "MemoryWriteRequest",
    "MemoryWriteResponse",
    "NativeMemoryProvider",
    "ProviderCapabilities",
    "ProviderHealth",
    "build_memory_router",
    "fence_external",
    "provider_diagnostics",
]
