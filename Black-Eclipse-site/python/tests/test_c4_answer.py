"""C4.4: the answer seam records checkable claims and discloses rejections."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.goals.answer import enforce_evidence_answer
from harness.goals.ledger import EvidenceLedger, handle
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-answer-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_1", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


@pytest.mark.asyncio
async def test_a_finance_number_without_evidence_is_disclosed(store):
    output, blob = await enforce_evidence_answer(
        "AAPL returned 18.4% last year.", store, "run_1", enforce=True,
    )
    assert "Evidence check" in output
    assert blob["unsupported"] == 1
    assert blob["enforced"] is True
    assert "18.4%" in output


@pytest.mark.asyncio
async def test_a_finance_number_backed_by_a_tool_record_is_supported(store):
    ledger = EvidenceLedger(store)
    ledger.record(
        run_id="run_1", text="get_quote: 190.12", status="supported",
        verifier="tool_result",
        handles=[handle("record", "tool:run_1:c1", source="get_quote")],
    )
    output, blob = await enforce_evidence_answer(
        "AAPL last traded at $190.12.", store, "run_1", enforce=True,
    )
    assert "Evidence check" not in output
    assert blob["supported"] >= 1
    assert blob["enforced"] is False


@pytest.mark.asyncio
async def test_generic_prose_is_left_alone(store):
    text = "The outlook is uncertain but the team remains focused."
    output, blob = await enforce_evidence_answer(text, store, "run_1", enforce=True)
    assert output == text
    assert blob["claims"] == 0


@pytest.mark.asyncio
async def test_a_url_claim_needs_a_citation_handle(store):
    ledger = EvidenceLedger(store)
    ledger.record(
        run_id="run_1", text="tool result", status="supported",
        verifier="tool_result", handles=[handle("record", "tool:run_1:c1")],
    )
    output, blob = await enforce_evidence_answer(
        "See https://example.test/report for the number.", store, "run_1", enforce=True,
    )
    assert "Evidence check" in output
    assert blob["unsupported"] >= 1


@pytest.mark.asyncio
async def test_repeat_enforcement_does_not_duplicate_claims(store):
    text = "AAPL returned 18.4% last year."
    await enforce_evidence_answer(text, store, "run_1", enforce=True)
    await enforce_evidence_answer(text, store, "run_1", enforce=True)
    claims = EvidenceLedger(store).claims("run_1")
    assert len([c for c in claims if c.text == text]) == 1


@pytest.mark.asyncio
async def test_enforcement_can_be_suppressed_without_losing_the_record(store):
    output, blob = await enforce_evidence_answer(
        "AAPL returned 18.4% last year.", store, "run_1", enforce=False,
    )
    assert output == "AAPL returned 18.4% last year."
    assert blob["unsupported"] == 1
    assert blob["enforced"] is False
