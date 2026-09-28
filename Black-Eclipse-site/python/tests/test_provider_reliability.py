"""External provider reliability (Phase 10): failure classification, bounded
retry, circuit breaking, and native isolation. In-memory; no native impact."""

from __future__ import annotations

import asyncio

import pytest

from harness.eclipse_memory.service import EclipseMemoryService
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.memory_providers.protocol import MemorySearchRequest, MemorySearchResponse
from harness.memory_providers.registry import MemoryProviderRegistry
from harness.memory_providers.reliability import (
    COOLDOWN_S,
    FAILURE_THRESHOLD,
    PERMANENT,
    RATE_LIMITED,
    TRANSIENT,
    UNAUTHORIZED,
    UNAVAILABLE,
    ProviderRecord,
    classify_failure,
    is_retryable,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


# ── Classification ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,category", [
    ("request timed out", TRANSIENT),
    ("connection reset", TRANSIENT),
    ("401 unauthorized", UNAUTHORIZED),
    ("403 forbidden", UNAUTHORIZED),
    ("429 too many requests", RATE_LIMITED),
    ("unsupported operation", "unsupported"),
    ("invalid JSON payload", PERMANENT),
    ("provider not connected", UNAVAILABLE),
    ("", UNAVAILABLE),
])
def test_failure_classification(text, category):
    assert classify_failure(text) == category


def test_retryable_only_transient_and_rate_limited():
    assert is_retryable(TRANSIENT) is True
    assert is_retryable(RATE_LIMITED) is True
    assert is_retryable(PERMANENT) is False
    assert is_retryable(UNAUTHORIZED) is False


# ── Circuit breaker ─────────────────────────────────────────────────────────


def test_circuit_opens_after_threshold():
    record = ProviderRecord(name="mcp:x")
    assert record.allows_call() is True
    for _ in range(FAILURE_THRESHOLD):
        record.record_failure(TRANSIENT)
    assert record.state() == "open"
    assert record.allows_call() is False


def test_circuit_half_opens_after_cooldown():
    record = ProviderRecord(name="mcp:x")
    now = 1000.0
    for _ in range(FAILURE_THRESHOLD):
        record.record_failure(TRANSIENT, now=now)
    assert record.allows_call(now=now) is False
    assert record.state(now=now + COOLDOWN_S + 1) == "half_open"
    assert record.allows_call(now=now + COOLDOWN_S + 1) is True


def test_success_resets_circuit():
    record = ProviderRecord(name="mcp:x")
    for _ in range(FAILURE_THRESHOLD):
        record.record_failure(TRANSIENT)
    record.record_success(12.0)
    assert record.state() == "closed"
    assert record.total_failures == FAILURE_THRESHOLD


def test_reliability_history_is_bounded():
    record = ProviderRecord(name="mcp:x")
    for _ in range(100):
        record.record_success(1.0)
    assert len(record.latencies_ms) <= 50
    snapshot = record.to_dict()
    assert snapshot["totalCalls"] == 100
    assert snapshot["meanLatencyMs"] is not None


# ── Router behaviour ────────────────────────────────────────────────────────


class _AlwaysFails:
    name = "mcp:bad"

    def capabilities(self):
        from harness.memory_providers.protocol import ProviderCapabilities

        return ProviderCapabilities(search=True)

    async def health(self):
        from harness.memory_providers.protocol import ProviderHealth

        return ProviderHealth(ok=False, state="unavailable")

    async def search(self, request):
        raise RuntimeError("429 too many requests")


def test_failing_provider_degrades_and_native_is_unaffected(service):
    service.write_memory(memory_type="preference", content="User prefers concise answers", source="explicit_user")
    registry = MemoryProviderRegistry(service, mcp_manager=None, external_enabled=True)
    # Inject a fake external provider directly (bypasses MCP wiring).
    registry._providers["mcp:bad"] = _AlwaysFails()  # noqa: SLF001

    from harness.memory_providers.reliability import global_reliability

    global_reliability().reset()

    request = MemorySearchRequest(query="concise answers", allow_external=True, limit=5)
    # The router always returns native results; external is degraded, never fatal.
    responses = asyncio.run(registry.search_external(request))
    assert responses and responses[0].degraded is True

    native = asyncio.run(registry.search_native(request))
    assert len(native.results) >= 1


def test_circuit_open_skips_provider_without_calling(service):
    calls = {"count": 0}

    class _Counting:
        name = "mcp:count"

        def capabilities(self):
            from harness.memory_providers.protocol import ProviderCapabilities

            return ProviderCapabilities(search=True)

        async def health(self):
            from harness.memory_providers.protocol import ProviderHealth

            return ProviderHealth(ok=True, state="available")

        async def search(self, request):
            calls["count"] += 1
            raise RuntimeError("timeout")

    registry = MemoryProviderRegistry(service, external_enabled=True)
    registry._providers["mcp:count"] = _Counting()  # noqa: SLF001
    from harness.memory_providers.reliability import global_reliability

    global_reliability().reset()
    request = MemorySearchRequest(query="q", allow_external=True, limit=3)
    # Three failing searches open the circuit (each search retries once).
    for _ in range(3):
        asyncio.run(registry.search_external(request))
    before = calls["count"]
    responses = asyncio.run(registry.search_external(request))
    # The open circuit skips the provider: no new call, reported as degraded.
    assert calls["count"] == before
    assert responses[0].detail and "circuit open" in responses[0].detail
    global_reliability().reset()
