"""Portfolio-faced condition facts — the engine's second fact provider.

A `pf.<id>.<field>` condition must resolve to a real, ledger-grounded number, and
a failed read must yield NO fact (honest UNAVAILABLE), never a fabricated value.
"""

from __future__ import annotations

import asyncio

from harness.automation.facts import (
    CompositeFactProvider,
    PortfolioFactProvider,
    StaticFactProvider,
)

READING = {
    "portfolio": {"baseCurrency": "USD"},
    "positions": [
        {"symbol": "AAPL", "weight": 60.0, "unrealizedPnlBase": "-1500.00",
         "quantity": "10", "currency": "USD"},
        {"symbol": "MSFT", "weight": 40.0, "unrealizedPnlBase": "500.00",
         "quantity": "5", "currency": "USD"},
    ],
    "valuation": {"totalValue": "100000.00"},
    "cash": {"balance": "10000.00"},
}


class _Portfolio:
    def __init__(self, reading):
        self._reading = reading
        self.calls = 0

    async def read(self, portfolio_id, **kwargs):
        self.calls += 1
        if self._reading is None:
            raise RuntimeError("portfolio unavailable")
        return self._reading


class _Service:
    def __init__(self, reading=READING):
        self.portfolio = _Portfolio(reading) if reading is not None else None
        self.market_gateway = None


def _snapshot(provider, variables):
    return asyncio.run(provider.snapshot(variables))


def test_portfolio_facts_resolve_from_the_ledger():
    provider = PortfolioFactProvider(_Service())
    facts = _snapshot(provider, [
        "pf.pf_1.weight.AAPL",
        "pf.pf_1.unrealized.AAPL",
        "pf.pf_1.cash_pct",
        "pf.pf_1.concentration_hhi",
        "pf.pf_1.position_count",
        "pf.pf_1.total_value",
    ])
    assert facts["pf.pf_1.weight.AAPL"] == 0.6
    assert facts["pf.pf_1.unrealized.AAPL"] == -1500.0
    assert abs(facts["pf.pf_1.cash_pct"] - 0.1) < 1e-9
    assert abs(facts["pf.pf_1.concentration_hhi"] - 0.52) < 1e-9
    assert facts["pf.pf_1.position_count"] == 2
    assert facts["pf.pf_1.total_value"] == 100000.0


def test_unknown_field_yields_no_fact():
    facts = _snapshot(PortfolioFactProvider(_Service()), ["pf.pf_1.nonsense"])
    assert facts == {}


def test_missing_portfolio_layer_yields_no_facts():
    assert _snapshot(PortfolioFactProvider(_Service(reading=None)), ["pf.pf_1.weight.AAPL"]) == {}


def test_a_failed_read_yields_no_facts():
    class _Broken(_Service):
        pass

    service = _Broken()
    service.portfolio = _Portfolio(None)  # read() raises
    assert _snapshot(PortfolioFactProvider(service), ["pf.pf_1.weight.AAPL"]) == {}


def test_composite_prefers_the_first_resolving_provider():
    market = StaticFactProvider({"BTC.price": 90000})
    portfolio = PortfolioFactProvider(_Service())
    composite = CompositeFactProvider([market, portfolio])
    facts = _snapshot(composite, ["BTC.price", "pf.pf_1.weight.AAPL", "UNKNOWN.x"])
    assert facts["BTC.price"] == 90000
    assert facts["pf.pf_1.weight.AAPL"] == 0.6
    assert "UNKNOWN.x" not in facts


def test_composite_skips_a_provider_that_raises():
    class _Exploding:
        async def snapshot(self, variables):
            raise RuntimeError("boom")

    composite = CompositeFactProvider([_Exploding(), StaticFactProvider({"x.y": 1})])
    assert _snapshot(composite, ["x.y"]) == {"x.y": 1}
