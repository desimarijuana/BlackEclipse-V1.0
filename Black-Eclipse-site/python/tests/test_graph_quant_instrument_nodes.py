"""Instrument nodes: multi-leg options and continuous futures.

The engines are tested elsewhere; these tests pin the adapter contracts: which
leg/contract shapes are accepted, that an unbounded payoff stays unbounded (no
made-up max loss), that the payoff range declares where it came from, and that a
spliced series is labelled a backtest proxy.
"""

from __future__ import annotations

import datetime as dt

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.quant import fixtures as F

REGISTRY = build_default_registry()


def _run(node_type: str, inputs: dict, config: dict | None = None) -> dict:
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type,
        run_id="run",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs,
        config=config or {},
    ))


# ── quant.options_strategy ──────────────────────────────────────────────────


def _bull_call_spread() -> list[dict]:
    return [
        {"type": "call", "strike": 490, "quantity": 1, "premium": 12},
        {"type": "call", "strike": 510, "quantity": -1, "premium": 5},
    ]


def test_bull_call_spread_payoff_and_break_even():
    result = _run(
        "quant.options_strategy",
        {"legs": _bull_call_spread()},
        {"spotMin": 470, "spotMax": 530, "points": 121},
    )
    analysis = result["analysis"]
    assert analysis["available"] is True
    assert analysis["netPremium"] == pytest.approx(700.0)  # (12 - 5) × 100
    assert analysis["maxProfit"] == pytest.approx(1300.0)  # 20 wide × 100 − 700
    assert analysis["maxLoss"] == pytest.approx(-700.0)
    assert analysis["bounded"] is True
    assert analysis["breakEvens"] == pytest.approx([497.0])
    assert analysis["spotRangeSource"] == "configured"
    assert result["summary"].startswith("2 leg(s)")


def test_a_naked_long_call_has_no_finite_max_profit():
    result = _run(
        "quant.options_strategy",
        {"legs": [{"type": "call", "strike": 500, "quantity": 1, "premium": 8}]},
        {"spotMin": 400, "spotMax": 700},
    )
    analysis = result["analysis"]
    assert analysis["bounded"] is False
    assert analysis["maxProfit"] is None  # unbounded, never a made-up number
    assert analysis["maxLoss"] == pytest.approx(-800.0)


def test_wiring_a_spot_and_expiry_adds_net_greeks():
    result = _run(
        "quant.options_strategy",
        {"legs": _bull_call_spread(), "spot": 500.0, "timeToExpiry": 0.08, "iv": 0.22},
        {"spotMin": 450, "spotMax": 550},
    )
    greeks = result["analysis"]["netGreeks"]
    assert set(greeks) >= {"delta", "gamma", "theta", "vega", "rho"}


def test_the_payoff_range_is_derived_and_says_so():
    result = _run("quant.options_strategy", {"legs": _bull_call_spread()})
    analysis = result["analysis"]
    assert analysis["spotRangeSource"] == "derivedFromStrikes"
    # Derived from the mean strike (500) ± 30%.
    assert analysis["spotRange"] == pytest.approx([350.0, 650.0])


def test_a_half_configured_range_is_an_explicit_failure():
    with pytest.raises(ValueError, match="spotMin and spotMax"):
        _run(
            "quant.options_strategy",
            {"legs": _bull_call_spread()},
            {"spotMin": 450},
        )


def test_an_invalid_leg_is_reported_by_the_engine():
    with pytest.raises(ValueError, match="option strategy failed"):
        _run(
            "quant.options_strategy",
            {"legs": [{"type": "call", "quantity": 1, "premium": 1}]},
            {"spotMin": 100, "spotMax": 200},
        )
    with pytest.raises(ValueError, match="non-empty legs"):
        _run("quant.options_strategy", {"legs": []})


# ── quant.futures_continuous ────────────────────────────────────────────────


def _contracts() -> list[dict]:
    near = F.bull_market("MAR", n=10)
    far = F.bull_market(
        "JUN", n=10, start_time=dt.datetime(2023, 1, 5, tzinfo=dt.timezone.utc),
    )
    return [
        {"symbol": "MAR", "rows": near},
        {"symbol": "JUN", "rows": far},
    ]


def test_continuous_series_splices_at_the_roll_date_and_marks_itself_a_proxy():
    result = _run(
        "quant.futures_continuous",
        {"contracts": _contracts()},
        {"rollDatesJson": '["2023-01-08"]', "adjustment": "difference", "symbol": "ES_CONT"},
    )
    series = result["series"]
    assert series["symbol"] == "ES_CONT"
    assert series["proxy"] is True
    assert "PROXY" in series["note"]
    assert series["contractSymbols"] == ["MAR", "JUN"]
    # MAR contributes Jan 1-7, JUN Jan 8-14 -> 14 unique sessions.
    assert len(series["rows"]) == 14
    assert series["rows"][0]["timestamp"].startswith("2023-01-01")
    assert result["metadata"]["rolls"]
    assert result["metadata"]["barCount"] == 14
    assert "bars" not in result["metadata"]


def test_no_adjustment_keeps_the_raw_contract_prices():
    result = _run(
        "quant.futures_continuous",
        {"contracts": _contracts()},
        {"rollDatesJson": '["2023-01-08"]', "adjustment": "none"},
    )
    rows = result["series"]["rows"]
    near = _contracts()[0]["rows"]
    assert rows[0]["close"] == near[0]["close"]
    assert result["metadata"]["adjustment"] == "none"


def test_a_wrong_roll_schedule_is_rejected():
    with pytest.raises(ValueError, match="continuous futures failed"):
        _run(
            "quant.futures_continuous",
            {"contracts": _contracts()},
            {"rollDatesJson": '["2023-01-08", "2023-01-10"]'},
        )
    with pytest.raises(ValueError, match="rollDatesJson is required"):
        _run("quant.futures_continuous", {"contracts": _contracts()})
    with pytest.raises(ValueError, match="adjustment"):
        _run(
            "quant.futures_continuous",
            {"contracts": _contracts()},
            {"rollDatesJson": '["2023-01-08"]', "adjustment": "magic"},
        )


def test_an_empty_contract_list_is_explicit():
    with pytest.raises(ValueError, match="non-empty contracts"):
        _run("quant.futures_continuous", {"contracts": []})
