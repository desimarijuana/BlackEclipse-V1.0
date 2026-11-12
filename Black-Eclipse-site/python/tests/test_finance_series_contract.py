"""Contract tests for the deterministic time-series adapter.

These pin the price-vs-returns contract and the exact audit vectors. The
calculators operate on a LEVEL path; a returns input is compounded once, so the
recovered returns are the caller's returns. Regression: before the contract,
`finance_series` differenced return inputs a second time and reported a Sharpe of
-17.11 for a series whose true Sharpe is +1.72.
"""

from __future__ import annotations

import pytest

from harness.research.calculations import CalculationError
from harness.research.web_finance import compute_series


MONTHLY = [0.02, -0.01, 0.03, 0.015, -0.02, 0.01, 0.025, -0.005, 0.02, 0.005, -0.015, 0.03]
DAILY = [-0.012, 0.008, -0.021, 0.004, 0.011, -0.006, -0.030, 0.015, 0.002, -0.009,
         0.017, -0.004, -0.014, 0.006, 0.001, -0.025, 0.009, -0.003, 0.012, -0.007]


def observations(values):
    return [{"date": f"2026-01-{i + 1:02d}", "value": v} for i, v in enumerate(values)]


def series(metric, values, *, input_kind="returns", frequency="monthly", **options):
    return compute_series(
        metric,
        observations(values),
        options={"input": input_kind, "frequency": frequency, **options},
    )


def test_sharpe_on_returns_is_not_double_differenced():
    result = series("sharpe", MONTHLY, risk_free_rate=0.0)
    assert result["inputKind"] == "returns"
    assert result["value"] == pytest.approx(1.7224901965, rel=1e-9)
    assert result["unit"] is None  # a ratio


def test_sortino_on_returns_matches_the_independent_value():
    result = series("sortino", MONTHLY, risk_free_rate=0.0)
    assert result["value"] == pytest.approx(3.6708309686, rel=1e-9)


def test_drawdown_on_returns_is_the_compounded_equity_drawdown():
    result = series("max_drawdown", MONTHLY)
    assert result["unit"] == "%"
    assert result["value"] == pytest.approx(-2.0, abs=1e-9)


def test_annualized_volatility_on_returns():
    result = series("annualized_volatility", MONTHLY)
    assert result["value"] == pytest.approx(6.0958256954, rel=1e-6)


def test_cagr_on_returns_uses_the_compounded_path():
    result = series("cagr", MONTHLY, frequency="monthly", years=1.0)
    assert result["value"] == pytest.approx(10.8339261026, rel=1e-6)


def test_historical_var_and_cvar_on_returns_are_percent_losses():
    var = series("value_at_risk", DAILY, frequency="daily", confidence=0.95)
    cvar = series("cvar", DAILY, frequency="daily", confidence=0.95)
    assert var["value"] == pytest.approx(3.0, rel=1e-9)
    assert cvar["value"] == pytest.approx(3.0, rel=1e-9)


def test_parametric_var_on_returns():
    result = series("parametric_var", DAILY, frequency="daily", confidence=0.95)
    assert result["value"] == pytest.approx(2.4213266393, rel=1e-6)


def test_auto_infers_returns_when_small_and_signed():
    result = compute_series(
        "sharpe",
        observations(MONTHLY),
        options={"frequency": "monthly", "risk_free_rate": 0.0},
    )
    assert result["inputKind"] == "returns"
    assert result["value"] == pytest.approx(1.7224901965, rel=1e-9)
    assert any("inferred" in a for a in result["assumptions"])


def test_price_input_is_unchanged():
    result = compute_series(
        "cumulative_return",
        observations([100.0, 110.0, 121.0]),
        options={"input": "prices", "frequency": "daily"},
    )
    assert result["inputKind"] == "prices"
    assert result["value"] == pytest.approx(21.0)


def test_a_return_of_minus_one_hundred_percent_is_refused():
    with pytest.raises(CalculationError):
        compute_series(
            "sharpe",
            observations([0.01, -1.0, 0.02]),
            options={"input": "returns", "frequency": "monthly", "risk_free_rate": 0.0},
        )


def test_unknown_input_kind_is_refused():
    with pytest.raises(CalculationError):
        compute_series(
            "sharpe",
            observations(MONTHLY),
            options={"input": "percent", "frequency": "monthly", "risk_free_rate": 0.0},
        )
