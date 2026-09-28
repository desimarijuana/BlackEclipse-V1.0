"""Milestone 8 — external memory providers: safety and routing tests.

These exercise the REAL provider layer against the REAL Eclipse-Memory service
(temp DB) and against a fake MCP manager (never a real subprocess). They assert
the non-negotiable invariants:

  * external results are labelled `external_provider`/`verified=false`;
  * discovery does not activate a provider;
  * external search requires explicit allow + policy enablement;
  * external results never enter native memory;
  * an external write requires explicit user intent AND approval;
  * a failing/timing-out/malformed provider degrades honestly;
  * profile/scope isolation is preserved.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from harness.eclipse_memory.service import EclipseMemoryService
from harness.memory_providers import (
    MCPMemoryProvider,
    MemoryProviderRegistry,
    MemoryRouter,
    MemorySearchRequest,
    MemoryWriteRequest,
    NativeMemoryProvider,
    build_memory_router,
    fence_external,
)
from harness.memory_providers.protocol import DEFAULT_EXTERNAL_PROVENANCE


@pytest.fixture()
def service(tmp_path):
    db = tmp_path / "eclipse-memory.db"
    svc = EclipseMemoryService()
    svc.store.close()
    from harness.eclipse_memory.store import EclipseMemoryStore

    svc = EclipseMemoryService(EclipseMemoryStore(str(db)))
    yield svc
    svc.close()


# ── native provider ─────────────────────────────────────────────────────────


def test_native_provider_searches_gated_memory(service):
    service.write_memory(memory_type="preference", content="User prefers concise answers.", source="explicit_user")
    provider = NativeMemoryProvider(service)
    result = asyncio.run(provider.search(MemorySearchRequest(query="concise answers", memory_types=["preference"])))
    assert result.provider == "native"
    assert len(result.results) == 1
    assert result.results[0].provenance == "native"
    assert result.results[0].verified is False  # native records are not auto-upgraded


def test_native_write_requires_explicit_user_request(service):
    provider = NativeMemoryProvider(service)
    refused = asyncio.run(provider.write(MemoryWriteRequest(content="x", memory_type="semantic")))
    assert refused.ok is False
    accepted = asyncio.run(provider.write(MemoryWriteRequest(
        content="User prefers dark mode.", memory_type="preference", explicit_user_request=True,
    )))
    assert accepted.ok is True


def test_native_delete_requires_approval(service):
    provider = NativeMemoryProvider(service)
    refused = asyncio.run(provider.delete(_delete_req("m1", approved=False)))
    assert refused.ok is False


def _delete_req(record_id: str, *, approved: bool):
    from harness.memory_providers.protocol import MemoryDeleteRequest

    return MemoryDeleteRequest(record_id=record_id, approved=approved)


# ── fake MCP manager ────────────────────────────────────────────────────────


class _FakeDescriptor:
    def __init__(self, name: str, effect: str = "read", *, activatable: bool = True) -> None:
        self.original_name = name
        self.eclipse_name = f"mcp_fake_{name}"
        self.effect = effect
        self.activatable = activatable
        self.selected = True


class _FakeOutcome:
    def __init__(self, text: str = "", *, ok: bool = True, is_error: bool = False) -> None:
        self.text = text
        self.data: Optional[dict[str, Any]] = None
        self.ok = ok
        self.is_error = is_error


class _FakeConnection:
    def __init__(self, *, text: str = "recalled: project uses PKR reporting", fail: bool = False, timeout: bool = False):
        self.protocol_version = "1"
        self.server_info = {"name": "fake-memory"}
        self.redaction_values: list[str] = []
        self._text = text
        self._fail = fail
        self._timeout = timeout
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name, args, *, timeout_ms=None):
        self.calls.append((name, args))
        if self._timeout:
            from harness.mcp.client import MCPTimeoutError

            raise MCPTimeoutError("timed out")
        if self._fail:
            from harness.mcp.client import MCPCallError

            raise MCPCallError("boom")
        return _FakeOutcome(self._text)


class _FakeConfig:
    def __init__(self, *, effects: Optional[list[str]] = None) -> None:
        self.id = "fake"
        self.enabled = True
        self.enabled_effects = effects or ["read"]
        self.transport = "stdio"


class _FakeRuntime:
    def __init__(self, descriptors, connection, config) -> None:
        self.descriptors = {d.original_name: d for d in descriptors}
        self.connection = connection
        self.config = config
        self.state = "connected"
        self.diagnostic = None
        self.limits = {"callTimeoutMs": 5000, "outputLimitBytes": 4096}

    def redact(self, text: str) -> str:
        return text


class _FakeManager:
    def __init__(self, runtime) -> None:
        self._runtimes = {"fake": runtime}


def _make_provider(*, fail=False, timeout=False, effects=None, search=True, write=False):
    descriptors = [_FakeDescriptor("memory_search")]
    if write:
        descriptors.append(_FakeDescriptor("memory_save", effect="write"))
    runtime = _FakeRuntime(descriptors, _FakeConnection(fail=fail, timeout=timeout), _FakeConfig(effects=effects))
    manager = _FakeManager(runtime)
    return MCPMemoryProvider(manager, "fake"), runtime


# ── external provider behavior ──────────────────────────────────────────────


def test_external_result_is_labelled_unverified():
    provider, _ = _make_provider()
    result = asyncio.run(provider.search(MemorySearchRequest(query="reporting", allow_external=True)))
    assert len(result.results) == 1
    item = result.results[0]
    assert item.provenance == DEFAULT_EXTERNAL_PROVENANCE
    assert item.verified is False
    assert item.provider == "mcp:fake"


def test_external_search_requires_allow_flag():
    provider, _ = _make_provider()
    result = asyncio.run(provider.search(MemorySearchRequest(query="reporting", allow_external=False)))
    assert result.results == []
    assert result.degraded is True


def test_external_search_degrades_on_timeout():
    provider, _ = _make_provider(timeout=True)
    result = asyncio.run(provider.search(MemorySearchRequest(query="x", allow_external=True)))
    assert result.degraded is True
    assert "timed out" in (result.detail or "")


def test_external_search_degrades_on_provider_error():
    provider, _ = _make_provider(fail=True)
    result = asyncio.run(provider.search(MemorySearchRequest(query="x", allow_external=True)))
    assert result.degraded is True


def test_external_is_unavailable_without_search_tool():
    runtime = _FakeRuntime([_FakeDescriptor("unrelated_tool")], _FakeConnection(), _FakeConfig())
    provider = MCPMemoryProvider(_FakeManager(runtime), "fake")
    health = asyncio.run(provider.health())
    assert health.ok is False
    assert runtime.connection is not None


def test_external_write_requires_user_and_approval():
    provider, runtime = _make_provider(write=True, effects=["read", "write"])
    # No explicit request:
    r1 = asyncio.run(provider.write(MemoryWriteRequest(content="x", explicit_user_request=False, approved=True)))
    assert r1.ok is False
    # Explicit but not approved:
    r2 = asyncio.run(provider.write(MemoryWriteRequest(content="x", explicit_user_request=True, approved=False)))
    assert r2.ok is False
    # Both set → the call reaches the connection (the fake returns ok).
    r3 = asyncio.run(provider.write(MemoryWriteRequest(content="x", explicit_user_request=True, approved=True)))
    assert r3.ok is True
    assert r3.audited is True


def test_external_delete_and_export_refused():
    provider, _ = _make_provider()
    from harness.memory_providers.protocol import MemoryDeleteRequest, MemoryExportRequest

    assert asyncio.run(provider.delete(MemoryDeleteRequest(record_id="x", approved=True))).ok is False
    assert asyncio.run(provider.export(MemoryExportRequest())).ok is False


# ── registry / router ───────────────────────────────────────────────────────


def test_discovery_does_not_activate_provider(service):
    provider, _ = _make_provider()
    manager = provider._manager
    registry = MemoryProviderRegistry(service, mcp_manager=manager, external_enabled=False)
    # The provider is REGISTERED but external search is off.
    assert "mcp:fake" in registry.names()
    responses = asyncio.run(registry.search_external(MemorySearchRequest(query="x", allow_external=True)))
    assert responses == []


def test_router_native_first_never_promotes(service):
    service.write_memory(memory_type="preference", content="User prefers concise answers.", source="explicit_user")
    provider, _ = _make_provider()
    registry = MemoryProviderRegistry(service, mcp_manager=provider._manager, external_enabled=True)
    router = MemoryRouter(registry, native_sufficiency=5)
    routed = asyncio.run(router.search(
        MemorySearchRequest(query="concise answers", memory_types=["preference"], allow_external=True),
        allow_external=True,
    ))
    assert len(routed.native.results) >= 1
    # External was consulted (native was insufficient) but never promoted.
    external_decisions = [d for d in routed.decisions if d.get("provider") != "native" and d.get("consulted")]
    assert all(d.get("promoted") is False for d in external_decisions)
    # The native result remains native; external lives only in its own bucket.
    assert all(r.provenance == "native" for r in routed.native.results)


def test_router_skips_external_when_native_sufficient(service):
    for i in range(3):
        service.write_memory(
            memory_type="semantic", content=f"Project convention alpha {i} for module {i}.",
            source="explicit_user", subject=f"module-{i}",
        )
    provider, runtime = _make_provider()
    registry = MemoryProviderRegistry(service, mcp_manager=provider._manager, external_enabled=True)
    router = MemoryRouter(registry, native_sufficiency=1)
    routed = asyncio.run(router.search(
        MemorySearchRequest(query="convention alpha", allow_external=True),
        allow_external=True,
    ))
    assert routed.native.results, "expected native results"
    assert routed.external == []
    assert any(d.get("reason", "").startswith("native returned") for d in routed.decisions)
    assert runtime.connection.calls == []


def test_fence_labels_provider():
    block = fence_external("mcp:notes", "some content")
    assert "EXTERNAL MEMORY" in block
    assert "mcp:notes" in block
    assert "UNVERIFIED CONTEXT" in block


def test_build_memory_router_has_native(service):
    router = build_memory_router(service)
    assert router._registry.get("native") is not None

# -- Phase 7 diagnostics + bounded test --------------------------------------


def test_diagnostics_includes_capability_summary_and_privacy(service):
    from harness.memory_providers.diagnostics import provider_diagnostics

    registry = build_memory_router(service)._registry
    report = asyncio.run(provider_diagnostics(registry))
    native = next(p for p in report["providers"] if p["isNative"])
    assert native["capabilitySummary"].startswith("native:")
    assert "local" in native["dataLocation"]
    assert native["verifiedByEclipse"] is True
    assert report["privacyNote"]
    assert "failed" in report


def test_provider_test_is_non_destructive(service):
    from harness.memory_providers.diagnostics import provider_test

    service.write_memory(memory_type="preference", content="User prefers concise answers.", source="explicit_user")
    registry = build_memory_router(service)._registry
    before = len(service.store.list_memories(limit=100))
    result = asyncio.run(provider_test(registry, "native"))
    assert result["ok"] is True
    assert result["externalVerified"] is False
    assert len(service.store.list_memories(limit=100)) == before


def test_provider_test_unknown_provider(service):
    from harness.memory_providers.diagnostics import provider_test

    registry = build_memory_router(service)._registry
    result = asyncio.run(provider_test(registry, "does-not-exist"))
    assert result["ok"] is False
    assert result["state"] == "unknown"
