"""Non-bar asset spine: the holder's sign convention, totals, XIRR and TVPI."""

from __future__ import annotations

import pytest

from harness.entities.cashflow import (
    KIND_DIRECTION,
    CashFlow,
    CashFlowSeries,
    xirr,
)


# -- sign convention ---------------------------------------------------------


def test_a_positive_capital_call_is_rejected():
    with pytest.raises(ValueError) as exc:
        CashFlow("2024-01-01", 100.0, "capital_call")
    assert "cash OUT" in str(exc.value)


def test_a_negative_distribution_is_rejected():
    with pytest.raises(ValueError) as exc:
        CashFlow("2024-06-01", -50.0, "distribution")
    assert "cash IN" in str(exc.value)


def test_the_canonical_signs_are_accepted():
    CashFlow("2024-01-01", -100.0, "capital_call")
    CashFlow("2024-06-01", 50.0, "distribution")
    CashFlow("2024-06-01", 5.0, "coupon")
    CashFlow("2024-06-01", -5.0, "fee")


def test_a_two_way_kind_carries_no_sign_constraint():
    assert CashFlow("2024-01-01", 100.0, "adjustment").amount == 100.0
    assert CashFlow("2024-01-01", -100.0, "adjustment").amount == -100.0


def test_an_unknown_kind_is_refused_so_it_cannot_dodge_the_check():
    with pytest.raises(ValueError) as exc:
        CashFlow("2024-01-01", 100.0, "mystery")
    assert "unknown kind" in str(exc.value)


def test_a_bad_date_is_refused():
    with pytest.raises(ValueError):
        CashFlow("not-a-date", -1.0, "fee")


def test_non_finite_amounts_are_refused():
    for amount in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            CashFlow("2024-01-01", amount, "flow")


def test_the_convention_table_covers_both_directions():
    assert any(sign < 0 for sign in KIND_DIRECTION.values())
    assert any(sign > 0 for sign in KIND_DIRECTION.values())


# -- valuations are not cash ------------------------------------------------


def test_a_valuation_is_excluded_from_total():
    series = CashFlowSeries.of(
        CashFlow("2024-01-01", -100.0, "capital_call"),
        CashFlow("2024-06-01", 20.0, "distribution"),
        CashFlow("2024-12-31", 500.0, "flow", is_valuation=True),
    )
    assert series.total() == pytest.approx(-80.0)
    assert len(series.cash) == 2
    assert len(series.valuations) == 1


def test_tvpi_uses_only_settled_cash():
    series = CashFlowSeries.of(
        CashFlow("2024-01-01", -100.0, "capital_call"),
        CashFlow("2024-06-01", 150.0, "distribution"),
        CashFlow("2024-12-31", 999.0, "flow", is_valuation=True),
    )
    assert series.invested() == pytest.approx(100.0)
    assert series.distributed() == pytest.approx(150.0)
    assert series.tvpi() == pytest.approx(1.5)


def test_tvpi_is_undefined_with_nothing_invested():
    assert CashFlowSeries.of(CashFlow("2024-01-01", 10.0, "flow")).tvpi() is None


# -- money-weighted return ---------------------------------------------------


def test_xirr_of_a_one_year_ten_percent_return():
    flows = [
        CashFlow("2024-01-01", -100.0, "capital_call"),
        CashFlow("2024-12-31", 110.0, "distribution"),
    ]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-4)


def test_xirr_of_a_two_year_compound_return():
    flows = [
        CashFlow("2022-01-01", -100.0, "capital_call"),
        CashFlow("2024-01-01", 121.0, "distribution"),
    ]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-4)


def test_xirr_is_none_without_a_sign_change():
    flows = [CashFlow("2024-01-01", -100.0, "capital_call"),
             CashFlow("2024-02-01", -50.0, "capital_call")]
    assert xirr(flows) is None


def test_xirr_is_none_for_a_single_flow():
    assert xirr([CashFlow("2024-01-01", -100.0, "capital_call")]) is None


def test_a_terminal_valuation_completes_the_return():
    series = CashFlowSeries.of(CashFlow("2024-01-01", -100.0, "capital_call"))
    # no distribution, but the position is worth 110 a year later
    assert series.money_weighted_return(
        terminal_value=110.0, as_of="2024-12-31") == pytest.approx(0.10, abs=1e-4)


def test_money_weighted_return_ignores_a_recorded_valuation_mark():
    # A valuation ROW in the series must not double-count the terminal value.
    series = CashFlowSeries.of(
        CashFlow("2024-01-01", -100.0, "capital_call"),
        CashFlow("2024-12-31", 110.0, "flow", is_valuation=True),
    )
    assert series.money_weighted_return(
        terminal_value=110.0, as_of="2024-12-31") == pytest.approx(0.10, abs=1e-4)


def test_unordered_flows_produce_the_same_return():
    ordered = CashFlowSeries.of(
        CashFlow("2024-01-01", -100.0, "capital_call"),
        CashFlow("2024-12-31", 110.0, "distribution"),
    )
    shuffled = CashFlowSeries.of(
        CashFlow("2024-12-31", 110.0, "distribution"),
        CashFlow("2024-01-01", -100.0, "capital_call"),
    )
    assert ordered.money_weighted_return() == pytest.approx(
        shuffled.money_weighted_return(), abs=1e-9)


def test_to_dict_is_serializable():
    payload = CashFlow("2024-01-01", -100.0, "capital_call").to_dict()
    assert payload == {"date": "2024-01-01", "amount": -100.0,
                       "kind": "capital_call", "isValuation": False, "note": ""}
