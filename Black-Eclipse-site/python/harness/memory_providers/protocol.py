"""The `MemoryProvider` contract (Milestone 8).

This is the ONE interface native memory and every external memory source
implement. It is deliberately small and async, and it carries provenance on
EVERY result so a caller can never confuse an external, unverified memory with
native, gate-authorized truth.

Design rules (non-negotiable):

  * a provider is a *retrieval/context* source, never an authority;
  * an external result defaults to ``provenance="external_provider"`` and
    ``verified=False``; it can never authorize a native write;
  * a provider declares its capabilities; a capability that is not declared is
    refused honestly, never emulated;
  * request/response types are bounded and content-safe (no secrets, no raw
    provider payloads in diagnostics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

# Defaults that make an external result's provenance unambiguous.
DEFAULT_EXTERNAL_PROVENANCE = "external_provider"
NATIVE_PROVENANCE = "native"

# Bounds (a provider may return less, never more).
MAX_RESULTS = 50
MAX_RESULT_CHARS = 4000
MAX_QUERY_CHARS = 2000


@dataclass
class ProviderCapabilities:
    """What a provider can do. Undeclared capabilities are refused, not faked."""

    search: bool = False
    write: bool = False
    delete: bool = False
    export: bool = False
    # `read_only` is derived in practice, but declared for clarity.
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "search": self.search,
            "write": self.write,
            "delete": self.delete,
            "export": self.export,
            "readOnly": self.read_only,
        }


@dataclass
class ProviderHealth:
    """Bounded, non-secret health for one provider."""

    ok: bool
    state: str  # "available" | "degraded" | "unavailable"
    detail: Optional[str] = None
    latency_ms: Optional[int] = None
    version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "state": self.state,
            "detail": self.detail,
            "latencyMs": self.latency_ms,
            "version": self.version,
        }


@dataclass
class MemorySearchRequest:
    query: str = ""
    scope: Optional[str] = None
    scope_id: Optional[str] = None
    user_id: Optional[str] = None
    profile_id: Optional[str] = None
    memory_types: Optional[list[str]] = None
    limit: int = 8
    # External providers may only be reached when the caller explicitly allowed
    # it for this request. Default False keeps native-only by construction.
    allow_external: bool = False

    def bounded(self) -> "MemorySearchRequest":
        return MemorySearchRequest(
            query=(self.query or "")[:MAX_QUERY_CHARS],
            scope=self.scope,
            scope_id=self.scope_id,
            user_id=self.user_id,
            profile_id=self.profile_id,
            memory_types=self.memory_types,
            limit=max(1, min(int(self.limit or 8), MAX_RESULTS)),
            allow_external=self.allow_external,
        )


@dataclass
class MemorySearchResult:
    """One result with full provenance. External results are labelled here."""

    record_id: str
    content: str
    scope: str = "general"
    scope_id: Optional[str] = None
    memory_type: str = "semantic"
    provider: str = "native"
    provenance: str = NATIVE_PROVENANCE
    verified: bool = False
    confidence: Optional[float] = None
    retrieved_at: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recordId": self.record_id,
            "content": self.content,
            "scope": self.scope,
            "scopeId": self.scope_id,
            "memoryType": self.memory_type,
            "provider": self.provider,
            "provenance": self.provenance,
            "verified": self.verified,
            "confidence": self.confidence,
            "retrievedAt": self.retrieved_at,
            "metadata": self.metadata,
        }


@dataclass
class MemorySearchResponse:
    provider: str
    results: list[MemorySearchResult] = field(default_factory=list)
    degraded: bool = False
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "results": [r.to_dict() for r in self.results],
            "degraded": self.degraded,
            "detail": self.detail,
        }


@dataclass
class MemoryWriteRequest:
    content: str = ""
    memory_type: str = "semantic"
    scope: str = "general"
    scope_id: Optional[str] = None
    profile_id: Optional[str] = None
    # The caller must have explicit user intent AND operator approval for an
    # external write. Both default False; a provider must refuse otherwise.
    explicit_user_request: bool = False
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "memoryType": self.memory_type,
            "scope": self.scope,
            "scopeId": self.scope_id,
            "profileId": self.profile_id,
            "explicitUserRequest": self.explicit_user_request,
            "approved": self.approved,
        }


@dataclass
class MemoryWriteResponse:
    provider: str
    ok: bool
    record_id: Optional[str] = None
    detail: Optional[str] = None
    audited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "recordId": self.record_id,
            "detail": self.detail,
            "audited": self.audited,
        }


@dataclass
class MemoryDeleteRequest:
    record_id: str = ""
    scope_id: Optional[str] = None
    profile_id: Optional[str] = None
    approved: bool = False


@dataclass
class MemoryDeleteResponse:
    provider: str
    ok: bool
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "ok": self.ok, "detail": self.detail}


@dataclass
class MemoryExportRequest:
    scope_id: Optional[str] = None
    profile_id: Optional[str] = None
    include_inactive: bool = False


@dataclass
class MemoryExportResponse:
    provider: str
    ok: bool
    payload: Optional[dict[str, Any]] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "payload": self.payload,
            "detail": self.detail,
        }


@runtime_checkable
class MemoryProvider(Protocol):
    """The ONE memory-provider interface.

    A provider implementation must never:
      * authorize a native mutation,
      * claim a result is Eclipse-verified,
      * return secrets or unrestricted provider payloads,
      * perform a write/delete without an explicit approval flag.
    """

    name: str
    version: str

    def capabilities(self) -> ProviderCapabilities: ...

    async def health(self) -> ProviderHealth: ...

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse: ...

    async def write(self, request: MemoryWriteRequest) -> MemoryWriteResponse: ...

    async def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResponse: ...

    async def export(self, request: MemoryExportRequest) -> MemoryExportResponse: ...


__all__ = [
    "DEFAULT_EXTERNAL_PROVENANCE",
    "MAX_QUERY_CHARS",
    "MAX_RESULTS",
    "MAX_RESULT_CHARS",
    "NATIVE_PROVENANCE",
    "MemoryDeleteRequest",
    "MemoryDeleteResponse",
    "MemoryExportRequest",
    "MemoryExportResponse",
    "MemoryProvider",
    "MemorySearchRequest",
    "MemorySearchResponse",
    "MemorySearchResult",
    "MemoryWriteRequest",
    "MemoryWriteResponse",
    "ProviderCapabilities",
    "ProviderHealth",
]
