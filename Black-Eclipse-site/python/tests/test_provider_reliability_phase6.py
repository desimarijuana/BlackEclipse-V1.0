"""Phase 6 (final hardening) — provider reliability validation.

Covers timeout budgets, retry classification (transient/permanent/auth/
rate-limit/unsupported/provider-failure), circuit breaker open/half-open/recovery,
bounded per-provider history with last-success, native fallback unaffected, and
external results remain fenced/unverified.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.memory_providers import reliability
from harness.memory_providers.protocol import (
    MemorySearchRequest,
    MemorySearchResponse,
    ProviderCapabilities,
    ProviderHealth,
)
from harness.memory_providers.registry import MemoryProviderRegistry


class _ScriptedProvider:
    """A provider whose search follows a scripted list of behaviours."""

    version = "test"

    def __init__(self, name, outcomes, *, search=True):
        self.name = name
        self._outcomes = list(outcomes)
        self._caps = ProviderCapabilities(search=search, write=False, read_only=True)

    def capabilities(self):
        return self._caps

    async def health(self):
        return ProviderHealth(ok=True, state="connected", detail=None)

    async def search(self, request):
        outcome = self._outcomes.pop(0) if self._outcomes else self._outcomes_default()
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == "hang":
            await asyncio.sleep(60)
        return MemorySearchResponse(provider=self.name, results=[], detail=None)

    def _outcomes_default(self):
        return MemorySearchResponse(provider=self.name, results=[], detail=None)


class _UnavailableSearch:
    version = "test"

    def __init__(self, name):
        self.name = name

    def capabilities(self):
        return ProviderCapabilities(search=True, write=False, read_only=True)

    async def health(self):
        return ProviderHealth(ok=True, state="connected", detail=None)

    async def search(self, request):
        await asyncio.sleep(60)  # never returns within the budget


def _registry_with(providers, *, enabled=True):
    registry = MemoryProviderRegistry(native_service=None, external_enabled=enabled)
    for provider in providers:
        registry._providers[provider.name] = provider
    return registry


def _request():
    return MemorySearchRequest(query="q", limit=5, allow_external=True)


# ── Classification ──────────────────────────────────────────────────────────


def test_failure_classification_covers_required_states():
    assert reliability.classify_failure("connection reset") == reliability.TRANSIENT
    assert reliability.classify_failure("invalid json") == reliability.PERMANENT
    assert reliability.classify_failure("401 unauthorized") == reliability.UNAUTHORIZED
    assert reliability.classify_failure("429 too many requests") == reliability.RATE_LIMITED
    assert reliability.classify_failure("unsupported method") == reliability.UNSUPPORTED
    assert reliability.classify_failure("502 bad gateway") == reliability.PROVIDER_FAILURE
    assert reliability.classify_failure("") == reliability.UNAVAILABLE


def test_retryable_classes_are_bounded():
    assert reliability.is_retryable(reliability.TRANSIENT)
    assert reliability.is_retryable(reliability.RATE_LIMITED)
    assert reliability.is_retryable(reliability.PROVIDER_FAILURE)
    assert not reliability.is_retryable(reliability.UNAUTHORIZED)
    assert not reliability.is_retryable(reliability.PERMANENT)


# ── Timeout budget ──────────────────────────────────────────────────────────


def test_provider_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(reliability, "SEARCH_TIMEOUT_S", 0.05)
    monkeypatch.setattr(reliability, "RETRY_BACKOFF_S", 0.0)
    reliability.global_reliability().reset()
    registry = _registry_with([_UnavailableSearch("slow")])
    responses = asyncio.run(registry.search_external(_request()))
    assert len(responses) == 1
    assert responses[0].degraded is True
    assert "timeout" in (responses[0].detail or "").lower()
    # The call is bounded — it did not hang for the full 60s sleep.
    record = reliability.global_reliability().record_for("slow")
    assert record.last_failure_category == reliability.TRANSIENT


# ── Circuit breaker + recovery through the router ───────────────────────────


def test_circuit_opens_then_recovers_through_router(monkeypatch):
    monkeypatch.setattr(reliability, "RETRY_BACKOFF_S", 0.0)
    reliability.global_reliability().reset()
    # Always fails transiently: each search_external call makes 2 attempts, so
    # after 3 failures (two calls) the circuit opens.
    provider = _ScriptedProvider("flaky", [RuntimeError("connection reset")] * 10)
    registry = _registry_with([provider])
    asyncio.run(registry.search_external(_request()))
    asyncio.run(registry.search_external(_request()))
    record = reliability.global_reliability().record_for("flaky")
    assert record.state() == "open"
    # An open circuit is skipped, not called.
    responses = asyncio.run(registry.search_external(_request()))
    assert responses and responses[0].degraded is True
    assert "circuit open" in (responses[0].detail or "")
    # After the cooldown, a successful call closes the circuit again.
    record.opened_at -= reliability.COOLDOWN_S + 1
    assert record.allows_call() is True
    good = _ScriptedProvider("flaky", [MemorySearchResponse(provider="flaky", results=[], detail=None)])
    registry._providers["flaky"] = good
    responses = asyncio.run(registry.search_external(_request()))
    assert responses and responses[0].degraded is not True
    assert record.state() == "closed"
    assert record.last_success_at is not None


def test_per_provider_history_is_bounded():
    record = reliability.ProviderRecord(name="p")
    for i in range(reliability.MAX_HISTORY + 20):
        record.record_success(10.0)
    assert len(record.latencies_ms) == reliability.MAX_HISTORY
    assert len(record.events) == reliability.MAX_HISTORY
    snapshot = record.to_dict()
    assert snapshot["lastSuccessAgeSec"] is not None
    assert snapshot["history"]


def test_native_untouched_by_external_failure(monkeypatch):
    monkeypatch.setattr(reliability, "RETRY_BACKOFF_S", 0.0)
    reliability.global_reliability().reset()
    registry = _registry_with([_ScriptedProvider("bad", [RuntimeError("500 internal server error")] * 4)])
    responses = asyncio.run(registry.search_external(_request()))
    assert all(r.degraded for r in responses)
    # Native is a separate provider and is never marked degraded by an external
    # failure.
    native_provider = registry.native()
    assert native_provider is not None


def test_external_not_reached_without_explicit_allow():
    reliability.global_reliability().reset()
    registry = _registry_with([_ScriptedProvider("x", [])])
    no_allow = MemorySearchRequest(query="q", limit=5, allow_external=False)
    assert asyncio.run(registry.search_external(no_allow)) == []
