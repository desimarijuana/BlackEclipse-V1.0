"""Exports: CSV, JSON and a well-formed-but-not-filing XBRL instance.

The refusals matter as much as the formats: SAF-T is declined with a reason rather
than approximated, and the XBRL document says in its own comment that it is not
taxonomy-conformant.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET

import pytest

from harness.ledger.errors import LedgerError
from harness.ledger.exports import export
from ledger_helpers import line, make_ledger, make_service, post


def _svc(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-05", [line("1010", debit="1000"), line("3000", credit="1000")])
    post(svc, lid, "2026-01-10", [line("6100", debit="100"), line("1010", credit="100")])
    return svc, lid


def test_journal_csv_has_one_row_per_line(tmp_path):
    svc, lid = _svc(tmp_path)
    result = export(svc, lid, fmt="journal_csv")
    assert result["contentType"] == "text/csv"
    rows = list(csv.reader(io.StringIO(result["content"])))
    assert rows[0][0] == "Date"
    assert len(rows) == 5          # header + 4 lines
    body = "\n".join(result["content"].splitlines()[1:])
    assert "1010" in body and "3000" in body and "6100" in body
    assert "1000.00000000" in body


def test_trial_balance_csv_totals_balance(tmp_path):
    svc, lid = _svc(tmp_path)
    result = export(svc, lid, fmt="trial_balance_csv")
    rows = list(csv.reader(io.StringIO(result["content"])))
    assert rows[0][0] == "Account Code"
    totals = rows[-1]
    assert totals[7] == totals[8]     # closing debit == closing credit


def test_json_bundle_carries_the_statements(tmp_path):
    svc, lid = _svc(tmp_path)
    result = export(svc, lid, fmt="json")
    payload = json.loads(result["content"])
    assert payload["ledger"]["id"] == lid
    assert payload["trialBalance"]["balanced"] is True
    assert payload["balanceSheet"]["balanced"] is True
    assert payload["incomeStatement"]["endDate"]
    assert payload["entries"][0]["entryNo"] >= 1
    assert result["contentType"] == "application/json"


def test_xbrl_is_well_formed_and_says_it_is_not_a_filing(tmp_path):
    svc, lid = _svc(tmp_path)
    result = export(svc, lid, fmt="xbrl")
    assert "NOT taxonomy-conformant" in result["content"]
    root = ET.fromstring(result["content"])
    assert root.tag.endswith("xbrl")
    facts = {child.tag.split("}")[-1]: child.text for child in root}
    assert facts["Assets"] == "900.00000000"
    assert facts["NetIncome"] == "-100.00000000"
    assert "iso4217:USD" in result["content"]


def test_saft_is_refused_with_a_reason(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        export(svc, lid, fmt="saft")
    assert info.value.code == "UNSUPPORTED_EXPORT"
    assert "jurisdiction" in info.value.message.lower()


def test_an_unknown_format_is_refused(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        export(svc, lid, fmt="docx")
    assert info.value.code == "UNSUPPORTED_EXPORT"


def test_a_reversed_date_range_is_refused(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        export(svc, lid, fmt="journal_csv", start="2026-02-01", end="2026-01-01")
    assert info.value.code == "UNSUPPORTED_EXPORT"


def test_the_export_is_recorded_in_the_audit_trail(tmp_path):
    svc, lid = _svc(tmp_path)
    export(svc, lid, fmt="json")
    kinds = [event["kind"] for event in svc.audit_log(lid)]
    assert "LEDGER_EXPORTED" in kinds
