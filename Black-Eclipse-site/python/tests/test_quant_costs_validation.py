"""Tests for standalone execution-cost diagnostics and statistical validation."""

from __future__ import annotations

import math

import pytest

from harness.quant.costs import CostModelError, simulate_costs
from harness.quant.validation import (
    ValidationError_,
    bootstrap_ci,
    returns_from_equity,
    split_index,
)


# ── Transaction costs ────────────────────────────────────────────────────────

def test_percentage_commission_with_minimum():
    out = simulate_costs("transaction", [
        {"side": "buy", "quantity": 10, "price": 100.0},
    ], {"commission": {"type": "percentage", "value": 0.1, "minimum": 5.0}})
    # 10 * 100 * 0.1% = 1.0, floored up to the 5.0 minimum.
    assert out["orders"][0]["commission"] == pytest.approx(5.0)
    assert out["total"] == pytest.approx(5.0)
    assert out["frictionless"] is False


def test_tiered_commission_is_marginal():
    out = simulate_costs("transaction", [
        {"side": "buy", "quantity": 20, "price": 100.0},  # notional 2000
    ], {"commission": {"type": "tiered", "tiers": [
        {"upTo": 1000, "rate": 0.1}, {"upTo": 100000, "rate": 0.05}]}})
    # 1000 * 0.1% + 1000 * 0.05% = 1.0 + 0.5
    assert out["orders"][0]["commission"] == pytest.approx(1.5)


def test_spread_bps_halved_on_each_side():
    out = simulate_costs("spread", [
        {"side": "buy", "quantity": 100, "price": 50.0},
    ], {"spread": {"type": "bps", "value": 20}})
    # half of 20bps of 50.0 = 0.05 per unit, * 100 units = 5.0
    assert out["orders"][0]["spreadCost"] == pytest.approx(5.0)


def test_slippage_percentage():
    out = simulate_costs("slippage", [
        {"side": "buy", "quantity": 10, "price": 100.0},
    ], {"slippage": {"type": "percentage", "value": 0.5}})
    assert out["orders"][0]["slippage"] == pytest.approx(5.0)


def test_impact_linear_uses_volume():
    out = simulate_costs("impact", [
        {"side": "buy", "quantity": 100, "price": 100.0, "avgVolume": 1000.0},
    ], {"marketImpact": {"type": "linear", "coefficient": 10.0}})
    # participation = 0.1; impact/unit = 100 * (10/10000) * 0.1 = 0.01; *100 = 1.0
    assert out["orders"][0]["impact"] == pytest.approx(1.0)
    assert out["warnings"] == []


def test_historical_spread_missing_is_warned_not_silent():
    out = simulate_costs("spread", [
        {"side": "buy", "quantity": 10, "price": 100.0},
    ], {"spread": {"type": "historical"}})
    assert out["orders"][0]["spreadCost"] == 0.0
    assert any(w["code"] == "HISTORICAL_SPREAD_UNAVAILABLE" for w in out["warnings"])


def test_frictionless_is_labelled():
    out = simulate_costs("transaction", [{"side": "buy", "quantity": 1, "price": 10.0}], {})
    assert out["frictionless"] is True
    assert any(w["code"] == "COMMISSION_MODEL_NONE" for w in out["warnings"])


def test_invalid_order_is_typed_error():
    with pytest.raises(CostModelError):
        simulate_costs("transaction", [{"side": "buy", "quantity": 0, "price": 10.0}], {})


# ── Bootstrap ────────────────────────────────────────────────────────────────

def _series(n=200, seed=3):
    import random

    rng = random.Random(seed)
    return [rng.gauss(0.0005, 0.01) for _ in range(n)]


def test_bootstrap_iid_reproducible_and_warns_independence():
    a = bootstrap_ci(_series(), method="iid", iterations=300, seed=7)
    b = bootstrap_ci(_series(), method="iid", iterations=300, seed=7)
    assert a["ciLower"] == b["ciLower"] and a["ciUpper"] == b["ciUpper"]
    assert a["available"] and a["ciLower"] <= a["estimate"] <= a["ciUpper"]
    assert any(w["code"] == "BOOTSTRAP_IID_ASSUMES_INDEPENDENCE" for w in a["warnings"])


def test_bootstrap_block_and_stationary_run():
    for method in ("block", "stationary"):
        out = bootstrap_ci(_series(), method=method, iterations=200, seed=1, block_size=10)
        assert out["available"] and out["blockSize"] == 10
        assert out["ciLower"] <= out["ciUpper"]


def test_bootstrap_sharpe_and_annualization():
    out = bootstrap_ci(_series(), statistic="sharpe", iterations=100, seed=2, interval="1d")
    assert out["available"] and out["annualization"] == 365.0


def test_bootstrap_rejects_bad_inputs():
    with pytest.raises(ValidationError_):
        bootstrap_ci([0.01], method="iid")
    with pytest.raises(ValidationError_):
        bootstrap_ci(_series(), method="nope")
    with pytest.raises(ValidationError_):
        bootstrap_ci(_series(), method="block", block_size=10_000)


def test_returns_from_equity():
    assert returns_from_equity([100.0, 110.0, 121.0]) == pytest.approx([0.1, 0.1])
    assert returns_from_equity([0.0, 0.0]) == [0.0]
    assert math.isclose(sum(returns_from_equity([1.0, 2.0])), 1.0)


def test_split_index_chronological_only():
    is_end, oos = split_index(100, oos_fraction=0.25)
    assert is_end == oos == 75
    is_end, oos = split_index(100, oos_start_index=80)
    assert (is_end, oos) == (80, 80)
    with pytest.raises(ValidationError_):
        split_index(100)  # neither
    with pytest.raises(ValidationError_):
        split_index(100, oos_fraction=0.5, oos_start_index=10)  # both
    with pytest.raises(ValidationError_):
        split_index(100, oos_start_index=100)  # out of range
