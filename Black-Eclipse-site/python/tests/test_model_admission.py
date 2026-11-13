"""Multi-session model admission: queue on quota, share cooldowns, honor hints."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from harness.model_runtime.credential_pool import get_credential_pool
from harness.model_runtime.health import RateLimitManager


@pytest.mark.asyncio
async def test_default_concurrency_queues_parallel_calls():
    limiter = RateLimitManager(default_concurrency=1)
    active = 0
    peak = 0

    async def call() -> None:
        nonlocal active, peak
        await limiter.acquire_slot("provider/model", timeout_s=2.0)
        try:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
        finally:
            active -= 1
            limiter.release_slot("provider/model")

    await asyncio.gather(*(call() for _ in range(5)))
    assert peak == 1


@pytest.mark.asyncio
async def test_retry_after_makes_the_next_call_wait():
    limiter = RateLimitManager(default_concurrency=4)
    limiter.record_429("provider/model", retry_after_s=0.08)
    assert limiter.seconds_until_available("provider/model") > 0

    started = time.monotonic()
    await limiter.acquire_slot("provider/model", timeout_s=2.0)
    elapsed = time.monotonic() - started
    limiter.release_slot("provider/model")
    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_admission_wait_is_bounded_by_the_caller_timeout():
    limiter = RateLimitManager(default_concurrency=1)
    limiter.record_429("provider/model", retry_after_s=30.0)
    with pytest.raises(asyncio.TimeoutError):
        await limiter.acquire_slot("provider/model", timeout_s=0.05)


def test_credential_pool_is_shared_across_runs():
    provider = f"test-{uuid4().hex[:8]}"
    settings = SimpleNamespace(provider=provider, api_key="key-one", base_url=None)

    first = get_credential_pool(settings, environ={})
    second = get_credential_pool(settings, environ={})
    assert first is second

    credential = first.acquire(provider)
    assert credential is not None
    first.record_failure(credential, status=429, retry_after_s=30.0)

    # A second run sees the first run's cooldown and can rotate/fail honestly
    # instead of firing into the same exhausted key.
    wait = second.seconds_until_available(provider)
    assert wait is not None and wait > 0
    assert second.acquire(provider) is None
