"""Ledger monitors: the fact provider behind them and the monitor shapes.

A monitor is only trustworthy if its facts are: these tests prove the provider
resolves real ledger numbers, returns NOTHING for a ledger it cannot read, and
that each monitor's condition is a valid expression over `ledger.*` variables.
"""

from __future__ import annotations

import asyncio

from harness.advisory.monitors import build_definition, get_monitor
from harness.automation.conditions import extract_variables, parse_condition
from harness.automation.facts import LedgerFactProvider
from ledger_helpers import line, make_ledger, make_service, post

LEDGER_MONITORS = ("ledger_suspense_watch", "ledger_close_blocked",
                   "ledger_receivables_watch")


class _Ctx:
    """The shape the provider reads: a service with a `.ledger` engine."""

    def __init__(self, ledger):
        self.ledger = ledger


def _svc(tmp_path):
    svc = make_service(tmp_path)
    return svc, make_ledger(svc)


def _facts(svc, variables):
    return asyncio.run(LedgerFactProvider(_Ctx(svc)).snapshot(variables))


def test_the_provider_reads_a_real_suspense_balance(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("9999", debit="50"), line("1010", credit="50")])
    facts = _facts(svc, [f"ledger.{lid}.suspense", f"ledger.{lid}.entries"])
    assert facts[f"ledger.{lid}.suspense"] == 50.0
    assert facts[f"ledger.{lid}.entries"] == 1.0


def test_a_blocked_period_is_reported_as_a_blocker_and_not_ready(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("9999", debit="50"), line("1010", credit="50")])
    facts = _facts(svc, [f"ledger.{lid}.blockers", f"ledger.{lid}.ready",
                         f"ledger.{lid}.warnings"])
    assert facts[f"ledger.{lid}.blockers"] >= 1.0
    assert facts[f"ledger.{lid}.ready"] == 0.0
    assert facts[f"ledger.{lid}.warnings"] >= 0.0


def test_open_receivables_come_from_the_subledger(tmp_path):
    svc, lid = _svc(tmp_path)
    customer = svc.create_party(lid, name="Acme", kind="CUSTOMER")
    svc.create_document(
        lid, kind="INVOICE", party_id=customer["id"], issue_date="2026-01-10",
        lines=[{"account_code": "4000", "unit_price": "120"}],
    )
    facts = _facts(svc, [f"ledger.{lid}.open_ar", f"ledger.{lid}.open_ap"])
    assert facts[f"ledger.{lid}.open_ar"] == 120.0
    assert facts[f"ledger.{lid}.open_ap"] == 0.0


def test_an_unknown_ledger_yields_no_fact(tmp_path):
    svc, _ = _svc(tmp_path)
    assert _facts(svc, ["ledger.ledg_missing.suspense"]) == {}


def test_an_unknown_field_yields_no_fact(tmp_path):
    svc, lid = _svc(tmp_path)
    assert _facts(svc, [f"ledger.{lid}.not_a_field"]) == {}


def test_every_ledger_monitor_shape_parses(tmp_path):
    for monitor_id in LEDGER_MONITORS:
        spec = get_monitor(monitor_id)
        assert spec is not None, monitor_id
        values = {param: ("0" if param == "threshold" else "l1")
                  for param in spec.params}
        condition = spec.condition.format(**values)
        parse_condition(condition)
        variables = extract_variables(condition)
        assert variables and all(v.startswith("ledger.") for v in variables), (
            monitor_id, variables)


def test_a_ledger_monitor_is_built_switched_off(tmp_path):
    svc, lid = _svc(tmp_path)
    definition = build_definition("ledger_close_blocked", {"ledger_id": lid})
    assert definition.state == "disabled"
    assert lid in definition.condition.expression
    assert definition.action.type == "run_agent"
    assert definition.tags == ["bot", "monitor"]
