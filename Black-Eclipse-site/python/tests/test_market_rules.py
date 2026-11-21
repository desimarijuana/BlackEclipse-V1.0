"""Market execution rules: limits, lots, settlement, taxes, shorting."""

from __future__ import annotations

import pytest

from harness.quant import market_rules as mr
from harness.quant.strategy import StrategySpec, validate_strategy


def _spec(**overrides) -> StrategySpec:
    base = dict(
        id="s1",
        name="Test",
        universe={"symbols": ["AAPL"]},
    )
    base.update(overrides)
    return StrategySpec(**base)


# -- lot rounding ------------------------------------------------------------


def test_a_share_floors_to_a_whole_100_share_lot():
    rules = mr.rules_for("a_share")
    assert rules.round_size(350) == 300
    assert rules.round_size(99) == 0
    assert rules.round_size(100) == 100


def test_a_share_never_returns_a_partial_lot():
    rules = mr.rules_for("a_share")
    assert rules.round_size(150.9) == 100


def test_fractional_market_keeps_precision():
    rules = mr.rules_for("crypto")
    assert rules.round_size(0.123456789) == pytest.approx(0.12345679, abs=1e-9)


def test_non_positive_and_non_finite_sizes_are_zero():
    rules = mr.rules_for("us_equity")
    for value in (0, -5, float("nan"), float("inf")):
        assert rules.round_size(value) == 0.0


# -- price limits ------------------------------------------------------------


def test_a_share_band_by_board():
    rules = mr.rules_for("a_share")
    assert rules.band(100.0, "main") == (90.0, 110.0)
    assert rules.band(100.0, "chinext") == (80.0, 120.0)
    assert rules.band(100.0, "beijing") == (70.0, 130.0)


def test_a_share_unknown_board_is_not_treated_as_the_loosest():
    assert mr.rules_for("a_share").band(100.0, None) is None
    assert mr.rules_for("a_share").band(100.0, "unknown") is None


def test_us_has_no_band():
    assert mr.rules_for("us_equity").band(100.0, "main") is None


# -- settlement --------------------------------------------------------------


def test_a_share_blocks_same_day_sell():
    ok, reason = mr.rules_for("a_share").can_sell(bought_today=True)
    assert ok is False and "T+1" in reason


def test_a_share_allows_next_day_sell():
    assert mr.rules_for("a_share").can_sell(bought_today=False) == (True, "")


def test_us_allows_same_day_sell():
    assert mr.rules_for("us_equity").can_sell(bought_today=True)[0] is True


# -- shorting ----------------------------------------------------------------


def test_a_share_bans_retail_shorts():
    ok, reason = mr.rules_for("a_share").can_short()
    assert ok is False and "short" in reason


def test_crypto_allows_shorts():
    assert mr.rules_for("crypto").can_short()[0] is True


# -- taxes -------------------------------------------------------------------


def test_a_share_stamp_duty_is_sell_side_only():
    rules = mr.rules_for("a_share")
    assert rules.sell_tax(100_000) == pytest.approx(50.0 + 1.0)   # 5bps + 0.1bps
    assert rules.buy_tax(100_000) == pytest.approx(1.0)          # transfer only


def test_hk_stamp_duty_is_both_sides():
    rules = mr.rules_for("hk_equity")
    assert rules.sell_tax(100_000) == pytest.approx(100.0)
    assert rules.buy_tax(100_000) == pytest.approx(100.0)


def test_zero_notional_has_no_tax():
    assert mr.rules_for("a_share").sell_tax(0) == 0.0


# -- registry ----------------------------------------------------------------


def test_unknown_market_raises_with_the_known_list():
    with pytest.raises(KeyError) as exc:
        mr.rules_for("nasdaq")
    assert "a_share" in str(exc.value)


def test_describe_is_json_shaped():
    payload = mr.rules_for("a_share").describe()
    assert payload["id"] == "a_share"
    assert payload["settleBuyDays"] == 1
    assert payload["allowsShort"] is False


# -- spec integration --------------------------------------------------------


def test_spec_defaults_to_us_equity():
    assert _spec().market == "us_equity"


def test_unknown_market_fails_validation():
    issues = validate_strategy(_spec(market="nasdaq"))
    assert any(issue.code == "UNKNOWN_MARKET" for issue in issues)


def test_a_share_with_shorting_fails_validation():
    issues = validate_strategy(_spec(market="a_share", universe={"symbols": ["600519"]}))
    assert any(issue.code == "MARKET_SHORT_NOT_PERMITTED" for issue in issues)


def test_a_share_without_shorting_validates_cleanly():
    issues = validate_strategy(
        _spec(market="a_share", universe={"symbols": ["600519"]}, risk={"allow_short": False})
    )
    assert not [i for i in issues if i.code == "MARKET_SHORT_NOT_PERMITTED"]


def test_market_survives_the_serialized_spec():
    spec = _spec(market="a_share", universe={"symbols": ["600519"]})
    assert spec.to_dict()["market"] == "a_share"
