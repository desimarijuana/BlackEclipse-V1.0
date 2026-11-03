"""Entity groups and consolidation: aggregate, eliminate, check.

The invariants: a member is included proportionately, a foreign member needs a
supplied rate (never an invented one), accounts are matched by code AND type, and
only the MATCHED intercompany amount is eliminated — an unmatched remainder is
reported rather than force-balanced.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from ledger_helpers import line, make_service, post


def _svc(tmp_path):
    return make_service(tmp_path)


def _ledger(svc, name, currency="USD"):
    return svc.create_ledger(name, base_currency=currency)["id"]


def _intercompany_pair(svc, parent, sub, amount="100"):
    post(svc, parent, "2026-01-10", [
        line("1800", debit=amount), line("4800", credit=amount),
    ])
    post(svc, sub, "2026-01-10", [
        line("6800", debit=amount), line("2800", credit=amount),
    ])


# ── groups ─────────────────────────────────────────────────────────────────


def test_a_group_lists_its_members(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub")
    group = svc.consolidation.create_group("Group", base_currency="USD")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub, ownership_pct="80")
    rows = svc.consolidation.list_groups()
    assert rows[0]["id"] == group["id"]
    assert [(m["ledgerId"], m["ownershipPct"]) for m in rows[0]["members"]] == [
        (parent, "100.0000000000"),
        (sub, "80.0000000000"),
    ]


def test_a_ledger_cannot_join_a_group_twice(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    group = svc.consolidation.create_group("Group")
    svc.consolidation.add_member(group["id"], parent)
    with pytest.raises(LedgerError) as info:
        svc.consolidation.add_member(group["id"], parent)
    assert info.value.code == "MEMBER_EXISTS"


def test_an_unknown_group_or_ledger_is_a_named_error(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.consolidation.add_member("grp_missing", "ledg_missing")
    assert info.value.code == "GROUP_NOT_FOUND"

    group = svc.consolidation.create_group("Group")
    with pytest.raises(LedgerError) as info:
        svc.consolidation.add_member(group["id"], "ledg_missing")
    assert info.value.code == "MEMBER_LEDGER_MISSING"


def test_an_empty_group_cannot_consolidate(tmp_path):
    svc = _svc(tmp_path)
    group = svc.consolidation.create_group("Empty")
    with pytest.raises(LedgerError) as info:
        svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert info.value.code == "GROUP_INVALID"


def test_ownership_must_be_a_percentage(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    group = svc.consolidation.create_group("Group")
    with pytest.raises(LedgerError) as info:
        svc.consolidation.add_member(group["id"], parent, ownership_pct="120")
    assert info.value.code == "GROUP_INVALID"


# ── consolidation ─────────────────────────────────────────────────────────


def test_intercompany_pairs_are_eliminated(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub")
    _intercompany_pair(svc, parent, sub)
    group = svc.consolidation.create_group("Group")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub)

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert report["status"] == "CONSOLIDATED"
    assert report["balanceSheet"]["balanced"] is True
    assert report["balanceSheet"]["assets"]["total"] == "0.00000000"
    assert report["balanceSheet"]["liabilities"]["total"] == "0.00000000"

    kinds = {elimination["kind"]: elimination for elimination in report["eliminations"]}
    assert kinds["BALANCE_SHEET"]["amount"] == "100.00000000"
    assert kinds["PROFIT_AND_LOSS"]["amount"] == "100.00000000"
    assert all(elimination["balanced"] for elimination in report["eliminations"])
    assert not any(f["severity"] == "blocker" for f in report["findings"])

    # Nothing intercompany survives into the consolidated statements.
    revenue = report["incomeStatement"]["revenue"]["total"]
    expenses = report["incomeStatement"]["totalExpenses"]
    assert revenue == "0.00000000"
    assert expenses == "0.00000000"


def test_an_unmatched_intercompany_balance_is_reported_not_balanced(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub")
    _intercompany_pair(svc, parent, sub, amount="100")
    # The sub only books 80 of it.
    post(svc, sub, "2026-01-11", [line("2800", debit="20"), line("6800", credit="20")])
    group = svc.consolidation.create_group("Group")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub)

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    finding = next(f for f in report["findings"]
                   if f["code"] == "INTERCOMPANY_OUT_OF_BALANCE")
    assert finding["severity"] == "warning"
    assert "20.00000000" in finding["detail"]
    # The remaining 20 stays as a consolidated receivable — visible, not hidden.
    totals = {row["code"]: row["net"] for row in report["totals"]}
    assert totals["1800"] == "20.00000000"
    assert report["balanceSheet"]["balanced"] is True


def test_a_member_can_be_included_proportionately(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub")
    post(svc, sub, "2026-01-10", [line("1010", debit="200"), line("4000", credit="200")])
    group = svc.consolidation.create_group("Group")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub, ownership_pct="50")

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert report["ownershipMethod"] == "PROPORTIONATE"
    totals = {row["code"]: row["net"] for row in report["totals"]}
    assert totals["4000"] == "-100.00000000"
    assert report["balanceSheet"]["assets"]["total"] == "100.00000000"


def test_a_foreign_member_needs_a_supplied_rate(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub", currency="EUR")
    post(svc, sub, "2026-01-10", [line("1010", debit="100"), line("4000", credit="100")])
    group = svc.consolidation.create_group("Group", base_currency="USD")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub)

    blocked = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert blocked["status"] == "BLOCKED"
    assert any(f["code"] == "RATE_REQUIRED" for f in blocked["findings"])

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31",
                                           rates={"EUR": "1.20"})
    assert report["status"] == "CONSOLIDATED"
    totals = {row["code"]: row["net"] for row in report["totals"]}
    assert totals["1010"] == "120.00000000"


def test_a_code_with_two_account_types_is_a_conflict(tmp_path):
    svc = _svc(tmp_path)
    parent = _ledger(svc, "Parent")
    sub = _ledger(svc, "Sub")
    svc.create_account(sub, code="1900", name="Odd", account_type="LIABILITY")
    svc.create_account(parent, code="1900", name="Odd", account_type="ASSET")
    group = svc.consolidation.create_group("Group")
    svc.consolidation.add_member(group["id"], parent)
    svc.consolidation.add_member(group["id"], sub)

    report = svc.consolidation.consolidate(group["id"], as_of="2026-01-31")
    assert report["status"] == "BLOCKED"
    assert any(f["code"] == "ACCOUNT_TYPE_CONFLICT" for f in report["findings"])
