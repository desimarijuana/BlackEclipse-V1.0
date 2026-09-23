"""Phase 4 — deterministic derived-metric tests (Milestone 6).

Pure calculations only: no model, no network. Every metric is checked for a
correct value AND for the guard rails (mixed identity, duplicate dates,
insufficient observations, missing assumptions, non-finite input).
"""

from __future__ import annotations

import math

import pytest

from harness.research.calculations import (
    CalculationError,
    annualized_volatility,
    cagr,
    max_drawdown,
    period_change,
    sharpe,
)


def obs(values, *, start=1, identity="AAPL", currency="USD"):
    return [
        {"date": f"2020-01-{start + i:02d}", "value": v, "identity": identity, "currency": currency}
        for i, v in enumerate(values)
    ]


def test_period_change_basic():
    result = period_change(100.0, 120.0)
    assert result.value == pytest.approx(20.0)
    assert result.unit == "%"
    assert result.version
    assert result.formula


def test_period_change_negative_start_uses_absolute_base():
    result = period_change(-50.0, -25.0)
    assert result.value == pytest.approx(50.0)


def test_period_change_zero_start_rejected():
    with pytest.raises(CalculationError):
        period_change(0.0, 10.0)


def test_cagr_known_value():
    # 100 → 121 over 2 years = 10%.
    result = cagr(obs([100.0, 121.0]), years=2.0)
    assert result.value == pytest.approx(10.0, abs=1e-6)


def test_cagr_requires_span_or_frequency():
    with pytest.raises(CalculationError):
        cagr(obs([100.0, 121.0]))


def test_cagr_rejects_non_positive():
    with pytest.raises(CalculationError):
        cagr(obs([0.0, 121.0]), years=1.0)


def test_volatility_known_value():
    # Alternating 0% / +1% returns have a sample stdev with a known scale.
    prices = [100.0, 100.0, 101.0, 101.0, 102.02]
    result = annualized_volatility(obs(prices), frequency="daily")
    assert result.annualization == 252
    assert result.value > 0
    assert result.unit == "%"


def test_volatility_requires_known_frequency():
    with pytest.raises(CalculationError):
        annualized_volatility(obs([1.0, 2.0, 3.0]), frequency="fortnightly")


def test_max_drawdown_known_value():
    # Peak 120 → trough 60 = -50%.
    result = max_drawdown(obs([100.0, 120.0, 60.0, 90.0]))
    assert result.value == pytest.approx(-50.0)
    assert result.value <= 0


def test_max_drawdown_monotonic_up_is_zero():
    result = max_drawdown(obs([100.0, 110.0, 120.0]))
    assert result.value == pytest.approx(0.0)


def test_sharpe_requires_risk_free_rate():
    with pytest.raises(CalculationError):
        sharpe(obs([100.0, 101.0, 102.0]), risk_free_rate=None)  # type: ignore[arg-type]


def test_sharpe_zero_excess_volatility_rejected():
    # Constant 10% returns → zero volatility of excess → undefined, must reject.
    with pytest.raises(CalculationError, match="volatility is 0"):
        sharpe(obs([100.0, 110.0, 121.0]), risk_free_rate=0.0, frequency="daily")


def test_sharpe_records_assumptions_and_source():
    prices = [100.0, 101.5, 100.8, 103.0, 104.2, 103.5]
    result = sharpe(obs(prices), risk_free_rate=0.02, frequency="daily", risk_free_source="FRED:DGS1")
    assert result.riskFreeRate == 0.02
    assert result.riskFreeSource == "FRED:DGS1"
    assert any("risk-free" in a for a in result.assumptions)
    assert result.value is not None and math.isfinite(result.value)


def test_mixed_identity_rejected():
    observations = obs([100.0, 110.0], identity="AAPL") + [
        {"date": "2020-02-01", "value": 200.0, "identity": "MSFT"}
    ]
    with pytest.raises(CalculationError, match="multiple instruments"):
        period_change(observations[0]["value"], observations[-1]["value"], observations=observations)


def test_mixed_currency_rejected():
    observations = [
        {"date": "2020-01-01", "value": 100.0, "currency": "USD"},
        {"date": "2020-01-02", "value": 110.0, "currency": "EUR"},
    ]
    with pytest.raises(CalculationError, match="multiple currencies"):
        max_drawdown(observations)


def test_duplicate_dates_rejected():
    observations = [
        {"date": "2020-01-01", "value": 100.0},
        {"date": "2020-01-01", "value": 105.0},
        {"date": "2020-01-02", "value": 110.0},
    ]
    with pytest.raises(CalculationError, match="duplicate"):
        max_drawdown(observations)


def test_non_finite_value_rejected():
    observations = [
        {"date": "2020-01-01", "value": 100.0},
        {"date": "2020-01-02", "value": float("nan")},
    ]
    with pytest.raises(CalculationError, match="non-finite"):
        max_drawdown(observations)


def test_insufficient_observations_rejected():
    with pytest.raises(CalculationError, match="insufficient"):
        annualized_volatility(obs([100.0]), frequency="daily")


def test_missing_value_dropped_not_interpolated():
    observations = [
        {"date": "2020-01-01", "value": 100.0},
        {"date": "2020-01-02", "value": None},
        {"date": "2020-01-03", "value": 120.0},
    ]
    result = period_change(100.0, 120.0, observations=observations)
    assert result.observationCount == 2
    assert result.missingDataPolicy == "omit_missing_no_interpolation"
