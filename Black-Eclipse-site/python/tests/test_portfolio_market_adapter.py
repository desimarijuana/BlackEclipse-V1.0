"""Portfolio market reads must be bounded and concurrent.

A single slow quote used to consume the whole `portfolio_get` tool budget
(TOOL_TIMEOUT at 20 s). The agent then abandoned the portfolio tools and guessed
app routes, eventually ending the run with no answer. These tests pin the two
properties that prevent that: every gateway call has its own timeout, and a
portfolio's symbols resolve concurrently.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from harness.portfolio.market_adapter import MarketAdapter, mark_timeout_s
from portfolio_helpers import buy, make_portfolio, make_service


class HangingGateway:
    async def get_quote(self, symbol, market=None, *, freshness="any"):
        await asyncio.sleep(3600)

    async def get_fx_rate(self, *, base, quote, freshness="any"):
        await asyncio.sleep(3600)


class TrackingGateway:
    """Answers immediately, but records how many lookups overlap."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def get_quote(self, symbol, market=None, *, freshness="any"):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.15)
            return SimpleNamespace(
                price=101.5,
                timestamp="2026-11-13T00:00:00Z",
                code=None,
                message=None,
                meta=SimpleNamespace(currency="USD", provider="test"),
            )
        finally:
            self.active -= 1

    async def get_fx_rate(self, *, base, quote, freshness="any"):
        return None


def test_a_hanging_quote_is_reported_unavailable_not_waited_out(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_MARK_TIMEOUT_S", "0.05")
    assert mark_timeout_s() == 0.05

    adapter = MarketAdapter(gateway=HangingGateway(), base_currency="USD")
    mark = asyncio.run(adapter.mark("FFC"))

    assert mark.price is None
    assert mark.status.value == "UNAVAILABLE"
    assert any("timed out" in warning for warning in mark.warnings)


def test_mark_timeout_defaults_and_ignores_bad_values(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_MARK_TIMEOUT_S", raising=False)
    assert mark_timeout_s() == 8.0
    monkeypatch.setenv("PORTFOLIO_MARK_TIMEOUT_S", "not-a-number")
    assert mark_timeout_s() == 8.0


def test_portfolio_symbols_are_resolved_concurrently(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    for symbol in ("FFC", "HUBC", "MCB", "MEBL", "OGDC"):
        assert buy(svc, pid, symbol, "1", "100")["status"] == "SUCCESS"

    gateway = TrackingGateway()
    reading = asyncio.run(svc.read(pid, gateway=gateway))

    assert len(reading["positions"]) == 5
    assert gateway.max_active >= 2, "quote lookups must overlap, not run one by one"
