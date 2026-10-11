"""Tests for options analytics and futures continuous-contract construction."""

from __future__ import annotations

import pytest

from harness.quant.futures import FuturesError, splice_continuous
from harness.quant.options import (
    OptionError,
    analyze_option_strategy,
    implied_volatility,
    price_option,
)


# ── Option pricing / Greeks ──────────────────────────────────────────────────

def test_black_scholes_reference_values():
    call = price_option(option_type="call", spot=100, strike=100, time_to_expiry=1.0,
                        iv=0.2, risk_free=0.05)
    put = price_option(option_type="put", spot=100, strike=100, time_to_expiry=1.0,
                       iv=0.2, risk_free=0.05)
    assert call["price"] == pytest.approx(10.4506, abs=1e-3)
    assert put["price"] == pytest.approx(5.5735, abs=1e-3)
    assert call["delta"] == pytest.approx(0.6368, abs=1e-3)
    assert call["gamma"] == pytest.approx(0.018762, abs=1e-5)


def test_price_option_rejects_bad_type():
    with pytest.raises(OptionError):
        price_option(option_type="banana", spot=100, strike=100, time_to_expiry=1, iv=0.2)


def test_price_option_unavailable_on_zero_time():
    out = price_option(option_type="call", spot=100, strike=100, time_to_expiry=0.0, iv=0.2)
    assert out["available"] is False


# ── Implied volatility ───────────────────────────────────────────────────────

def test_implied_volatility_round_trip():
    price = price_option(option_type="call", spot=100, strike=105, time_to_expiry=0.5,
                         iv=0.35, risk_free=0.03)["price"]
    iv = implied_volatility(price, option_type="call", spot=100, strike=105,
                            time_to_expiry=0.5, risk_free=0.03)
    assert iv["available"] is True
    assert iv["impliedVolatility"] == pytest.approx(0.35, abs=1e-3)


def test_implied_volatility_rejects_out_of_bounds():
    out = implied_volatility(1000.0, option_type="call", spot=100, strike=100, time_to_expiry=1)
    assert out["available"] is False and "bounds" in out["reason"]


# ── Strategy analytics ───────────────────────────────────────────────────────

def test_long_call_payoff_unbounded_profit():
    out = analyze_option_strategy(
        [{"type": "call", "strike": 100, "quantity": 1, "premium": 5, "multiplier": 100}],
        spot_min=50, spot_max=200)
    assert out["bounded"] is False
    assert out["maxProfit"] is None            # unbounded above
    assert out["maxLoss"] == pytest.approx(-500)   # premium paid
    assert out["breakEvens"] == [pytest.approx(105.0)]


def test_bull_call_spread_is_bounded():
    out = analyze_option_strategy([
        {"type": "call", "strike": 100, "quantity": 1, "premium": 5},
        {"type": "call", "strike": 110, "quantity": -1, "premium": 2},
    ], spot_min=80, spot_max=140)
    assert out["bounded"] is True
    # debit = (5-2)*100 = 300; width 10*100 = 1000 -> max profit 700, max loss -300
    assert out["maxProfit"] == pytest.approx(700)
    assert out["maxLoss"] == pytest.approx(-300)
    assert out["breakEvens"] == [pytest.approx(103.0)]


def test_short_straddle_bounded_profit_unbounded_loss():
    out = analyze_option_strategy([
        {"type": "call", "strike": 100, "quantity": -1, "premium": 5},
        {"type": "put", "strike": 100, "quantity": -1, "premium": 4},
    ], spot_min=50, spot_max=150)
    assert out["bounded"] is False
    assert out["maxProfit"] == pytest.approx(900)   # credit received
    assert out["maxLoss"] is None                    # unbounded below


def test_strategy_net_greeks_when_valued():
    out = analyze_option_strategy(
        [{"type": "call", "strike": 100, "quantity": 1, "premium": 5}],
        spot_min=50, spot_max=200, valuation_spot=100, time_to_expiry=0.5, iv=0.2)
    assert "netGreeks" in out
    # position Greeks scale by the contract multiplier (default 100)
    assert out["netGreeks"]["delta"] == pytest.approx(58.4, abs=1.0)


def test_strategy_rejects_bad_leg():
    with pytest.raises(OptionError):
        analyze_option_strategy([{"type": "call", "strike": 0, "quantity": 1, "premium": 5}],
                                spot_min=50, spot_max=150)


# ── Futures continuous contracts ─────────────────────────────────────────────

def _contract(symbol, pairs):
    return {"symbol": symbol, "rows": [
        {"timestamp": ts, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10}
        for ts, c in pairs]}


def test_splice_difference_is_continuous_and_newest_unadjusted():
    a = _contract("A", [("t0", 10), ("t1", 11), ("t2", 12)])
    b = _contract("B", [("t3", 20), ("t4", 21), ("t5", 22)])
    out = splice_continuous([a, b], ["t3"], adjustment="difference")
    closes = [bar["close"] for bar in out["bars"]]
    assert closes == pytest.approx([18, 19, 20, 20, 21, 22])
    assert out["bars"][-1]["close"] == 22            # newest unadjusted
    assert out["rolls"][0]["gap"] == pytest.approx(8)


def test_splice_ratio_and_none():
    a = _contract("A", [("t0", 10), ("t1", 12)])
    b = _contract("B", [("t2", 24), ("t3", 25)])
    ratio = splice_continuous([a, b], ["t2"], adjustment="ratio")
    assert [bar["close"] for bar in ratio["bars"]] == pytest.approx([20, 24, 24, 25])
    raw = splice_continuous([a, b], ["t2"], adjustment="none")
    assert [bar["close"] for bar in raw["bars"]] == pytest.approx([10, 12, 24, 25])


def test_splice_validates_roll_schedule():
    a = _contract("A", [("t0", 10)])
    b = _contract("B", [("t1", 20)])
    with pytest.raises(FuturesError):
        splice_continuous([a, b], [], adjustment="difference")  # missing a roll date
    with pytest.raises(FuturesError):
        splice_continuous([a], ["t9"], adjustment="bogus")  # unknown adjustment
