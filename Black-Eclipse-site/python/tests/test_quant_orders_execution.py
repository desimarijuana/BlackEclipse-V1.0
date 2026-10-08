"""Unit tests for the order state machine and the execution cost simulator."""

from __future__ import annotations

import pytest

from harness.quant.execution import BarContext, ExecutionSimulator
from harness.quant.errors import IllegalOrderTransition, InvalidOrder
from harness.quant.models import transition_allowed
from harness.quant.orders import OrderEngine
from harness.quant.strategy import (
    CommissionModel,
    ExecutionAssumptions,
    MarketImpactModel,
    SlippageModel,
    SpreadModel,
)


def _bar(index=1, o=100.0, h=105.0, l=95.0, c=102.0, v=1000.0) -> BarContext:
    return BarContext(symbol="X", index=index, ts="2024-01-01", open=o, high=h, low=l,
                      close=c, volume=v)


def test_order_validation():
    oe = OrderEngine()
    with pytest.raises(InvalidOrder):
        oe.create("X", "buy", "market", 0)
    with pytest.raises(InvalidOrder):
        oe.create("X", "buy", "limit", 1)  # no limit price
    with pytest.raises(InvalidOrder):
        oe.create("X", "buy", "stop", 1)  # no stop price
    with pytest.raises(InvalidOrder):
        oe.create("X", "buy", "trailing_stop", 1)  # no trail


def test_order_state_machine_and_partial_fill():
    oe = OrderEngine()
    o = oe.create("X", "buy", "market", 10, index=0)
    oe.submit(o, 0)
    oe.accept(o, 0)
    oe.apply_fill(o, 4, 100.0, 0.1)
    assert o.status == "partially_filled"
    oe.apply_fill(o, 6, 110.0, 0.2)
    assert o.status == "filled"
    assert o.filled_quantity == pytest.approx(10.0)
    assert o.avg_fill_price == pytest.approx((4 * 100 + 6 * 110) / 10)
    # Terminal: a further transition is illegal.
    with pytest.raises(IllegalOrderTransition):
        oe.cancel(o, 1)
    with pytest.raises(IllegalOrderTransition):
        oe.apply_fill(o, 1, 100.0, 0.0)


def test_transition_graph():
    assert transition_allowed("created", "rejected")
    assert not transition_allowed("filled", "cancelled")
    assert not transition_allowed("cancelled", "submitted")


def test_commission_models():
    pct = ExecutionSimulator(ExecutionAssumptions(commission=CommissionModel(type="percentage", value=0.1)))
    assert pct.commission(10, 100) == pytest.approx(1.0)
    per_share = ExecutionSimulator(ExecutionAssumptions(commission=CommissionModel(type="per_share", value=0.005)))
    assert per_share.commission(10, 100) == pytest.approx(0.05)
    fixed = ExecutionSimulator(ExecutionAssumptions(commission=CommissionModel(type="fixed", value=5, minimum=7)))
    assert fixed.commission(10, 100) == pytest.approx(7.0)
    tiered = ExecutionSimulator(ExecutionAssumptions(commission=CommissionModel(
        type="tiered", tiers=[{"upTo": 1000, "rate": 0.1}, {"upTo": 1e12, "rate": 0.05}])))
    assert tiered.commission(20, 100) == pytest.approx(1.5)


def test_spread_and_slippage_adverse():
    sim = ExecutionSimulator(ExecutionAssumptions(
        spread=SpreadModel(type="bps", value=10), slippage=SlippageModel(type="percentage", value=0.1)))
    oe = OrderEngine()
    o = oe.create("X", "buy", "market", 1, index=0)
    oe.submit(o, 0)
    fill = sim.try_fill(o, _bar(o=100.0), current_index=1)
    assert fill is not None
    # buy pays MORE: 100 + half-spread(0.05) + slippage(0.1) = 100.15
    assert fill.price == pytest.approx(100.15)
    assert fill.spread_cost == pytest.approx(0.05)


def test_market_order_fills_next_bar_only():
    sim = ExecutionSimulator(ExecutionAssumptions())
    oe = OrderEngine()
    o = oe.create("X", "buy", "market", 1, index=0)
    oe.submit(o, 0)
    assert sim.try_fill(o, _bar(index=0), current_index=0) is None  # same bar
    fill = sim.try_fill(o, _bar(index=1, o=101.0), current_index=1)
    assert fill is not None and fill.price == pytest.approx(101.0)


def test_limit_requires_crossing():
    sim = ExecutionSimulator(ExecutionAssumptions())
    oe = OrderEngine()
    o = oe.create("X", "buy", "limit", 1, index=0, limit_price=99.0)
    oe.submit(o, 0)
    assert sim.try_fill(o, _bar(index=1, l=100.0), current_index=1) is None  # not crossed
    fill = sim.try_fill(o, _bar(index=2, o=100.0, l=98.0), current_index=2)
    assert fill is not None and fill.price == pytest.approx(99.0)


def test_stop_triggers_adverse():
    sim = ExecutionSimulator(ExecutionAssumptions())
    oe = OrderEngine()
    sell = oe.create("X", "sell", "stop_loss", 1, index=0, stop_price=95.0)
    oe.submit(sell, 0)
    assert sim.try_fill(sell, _bar(index=1, l=96.0), current_index=1) is None
    fill = sim.try_fill(sell, _bar(index=2, o=94.0, l=93.0), current_index=2)
    assert fill is not None and fill.price == pytest.approx(94.0)


def test_randomized_slippage_is_seeded():
    a = ExecutionSimulator(ExecutionAssumptions(slippage=SlippageModel(type="randomized", value=0.5, seed=7)))
    b = ExecutionSimulator(ExecutionAssumptions(slippage=SlippageModel(type="randomized", value=0.5, seed=7)))
    c = ExecutionSimulator(ExecutionAssumptions(slippage=SlippageModel(type="randomized", value=0.5, seed=8)))
    va = [a.slippage_adjustment(100, 1, _bar()) for _ in range(3)]
    vbs = [b.slippage_adjustment(100, 1, _bar()) for _ in range(3)]
    vcs = [c.slippage_adjustment(100, 1, _bar()) for _ in range(5)]
    assert va == pytest.approx(vbs)
    assert any(abs(x - y) > 1e-12 for x in va for y in vcs)
