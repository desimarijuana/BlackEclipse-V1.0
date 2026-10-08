"""Crypto: swap, bridge, staking rewards and custody events."""

from __future__ import annotations

from decimal import Decimal

from portfolio_helpers import buy, make_portfolio, make_service


def _lots(svc, pid):
    out = svc.calculate_tax_lots(pid, persist=True)
    return {s["symbol"]: s for s in out["symbols"]}


def test_swap_disposes_and_acquires_at_fmv(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "BTC", "1", "30000")
    out = svc.apply_swap(pid, {
        "from_symbol": "BTC", "to_symbol": "ETH", "from_quantity": "1",
        "from_price": "40000", "to_price": "2000",
    })
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["BTC"]["remainingQuantity"]) == Decimal("0")
    # realized 40000 - 30000 = 10000
    assert Decimal(lots["BTC"]["realizedPnl"]) == Decimal("10000")
    assert Decimal(lots["ETH"]["remainingQuantity"]) == Decimal("20")
    assert Decimal(lots["ETH"]["remainingCostBasis"]) == Decimal("40000")


def test_bridge_carries_basis_without_gain(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "USDC", "1000", "1")
    out = svc.apply_bridge(pid, {"from_symbol": "USDC", "to_symbol": "USDC.E", "quantity": "1000"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["USDC"]["remainingQuantity"]) == Decimal("0")
    assert Decimal(lots["USDC"]["realizedPnl"]) == Decimal("0")
    assert Decimal(lots["USDC.E"]["remainingQuantity"]) == Decimal("1000")
    assert Decimal(lots["USDC.E"]["remainingCostBasis"]) == Decimal("1000")


def test_staking_reward_is_an_acquisition_at_fmv(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.record_reward(pid, {"type": "STAKING_REWARD", "symbol": "SOL", "quantity": "5", "price": "10"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["SOL"]["remainingQuantity"]) == Decimal("5")
    assert Decimal(lots["SOL"]["remainingCostBasis"]) == Decimal("50")


def test_airdrop_is_an_acquisition(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.record_reward(pid, {"type": "AIRDROP", "symbol": "XYZ", "quantity": "100", "price": "0.5"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["XYZ"]["remainingCostBasis"]) == Decimal("50")


def test_staking_custody_does_not_change_position(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "SOL", "10", "20")
    before = _lots(svc, pid)
    out = svc.apply_staking(pid, {"action": "stake", "symbol": "SOL", "quantity": "10"})
    assert out["status"] == "SUCCESS"
    after = _lots(svc, pid)
    assert after["SOL"]["remainingQuantity"] == before["SOL"]["remainingQuantity"]
    assert after["SOL"]["remainingCostBasis"] == before["SOL"]["remainingCostBasis"]
    # the custody event is still recorded and auditable
    types = [t.transaction_type.value for t in svc.store.list_transactions(pid)]
    assert "STAKE" in types
