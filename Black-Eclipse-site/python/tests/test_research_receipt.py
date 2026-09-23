"""Phase 4 — citations, failure classes, and durable receipts (Milestones 7-8)."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.research.citations import build_response_metadata
from harness.research.claims import Synthesis, validate_claims
from harness.research.coverage import build_coverage
from harness.research.failures import classify_failure
from harness.research.mandate import parse_mandate
from harness.research.receipt import build_receipt
from harness.retrieval.contract import (
    EvidenceItem,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    SourceReference,
)


def obj(value, period):
    return NormalizedFinancialObject(
        name="revenue",
        value=value,
        period=period,
        currency="USD",
        instrument="TEST",
        source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
    )


def ev(eid):
    return EvidenceItem(
        id=eid,
        kind="structured",
        summary=f"{eid} summary",
        objects=[obj(800.0, "FY2023")],
        source=SourceReference(
            source="JDDS", sourceType="structured",
            url="https://real.example/filing", title="10-K",
            publishedAt="2024-02-01", validationStatus="valid",
        ),
    )


# ── citations / response metadata ───────────────────────────────────────────


def test_citations_only_from_evidence():
    mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
    items = [ev("ev_real")]
    coverage = build_coverage(mandate, items)
    meta = build_response_metadata(mandate, coverage, items)
    assert len(meta.citations) == 1
    citation = meta.citations[0]
    assert citation.evidenceId == "ev_real"
    assert citation.url == "https://real.example/filing"
    assert citation.publishedAt == "2024-02-01"


def test_limitations_disclose_missing_evidence():
    mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
    coverage = build_coverage(mandate, [])
    meta = build_response_metadata(mandate, coverage, [])
    assert meta.status == "rejected"
    assert any("no evidence retrieved" in l for l in meta.limitations)


def test_metadata_carries_interpretations_and_conflicts():
    mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
    items = [ev("ev_real")]
    coverage = build_coverage(mandate, items)
    validation = validate_claims(
        mandate,
        Synthesis(claims=[{"text": "Growth came from pricing.", "kind": "interpretation",
                           "interpretations": ["management attributed growth to pricing"]}]),
        items, coverage,
    )
    meta = build_response_metadata(
        mandate, coverage, items, validation=validation,
        conflicts=[{"metric": "revenue", "period": "FY2023", "candidates": [{"value": 800, "source": "JDDS"}]}],
    )
    assert meta.interpretations
    assert len(meta.conflicts) == 1


# ── failure classification ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "result,expected",
    [
        (FinancialRetrievalResult(status="AMBIGUOUS", objective="o", dataType="current_quote"), "ambiguous_entity"),
        (FinancialRetrievalResult(status="UNAVAILABLE", objective="o", dataType="current_quote",
                                  warnings=["live provider timed out"]), "timeout"),
        (FinancialRetrievalResult(status="UNAVAILABLE", objective="o", dataType="current_quote",
                                  warnings=["instrument is not covered"]), "no_coverage"),
        (FinancialRetrievalResult(status="UNAVAILABLE", objective="o", dataType="current_quote",
                                  warnings=["data parse incomplete"]), "incomplete"),
        (FinancialRetrievalResult(status="CONFLICTING", objective="o", dataType="current_quote"), "conflicting"),
        (None, "unknown"),
    ],
)
def test_failure_classification(result, expected):
    assert classify_failure(result) == expected


# ── durable receipt ─────────────────────────────────────────────────────────


def test_receipt_persists_and_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentMemoryStore(os.path.join(tmp, "agent-memory.db"))
        try:
            store.create_run("run_1", "eclipse-agent", {"query": "x"})
            mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
            items = [ev("ev_real")]
            coverage = build_coverage(mandate, items)
            receipt = build_receipt("run_1", mandate, coverage=coverage, evidence=items)
            store.save_receipt(receipt.model_dump())

            loaded = store.get_receipt("run_1")
            assert loaded is not None
            assert loaded["runId"] == "run_1"
            assert loaded["taskType"] == "financial_comparison"
            assert loaded["finalStatus"] == coverage.status
            assert len(loaded["evidenceRefs"]) == 1
            assert loaded["evidenceRefs"][0]["id"] == "ev_real"

            listing = store.list_receipts()
            assert any(r["runId"] == "run_1" for r in listing)
        finally:
            store.close()


def test_receipt_save_requires_run_id():
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentMemoryStore(os.path.join(tmp, "agent-memory.db"))
        try:
            with pytest.raises(ValueError):
                store.save_receipt({"runId": ""})
        finally:
            store.close()


def test_receipt_idempotent_per_run():
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentMemoryStore(os.path.join(tmp, "agent-memory.db"))
        try:
            store.create_run("run_2", "eclipse-agent", {"query": "x"})
            mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
            first = build_receipt("run_2", mandate, evidence=[ev("ev_a")], final_status="partial")
            store.save_receipt(first.model_dump())
            second = build_receipt("run_2", mandate, evidence=[ev("ev_b")], final_status="accepted")
            store.save_receipt(second.model_dump())
            loaded = store.get_receipt("run_2")
            assert loaded["finalStatus"] == "accepted"
            assert loaded["evidenceRefs"][0]["id"] == "ev_b"
        finally:
            store.close()


def test_receipt_never_stores_full_source_documents():
    mandate = parse_mandate("Compare TEST revenue FY2023 vs FY2024", ticker="TEST")
    items = [ev("ev_real")]
    receipt = build_receipt("run_3", mandate, evidence=items)
    dumped = receipt.model_dump()
    ref = dumped["evidenceRefs"][0]
    assert "summary" in ref and len(ref["summary"]) <= 240
    assert "text" not in ref  # no unbounded document body
