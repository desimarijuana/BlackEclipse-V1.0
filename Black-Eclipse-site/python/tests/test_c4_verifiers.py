"""C4.2: the verifier registry and its deterministic built-ins."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.goals import (
    EvidenceLedger,
    VerificationContext,
    default_registry,
    handle,
)
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-verify-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_1", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


def _ctx(finance: bool = False, checks=()) -> VerificationContext:
    return VerificationContext(run_id="run_1", finance_domain=finance, checks=tuple(checks))


def _claim(ledger, text, handles=(), status="unverified"):
    return ledger.record(run_id="run_1", text=text, handles=list(handles), status=status)


def test_a_finance_number_without_a_computation_is_rejected(store):
    ledger = EvidenceLedger(store)
    claim = _claim(ledger, "AAPL returned 18.4% last year", status="unverified")
    verdict = default_registry().verify_claim(claim, _ctx(finance=True))
    assert verdict.ok is False
    assert verdict.verifier == "finance_number"
    assert "no computation" in verdict.reason


def test_a_finance_number_with_a_computation_is_supported(store):
    ledger = EvidenceLedger(store)
    claim = _claim(
        ledger, "AAPL returned 18.4% last year",
        handles=[handle("computation", "calc_run_1", source="quant")],
    )
    verdict = default_registry().verify_claim(claim, _ctx(finance=True))
    assert verdict.ok is True


def test_a_bare_run_handle_does_not_support_a_finance_number(store):
    ledger = EvidenceLedger(store)
    claim = _claim(
        ledger, "The P/E is 28.1",
        handles=[handle("run", "run_1")],
    )
    verdict = default_registry().verify_claim(claim, _ctx(finance=True))
    assert verdict.ok is False


def test_a_url_claim_needs_a_citation(store):
    registry = default_registry()
    ledger = EvidenceLedger(store)
    without = _claim(ledger, "See https://example.test/report for the figure")
    assert registry.verify_claim(without, _ctx()).ok is False

    with_citation = _claim(
        ledger, "See https://example.test/report for the figure",
        handles=[handle("citation", "https://example.test/report")],
    )
    assert registry.verify_claim(with_citation, _ctx()).ok is True


def test_a_test_claim_needs_a_passing_check(store):
    registry = default_registry()
    ledger = EvidenceLedger(store)
    without = _claim(ledger, "All tests passed")
    assert registry.verify_claim(without, _ctx()).ok is False

    with_check = _claim(
        ledger, "All tests passed",
        handles=[handle("record", "check_1", source="pytest")],
    )
    assert registry.verify_claim(with_check, _ctx()).ok is True

    with_context = _claim(ledger, "The build passed")
    assert registry.verify_claim(
        with_context, _ctx(checks=[{"id": "c1", "status": "passed"}]),
    ).ok is True


def test_a_produced_file_claim_needs_a_file_or_artifact(store):
    registry = default_registry()
    ledger = EvidenceLedger(store)
    without = _claim(ledger, "I wrote risk_brief.pdf")
    assert registry.verify_claim(without, _ctx()).ok is False

    with_file = _claim(
        ledger, "I wrote risk_brief.pdf",
        handles=[handle("artifact", "art_1")],
    )
    assert registry.verify_claim(with_file, _ctx()).ok is True


def test_generic_prose_without_a_handle_is_unverified_not_supported(store):
    ledger = EvidenceLedger(store)
    claim = _claim(ledger, "The outlook is uncertain")
    verdict = default_registry().verify_claim(claim, _ctx())
    assert verdict.ok is False
    assert verdict.verifier == "evidence"


def test_the_code_ledger_is_adapted_into_checks():
    from harness.goals.verifiers import checks_from_ledger

    class Record:
        command_execution_id = "exec_1"
        command_class = "unit_test"
        exit_code = 0

    class Ledger:
        def records(self):
            return [Record()]

    assert checks_from_ledger(Ledger()) == (
        {"id": "exec_1", "kind": "unit_test", "status": "passed"},
    )
    assert checks_from_ledger(None) == ()


def test_verify_run_updates_statuses_and_aggregates(store):
    ledger = EvidenceLedger(store)
    _claim(ledger, "AAPL returned 18.4%", status="unverified")
    _claim(
        ledger, "AAPL returned 18.4%",
        handles=[handle("computation", "calc_1")],
    )
    _claim(ledger, "The outlook is uncertain")

    result = default_registry().verify_run(ledger, "run_1", _ctx(finance=True))
    assert result.supported == 1
    assert result.unsupported == 1
    assert result.unverified == 1
    assert result.ok is False

    statuses = {claim.status for claim in ledger.claims("run_1")}
    assert statuses == {"supported", "unsupported", "unverified"}
