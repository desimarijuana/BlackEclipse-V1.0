"""HARDCORE accounting tests — the prompts in `docs/accounting-hardcore-tests.md`
executed deterministically against the two books of record.

The General Ledger keeps a company's books (double-entry). The Portfolio
Accounting Engine keeps a securities book (lots, cost basis, realized P&L).
Both must survive adversarial bookkeeping, not just the happy path.

These tests are the offline half of each prompt pair in that document: the chat
prompt states what the bookkeeper must do; the test pins what the engine must
produce, so a regression is caught without a model in the loop.
"""

from __future__ import annotations

import csv
import io
import random
from decimal import Decimal

import pytest

from harness.ledger.errors import LedgerError
from harness.ledger.exports import export as export_ledger
from harness.portfolio.accounting import compute_accounting
from harness.portfolio.models import CostBasisMethod, Transaction, TransactionType
from ledger_helpers import line, make_ledger as make_books, make_service as make_ledger_service, post
from portfolio_helpers import buy, make_portfolio, make_service as make_portfolio_service, sell


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio Accounting Engine — securities book
# ═══════════════════════════════════════════════════════════════════════════

def tx(kind, qty, price=None, date="2024-01-01", *, fees="0", taxes="0",
       gross=None, net=None, symbol="X", **kw):
    return Transaction(
        portfolio_id="p", transaction_type=kind, symbol=symbol,
        quantity=Decimal(str(qty)),
        price=None if price is None else Decimal(str(price)),
        fees=Decimal(str(fees)), taxes=Decimal(str(taxes)),
        gross_amount=None if gross is None else Decimal(str(gross)),
        net_amount=None if net is None else Decimal(str(net)),
        trade_date=date, **kw,
    )


@pytest.mark.parametrize("method", [CostBasisMethod.FIFO, CostBasisMethod.AVERAGE_COST])
def test_a_net_amount_only_sell_is_cash_proceeds_not_a_total_loss(method):
    """Broker exports often carry only a settled net amount — no price, no gross.

    Reading gross=0 booked a fabricated 100% loss (realized -1000 on a 1500 sale).
    """
    result = compute_accounting("p", "X", [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SELL, "10", None, "2024-06-01", net="1500"),
    ], method)
    assert not result.has_errors()
    assert result.total_proceeds == Decimal("1500")
    assert result.realized_pnl == Decimal("500")
    assert result.realized_cost_basis == Decimal("1000")
    assert result.remaining_qty == 0


def test_an_oversell_prorates_proceeds_instead_of_inflating_them():
    """20 requested @300 clamped to 10 available must not report 6000 of proceeds."""
    result = compute_accounting("p", "X", [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SELL, "20", "300", "2024-06-01"),
    ], CostBasisMethod.FIFO)
    assert any(e.code == "INSUFFICIENT_POSITION" for e in result.errors)
    assert result.total_disposed_qty == Decimal("10")
    assert result.total_proceeds == Decimal("3000")
    assert result.realized_pnl == Decimal("2000")


@pytest.mark.parametrize("method", [CostBasisMethod.FIFO, CostBasisMethod.AVERAGE_COST])
def test_a_split_keeps_the_documented_quantity_invariant(method):
    """A pre-split disposal must be restated in post-split share units.

    The advertised invariant `acquired − disposed == remaining` used to break by
    exactly the split factor on every disposal that happened before the split.
    """
    result = compute_accounting("p", "X", [
        tx(TransactionType.BUY, "10", "100", "2024-01-01"),
        tx(TransactionType.SELL, "4", "150", "2024-02-01"),
        tx(TransactionType.SPLIT, "2", None, "2024-03-01"),
    ], method)
    assert not result.has_errors()
    assert result.remaining_qty == Decimal("12")
    assert result.total_acquired_qty - result.total_disposed_qty == result.remaining_qty
    assert (result.total_acquired_qty, result.total_disposed_qty) == (
        Decimal("20"), Decimal("8"))


def test_average_cost_reports_a_real_holding_period():
    """Average basis is pooled, but the match cannot claim a 0-day holding for
    shares bought years earlier (that fabricated short-term tax treatment)."""
    result = compute_accounting("p", "X", [
        tx(TransactionType.BUY, "10", "100", "2020-01-01"),
        tx(TransactionType.BUY, "10", "200", "2024-01-01"),
        tx(TransactionType.SELL, "10", "300", "2026-01-01"),
    ], CostBasisMethod.AVERAGE_COST)
    match = result.matches[0]
    assert match.acquired_at == "2020-01-01"
    assert match.holding_days() > 365 * 5
    assert result.realized_cost_basis == Decimal("1500")


def test_specific_id_with_an_unknown_lot_is_refused_not_silently_fifo():
    """Designating a lot is a tax instruction; a typo must not quietly become FIFO."""
    buy_lot = tx(TransactionType.BUY, "10", "100", "2024-01-01")
    sell_tx = tx(TransactionType.SELL, "5", "200", "2024-02-01",
                 lot_selection=[{"lotId": "lot_does_not_exist", "quantity": "5"}])
    result = compute_accounting("p", "X", [buy_lot, sell_tx], CostBasisMethod.SPECIFIC_ID)
    assert any(e.code == "LOT_MISMATCH" for e in result.errors)
    # The engine still completes a FIFO fallback so a caller can inspect it, but
    # the recorded error is what makes the service refuse the write.
    assert result.realized_cost_basis == Decimal("500")


def test_specific_id_with_a_malformed_quantity_is_refused():
    buy_tx = tx(TransactionType.BUY, "10", "100", "2024-01-01")
    base = compute_accounting("p", "X", [buy_tx], CostBasisMethod.SPECIFIC_ID)
    lot_id = base.open_lots[0].id
    sell_tx = tx(TransactionType.SELL, "5", "200", "2024-02-01",
                 lot_selection=[{"lotId": lot_id, "quantity": "not-a-number"}])
    result = compute_accounting("p", "X", [buy_tx, sell_tx], CostBasisMethod.SPECIFIC_ID)
    assert any(e.code == "INVALID_TRANSACTION" for e in result.errors)


def test_service_refuses_a_bad_lot_designation_without_writing(tmp_path):
    svc = make_portfolio_service(tmp_path)
    pid = make_portfolio(svc, method="SPECIFIC_ID")
    buy(svc, pid, "AAPL", "10", "100")
    out = svc.add_transaction(pid, {
        "type": "SELL", "symbol": "AAPL", "quantity": "5", "price": "200",
        "lot_selection": [{"lotId": "typo", "quantity": "5"}],
    })
    assert out["status"] == "FAILED"
    assert out["error"]["code"] in ("LOT_MISMATCH", "INVALID_TRANSACTION")
    assert svc.store.count_transactions(pid) == 1


@pytest.mark.asyncio
async def test_net_only_buy_and_sell_keep_the_cash_ledger_honest(tmp_path):
    """Net-only imports must move cash by the settled amount, not by fees alone."""
    svc = make_portfolio_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "10000"})
    svc.add_transaction(pid, {"type": "BUY", "symbol": "X", "quantity": "10",
                              "net_amount": "1000"})
    svc.add_transaction(pid, {"type": "SELL", "symbol": "X", "quantity": "10",
                              "net_amount": "1500"})
    read = await svc.read(pid, include=["cash", "pnl"])
    assert read["cash"]["balance"] == "10500.00000000"
    assert read["pnl"]["realizedPnl"] == "500.00000000"


@pytest.mark.asyncio
async def test_a_net_only_dividend_appears_in_the_pnl_report(tmp_path):
    svc = make_portfolio_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "1000"})
    buy(svc, pid, "AAPL", "10", "100")
    svc.add_transaction(pid, {"type": "DIVIDEND", "symbol": "AAPL",
                              "gross_amount": "50", "taxes": "7.5"})
    read = await svc.read(pid, include=["pnl"])
    # Net cash received, not the gross that was never credited.
    assert read["pnl"]["dividends"] == "42.50000000"


@pytest.mark.parametrize("method", list(CostBasisMethod))
def test_property_random_ledger_sequences_keep_every_lot_invariant(method):
    """Deterministic property test over buys, sells, splits, adjustments, basis
    reallocations and in-kind transfers — the arithmetic must never drift."""
    rng = random.Random(20261113)
    for _ in range(20):
        transactions = []
        for _ in range(14):
            day = f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            roll = rng.random()
            qty = Decimal(rng.randint(1, 40)) / Decimal(rng.choice([1, 2, 4]))
            price = Decimal(rng.randint(50, 400)) / Decimal(10)
            fees = Decimal(rng.randint(0, 20)) / Decimal(10)
            if roll < 0.45:
                transactions.append(tx(rng.choice([
                    TransactionType.BUY, TransactionType.TRANSFER_IN,
                    TransactionType.STAKING_REWARD,
                ]), qty, price, day, fees=fees))
            elif roll < 0.8:
                transactions.append(tx(rng.choice([
                    TransactionType.SELL, TransactionType.TRANSFER_OUT,
                ]), qty, None if rng.random() < 0.2 else price, day, fees=fees))
            elif roll < 0.9:
                transactions.append(tx(rng.choice([
                    TransactionType.SPLIT, TransactionType.REVERSE_SPLIT,
                ]), "2" if rng.random() < 0.5 else "0.5", None, day))
            elif roll < 0.96:
                transactions.append(tx(TransactionType.COST_BASIS_ADJUSTMENT, "0", None, day,
                                       basis_adjustment=Decimal(rng.randint(-300, 300))))
            else:
                transactions.append(tx(TransactionType.ADJUSTMENT,
                                       rng.randint(-10, 10), price, day))
        result = compute_accounting("p", "X", transactions, method)
        if result.has_errors():
            continue
        assert result.remaining_qty >= 0
        assert result.total_acquired_qty - result.total_disposed_qty == result.remaining_qty
        assert all(lot.quantity > 0 and lot.cost_per_unit >= 0 for lot in result.open_lots)
        # Aggregate realized P&L is the aggregate of (proceeds - consumed basis),
        # up to the 8-dp output rounding of individual matches.
        assert abs(result.realized_pnl - (result.total_proceeds - result.realized_cost_basis)) \
            <= Decimal("0.00000001")


# ═══════════════════════════════════════════════════════════════════════════
# General Ledger — double-entry book of record
# ═══════════════════════════════════════════════════════════════════════════

def test_designated_lots_are_stable_across_reads_and_usable_in_a_sale(tmp_path):
    """A lot id read from `tax_lots` must still be found when the sell posts.

    Lot ids used to be random per recompute, so a SPECIFIC_ID designation was
    unknowable to the engine a moment later and silently fell back to FIFO.
    """
    svc = make_portfolio_service(tmp_path)
    pid = make_portfolio(svc, method="SPECIFIC_ID")
    buy(svc, pid, "X", "10", "100", date="2024-01-01")
    buy(svc, pid, "X", "10", "200", date="2024-02-01")

    first = svc.calculate_tax_lots(pid, symbol="X", persist=True)["symbols"][0]
    second = svc.calculate_tax_lots(pid, symbol="X", persist=True)["symbols"][0]
    first_ids = [lot["id"] for lot in first["openLots"]]
    assert first_ids == [lot["id"] for lot in second["openLots"]]

    cheap = min(first["openLots"], key=lambda lot: Decimal(lot["costPerUnit"]))
    out = svc.add_transaction(pid, {
        "type": "SELL", "symbol": "X", "quantity": "10", "price": "300",
        "lot_selection": [{"lotId": cheap["id"], "quantity": "10"}],
    })
    assert out["status"] == "SUCCESS", out
    assert out["position"]["symbol"] == "X"
    lots = svc.calculate_tax_lots(pid, symbol="X", persist=True)["symbols"][0]
    assert Decimal(lots["remainingQuantity"]) == Decimal("10")
    assert Decimal(lots["realizedPnl"]) == Decimal("2000")
    assert Decimal(lots["remainingCostBasis"]) == Decimal("2000")


def test_a_full_cycle_reconciles_every_statement(tmp_path):
    """Capital, credit sale, COGS, paid expense, equipment and a loan — then prove
    every statement and the cash reconciliation from the postings alone."""
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)

    post(svc, lid, "2026-01-02", [line("1010", debit="100000"), line("3000", credit="100000")], memo="capital")
    post(svc, lid, "2026-01-10", [line("1200", debit="9000"), line("2000", credit="9000")], memo="inventory")
    post(svc, lid, "2026-01-15", [line("1100", debit="24000"), line("4000", credit="24000")], memo="sale")
    post(svc, lid, "2026-01-15", [line("5000", debit="9000"), line("1200", credit="9000")], memo="cogs")
    post(svc, lid, "2026-01-20", [line("6100", debit="2000"), line("1010", credit="2000")], memo="rent")
    post(svc, lid, "2026-01-25", [line("1010", debit="12000"), line("1100", credit="12000")], memo="receipt")
    post(svc, lid, "2026-01-28", [line("1500", debit="15000"), line("1010", credit="15000")], memo="equipment")
    post(svc, lid, "2026-01-29", [line("1010", debit="30000"), line("2500", credit="30000")], memo="loan")

    tb = svc.trial_balance(lid, as_of="2026-01-31")
    bs = svc.balance_sheet(lid, as_of="2026-01-31")
    income = svc.income_statement(lid, start="2026-01-01", end="2026-01-31")
    cash = svc.cash_flow(lid, start="2026-01-01", end="2026-01-31")

    assert tb["balanced"], tb["checks"]
    assert bs["balanced"], bs["checks"]
    assert income["balanced"], income["checks"]
    assert cash["balanced"], cash["checks"]
    assert cash["complete"] is True

    # P&L arithmetic from the same postings.
    assert income["revenue"]["total"] == "24000.00000000"
    assert income["costOfSales"]["total"] == "9000.00000000"
    assert income["operatingExpenses"]["total"] == "2000.00000000"
    assert income["netIncome"] == "13000.00000000"
    assert bs["currentEarnings"] == income["netIncome"]

    # Cash-flow categories derive from the COUNTER account, not the cash account.
    assert cash["financing"] == "130000.00000000"   # capital 100k + loan 30k
    assert cash["investing"] == "-15000.00000000"   # equipment
    assert cash["operating"] == "10000.00000000"    # receipt 12k - rent 2k

    # Closing cash must equal the cash accounts' trial balance, exactly.
    cash_tb = sum(Decimal(row["closingDebit"]) - Decimal(row["closingCredit"])
                  for row in tb["rows"] if row["code"] in ("1000", "1010", "1020"))
    assert Decimal(cash["closingCash"]) == cash_tb

    period = next(p for p in svc.list_periods(lid) if p["startDate"] == "2026-01-01")
    report = svc.close_report(lid, period_id=period["id"])
    assert report["status"] == "READY", report["findings"]
    assert svc.close_period(lid, period_id=period["id"])["status"] == "CLOSED"


def test_a_reversal_in_a_later_period_removes_the_effect_without_rewriting_history(tmp_path):
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)
    entry = post(svc, lid, "2026-01-31", [
        line("6200", debit="800"), line("1010", credit="800"),
    ], memo="utilities estimate")
    reversal = svc.reverse(lid, entry["id"], entry_date="2026-02-03", memo="reversal")

    assert reversal["reversesEntryId"] == entry["id"]
    assert reversal["status"] == "POSTED"
    # January keeps the original expense; February carries the credit.
    jan = svc.income_statement(lid, start="2026-01-01", end="2026-01-31")
    feb = svc.income_statement(lid, start="2026-02-01", end="2026-02-28")
    assert jan["operatingExpenses"]["total"] == "800.00000000"
    assert feb["operatingExpenses"]["total"] == "-800.00000000"
    assert svc.trial_balance(lid, as_of="2026-02-28")["balanced"] is True
    # Original values are untouched; only its status records the reversal link.
    original = svc.get_entry(lid, entry["id"])
    assert original["status"] == "REVERSED"
    assert original["lines"][0]["debit"] == "800.00000000"
    assert original["reversedByEntryId"] == reversal["id"]


def test_a_transfer_between_cash_accounts_has_no_cash_flow_effect(tmp_path):
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)
    post(svc, lid, "2026-01-05", [line("1000", debit="500"), line("1010", credit="500")],
         memo="cash to bank")
    flow = svc.cash_flow(lid, start="2026-01-01", end="2026-01-31")
    assert flow["netChange"] == "0.00000000"
    assert flow["complete"] is True
    assert flow["balanced"] is True


def test_a_foreign_line_balances_on_base_amounts_and_a_missing_rate_is_refused(tmp_path):
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)
    svc.create_account(lid, code="1050", name="EUR bank", account_type="ASSET",
                       currency="EUR", is_cash=True)
    entry = post(svc, lid, "2026-01-05", [
        line("1050", debit="100", currency="EUR", fx_rate="1.10"),
        line("4000", credit="110", currency="USD"),
    ])
    assert entry["totalDebit"] == "110.00000000"
    assert entry["lines"][0]["baseDebit"] == "110.00000000"

    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-06", [
            line("1050", debit="100", currency="EUR"), line("4000", credit="100"),
        ])
    assert info.value.code == "MISSING_FX"
    assert svc.trial_balance(lid, as_of="2026-01-31")["balanced"] is True


def test_an_inclusive_tax_invoice_partial_payment_and_aging_reconcile(tmp_path):
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)
    customer = svc.create_party(lid, name="Acme", kind="CUSTOMER")
    svc.create_tax_code(lid, code="VAT20", name="VAT 20", jurisdiction="GB",
                        rate="0.20", account_code="2100", price_includes_tax=True)
    invoice = svc.create_document(
        lid, kind="INVOICE", party_id=customer["id"],
        issue_date="2026-01-15", due_date="2026-02-14",
        lines=[{"description": "3 widgets @ 10.00 incl. VAT", "account_code": "4000",
                "quantity": "3", "unit_price": "10.00", "tax_code": "VAT20"}],
    )
    # 30 inclusive at 20% ⇒ 25 net + 5 tax, and the header equals the lines.
    assert invoice["subtotal"] == "25.00000000"
    assert invoice["taxTotal"] == "5.00000000"
    assert invoice["total"] == "30.00000000"

    svc.pay_document(lid, invoice["id"], date_paid="2026-02-10", amount="10",
                     bank_account="1010", reference="rcpt-1")
    january = svc.aging(lid, kind="AR", as_of="2026-01-31")
    assert january["openTotal"] == "30.00000000"   # the payment is in February
    assert january["reconciled"] is True
    february = svc.aging(lid, kind="AR", as_of="2026-02-28")
    assert february["openTotal"] == "20.00000000"
    assert february["reconciled"] is True

    rows = {row["code"]: row for row in svc.trial_balance(lid, as_of="2026-02-28")["rows"]}
    assert rows["1100"]["closingDebit"] == "20.00000000"
    assert rows["2100"]["closingCredit"] == "5.00000000"

    with pytest.raises(LedgerError) as info:
        svc.pay_document(lid, invoice["id"], date_paid="2026-03-01", amount="20.01",
                         bank_account="1010")
    assert info.value.code == "DOCUMENT_OVERPAID"


def test_proportionate_consolidation_eliminates_only_the_matched_intercompany_amount(tmp_path):
    svc = make_ledger_service(tmp_path)
    parent = make_books(svc)
    sub = svc.create_ledger("Sub", base_currency="USD")["id"]

    # Parent invoices the sub 100; the sub books the payable.
    post(svc, parent, "2026-01-10", [line("1800", debit="100"), line("4800", credit="100")])
    post(svc, sub, "2026-01-10", [line("6800", debit="100"), line("2800", credit="100")])

    group = svc.consolidation.create_group("Group", base_currency="USD")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub, ownership_pct="80")

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert report["status"] == "CONSOLIDATED"
    assert report["balanceSheet"]["balanced"] is True
    totals = {row["code"]: row["net"] for row in report["totals"]}
    # 80 of the 100 pair is eliminated; 20 (the parent's share of an 80%-owned
    # sub) remains visible and is reported, never force-balanced away.
    assert totals["1800"] == "20.00000000"
    assert totals.get("2800", "0.00000000") == "0.00000000"
    warning = next(f for f in report["findings"] if f["code"] == "INTERCOMPANY_OUT_OF_BALANCE")
    assert "20.00000000" in warning["detail"]


def test_journal_csv_round_trips_commas_quotes_and_newlines(tmp_path):
    svc = make_ledger_service(tmp_path)
    lid = make_books(svc)
    memo = 'He said "hi", then left\nline two'
    post(svc, lid, "2026-01-05", [line("1010", debit="10"), line("4000", credit="10")],
         memo=memo)
    export = export_ledger(svc, lid, fmt="journal_csv")
    rows = list(csv.reader(io.StringIO(export["content"])))
    assert rows[0][:2] == ["Date", "Entry"]
    # csv.writer must quote the memo so it survives a round trip as one field.
    assert memo in [row[3] for row in rows[1:] if len(row) > 3]
    assert export["truncated"] is False
