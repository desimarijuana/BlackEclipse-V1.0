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
