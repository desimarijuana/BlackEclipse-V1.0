"""Per-identity rate limiting (abuse control)."""

from __future__ import annotations

from harness.security.ratelimit import RateLimiter


def test_burst_then_refuse():
    limiter = RateLimiter(rate_per_minute=60, burst=3)
    assert [limiter.allow("t1") for _ in range(3)] == [True, True, True]
    assert limiter.allow("t1") is False
    assert limiter.retry_after("t1") > 0


def test_keys_are_independent():
    limiter = RateLimiter(rate_per_minute=60, burst=1)
    assert limiter.allow("tenant-a") is True
    assert limiter.allow("tenant-a") is False
    assert limiter.allow("tenant-b") is True  # not starved by tenant-a


def test_bucket_refills():
    limiter = RateLimiter(rate_per_minute=6000, burst=1)  # 100 tokens/sec
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False
    import time

    time.sleep(0.05)  # ~5 tokens
    assert limiter.allow("k") is True


def test_memory_is_bounded():
    limiter = RateLimiter(rate_per_minute=60, burst=1, max_keys=16)
    for i in range(100):
        limiter.allow(f"k{i}")
    assert len(limiter._buckets) <= 16  # noqa: SLF001
