"""Wave A research analysis nodes (local, deterministic reads)."""

from __future__ import annotations

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.research_nodes import set_evidence_store
from harness.persistence import AgentMemoryStore
from harness.research.web_store import EvidenceStore

REGISTRY = build_default_registry()
RID = "r_analysis"


def _evidence(evidence_id: str, **overrides):
    row = {
        "evidenceId": evidence_id,
        "sourceId": f"s_{evidence_id}",
        "sourceUrl": f"https://example.com/{evidence_id}",
        "sourceType": "company",
        "claimText": "Revenue grew 10%",
        "rawText": "Revenue grew 10% year over year.",
        "retrievedAt": "2026-10-25T00:00:00Z",
        "publishedAt": "2026-10-20T00:00:00Z",
        "confidence": 0.9,
        "contentTrust": "UNTRUSTED",
        "provenance": {"metric": "revenue"},
        "structuredValue": {"value": 100},
        "period": "2025",
    }
    row.update(overrides)
    return row


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    evidence = EvidenceStore(memory)
    evidence.save_run({
        "researchId": RID, "question": "Did revenue grow?",
        "state": "COMPLETED", "status": "OK", "answer": "Revenue grew 10%.",
    })
    evidence.save_question(RID, {
        "id": "q1", "question": "What was FY2025 revenue?", "required": True,
        "answered": False,
    })
    evidence.save_source({
        "sourceId": "s_e1", "canonicalUrl": "https://example.com/e1",
        "domain": "example.com", "sourceType": "company",
        "publishedAt": "2026-10-20T00:00:00Z",
        "retrievedAt": "2026-10-25T00:00:00Z",
        "contentHash": "h_same",
    }, research_id=RID)
    evidence.save_source({
        "sourceId": "s_e2", "canonicalUrl": "https://example.com/e2",
        "domain": "other.test", "sourceType": "news",
        "publishedAt": "2026-10-21T00:00:00Z",
        "retrievedAt": "2026-10-25T00:00:00Z",
        "contentHash": "h_same",
    }, research_id=RID)
    evidence.save_evidence(_evidence("e1"), research_id=RID)
    evidence.save_evidence(_evidence(
        "e2", structuredValue={"value": 110},
        provenance={"metric": "revenue", "supersedesEvidenceId": "e1",
                    "relationshipKind": "amends"},
        publishedAt="2026-10-28T00:00:00Z",
    ), research_id=RID)
    evidence.save_evidence(_evidence(
        "e3", structuredValue={"value": 120},
        provenance={"metric": "revenue"},
        sourceType="news", sourceUrl="https://other.test/e3",
    ), research_id=RID)
    evidence.save_claim(RID, {
        "id": "c1", "text": "Revenue grew 10%", "kind": "FACT",
        "status": "SUPPORTED", "confidence": 0.9,
    })
    evidence.link_claim_evidence("c1", "e1", "supports")
    evidence.save_claim(RID, {
        "id": "c2", "text": "Margins expanded", "kind": "FACT",
        "status": "UNSUPPORTED", "confidence": 0.0,
    })
    evidence.save_citation(RID, {
        "citationId": "ci1", "claimId": "c1", "evidenceId": "e1",
        "sourceUrl": "https://example.com/e1", "title": "10-K",
        "section": "MD&A", "page": 12,
    })
    evidence.save_conflict(RID, {
        "id": "cf1", "metric": "revenue", "period": "2025", "status": "OPEN",
        "material": True, "explanation": "two sources disagree",
        "candidates": [{"value": 100}, {"value": 110}],
    })
    evidence.save_entity({
        "entityId": "ent1", "name": "Example Corp", "kind": "company",
        "evidenceId": "e1",
    }, research_id=RID)
    evidence.save_relation({
        "id": "rel1", "subjectId": "ent1", "predicate": "reported",
        "objectValue": "revenue", "evidenceId": "e1",
    }, research_id=RID)
    set_evidence_store(evidence)
    try:
        yield evidence
    finally:
        set_evidence_store(None)
        memory.close()


def _exec(node_type: str, config: dict | None = None, research_id: str | None = RID, inputs=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    wired = dict(inputs or {})
    if research_id is not None:
        wired.setdefault("researchId", research_id)
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=wired, config=config or {},
    ))


def test_latest_resolves_by_question_and_requires_a_match(store):
    result = _exec("research.latest", {}, research_id=None,
                   inputs={"question": "revenue grow"})
    assert result["researchId"] == RID
    with pytest.raises(ValueError, match="no research run"):
        _exec("research.latest", {}, research_id=None, inputs={"question": "nothing"})


def test_sources_dedupe_and_filters(store):
    result = _exec("research.sources", {"dedupe": True})
    assert result["summary"]["total"] == 1  # same contentHash, one source
    assert result["summary"]["byType"] == {"company": 1}
    all_rows = _exec("research.sources", {"dedupe": False})
    assert all_rows["summary"]["total"] == 2
    undated = _exec("research.sources", {
        "dedupe": False, "publishedAfter": "2027-01-01",
    })
    assert undated["summary"]["total"] == 0
    assert undated["summary"]["excludedUndated"] == 0


def test_gaps_lists_question_claim_and_citation_absences(store):
    result = _exec("research.gaps", {})
    kinds = {gap["kind"] for gap in result["gaps"]}
    assert "question" in kinds
    assert "claim" in kinds
    assert result["summary"]["hasGaps"] is True


def test_freshness_partitions_with_reasons(store):
    result = _exec("research.freshness", {"freshness": "week"})
    assert result["summary"]["admissible"] == 3
    stale = _exec("research.freshness", {"asOf": "2026-10-01T00:00:00Z"})
    assert stale["summary"]["admissible"] == 0
    assert stale["rejected"]
    assert all(item["reason"] for item in stale["rejected"])


def test_conflict_scan_detects_disagreement(store):
    result = _exec("research.conflict_scan", {"mergeStored": False})
    assert any(
        "revenue" in item["metric"] and item["status"] == "UNRESOLVED"
        for item in result["conflicts"]
    )
    assert result["summary"]["unresolved"] >= 1


def test_citation_audit_flags_an_uncited_material_claim(store):
    store.save_claim(RID, {
        "id": "c3", "text": "Cash flow improved", "kind": "FACT",
        "status": "SUPPORTED", "confidence": 0.8,
    })
    result = _exec("research.citation_audit", {})
    assert result["audit"]["ok"] is False
    assert any("no citation" in issue for issue in result["issues"])


def test_supersession_chain_uses_recorded_metadata(store):
    result = _exec("research.supersession", {})
    assert result["chain"]["coverage"] == "available"
    assert result["summary"]["links"] >= 1
    assert result["chain"]["currentByKey"]


def test_quality_carries_components_and_disclaimer(store):
    result = _exec("research.quality", {})
    quality = result["quality"]
    assert 0.0 <= quality["score"] <= 1.0
    assert abs(sum(quality["weights"].values()) - 1.0) < 1e-9
    assert quality["disclaimer"]
    assert sum(quality["contributions"].values()) == pytest.approx(quality["score"], abs=1e-4)


def test_entities_reads_the_anchored_graph(store):
    result = _exec("research.entities", {})
    assert result["entities"][0]["name"] == "Example Corp"
    assert result["summary"]["unanchoredEntities"] == 0
    assert result["relations"][0]["predicate"] == "reported"


def test_batch_verify_applies_the_stored_conflict(store):
    result = _exec("research.claims_verify", {})
    by_text = {row["text"]: row for row in result["claims"]}
    assert by_text["Revenue grew 10%"]["status"] == "CONTRADICTED"
    assert by_text["Margins expanded"]["status"] == "UNSUPPORTED"
    assert result["summary"]["byStatus"]["CONTRADICTED"] == 1


def test_single_claim_verify_applies_the_stored_conflict(store):
    result = _exec("research.claim_verify", {"claim": "Revenue grew 10%"})
    assert result["status"] == "CONTRADICTED"
    assert result["claim"]["evidenceIds"] == ["e1"]


def test_queries_expand_question_gaps_and_weak_claims(store):
    result = _exec("research.queries", {
        "siteFilter": "sec.gov", "maxQueries": 10,
    }, research_id=None, inputs={
        "question": "Did revenue grow?",
        "gaps": [{"kind": "question", "text": "What was FY2025 revenue?"}],
        "claims": [{"text": "Revenue grew 10%", "status": "CONTRADICTED"}],
    })
    purposes = {entry["purpose"] for entry in result["queries"]}
    assert {"answer", "primary_source", "gap", "support", "counter_evidence"} <= purposes
    primary = next(item for item in result["queries"] if item["purpose"] == "primary_source")
    assert primary["query"] == "site:sec.gov Did revenue grow?"
    assert any("contradicting evidence" in item["query"] for item in result["queries"])
    assert result["summary"]["count"] == len(result["queries"])


def test_queries_dedupe_and_cap(store):
    result = _exec("research.queries", {
        "maxQueries": 2, "includePrimarySources": False,
    }, research_id=None, inputs={
        "claims": [{"text": "Revenue grew", "status": "UNSUPPORTED"}] * 3,
    })
    assert result["summary"]["total"] == 2
    assert result["summary"]["truncated"] is False
    assert len(result["queries"]) == 2


def test_queries_require_something_to_expand(store):
    with pytest.raises(ValueError, match="question or claims"):
        _exec("research.queries", {}, research_id=None)


def test_start_run_is_idempotent_and_never_overwrites(store):
    first = _exec("research.start_run", {
        "question": "How fast did cloud revenue grow?",
        "objective": "growth",
    }, research_id=None)
    second = _exec("research.start_run", {
        "question": "How fast did cloud revenue grow?",
        "objective": "growth",
    }, research_id=None)
    assert first["researchId"] == second["researchId"]
    assert first["summary"]["created"] is True
    assert second["summary"]["created"] is False
    assert store.get_run(first["researchId"])["question"] == "How fast did cloud revenue grow?"


def test_start_run_requires_a_question(store):
    with pytest.raises(ValueError, match="question"):
        _exec("research.start_run", {}, research_id=None)


def test_snapshot_is_versioned_and_counts_sections(store):
    first = _exec("research.snapshot", {"include": "evidence,citations"})
    second = _exec("research.snapshot", {"include": "evidence,citations"})
    assert first["version"] == 1
    assert second["version"] == 2
    assert first["summary"]["counts"]["evidence"] == 3
    assert first["summary"]["counts"]["citations"] == 1
    assert first["snapshotId"].startswith(RID)


def test_snapshot_requires_a_run_row(store):
    with pytest.raises(ValueError, match="start_run"):
        _exec("research.snapshot", {}, research_id="missing")


def test_local_research_writes_are_refused_in_a_test_run(store):
    ir = WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_research_write", "name": "Research write",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0",
             "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "start", "type": "research.start_run", "version": "1.0.0",
             "config": {"question": "q"}, "layout": {"x": 0, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0",
             "config": {}, "layout": {"x": 0, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start",
             "target": "start", "targetHandle": "question"},
            {"id": "e2", "source": "start", "sourceHandle": "researchId",
             "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False,
                     "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["research.write"],
    })
    denied = compile_workflow(ir, REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "capability_denied" for d in denied.diagnostics)

