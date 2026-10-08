"""Unit tests for portfolio accounting, position sizing and the risk engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from harness.portfolio.accounting import compute_accounting
from harness.portfolio.models import CostBasisMethod, Transaction, TransactionType
from harness.quant.models import Fill
from harness.quant.portfolio import Portfolio
from harness.quant.risk import RiskContext, RiskEngine
from harness.quant.sizing import SizingContext, compute_quantity
from harness.quant.strategy import PositionSizing, RiskRules


def _fill(symbol="X", side="buy", qty=10.0, price=100.0, idx=0, commission=0.0) -> Fill:
    from harness.quant.models import OrderSide

    return Fill(id=f"f{idx}", order_id="o", symbol=symbol, side=side, quantity=qty,
                price=price, commission=commission, slippage=0.0, spread_cost=0.0,
                impact=0.0, index=idx, ts=None, reason="")


def test_long_round_trip_pnl_and_equity_invariant():
    p = Portfolio(10_000.0)
    p.mark("X", 100.0)
    p.apply_fill(_fill(side="buy", price=100.0, idx=0))
    p.mark("X", 100.0)
    assert p.equity == pytest.approx(10_000.0)
    assert p.cash + sum(pos.market_value() for pos in p.positions.values()) == pytest.approx(p.equity)
    trade = p.apply_fill(_fill(side="sell", price=110.0, idx=5))
    assert trade is not None
    assert trade.net_pnl == pytest.approx(100.0)
    assert p.realized_pnl == pytest.approx(100.0)
    assert p.equity == pytest.approx(10_100.0)
    assert p.is_flat("X")


def test_short_round_trip_pnl():
    p = Portfolio(10_000.0, allow_short=True)
    p.apply_fill(_fill(side="sell", qty=5, price=100.0, idx=0))
    p.mark("X", 90.0)
    assert p.unrealized_pnl() == pytest.approx(50.0)
    trade = p.apply_fill(_fill(side="buy", qty=5, price=90.0, idx=1))
    assert trade is not None
    assert trade.net_pnl == pytest.approx(50.0)
    assert p.equity == pytest.approx(10_050.0)


def test_reconciles_with_portfolio_accounting_engine_long_only():
    p = Portfolio(10_000.0)
    p.apply_fill(_fill(side="buy", qty=10, price=100.0, idx=0))
    p.apply_fill(_fill(side="sell", qty=10, price=110.0, idx=5))
    txs = [
        Transaction(portfolio_id="p", transaction_type=TransactionType.BUY, symbol="X",
                    quantity=Decimal(10), price=Decimal(100), timestamp="2024-01-01T00:00:00Z"),
        Transaction(portfolio_id="p", transaction_type=TransactionType.SELL, symbol="X",
                    quantity=Decimal(10), price=Decimal(110), timestamp="2024-01-06T00:00:00Z"),
    ]
    acct = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert not acct.has_errors()
    assert float(acct.realized_pnl) == pytest.approx(p.realized_pnl)


def test_sizing_methods():
    eq = 10_000.0
    pct = compute_quantity(PositionSizing(type="percent_equity", value=50),
                           SizingContext(equity=eq, price=100.0))
    assert pct[0] == pytest.approx(50.0)
    risk = compute_quantity(PositionSizing(type="percent_risk", value=1),
                            SizingContext(equity=eq, price=100.0, stop_distance=5.0))
    assert risk[0] == pytest.approx(20.0)
    atr = compute_quantity(PositionSizing(type="atr", value=1, atr_multiplier=2),
                           SizingContext(equity=eq, price=100.0, atr=2.0))
    assert atr[0] == pytest.approx(25.0)
    fixed = compute_quantity(PositionSizing(type="fixed_quantity", value=7),
                             SizingContext(equity=eq, price=100.0))
    assert fixed[0] == pytest.approx(7.0)
    missing = compute_quantity(PositionSizing(type="percent_risk", value=1),
                               SizingContext(equity=eq, price=100.0, stop_distance=None))
    assert missing[0] is None


def test_sizing_venue_constraints():
    qty, _ = compute_quantity(PositionSizing(type="percent_equity", value=0.05, min_quantity=10),
                              SizingContext(equity=10_000.0, price=100.0))
    assert qty == 0.0  # 5 units < 10 minimum
    qty2, _ = compute_quantity(PositionSizing(type="fixed_quantity", value=250, lot_size=100,
                                              max_fraction=None),
                               SizingContext(equity=10_000.0, price=100.0))
    assert qty2 == pytest.approx(200.0)


def test_risk_engine_caps_and_rejections():
    rules = RiskRules(max_position_pct=10, max_leverage=1.0, max_open_positions=1,
                      allow_short=False, max_daily_loss_pct=2)
    risk = RiskEngine(rules)
    # Position cap: 10% of 10,000 = 1,000 → 10 units at 100.
    d = risk.evaluate(RiskContext(equity=10_000, side="buy", price=100.0,
                                  proposed_quantity=50, is_opening=True, gross_exposure=0.0))
    assert d.allowed and d.quantity == pytest.approx(10.0)
    # Short disabled.
    d2 = risk.evaluate(RiskContext(equity=10_000, side="sell", price=100.0,
                                   proposed_quantity=5, is_opening=True))
    assert d2.rejected
    # Max open positions.
    d3 = risk.evaluate(RiskContext(equity=10_000, side="buy", price=100.0,
                                   proposed_quantity=5, is_opening=True, open_positions=1))
    assert d3.rejected
    # Daily loss breaker.
    d4 = risk.evaluate(RiskContext(equity=10_000, side="buy", price=100.0,
                                   proposed_quantity=5, is_opening=True,
                                   daily_pnl=-300.0, daily_start_equity=10_000.0))
    assert d4.rejected
