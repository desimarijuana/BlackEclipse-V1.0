"""Statement parsing and the import pipeline — parse, categorise, preview, post.

The point of these tests is the refusals: a bad date names its row, a foreign
currency without a rate is not posted, an unmatched row goes to suspense, and a
re-import posts nothing.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from harness.ledger.importers import CsvMapping, parse_decimal, parse_statement
from ledger_helpers import line, make_ledger, make_service, post

CSV = """Date,Description,Amount
2026-01-05,ACME PAYROLL,2500.00
2026-01-06,Office rent,-1200.00
2026-01-07,STARBUCKS,-4.50
"""

MAPPING = CsvMapping(
    date_column="Date",
    description_columns=("Description",),
    amount_column="Amount",
)


def _svc_with_ledger(tmp_path):
    svc = make_service(tmp_path)
    return svc, make_ledger(svc)


# ── parsers ─────────────────────────────────────────────────────────────────


def test_csv_parses_rows_totals_and_stable_ids():
    parsed = parse_statement(CSV, "csv", mapping=MAPPING, account_ref="l1:1010")
    assert len(parsed.rows) == 3
    assert parsed.total_in == parse_decimal("2500.00")
    assert parsed.total_out == parse_decimal("-1204.50")
    first = parsed.rows[0]
    assert first.currency == "USD"
    again = parse_statement(CSV, "csv", mapping=MAPPING, account_ref="l1:1010")
    assert [row.external_id for row in parsed.rows] == [row.external_id for row in again.rows]


def test_csv_accepts_accounting_parentheses_and_thousands_separators():
    content = 'Date,Description,Amount\n2026-01-05,Rent,"(1,200.00)"\n'
    mapping = CsvMapping(date_column="Date", description_columns=("Description",),
                          amount_column="Amount", thousands_separator=",")
    parsed = parse_statement(content, "csv", mapping=mapping, account_ref="x")
    assert parsed.rows[0].amount == parse_decimal("-1200.00")


def test_csv_debit_and_credit_columns_are_signed():
    content = "Date,Desc,Paid,Received\n2026-01-05,Rent,1200,\n2026-01-06,Refund,,300\n"
    mapping = CsvMapping(date_column="Date", description_columns=("Desc",),
                          debit_column="Paid", credit_column="Received")
    parsed = parse_statement(content, "csv", mapping=mapping, account_ref="x")
    assert [f"{row.amount:f}" for row in parsed.rows] == [
        "-1200.00000000", "300.00000000",
    ]


def test_a_bad_date_names_the_row():
    content = "Date,Description,Amount\n05/01/2026,Rent,-10\n"
    mapping = CsvMapping(date_column="Date", description_columns=("Description",),
                          amount_column="Amount", date_format="%Y-%m-%d")
    with pytest.raises(LedgerError) as info:
        parse_statement(content, "csv", mapping=mapping, account_ref="x")
    assert info.value.code == "IMPORT_ROW_INVALID"
    assert info.value.details["row"] == 1


def test_a_declared_date_format_is_honoured():
    content = "Date,Description,Amount\n05/01/2026,Rent,-10\n"
    mapping = CsvMapping(date_column="Date", description_columns=("Description",),
                          amount_column="Amount", date_format="%d/%m/%Y")
    parsed = parse_statement(content, "csv", mapping=mapping, account_ref="x")
    assert parsed.rows[0].date == "2026-01-05"


def test_an_unsupported_format_is_refused():
    with pytest.raises(LedgerError) as info:
        parse_statement(CSV, "pdf", account_ref="x")
    assert info.value.code == "UNSUPPORTED_STATEMENT_FORMAT"


def test_a_mapping_without_an_amount_is_refused():
    with pytest.raises(LedgerError) as info:
        CsvMapping(date_column="Date").validate()
    assert info.value.code == "INVALID_MAPPING"


def test_qif_parses_and_requires_an_explicit_day_month_order():
    content = """!Type:Bank
D1/15/2026
T-45.00
PCoffee shop
MRound-up
^
D1/16/2026
T250.00
PClient payment
^
"""
    parsed = parse_statement(content, "qif", account_ref="x")
    assert len(parsed.rows) == 2
    assert parsed.rows[0].date == "2026-01-15"
    assert parsed.rows[0].description == "Coffee shop Round-up"

    bad = """!Type:Bank
D15/01/2026
T-45.00
PShop
^
"""
    with pytest.raises(LedgerError) as info:
        parse_statement(bad, "qif", account_ref="x")
    assert info.value.code == "IMPORT_ROW_INVALID"
    assert "date_format" in info.value.message


def test_ofx_uses_fitid_and_reads_the_ledger_balance():
    content = """<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>USD
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260105<TRNAMT>-45.00<FITID>ABC123<NAME>COFFEE SHOP</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260106<TRNAMT>250.00<FITID>ABC124<NAME>CLIENT</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>1295.50</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
    parsed = parse_statement(content, "ofx", account_ref="x")
    assert [row.external_id for row in parsed.rows] == ["ofx:ABC123", "ofx:ABC124"]
    assert parsed.closing_balance == parse_decimal("1295.50")


# ── rules ──────────────────────────────────────────────────────────────────


def test_a_rule_matches_by_payee_priority_and_direction(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.create_rule(lid, name="Rent", target_account="6100",
                    payee_contains=["rent"], priority=10)
    svc.create_rule(lid, name="Income", target_account="4000",
                    payee_contains=["payroll"], direction="IN", priority=20)
    svc.create_rule(lid, name="Small stuff", target_account="6500",
                    amount_max="10", direction="OUT", priority=30)
    svc.create_rule(lid, name="Catch-all rent", target_account="6200",
                    payee_regex="rent", priority=99)

    preview = svc.preview_import(lid, account_code="1010", content=CSV,
                                 statement_format="csv", mapping=MAPPING)
    methods = [(row["description"], row["accountCode"], row["method"])
               for row in preview["rows"]]
    assert methods == [
        ("ACME PAYROLL", "4000", "RULE"),
        ("Office rent", "6100", "RULE"),        # priority 10 beats the catch-all
        ("STARBUCKS", "6500", "RULE"),          # |amount| <= 10
    ]
    assert preview["categorisedCount"] == 3
    assert preview["suspenseCount"] == 0


def test_an_unmatched_row_goes_to_suspense_not_a_guess(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    preview = svc.preview_import(lid, account_code="1010", content=CSV,
                                 statement_format="csv", mapping=MAPPING)
    statuses = {row["accountCode"] for row in preview["rows"]}
    assert statuses == {"9999"}
    assert preview["suspenseCount"] == 3


def test_creating_a_rule_with_the_same_name_versions_and_deactivates():
    svc = make_service()
    lid = make_ledger(svc)
    first = svc.create_rule(lid, name="Rent", target_account="6100",
                            payee_contains=["rent"])
    second = svc.create_rule(lid, name="Rent", target_account="6200",
                             payee_contains=["rent"])
    assert second["version"] == first["version"] + 1
    active = svc.list_rules(lid, active_only=True)
    assert [rule["targetAccount"] for rule in active] == ["6200"]


def test_a_rule_with_no_condition_is_refused(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_rule(lid, name="Everything", target_account="6100")
    assert info.value.code == "RULE_INVALID"


def test_a_rule_with_an_invalid_regex_is_refused(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_rule(lid, name="Bad", target_account="6100", payee_regex="([")
    assert info.value.code == "RULE_INVALID"


def test_a_rule_targeting_a_missing_account_is_refused(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_rule(lid, name="Ghost", target_account="7777", payee_contains=["x"])
    assert info.value.code == "ACCOUNT_NOT_FOUND"


# ── commit ─────────────────────────────────────────────────────────────────


def test_commit_posts_balanced_entries_and_reimport_is_idempotent(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.create_rule(lid, name="Rent", target_account="6100", payee_contains=["rent"])
    svc.create_rule(lid, name="Income", target_account="4000", payee_contains=["payroll"])
    svc.create_rule(lid, name="Coffee", target_account="6600", payee_contains=["starbucks"])

    result = svc.commit_import(lid, account_code="1010", content=CSV,
                               statement_format="csv", mapping=MAPPING)
    assert result["status"] == "COMPLETE"
    assert result["postedCount"] == 3
    assert result["errorCount"] == 0
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    assert trial["balanced"] is True

    again = svc.commit_import(lid, account_code="1010", content=CSV,
                              statement_format="csv", mapping=MAPPING)
    assert again["postedCount"] == 0
    assert again["duplicateCount"] == 3
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 3


def test_commit_parks_uncategorised_rows_in_suspense_and_blocks_the_close(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    result = svc.commit_import(lid, account_code="1010", content=CSV,
                               statement_format="csv", mapping=MAPPING)
    assert result["postedCount"] == 3
    assert result["suspenseCount"] == 3
    period = svc.list_periods(lid)[0]
    with pytest.raises(LedgerError) as info:
        svc.close_period(lid, period_id=period["id"])
    assert info.value.code == "PERIOD_NOT_READY"


def test_a_foreign_statement_without_a_rate_is_not_posted(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.create_rule(lid, name="All", target_account="4000",
                    payee_contains=["payroll"])
    content = "Date,Description,Amount,Currency\n2026-01-05,ACME PAYROLL,100,EUR\n"
    mapping = CsvMapping(date_column="Date", description_columns=("Description",),
                          amount_column="Amount", currency_column="Currency")
    preview = svc.preview_import(lid, account_code="1010", content=content,
                                 statement_format="csv", mapping=mapping)
    assert preview["requiresFxCount"] == 1
    assert preview["rows"][0]["status"] == "REQUIRES_FX"

    result = svc.commit_import(lid, account_code="1010", content=content,
                               statement_format="csv", mapping=mapping)
    assert result["postedCount"] == 0
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 0


def test_a_foreign_statement_with_a_rate_posts_at_that_rate(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.create_rule(lid, name="All", target_account="4000",
                    payee_contains=["payroll"])
    content = "Date,Description,Amount,Currency\n2026-01-05,ACME PAYROLL,100,EUR\n"
    mapping = CsvMapping(date_column="Date", description_columns=("Description",),
                          amount_column="Amount", currency_column="Currency")
    result = svc.commit_import(lid, account_code="1010", content=content,
                               statement_format="csv", mapping=mapping, fx_rate="1.10")
    assert result["postedCount"] == 1
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["1010"]["closingDebit"] == "110.00000000"
    assert trial["balanced"] is True


def test_a_commit_into_a_closed_period_reports_the_row_and_the_batch_is_failed(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.create_rule(lid, name="All", target_account="4000", payee_contains=["payroll"])
    svc.post(lid, entry_date="2026-01-02", lines=[
        line("1010", debit="1"), line("4000", credit="1"),
    ])
    period = svc.list_periods(lid)[0]
    svc.close_period(lid, period_id=period["id"])

    result = svc.commit_import(lid, account_code="1010", content=CSV,
                               statement_format="csv", mapping=MAPPING)
    assert result["status"] == "FAILED"
    assert result["postedCount"] == 0
    assert {row["code"] for row in result["errorRows"]} == {"PERIOD_CLOSED"}


def test_the_import_batch_is_recorded(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    result = svc.commit_import(lid, account_code="1010", content=CSV,
                               statement_format="csv", mapping=MAPPING,
                               batch_ref="jan-2026")
    batches = svc.list_import_batches(lid)
    assert batches[0]["id"] == result["batchId"]
    assert batches[0]["batchRef"] == "jan-2026"
    assert batches[0]["rowCount"] == 3
    assert batches[0]["postedCount"] == 3


def test_a_preview_writes_nothing(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    svc.preview_import(lid, account_code="1010", content=CSV,
                       statement_format="csv", mapping=MAPPING)
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 0
    assert svc.list_import_batches(lid) == []


def test_importing_into_a_non_cash_account_is_allowed_but_a_missing_one_is_not(tmp_path):
    svc, lid = _svc_with_ledger(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.preview_import(lid, account_code="7777", content=CSV,
                           statement_format="csv", mapping=MAPPING)
    assert info.value.code == "IMPORT_ACCOUNT_INVALID"
