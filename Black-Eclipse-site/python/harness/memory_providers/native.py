"""The native Eclipse-Memory provider.

Wraps `EclipseMemoryService` in the `MemoryProvider` contract WITHOUT adding a
second store or a second write path. A native write still goes through the
existing service pipeline; this provider simply exposes it in the uniform shape
so a router can compare native vs external results.

`export` delegates to the existing `transfer.export_payload`. Native records are
`verified` only when their own verification field says so — this provider never
upgrades a native record's verification state.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .protocol import (
    MAX_RESULT_CHARS,
    NATIVE_PROVENANCE,
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


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


class NativeMemoryProvider:
    """The native provider — search/write/delete/export over Eclipse-Memory."""

    name = "native"
    version = "1"

    def __init__(self, service: Any) -> None:
        self._service = service

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=True, write=True, delete=True, export=True, read_only=False
        )

    async def health(self) -> ProviderHealth:
        if self._service is None:
            return ProviderHealth(ok=False, state="unavailable", detail="no memory service", version=self.version)
        try:
            counts = self._service.store.memory_lifecycle_counts()
            active = counts.get("active") if isinstance(counts, dict) else None
            return ProviderHealth(
                ok=True, state="available",
                detail=(f"{active} active" if active is not None else None),
                version=self.version,
            )
        except Exception as exc:  # noqa: BLE001 - health is diagnostic, never fatal
            return ProviderHealth(ok=False, state="degraded", detail=str(exc), version=self.version)

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        if self._service is None:
            return MemorySearchResponse(provider=self.name, degraded=True, detail="memory service unavailable")
        req = request.bounded()
        result = self._service.retrieve(
            query=req.query,
            memory_types=req.memory_types,
            scope=req.scope,
            scope_id=req.scope_id,
            actor_scope=("user" if req.user_id else None),
            limit=req.limit,
        )
        results: list[MemorySearchResult] = []
        for memory in result.memories:
            results.append(MemorySearchResult(
                record_id=str(memory.get("id") or ""),
                content=(memory.get("content") or "")[:MAX_RESULT_CHARS],
                scope=memory.get("scope") or "general",
                scope_id=memory.get("scopeId"),
                memory_type=memory.get("memoryType") or "semantic",
                provider=self.name,
                provenance=NATIVE_PROVENANCE,
                verified=(memory.get("verification") == "verified"),
                confidence=memory.get("confidence"),
                retrieved_at=_now(),
                metadata={"source": memory.get("source"), "status": memory.get("status")},
            ))
        return MemorySearchResponse(provider=self.name, results=results)

    async def write(self, request: MemoryWriteRequest) -> MemoryWriteResponse:
        # A native write through this provider STILL requires an explicit user
        # request — a provider must never silently persist content. The service's
        # own gate remains authoritative if a caller routes through it directly.
        if not request.explicit_user_request:
            return MemoryWriteResponse(
                provider=self.name, ok=False,
                detail="native write requires an explicit user request",
            )
        if self._service is None:
            return MemoryWriteResponse(provider=self.name, ok=False, detail="memory service unavailable")
        try:
            memory = self._service.write_memory(
                memory_type=request.memory_type,
                content=request.content,
                source="explicit_user",
                scope=request.scope,
                scope_id=request.scope_id,
            )
            return MemoryWriteResponse(provider=self.name, ok=True, record_id=memory.get("id"), audited=True)
        except Exception as exc:  # noqa: BLE001 - a refused write is an honest failure
            return MemoryWriteResponse(provider=self.name, ok=False, detail=str(exc))

    async def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResponse:
        # Native memory is never hard-deleted; this delegates to archive, and only
        # with explicit approval.
        if not request.approved:
            return MemoryDeleteResponse(provider=self.name, ok=False, detail="archive requires explicit approval")
        if self._service is None or not request.record_id:
            return MemoryDeleteResponse(provider=self.name, ok=False, detail="memory service/record id unavailable")
        try:
            self._service.store.archive_memory(request.record_id, reason="provider_delete")
            return MemoryDeleteResponse(provider=self.name, ok=True)
        except Exception as exc:  # noqa: BLE001
            return MemoryDeleteResponse(provider=self.name, ok=False, detail=str(exc))

    async def export(self, request: MemoryExportRequest) -> MemoryExportResponse:
        if self._service is None:
            return MemoryExportResponse(provider=self.name, ok=False, detail="memory service unavailable")
        try:
            from ..eclipse_memory.transfer import export_payload  # noqa: PLC0415

            payload = export_payload(self._service.store, include_inactive=request.include_inactive)
            return MemoryExportResponse(provider=self.name, ok=True, payload=payload)
        except Exception as exc:  # noqa: BLE001
            return MemoryExportResponse(provider=self.name, ok=False, detail=str(exc))


__all__ = ["NativeMemoryProvider"]
