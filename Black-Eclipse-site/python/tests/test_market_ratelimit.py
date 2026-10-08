"""Rate-limit realism tests — declared enforcement + live-quota observation."""

from __future__ import annotations

import asyncio

from harness.market.providers import RateLimit
from harness.market.ratelimit import MarketRateLimiter


def test_declared_rpm_is_enforced():
    limiter = MarketRateLimiter()

    async def run():
        decisions = []
        for _ in range(4):
            decisions.append(await limiter.acquire("p", RateLimit(requests_per_minute=3, concurrency=8)))
            await limiter.release("p")
        return decisions

    decisions = asyncio.run(run())
    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert limiter.snapshot()["p"]["denied"] == 1


def test_concurrency_cap():
    limiter = MarketRateLimiter()

    async def run():
        first = await limiter.acquire("p", RateLimit(concurrency=1))
        second = await limiter.acquire("p", RateLimit(concurrency=1))  # no release yet
        return first, second

    first, second = asyncio.run(run())
    assert first.allowed and not second.allowed


def test_observed_quota_raises_effective_limit_strictness():
    limiter = MarketRateLimiter()

    async def run():
        await limiter.acquire("p", RateLimit(requests_per_minute=1200, concurrency=8))
        await limiter.release("p")
        # The provider reports a much tighter real window (e.g. a low tier).
        await limiter.observe("p", limit=60, used=10, remaining=50, window_seconds=60)
        snap = limiter.snapshot()["p"]
        return snap

    snap = asyncio.run(run())
    assert snap["declared"]["requestsPerMinute"] == 1200
    assert snap["observed"]["remaining"] == 50
    # Effective = min(declared 1200, observed 60) = 60.
    assert snap["effectiveRequestsPerMinute"] == 60


def test_429_opens_cooldown():
    limiter = MarketRateLimiter()

    async def run():
        await limiter.record_429("p", retry_after_s=5.0)
        denied = await limiter.acquire("p", RateLimit(concurrency=4))
        return denied

    denied = asyncio.run(run())
    assert not denied.allowed
    assert denied.retry_after_s and denied.retry_after_s > 0


def test_gateway_feeds_observed_quota_and_metrics():
    """The gateway observes provider rate-limit metadata and records latency."""
    import asyncio

    from harness.market.cache import MarketCache
    from harness.market.gateway import MarketDataGateway
    from harness.market.router import ProviderRouter
    from harness.tools import DataBridge

    class FakeBridge(DataBridge):
        async def fetch(self, capability, params):
            if capability == "market_snapshot":
                return {"status": "OK", "symbol": params.get("symbol"), "market": "US",
                        "currency": "USD", "assetClass": "equity", "instrumentId": "US:AAPL"}
            return {
                "status": "OK", "provider": "yahoo", "symbol": "AAPL",
                "price": {"price": 100.0},
                "rateLimit": {"limit": 100, "used": 7, "remaining": 93, "windowSeconds": 60},
                "observationTime": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
                "observationSource": "provider_asof",
            }

    gw = MarketDataGateway(FakeBridge(), cache=MarketCache(), router=ProviderRouter())
    asyncio.run(gw.get_quote("AAPL", "US"))
    metrics = gw.provider_metrics()
    rl = metrics["rateLimits"]["yahoo"]
    assert rl["observed"]["remaining"] == 93
    assert metrics["providers"]["yahoo"]["calls"] == 1
    assert metrics["providers"]["yahoo"]["avgLatencyMs"] >= 0
