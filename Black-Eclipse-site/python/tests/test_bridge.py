"""Data bridge: per-class timeouts stay inside tool budgets; retry only on ConnectError."""

from __future__ import annotations

import httpx
import pytest

from harness.bridge import HttpDataBridge
from harness.finance_tools import register_finance_tools
from harness.tools import ToolRegistry


def test_timeout_classes_stay_inside_the_tool_budgets_they_serve():
    registry = ToolRegistry()
    register_finance_tools(registry)
    # The structured/vault class must fail before the smallest market-tool
    # budget (get_market_snapshot = 10s) so the tool reports UNAVAILABLE, never
    # TOOL_TIMEOUT.
    assert HttpDataBridge._TIMEOUT_S * 1000 < registry.get("get_market_snapshot").timeout_ms
    # The network class serves the research tools, whose budget is 30s.
    assert HttpDataBridge._NETWORK_TIMEOUT_S * 1000 < 30_000
    # Slow-class membership is explicit, not prefix magic.
    assert "web_fetch" in HttpDataBridge._NETWORK_CAPABILITIES
    assert "market_snapshot" not in HttpDataBridge._NETWORK_CAPABILITIES


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"status": "OK"}


class _FakeClient:
    def __init__(self, factory: "_ClientFactory") -> None:
        self.factory = factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.factory.calls += 1
        if self.factory.error is not None:
            raise self.factory.error
        if self.factory.calls <= self.factory.failures:
            raise httpx.ConnectError("connection refused")
        return _FakeResponse()


class _ClientFactory:
    def __init__(self, *, failures: int = 0, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeClient(self)


@pytest.mark.asyncio
async def test_retries_once_on_connect_error(monkeypatch):
    factory = _ClientFactory(failures=1)
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    bridge = HttpDataBridge("http://127.0.0.1:3000", None)
    out = await bridge.fetch("market_snapshot", {"symbol": "AAPL"})
    assert out == {"status": "OK"}
    assert factory.calls == 2  # first refused, retried, succeeded


@pytest.mark.asyncio
async def test_persistent_connect_error_is_unavailable_without_a_loop(monkeypatch):
    factory = _ClientFactory(failures=5)
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    bridge = HttpDataBridge("http://127.0.0.1:3000", None)
    out = await bridge.fetch("market_snapshot", {"symbol": "AAPL"})
    assert out["status"] == "UNAVAILABLE"
    assert factory.calls == 2  # exactly one retry


@pytest.mark.asyncio
async def test_a_timeout_is_never_retried(monkeypatch):
    # A timeout already consumed the per-class budget; a retry would double the
    # wait past the caller's tool budget.
    factory = _ClientFactory(error=httpx.ReadTimeout("slow"))
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    bridge = HttpDataBridge("http://127.0.0.1:3000", None)
    out = await bridge.fetch("web_fetch", {"url": "https://example.com"})
    assert out["status"] == "UNAVAILABLE"
    assert factory.calls == 1


@pytest.mark.asyncio
async def test_price_history_serves_the_last_good_read_on_timeout(monkeypatch):
    """A slow series read falls back to the cached one, marked STALE."""
    calls = {"n": 0}
    payload = {
        "status": "OK", "symbol": "MSFT", "series": [{"close": 1.0}],
        "retrievedAt": "2026-11-17T00:00:00Z",
    }

    class _Resp:
        status_code = 200

        def json(self):
            return payload

    class _Client:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):  # noqa: ANN002, ANN003
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp()
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    bridge = HttpDataBridge("http://127.0.0.1:3000", None)
    first = await bridge.fetch("price_history", {"symbol": "MSFT"})
    assert first["status"] == "OK"
    second = await bridge.fetch("price_history", {"symbol": "MSFT"})
    assert second["status"] == "STALE"
    assert second["stale"] is True and second["cached"] is True
    assert second["series"] == payload["series"]
    # A different query never borrows another symbol's series.
    third = await bridge.fetch("price_history", {"symbol": "AAPL"})
    assert third["status"] == "UNAVAILABLE"


# --- the live lane's preflight -------------------------------------------
from harness.evaluation import live_gate  # noqa: E402


@pytest.mark.asyncio
async def test_a_dead_bridge_is_a_reason_not_a_score(monkeypatch):
    class Dead:
        async def fetch(self, capability, params):
            return {"status": "UNAVAILABLE", "error": "ConnectError: refused"}

    monkeypatch.setattr("harness.bridge.HttpDataBridge", lambda *a, **k: Dead())
    reason = await live_gate.preflight_bridge()
    assert "answered UNAVAILABLE" in reason and "npm run up" in reason


@pytest.mark.asyncio
async def test_a_healthy_bridge_has_no_reason(monkeypatch):
    class Healthy:
        async def fetch(self, capability, params):
            return {"status": "OK"}

    monkeypatch.setattr("harness.bridge.HttpDataBridge", lambda *a, **k: Healthy())
    assert await live_gate.preflight_bridge() == ""
