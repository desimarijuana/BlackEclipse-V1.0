"""Tax-lot accounting engines: FIFO, LIFO, average cost — golden + edge cases.

Purely in-memory (no database, no network). Covers the §47 golden test, fees,
fractional quantities, partial/complete liquidation, splits, transfers, lot
matching and the §46 accounting invariants.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from harness.portfolio.accounting import compute_accounting
from harness.portfolio.models import CostBasisMethod, Transaction, TransactionType


def tx(kind, qty, price=None, date="2024-01-01", symbol="X", fees="0", **kw):
    return Transaction(
        portfolio_id="p", transaction_type=kind, symbol=symbol,
        quantity=Decimal(qty), price=None if price is None else Decimal(price),
        fees=Decimal(fees), trade_date=date, **kw,
    )


def golden(method):
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.BUY, "10", "200", "2024-01-02"),
        tx(TransactionType.SELL, "10", "300", "2024-01-03"),
    ]
    return compute_accounting("p", "X", txs, method)


def test_golden_fifo():
    r = golden(CostBasisMethod.FIFO)
    assert r.realized_cost_basis == Decimal("1000")
    assert r.realized_pnl == Decimal("2000")
    assert r.remaining_qty == Decimal("10")


def test_golden_lifo():
    r = golden(CostBasisMethod.LIFO)
    assert r.realized_cost_basis == Decimal("2000")
    assert r.realized_pnl == Decimal("1000")
    assert r.remaining_qty == Decimal("10")


def test_golden_average_cost():
    r = golden(CostBasisMethod.AVERAGE_COST)
    assert r.realized_cost_basis == Decimal("1500")
    assert r.realized_pnl == Decimal("1500")
    assert r.remaining_qty == Decimal("10")
    assert r.average_cost == Decimal("150")


def test_partial_sell_spans_multiple_lots_fifo():
    txs = [
        tx(TransactionType.BUY, "100", "40", "2024-01-01"),
        tx(TransactionType.BUY, "50", "55", "2024-01-02"),
        tx(TransactionType.SELL, "70", "65", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    # 70 from the $40 lot
    assert r.realized_cost_basis == Decimal("2800")
    assert r.realized_pnl == Decimal("1750")  # 70*65 - 70*40
    assert r.remaining_qty == Decimal("80")


def test_partial_sell_spans_multiple_lots_lifo():
    txs = [
        tx(TransactionType.BUY, "100", "40", "2024-01-01"),
        tx(TransactionType.BUY, "50", "55", "2024-01-02"),
        tx(TransactionType.SELL, "70", "65", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.LIFO)
    # 50 from $55 + 20 from $40
    assert r.realized_cost_basis == Decimal("3550")
    assert r.realized_pnl == Decimal("1000")  # 70*65 - 3550


def test_fees_are_allocated_into_cost_and_proceeds():
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01", fees="10"),
        tx(TransactionType.SELL, "10", "300", "2024-01-02", fees="5"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.realized_cost_basis == Decimal("1010")  # 1000 + 10 fee
    assert r.realized_pnl == Decimal("1985")  # (3000 - 5) - 1010


def test_fractional_quantities():
    txs = [
        tx(TransactionType.BUY, "0.5", "30000", "2024-01-01"),
        tx(TransactionType.BUY, "0.25", "32000", "2024-01-02"),
        tx(TransactionType.SELL, "0.6", "40000", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.remaining_qty == Decimal("0.15")
    # consumed 0.5 @30000 + 0.1 @32000 = 15000 + 3200
    assert r.realized_cost_basis == Decimal("18200")
    assert r.realized_pnl == Decimal("5800")  # 0.6*40000 - 18200


def test_complete_liquidation_leaves_no_open_lots():
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SELL, "10", "150", "2024-01-02"),
    ]
    for method in CostBasisMethod:
        r = compute_accounting("p", "X", txs, method)
        assert r.remaining_qty == 0
        assert r.open_lots == []
        assert not r.has_errors()


def test_insufficient_position_is_refused():
    txs = [
        tx(TransactionType.BUY, "5", "100", "2024-01-01"),
        tx(TransactionType.SELL, "10", "150", "2024-01-02"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.has_errors()
    assert r.errors[0].code == "INSUFFICIENT_POSITION"


def test_oversell_with_no_lot_reports_short_not_supported():
    txs = [tx(TransactionType.SELL, "1", "10", "2024-01-01")]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.errors[0].code == "SHORT_NOT_SUPPORTED"


def test_split_scales_quantity_and_cost():
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SPLIT, "2", None, "2024-01-02"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.remaining_qty == Decimal("20")
    assert r.open_lots[0].cost_per_unit == Decimal("50")
    assert r.remaining_cost_basis == Decimal("1000")


def test_reverse_split_scales_quantity_and_cost():
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.REVERSE_SPLIT, "0.5", None, "2024-01-02"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert r.remaining_qty == Decimal("5")
    assert r.open_lots[0].cost_per_unit == Decimal("200")


def test_transfer_in_takes_cost_basis_and_transfer_out_realizes_nothing():
    txs = [
        tx(TransactionType.TRANSFER_IN, "10", "100", "2024-01-01"),
        tx(TransactionType.TRANSFER_OUT, "10", None, "2024-01-02"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    # Transferred in at book value 1000, out at the same book value (no stated
    # price ⇒ book-value carry-over) ⇒ no realized gain.
    assert r.realized_pnl == Decimal("0")
    assert r.remaining_qty == 0


def test_lot_matches_record_holding_period():
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SELL, "10", "150", "2024-06-01"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.FIFO)
    assert len(r.matches) == 1
    assert r.matches[0].holding_days() == 152


@pytest.mark.parametrize("method", list(CostBasisMethod))
def test_invariant_remaining_plus_realized_cost_equals_acquired(method):
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.BUY, "5", "120", "2024-01-02"),
        tx(TransactionType.SELL, "8", "130", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, method)
    acquired_cost = r.remaining_cost_basis + r.realized_cost_basis
    assert acquired_cost == Decimal("1600")  # 10*100 + 5*120


@pytest.mark.parametrize("method", list(CostBasisMethod))
def test_invariant_acquired_minus_disposed_equals_remaining(method):
    txs = [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.BUY, "5", "120", "2024-01-02"),
        tx(TransactionType.SELL, "12", "130", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, method)
    assert r.total_acquired_qty - r.total_disposed_qty == r.remaining_qty


def test_average_cost_consistency_after_partial_sell():
    txs = [
        tx(TransactionType.BUY, "100", "40", "2024-01-01"),
        tx(TransactionType.BUY, "50", "60", "2024-01-02"),
        tx(TransactionType.SELL, "30", "80", "2024-01-03"),
    ]
    r = compute_accounting("p", "X", txs, CostBasisMethod.AVERAGE_COST)
    # avg = 7000/150 = 46.666..., sold 30 => cost 1400
    assert r.realized_cost_basis == Decimal("1400")
    assert r.remaining_qty == Decimal("120")
    assert r.remaining_cost_basis == Decimal("5600")
