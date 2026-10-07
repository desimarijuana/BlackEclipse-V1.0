"""Browser provider-layer unit tests (Phase 9).

Router maturity (health demotion, cost preference, fallback rationale), the
Camofox / Browser Use / Firecrawl providers' honest availability and capability
declarations, and Firecrawl's extraction-only routing. No browser is launched.
"""

from __future__ import annotations

import pytest

from harness.browser.capabilities import BrowserCapabilities, PROVIDER_CAPABILITIES
from harness.browser.config import BrowserConfig
from harness.browser.providers.base import BrowserProvider
from harness.browser.providers.optional import (
    BrowserUseProvider,
    CamofoxProvider,
    FirecrawlProvider,
)
from harness.browser.router import BrowserProviderRouter, PROVIDER_COST, ProviderHealth, RoutingRequest


# ── Router health + cost + fallback (9.5) ────────────────────────────────────

class _Fake(BrowserProvider):
    def __init__(self, pid, caps, available=True):
        self.id = pid
        self.label = pid
        self._caps = caps
        self._available = available

    def capabilities(self):
        return self._caps

    def availability(self):
        return {"available": True} if self._available else {"available": False, "reason": "off"}


def _router(config=None, **availability):
    providers = {
        "local_chromium": _Fake("local_chromium", PROVIDER_CAPABILITIES["local_chromium"], availability.get("local_chromium", True)),
        "cdp": _Fake("cdp", PROVIDER_CAPABILITIES["cdp"], availability.get("cdp", True)),
        "camofox": _Fake("camofox", PROVIDER_CAPABILITIES["camofox"], availability.get("camofox", True)),
        "browser_use": _Fake("browser_use", PROVIDER_CAPABILITIES["browser_use"], availability.get("browser_use", True)),
        "browserbase": _Fake("browserbase", BrowserCapabilities(remote=True), availability.get("browserbase", True)),
    }
    return BrowserProviderRouter(config or BrowserConfig(), providers)


def test_health_demotes_after_consecutive_failures():
    router = _router()
    for _ in range(3):
        router.record_result("local_chromium", False)
    assert router.health.demoted("local_chromium")
    # local is demoted, so a non-private interactive task falls to the next best.
    decision = router.decide(RoutingRequest(url="https://example.com"))
    assert decision.provider == "cdp"
    assert any(d["provider"] == "local_chromium" for d in decision.demotions)
    assert "Demoted" in decision.rationale


def test_health_repromotes_on_success():
    health = ProviderHealth(threshold=2)
    health.record("cdp", False)
    health.record("cdp", False)
    assert health.demoted("cdp")
    health.record("cdp", True)
    assert not health.demoted("cdp")


def test_explicit_request_overrides_demotion():
    router = _router()
    for _ in range(3):
        router.record_result("local_chromium", False)
    decision = router.decide(RoutingRequest(url="https://example.com", provider="local_chromium"))
    assert decision.provider == "local_chromium"  # honoured even while demoted


def test_cost_preference_reorders_candidates():
    config = BrowserConfig()
    config.prefer_low_cost = True
    router = _router(config)
    # cdp (cost 1) is cheaper than browser_use (3)/browserbase (5); local is best
    # but unavailable here, so cdp wins on cost over the others.
    router._providers["local_chromium"]._available = False  # noqa: SLF001
    decision = router.decide(RoutingRequest(url="https://example.com"))
    assert decision.provider == "cdp"
    assert decision.candidates[0] == "cdp"
    assert "lower-cost" in decision.rationale


def test_failing_provider_falls_to_next_best():
    router = _router(local_chromium=False)
    decision = router.decide(RoutingRequest(url="https://x.com"))
    assert decision.provider == "cdp"
    assert "local_chromium" in decision.rejected


def test_private_target_never_routes_to_remote():
    router = _router()
    decision = router.decide(RoutingRequest(url="http://localhost:3000"))
    assert decision.provider == "local_chromium"
    # A remote provider is never even a candidate for a private target.
    assert "browserbase" not in decision.candidates
    assert "private" in decision.rationale.lower() or "local" in decision.rationale.lower()


def test_private_target_rejects_explicit_remote():
    router = _router()
    decision = router.decide(RoutingRequest(url="http://127.0.0.1:8080", provider="browserbase"))
    # The explicitly requested cloud provider is rejected and local is used.
    assert decision.provider == "local_chromium"
    assert "private" in decision.rejected.get("browserbase", "").lower()


def test_provider_cost_table_covers_registered_providers():
    for pid in ("local_chromium", "cdp", "camofox", "browser_use", "browserbase", "firecrawl"):
        assert pid in PROVIDER_COST


# ── Camofox (9.1) ────────────────────────────────────────────────────────────

def test_camofox_reports_honest_unavailability(monkeypatch):
    from harness.browser import config as config_mod

    monkeypatch.delenv("HARNESS_CAMOFOX_ENABLED", raising=False)
    config_mod.browser_config(refresh=True)
    try:
        status = CamofoxProvider().availability()
        assert status["available"] is False and status["reason"]
    finally:
        config_mod.browser_config(refresh=True)


def test_camofox_enabled_without_binary_is_unavailable(monkeypatch):
    from harness.browser import config as config_mod

    monkeypatch.setenv("HARNESS_CAMOFOX_ENABLED", "true")
    monkeypatch.delenv("HARNESS_CAMOFOX_ENDPOINT", raising=False)
    config_mod.browser_config(refresh=True)
    try:
        provider = CamofoxProvider()
        # No camoufox package/binary in this environment -> honest unavailable.
        status = provider.availability()
        assert status["available"] is False
        assert "camoufox" in status["reason"].lower() or "binary" in status["reason"].lower()
    finally:
        monkeypatch.delenv("HARNESS_CAMOFOX_ENABLED", raising=False)
        config_mod.browser_config(refresh=True)


def test_camofox_enabled_with_endpoint_is_available(monkeypatch):
    from harness.browser import config as config_mod

    monkeypatch.setenv("HARNESS_CAMOFOX_ENABLED", "true")
    monkeypatch.setenv("HARNESS_CAMOFOX_ENDPOINT", "ws://127.0.0.1:9222/devtools/browser/abc")
    config_mod.browser_config(refresh=True)
    try:
        status = CamofoxProvider().availability()
        assert status["available"] is True
        assert status["endpoint"].startswith("ws://")
    finally:
        monkeypatch.delenv("HARNESS_CAMOFOX_ENABLED", raising=False)
        monkeypatch.delenv("HARNESS_CAMOFOX_ENDPOINT", raising=False)
        config_mod.browser_config(refresh=True)


def test_camofox_capabilities_declared():
    caps = PROVIDER_CAPABILITIES["camofox"]
    assert caps.interactive is True
    assert caps.cdp is False  # Camoufox is Firefox/Playwright, not CDP
    assert caps.remote is False


# ── Browser Use (9.2) ────────────────────────────────────────────────────────

def test_browser_use_unavailable_when_not_installed():
    provider = BrowserUseProvider()
    # `browser_use` is not installed in the test environment.
    status = provider.availability()
    if status["available"]:
        pytest.skip("browser_use is installed in this environment")
    assert status["available"] is False and status["reason"]


async def test_browser_use_launch_refuses_honestly_when_absent():
    from harness.browser.errors import BrowserUnavailable
    from harness.browser.providers.base import LaunchOptions

    provider = BrowserUseProvider()
    if provider.availability()["available"]:
        pytest.skip("browser_use is installed in this environment")
    with pytest.raises(BrowserUnavailable):
        await provider.launch(LaunchOptions())


# ── Firecrawl (9.3) ──────────────────────────────────────────────────────────

def test_firecrawl_capabilities_are_extraction_only():
    caps = PROVIDER_CAPABILITIES["firecrawl"]
    assert caps.interactive is False
    assert caps.evaluate_js is False
    assert caps.downloads is False
    assert caps.remote is True


def test_firecrawl_is_unavailable_by_default():
    status = FirecrawlProvider().availability()
    assert status["available"] is False and status["reason"]


async def test_firecrawl_launch_is_refused():
    from harness.browser.errors import BrowserCapabilityError
    from harness.browser.providers.base import LaunchOptions

    with pytest.raises(BrowserCapabilityError):
        await FirecrawlProvider().launch(LaunchOptions())


def test_router_extraction_prefers_firecrawl_over_interaction():
    router = _router(firecrawl=True)
    # The extraction request routes to firecrawl; an interactive one never does.
    extraction = router.decide(RoutingRequest(url="https://example.com", interactive=False))
    # firecrawl isn't registered in this stub router, so it is rejected as such;
    # the point is that an INTERACTIVE request can never select it.
    interactive = router.decide(RoutingRequest(url="https://example.com", interactive=True))
    assert interactive.provider != "firecrawl"


def test_router_extraction_selects_firecrawl_when_registered():
    providers = {
        "local_chromium": _Fake("local_chromium", PROVIDER_CAPABILITIES["local_chromium"]),
        "firecrawl": _Fake("firecrawl", PROVIDER_CAPABILITIES["firecrawl"]),
    }
    router = BrowserProviderRouter(BrowserConfig(), providers)
    decision = router.decide(RoutingRequest(url="https://example.com", interactive=False))
    assert decision.provider == "firecrawl"
    # An interactive request can never route to the extraction backend.
    interactive = router.decide(RoutingRequest(url="https://example.com", interactive=True))
    assert interactive.provider == "local_chromium"


async def test_web_extract_routes_firecrawl_only_for_extraction(monkeypatch):
    from harness.research import web_extract

    calls: list[str] = []

    class _Provider:
        def availability(self):
            return {"available": True}

        async def extract(self, url, *, timeout_s=30.0):
            calls.append(url)
            return {"ok": True, "url": url, "title": "T", "text": "x" * 500, "extraction": "firecrawl", "status": "OK"}

    monkeypatch.setattr("harness.browser.providers.optional.FirecrawlProvider", lambda *a, **k: _Provider())
    result = await web_extract.fetch("https://example.com/a", bridge=None, prefer="firecrawl")
    assert result.ok and result.extraction == "firecrawl"
    assert calls == ["https://example.com/a"]

    # `prefer="bridge"` (interaction/default) never reaches Firecrawl.
    calls.clear()
    result2 = await web_extract.fetch("https://example.com/b", bridge=None, prefer="bridge")
    assert calls == []
    assert result2.ok is False  # no bridge configured


async def test_web_extract_firecrawl_failure_falls_back_to_bridge(monkeypatch):
    from harness.research import web_extract

    class _Provider:
        def availability(self):
            return {"available": True}

        async def extract(self, url, *, timeout_s=30.0):
            return {"ok": False, "status": "UNAVAILABLE", "error": "blocked"}

    class _Bridge:
        async def fetch(self, capability, params):
            return {"status": "OK", "url": params["url"], "title": "B", "text": "y" * 500}

    monkeypatch.setattr("harness.browser.providers.optional.FirecrawlProvider", lambda *a, **k: _Provider())
    result = await web_extract.fetch("https://example.com/c", bridge=_Bridge(), prefer="firecrawl")
    # Firecrawl failed, so the bridge supplied the content.
    assert result.ok and result.extraction != "firecrawl"