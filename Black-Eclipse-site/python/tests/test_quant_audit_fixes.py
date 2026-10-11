"""Regression tests for quantitative-correctness defects found in the audit.

Each test pins a specific, independently-verified bug so it cannot silently
return:

* look-ahead bias in volatility position sizing (future prices leaked into size);
* entry commission omitted from event-engine trade P&L;
* factor covariance built on a different sample than the factor loadings;
* too-weak shrinkage auto-intensity for expected returns;
* ragged covariance for unequal-length series;
* historical replay mis-reporting the worst period and drawdown;
* MACD signal line seeded with zeros during warm-up;
* ML research tools missing from the agent allowlist.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from harness.agents import ECLIPSE_AGENT
from harness.ml.tools import ML_TOOLS
from harness.portfolio import estimation as ES
from harness.portfolio import risk_engine as RE
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.indicators import IndicatorSpec, compute_one, ema
from harness.quant.models import Fill
from harness.quant.portfolio import Portfolio


def _fill(side="buy", qty=10.0, price=100.0, idx=0, commission=0.0) -> Fill:
    return Fill(id=f"f{idx}", order_id="o", symbol="X", side=side, quantity=qty,
                price=price, commission=commission, slippage=0.0, spread_cost=0.0,
                impact=0.0, index=idx, ts=None, reason="")


# ── look-ahead in volatility sizing ──────────────────────────────────────────

def _vol_spec():
    return S.parse_strategy({
        "strategy": {"id": "vol", "name": "Vol", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
        ],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}}},
        "position_sizing": {"type": "volatility", "value": 20.0, "lookback": 10},
    })


def _dataset(rows):
    return D.build_dataset(
        {"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


def test_volatility_sizing_is_causal():
    base = F.bull_market("TESTUSDT", n=300, seed=11)
    t0 = datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=300)
    future = F.high_volatility("TESTUSDT", n=300, seed=5, start_time=t0)

    only_base = E.run_backtest(_vol_spec(), _dataset(base), E.BacktestConfig(initial_capital=100_000))
    extended = E.run_backtest(_vol_spec(), _dataset([dict(r) for r in base] + future),
                              E.BacktestConfig(initial_capital=100_000))

    assert only_base.fills, "expected at least one entry to make the check non-vacuous"
    # The first 300 equity points must be identical: appending future bars with a
    # different volatility must not change any past decision.
    for i in range(300):
        assert only_base.equity_curve[i]["equity"] == pytest.approx(
            extended.equity_curve[i]["equity"])


# ── entry commission in trade P&L ────────────────────────────────────────────

def test_entry_commission_is_included_in_trade_pnl():
    p = Portfolio(10_000.0)
    p.mark("X", 100.0)
    p.apply_fill(_fill("buy", 10, 100.0, idx=0, commission=5.0))
    p.mark("X", 100.0)
    trade = p.apply_fill(_fill("sell", 10, 110.0, idx=5, commission=7.0))

    assert trade is not None
    assert trade.gross_pnl == pytest.approx(100.0)
    assert trade.commission == pytest.approx(12.0)          # entry 5 + exit 7
    assert trade.net_pnl == pytest.approx(88.0)
    assert p.realized_pnl == pytest.approx(88.0)
    # Cash ledger includes both commissions, so equity reconciles to the trade P&L.
    assert p.equity == pytest.approx(10_000.0 + 88.0)


def test_partial_close_keeps_original_basis():
    p = Portfolio(10_000.0)
    p.mark("X", 100.0)
    p.apply_fill(_fill("buy", 10, 100.0, idx=0, commission=0.0))
    p.mark("X", 100.0)
    p.apply_fill(_fill("sell", 4, 110.0, idx=3, commission=0.0))
    pos = p.positions["X"]
    assert pos.quantity == pytest.approx(6.0)
    assert pos.avg_entry_price == pytest.approx(100.0)       # basis preserved


# ── factor covariance alignment ──────────────────────────────────────────────

def test_factor_covariance_ignores_factors_outside_asset_window():
    rng = np.random.default_rng(1)
    assets = {"A": list(rng.normal(0, 0.01, 60)), "B": list(rng.normal(0, 0.01, 60))}
    f = list(rng.normal(0, 0.01, 100))
    f2 = list(f)
    # Perturb a factor observation that lies OUTSIDE the last-60 asset window.
    f[0], f2[0] = 5.0, -3.0
    fm1 = ES.estimate_factor_covariance(assets, {"M": f})
    fm2 = ES.estimate_factor_covariance(assets, {"M": f2})
    assert fm1["available"] and fm2["available"]
    assert fm1["observations"] == 60
    assert fm1["factorCovariance"] == fm2["factorCovariance"]
    cov = np.array(fm1["covariance"])
    assert np.allclose(cov, cov.T)


# ── shrinkage intensity ──────────────────────────────────────────────────────

def test_shrinkage_expected_return_intensity_matches_heuristic():
    series = {f"S{i}": [0.01] * 100 for i in range(10)}
    er = ES.estimate_expected_returns(series, method="shrinkage")
    assert er["available"]
    # N / T̄ = 10 / 100 = 0.1 (NOT N / (N·T̄) = 0.01).
    assert er["meta"]["shrinkage"] == pytest.approx(0.1)


# ── covariance truncation ────────────────────────────────────────────────────

def test_covariance_truncates_unequal_length_series():
    cov = ES.estimate_covariance({"A": [0.01] * 50, "B": [0.01] * 40})
    assert cov["available"]
    assert cov["observations"] == 40
    assert len(cov["covariance"]) == 2 and len(cov["covariance"][0]) == 2


# ── historical replay reporting ──────────────────────────────────────────────

def test_historical_replay_reports_period_extremes():
    res = RE.historical_replay({"A": 1.0}, {"A": [0.1, -0.2, 0.05]})
    assert res["available"]
    assert res["worstSinglePeriod"] == pytest.approx(-0.2)
    assert res["cumulativeReturn"] == pytest.approx(1.1 * 0.8 * 1.05 - 1.0)
    assert res["maxDrawdown"] == pytest.approx((1.1 * 0.8) / 1.1 - 1.0)


# ── MACD warm-up seeding ─────────────────────────────────────────────────────

def test_macd_signal_is_not_zero_seeded():
    close = np.arange(1.0, 201.0)
    ohlcv = {
        "open": close, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.full(200, 1000.0),
    }
    spec = IndicatorSpec(type="macd", params={"fast": 12, "slow": 26, "signal": 9})
    base = spec.resolved_id()
    out = compute_one(spec, ohlcv)
    macd, sig = out[base], out[f"{base}_signal"]

    first_valid = int(np.argmax(~np.isnan(macd)))
    # The signal line is the EMA of the VALID MACD segment only.
    expected = ema(macd[first_valid:], 9)
    np.testing.assert_allclose(sig[first_valid:], expected, equal_nan=True)
    first_signal = first_valid + 9 - 1
    assert sig[first_signal] > 0.0  # not pulled toward a zero warm-up seed


# ── bracket-stop ATR causality ───────────────────────────────────────────────

def test_protective_bracket_sizes_from_decision_bar(monkeypatch):
    calls: list[tuple[int, int]] = []
    original = E.BacktestEngine._make_protective

    def spy(self, binding, symbol, i, entry_side, quantity, entry_price,
            stop_distance, atr_index=None):
        calls.append((i, atr_index))
        return original(self, binding, symbol, i, entry_side, quantity, entry_price,
                        stop_distance, atr_index)

    monkeypatch.setattr(E.BacktestEngine, "_make_protective", spy)
    res = E.run_backtest(
        S.parse_strategy({
            "strategy": {"id": "atr", "name": "ATR", "version": "1.0.0"},
            "universe": {"symbols": ["TESTUSDT"]},
            "indicators": [
                {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
                {"id": "atr", "type": "atr", "params": {"period": 14}},
            ],
            "rules": {
                "entry": {"long": {"conditions": [
                    {"left": {"ref": "ema_fast"}, "op": "cross_above",
                     "right": {"ref": "ema_slow"}}]}},
                "exit": {"stop_loss": {"type": "atr", "value": 2}},
            },
            "position_sizing": {"type": "percent_equity", "value": 50},
        }),
        _dataset(F.bull_market("TESTUSDT", n=300, seed=11)),
        E.BacktestConfig(initial_capital=100_000),
    )
    assert res.fills and calls, "expected entries with an ATR bracket"
    for fill_index, atr_index in calls:
        assert atr_index is not None
        assert 0 <= atr_index < fill_index  # the DECISION bar, never the fill bar


# ── downside-deviation convention consistency ────────────────────────────────

def test_portfolio_sortino_uses_sample_downside_deviation():
    from harness.portfolio.risk import sortino

    r = [0.01, -0.02, 0.015, -0.005]
    periods = 252
    mean = sum(r) / len(r)
    dd = math.sqrt(sum(min(0.0, x) ** 2 for x in r) / (len(r) - 1))
    expected = (mean * periods) / (dd * math.sqrt(periods))
    assert sortino(r) == pytest.approx(expected)


# ── ML tool allowlist ────────────────────────────────────────────────────────

def test_ml_tools_are_allowlisted_for_eclipse_agent():
    assert set(ML_TOOLS).issubset(set(ECLIPSE_AGENT.tools or []))
