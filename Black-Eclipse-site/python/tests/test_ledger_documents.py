"""AR/AP subledger: invoices, bills, tax codes, payments and aging.

The properties that matter: a document posts through the normal journal path and
balances; the open item is derived, never cached; aging reconciles to the control
account; and every refusal (unknown tax code, wrong party kind, over-payment,
voiding a paid invoice) is a named error.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from ledger_helpers import line, make_ledger, make_service, post


def _svc(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    svc.create_account(lid, code="1400", name="VAT recoverable", account_type="ASSET",
                       subtype="RECOVERABLE")
    return svc, lid


def _setup(svc, lid, *, rate="0.20"):
    customer = svc.create_party(lid, name="Acme Client", kind="CUSTOMER",
                                payment_terms_days=14)
    vendor = svc.create_party(lid, name="Office Supply Co", kind="VENDOR")
    svc.create_tax_code(lid, code="VAT-S", name="Sales VAT", jurisdiction="GB",
                        rate=rate, account_code="2100")
    svc.create_tax_code(lid, code="VAT-P", name="Purchase VAT", jurisdiction="GB",
                        rate=rate, account_code="1400")
    return customer, vendor


def _invoice(svc, lid, customer, *, amount="1000", quantity="1", tax="VAT-S",
             due_date="2026-02-14", issue_date="2026-01-15"):
    return svc.create_document(
        lid, kind="INVOICE", party_id=customer["id"], issue_date=issue_date,
        due_date=due_date,
        lines=[{"description": "Consulting", "account_code": "4000",
                "quantity": quantity, "unit_price": amount, "tax_code": tax}],
    )


# ── tax codes ──────────────────────────────────────────────────────────────


def test_a_tax_code_is_configured_data_never_a_bundled_rate(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_document(
            lid, kind="INVOICE", party_id="missing", issue_date="2026-01-01",
            lines=[{"account_code": "4000", "unit_price": "100", "tax_code": "VAT"}],
        )
    assert info.value.code in ("PARTY_NOT_FOUND",)

    customer = svc.create_party(lid, name="C", kind="CUSTOMER")
    svc.create_tax_code(lid, code="VAT-S", jurisdiction="GB", rate="0.20",
                        account_code="2100")
    codes = svc.list_tax_codes(lid)
    assert codes[0]["code"] == "VAT-S"
    assert codes[0]["rate"] == "0.2000000000"


def test_an_unconfigured_tax_code_is_refused(tmp_path):
    svc, lid = _svc(tmp_path)
    customer = svc.create_party(lid, name="C", kind="CUSTOMER")
    with pytest.raises(LedgerError) as info:
        svc.create_document(
            lid, kind="INVOICE", party_id=customer["id"], issue_date="2026-01-01",
            lines=[{"account_code": "4000", "unit_price": "100", "tax_code": "XX"}],
        )
    assert info.value.code == "TAX_CODE_NOT_FOUND"


def test_a_duplicate_tax_code_is_refused(tmp_path):
    svc, lid = _svc(tmp_path)
    svc.create_tax_code(lid, code="VAT-S", jurisdiction="GB", rate="0.20",
                        account_code="2100")
    with pytest.raises(LedgerError) as info:
        svc.create_tax_code(lid, code="VAT-S", jurisdiction="GB", rate="0.20",
                            account_code="2100")
    assert info.value.code == "TAX_CODE_INVALID"


def test_a_rate_is_a_fraction_not_a_percentage(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_tax_code(lid, code="BAD", jurisdiction="GB", rate="20",
                            account_code="2100")
    assert info.value.code == "TAX_CODE_INVALID"


# ── invoices and bills ─────────────────────────────────────────────────────


def test_an_invoice_posts_through_the_journal_and_balances(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    assert invoice["number"] == "INV-0001"
    assert invoice["subtotal"] == "1000.00000000"
    assert invoice["taxTotal"] == "200.00000000"
    assert invoice["total"] == "1200.00000000"
    assert invoice["outstanding"] == "1200.00000000"

    trial = svc.trial_balance(lid, as_of="2026-01-31")
    assert trial["balanced"] is True
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["1100"]["closingDebit"] == "1200.00000000"
    assert rows["4000"]["closingCredit"] == "1000.00000000"
    assert rows["2100"]["closingCredit"] == "200.00000000"

    sheet = svc.balance_sheet(lid, as_of="2026-01-31")
    assert sheet["balanced"] is True


def test_a_bill_posts_the_expense_and_recoverable_tax(tmp_path):
    svc, lid = _svc(tmp_path)
    _, vendor = _setup(svc, lid)
    bill = svc.create_document(
        lid, kind="BILL", party_id=vendor["id"], issue_date="2026-01-10",
        lines=[{"description": "Paper", "account_code": "6300",
                "quantity": "1", "unit_price": "100", "tax_code": "VAT-P"}],
    )
    assert bill["number"] == "BILL-0001"
    assert bill["total"] == "120.00000000"
    rows = {row["code"]: row for row in svc.trial_balance(lid, as_of="2026-01-31")["rows"]}
    assert rows["6300"]["closingDebit"] == "100.00000000"
    assert rows["1400"]["closingDebit"] == "20.00000000"
    assert rows["2000"]["closingCredit"] == "120.00000000"


def test_inclusive_pricing_recovers_the_net_exactly(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    svc.create_tax_code(lid, code="VAT-INC", jurisdiction="GB", rate="0.20",
                        account_code="2100", price_includes_tax=True)
    invoice = svc.create_document(
        lid, kind="INVOICE", party_id=customer["id"], issue_date="2026-01-15",
        lines=[{"account_code": "4000", "unit_price": "120", "tax_code": "VAT-INC"}],
    )
    assert invoice["subtotal"] == "100.00000000"
    assert invoice["taxTotal"] == "20.00000000"
    assert invoice["total"] == "120.00000000"


def test_a_document_needs_the_right_party_kind(tmp_path):
    svc, lid = _svc(tmp_path)
    _, vendor = _setup(svc, lid)
    with pytest.raises(LedgerError) as info:
        svc.create_document(
            lid, kind="INVOICE", party_id=vendor["id"], issue_date="2026-01-15",
            lines=[{"account_code": "4000", "unit_price": "10"}],
        )
    assert info.value.code == "PARTY_INVALID"


def test_document_numbers_are_sequential_and_unique(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    assert _invoice(svc, lid, customer)["number"] == "INV-0001"
    assert _invoice(svc, lid, customer)["number"] == "INV-0002"
    with pytest.raises(LedgerError) as info:
        svc.create_document(
            lid, kind="INVOICE", party_id=customer["id"], issue_date="2026-01-15",
            number="INV-0001",
            lines=[{"account_code": "4000", "unit_price": "10"}],
        )
    assert info.value.code == "DOCUMENT_NUMBER_EXISTS"


def test_a_document_total_must_be_positive(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    with pytest.raises(LedgerError) as info:
        svc.create_document(
            lid, kind="INVOICE", party_id=customer["id"], issue_date="2026-01-15",
            lines=[{"account_code": "4000", "unit_price": "0"}],
        )
    assert info.value.code == "DOCUMENT_INVALID"


# ── payments ───────────────────────────────────────────────────────────────


def test_a_partial_then_full_payment_settles_the_invoice(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)

    first = svc.pay_document(lid, invoice["id"], date_paid="2026-01-20",
                             amount="500", bank_account="1010", reference="rcpt-1")
    assert first["status"] == "PARTIALLY_PAID"
    assert first["outstanding"] == "700.00000000"

    second = svc.pay_document(lid, invoice["id"], date_paid="2026-02-01",
                              amount="700", bank_account="1010", reference="rcpt-2")
    assert second["status"] == "PAID"
    assert second["outstanding"] == "0.00000000"

    rows = {row["code"]: row
            for row in svc.trial_balance(lid, as_of="2026-02-28")["rows"]}
    assert rows["1100"]["closingDebit"] == "0.00000000"
    assert rows["1010"]["closingDebit"] == "1200.00000000"


def test_an_overpayment_is_refused(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    with pytest.raises(LedgerError) as info:
        svc.pay_document(lid, invoice["id"], date_paid="2026-01-20",
                         amount="1200.01", bank_account="1010")
    assert info.value.code == "DOCUMENT_OVERPAID"


def test_a_repeated_payment_reference_posts_once(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    args = dict(date_paid="2026-01-20", amount="500", bank_account="1010",
                reference="rcpt-1")
    svc.pay_document(lid, invoice["id"], **args)
    again = svc.pay_document(lid, invoice["id"], **args)
    assert again["duplicate"] is True
    assert again["outstanding"] == "700.00000000"     # not double-counted
    document = svc.get_document(lid, invoice["id"])
    assert len(document["allocations"]) == 1


def test_a_bill_is_paid_from_the_bank(tmp_path):
    svc, lid = _svc(tmp_path)
    _, vendor = _setup(svc, lid)
    bill = svc.create_document(
        lid, kind="BILL", party_id=vendor["id"], issue_date="2026-01-10",
        lines=[{"account_code": "6300", "unit_price": "100", "tax_code": "VAT-P"}],
    )
    paid = svc.pay_document(lid, bill["id"], date_paid="2026-01-25", amount="120",
                            bank_account="1010")
    assert paid["status"] == "PAID"
    rows = {row["code"]: row for row in svc.trial_balance(lid, as_of="2026-01-31")["rows"]}
    assert rows["1010"]["closingCredit"] == "120.00000000"
    # The bill and its payment net the payable control account to zero.
    assert rows["2000"]["closingDebit"] == "0.00000000"
    assert rows["2000"]["closingCredit"] == "0.00000000"


def test_a_payment_needs_a_cash_account(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    with pytest.raises(LedgerError) as info:
        svc.pay_document(lid, invoice["id"], date_paid="2026-01-20", amount="10",
                         bank_account="4000")
    assert info.value.code == "DOCUMENT_INVALID"


# ── void ───────────────────────────────────────────────────────────────────


def test_voiding_an_unpaid_invoice_reverses_the_journal(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    voided = svc.void_document(lid, invoice["id"], reason="issued in error")
    assert voided["status"] == "VOID"
    rows = {row["code"]: row for row in svc.trial_balance(lid, as_of="2026-01-31")["rows"]}
    assert rows["1100"]["closingDebit"] == "0.00000000"
    assert rows["4000"]["closingCredit"] == "0.00000000"
    assert svc.balance_sheet(lid, as_of="2026-01-31")["balanced"] is True


def test_a_paid_invoice_cannot_be_voided(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer)
    svc.pay_document(lid, invoice["id"], date_paid="2026-01-20", amount="100",
                     bank_account="1010")
    with pytest.raises(LedgerError) as info:
        svc.void_document(lid, invoice["id"])
    assert info.value.code == "DOCUMENT_HAS_PAYMENTS"


# ── aging ──────────────────────────────────────────────────────────────────


def test_aging_buckets_and_reconciles_to_the_control_account(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    _invoice(svc, lid, customer, amount="100", due_date="2026-02-28",
             issue_date="2026-01-15")
    _invoice(svc, lid, customer, amount="200", due_date="2026-01-05",
             issue_date="2025-12-15")
    _invoice(svc, lid, customer, amount="300", due_date="2025-10-01",
             issue_date="2025-09-01")

    report = svc.aging(lid, kind="AR", as_of="2026-01-31")
    # 100 not yet due, 200 26 days overdue, 300 122 days overdue.
    assert report["buckets"]["current"] == "120.00000000"
    assert report["buckets"]["1-30"] == "240.00000000"
    assert report["buckets"]["90+"] == "360.00000000"
    assert report["openTotal"] == "720.00000000"
    assert report["controlBalance"] == "720.00000000"
    assert report["reconciled"] is True
    assert len(report["parties"]) == 1
    assert report["parties"][0]["oldestDays"] == 122


def test_aging_uses_allocations_as_of_the_report_date(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    invoice = _invoice(svc, lid, customer, amount="1000")
    svc.pay_document(lid, invoice["id"], date_paid="2026-02-10", amount="1200",
                     bank_account="1010")
    january = svc.aging(lid, kind="AR", as_of="2026-01-31")
    assert january["openTotal"] == "1200.00000000"      # the payment is in February
    february = svc.aging(lid, kind="AR", as_of="2026-02-28")
    assert february["openTotal"] == "0.00000000"


def test_ap_aging_uses_the_payable_control_account(tmp_path):
    svc, lid = _svc(tmp_path)
    _, vendor = _setup(svc, lid)
    svc.create_document(lid, kind="BILL", party_id=vendor["id"],
                        issue_date="2026-01-01", due_date="2026-01-31",
                        lines=[{"account_code": "6300", "unit_price": "100"}])
    report = svc.aging(lid, kind="AP", as_of="2026-01-31")
    assert report["controlAccount"] == "2000"
    assert report["openTotal"] == "100.00000000"
    assert report["reconciled"] is True


def test_a_manual_posting_to_the_control_account_breaks_the_aging_check(tmp_path):
    svc, lid = _svc(tmp_path)
    customer, _ = _setup(svc, lid)
    _invoice(svc, lid, customer, amount="100")
    # A manual AR posting that no document explains — the check must notice.
    post(svc, lid, "2026-01-20", [line("1100", debit="50"), line("4000", credit="50")])
    report = svc.aging(lid, kind="AR", as_of="2026-01-31")
    assert report["reconciled"] is False
    assert report["difference"] == "-50.00000000"
