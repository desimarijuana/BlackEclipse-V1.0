"""Local research/evidence nodes over the existing EvidenceStore."""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.research_nodes import set_evidence_store
from harness.persistence import AgentMemoryStore
from harness.research.web_store import EvidenceStore

REGISTRY = build_default_registry()
RID = "r1"


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    evidence = EvidenceStore(memory)
    evidence.save_run({
        "researchId": RID, "question": "Did revenue grow?",
        "state": "COMPLETED", "status": "OK", "answer": "Revenue grew 10%.",
    })
    evidence.save_evidence({
        "evidenceId": "e1", "sourceId": "s1", "sourceUrl": "https://example.com/10k",
        "sourceType": "PRIMARY", "claimText": "Revenue grew 10%",
        "rawText": "Revenue grew 10% year over year.", "retrievedAt": "2026-10-25T00:00:00Z",
        "confidence": 0.9, "contentTrust": "TRUSTED", "provenance": {},
    }, research_id=RID)
    evidence.save_claim(RID, {
        "id": "c1", "text": "Revenue grew 10%", "kind": "FACT",
        "status": "SUPPORTED", "confidence": 0.9,
    })
    evidence.save_citation(RID, {
        "citationId": "ci1", "claimId": "c1", "evidenceId": "e1",
        "sourceUrl": "https://example.com/10k", "title": "10-K",
        "section": "MD&A", "page": 12,
    })
    evidence.save_conflict(RID, {
        "id": "cf1", "metric": "revenue", "period": "2025", "status": "OPEN",
        "material": True, "explanation": "two sources disagree", "candidates": [],
    })
    set_evidence_store(evidence)
    try:
        yield evidence
    finally:
        set_evidence_store(None)
        memory.close()


def _exec(node_type: str, config: dict | None = None, research_id: str | None = None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"researchId": research_id} if research_id is not None else {},
        config=config or {},
    ))


def test_evidence_read_and_filter(store):
    all_items = _exec("research.evidence", {"researchId": RID})
    assert all_items["summary"]["count"] == 1
    assert all_items["evidence"][0]["claimText"] == "Revenue grew 10%"
    filtered = _exec("research.evidence", {"researchId": RID, "query": "revenue"})
    assert filtered["summary"]["count"] == 1
    missing = _exec("research.evidence", {"researchId": RID, "query": "nothing"})
    assert missing["summary"]["count"] == 0
    wired = _exec("research.evidence", {}, research_id=RID)
    assert wired["summary"]["count"] == 1


def test_citations_claims_conflicts(store):
    citations = _exec("research.citations", {"researchId": RID})
    assert citations["citations"][0]["title"] == "10-K"
    assert citations["claims"][0]["status"] == "SUPPORTED"
    conflicts = _exec("research.conflicts", {"researchId": RID})
    assert conflicts["conflicts"][0]["metric"] == "revenue"


def test_completeness_is_partial_with_an_open_conflict(store):
    result = _exec("research.completeness", {"researchId": RID})
    summary = result["summary"]
    assert summary["status"] == "PARTIAL"
    assert summary["evidence"] == 1
    assert summary["supportedClaims"] == 1
    assert summary["unresolvedConflicts"] == 1


def test_report_is_deterministic_markdown(store):
    first = _exec("research.report", {"researchId": RID})
    second = _exec("research.report", {"researchId": RID})
    assert first["report"] == second["report"]
    report = first["report"]
    assert "Did revenue grow?" in report
    assert "Revenue grew 10%." in report
    assert "10-K" in report
    assert "two sources disagree" in report


def test_missing_research_id_is_explicit(store):
    with pytest.raises(ValueError, match="researchId"):
        _exec("research.evidence", {})
