"""Ordinary-run source collection (provenance for the chat Sources panel).

These tests pin the contract the chat UI relies on: a normal (non-gated) run's
retrieval provenance is shaped like the `research` blob, built ONLY from what was
retrieved, with honest failure reporting and no fabrication. They are pure and
never touch a provider.
"""

from __future__ import annotations

from harness.retrieval.contract import (
    EvidenceItem,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    SourceReference,
)
from harness.source_collector import SourceCollector


def _ref(**kw):
    base = {"source": "jdds", "sourceType": "structured", "retrievedAt": "2026-01-01T00:00:00Z"}
    base.update(kw)
    return SourceReference(**base)


def _result(*, status="OK", refs=None, evidence=None, conflicts=None):
    return FinancialRetrievalResult(
        status=status,
        objective="o",
        dataType="financial_statements",
        sourceReferences=refs or [],
        evidence=evidence or [],
        conflicts=conflicts or [],
    )


def _evidence(ref, *, period="2024-Q1"):
    obj = NormalizedFinancialObject(
        name="revenue", value=1.2e9, currency="USD", period=period, source=ref
    )
    return EvidenceItem(
        id=f"ev:{ref.url or ref.source}",
        kind="structured",
        summary="revenue",
        objects=[obj],
        source=ref,
        quality="valid",
    )


def test_empty_collector_produces_no_blob():
    # An ordinary run that consulted nothing must not render an empty panel.
    assert SourceCollector().to_research_blob() is None


def test_citations_are_built_from_evidence():
    ref = _ref(url="https://example.com/filing", title="Filing")
    collector = SourceCollector()
    collector.add(_result(refs=[ref], evidence=[_evidence(ref)]))
    blob = collector.to_research_blob()
    assert blob["status"] == "collected"
    assert blob["metadata"]["status"] == "collected"
    citations = blob["metadata"]["citations"]
    assert len(citations) == 1
    c = citations[0]
    assert c["source"] == "jdds"
    assert c["url"] == "https://example.com/filing"
    assert c["fiscalPeriod"] == "2024-Q1"
    assert c["currency"] == "USD"


def test_sources_without_evidence_still_produce_a_citation():
    ref = _ref(source="sec", sourceType="primary", url="https://sec.gov/x", title="10-K")
    collector = SourceCollector()
    collector.add(_result(refs=[ref]))
    blob = collector.to_research_blob()
    citations = blob["metadata"]["citations"]
    assert len(citations) == 1
    assert citations[0]["source"] == "sec"
    assert citations[0]["sourceType"] == "primary"


def test_duplicate_sources_are_deduplicated_by_url():
    ref = _ref(url="https://example.com/same")
    collector = SourceCollector()
    collector.add(_result(refs=[ref], evidence=[_evidence(ref)]))
    collector.add(_result(refs=[ref], evidence=[_evidence(ref)]))
    assert len(collector.to_research_blob()["metadata"]["citations"]) == 1


def test_failed_fetch_is_a_failed_route_not_a_citation():
    collector = SourceCollector()
    collector.add_fetched_source(url="https://blocked.example", ok=False)
    blob = collector.to_research_blob()
    assert blob["metadata"]["citations"] == []
    assert any("blocked.example" in r for r in blob["failedRoutes"])


def test_successful_fetch_is_listed_as_a_secondary_source():
    collector = SourceCollector()
    collector.add_fetched_source(
        url="https://ir.example.com/report", title="IR Report", ok=True
    )
    citations = collector.to_research_blob()["metadata"]["citations"]
    assert len(citations) == 1
    assert citations[0]["url"] == "https://ir.example.com/report"
    assert citations[0]["sourceType"] == "secondary"


def test_unavailable_retrieval_source_is_reported_as_failed_route():
    ref = _ref(source="web", sourceType="secondary")
    collector = SourceCollector()
    collector.add(_result(status="UNAVAILABLE", refs=[ref]))
    blob = collector.to_research_blob()
    assert any("web" in r for r in blob["failedRoutes"])


def test_conflicts_are_carried_into_metadata():
    ref = _ref(source="jdds")
    collector = SourceCollector()
    collector.add(
        _result(
            refs=[ref],
            evidence=[_evidence(ref)],
            conflicts=[{"metric": "revenue", "period": "2024-Q1", "candidates": [{"value": 1}]}],
        )
    )
    conflicts = collector.to_research_blob()["metadata"]["conflicts"]
    assert conflicts and conflicts[0]["metric"] == "revenue"


def test_add_never_raises_on_a_bad_result():
    # Collection is best-effort provenance; a malformed result must be swallowed.
    collector = SourceCollector()
    collector.add(object())  # type: ignore[arg-type]
    assert collector.to_research_blob() is None
