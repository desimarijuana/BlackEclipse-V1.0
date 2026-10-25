"""Local research/evidence nodes over the existing EvidenceStore."""

from __future__ import annotations

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.research_nodes import set_evidence_store, set_research_bridge
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
        "sourceType": "company", "claimText": "Revenue grew 10%",
        "rawText": "Revenue grew 10% year over year.", "retrievedAt": "2026-10-25T00:00:00Z",
        "confidence": 0.9, "contentTrust": "UNTRUSTED", "provenance": {},
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


class _FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, capability: str, params: dict):
        self.calls.append((capability, params))
        if capability == "web_search":
            return {
                "status": "OK",
                "provider": "fake",
                "results": [
                    {"title": "A", "url": "https://news.example.com/a", "snippet": "a"},
                    {"title": "B", "url": "https://other.test/b", "snippet": "b"},
                ],
            }
        if capability == "web_fetch":
            return {
                "status": "OK",
                "url": params["url"],
                "title": "Fetched page",
                "text": "Revenue grew 10% year over year. " * 20,
                "extraction": "bridge",
            }
        return {"status": "UNAVAILABLE", "error": "unexpected capability"}


@pytest.fixture()
def bridge():
    fake = _FakeBridge()
    set_research_bridge(fake)
    try:
        yield fake
    finally:
        set_research_bridge(None)


def test_web_search_returns_pointers_and_filters_domains(store, bridge):
    result = _exec("research.web_search", {"query": "revenue growth", "domains": ["example.com"]})
    assert result["summary"]["status"] == "OK"
    assert [row["title"] for row in result["results"]] == ["A"]
    assert result["results"][0]["url"] == "https://news.example.com/a"
    assert "not evidence" in result["summary"]["note"]
    assert bridge.calls[0][0] == "web_search"


def test_web_search_requires_a_query(store, bridge):
    with pytest.raises(ValueError, match="query"):
        _exec("research.web_search", {})


def test_web_fetch_saves_evidence_when_a_research_id_is_set(store, bridge):
    result = _exec("research.web_fetch", {
        "url": "https://example.com/page", "researchId": RID, "maxChars": 600,
    })
    assert result["page"]["status"] == "OK"
    assert result["page"]["truncated"] is True
    assert len(result["text"]) == 600
    rows = store.list_evidence(RID)
    assert any(row["sourceUrl"] == "https://example.com/page" for row in rows)
    assert bridge.calls[0] == ("web_fetch", {"url": "https://example.com/page"})


def test_web_fetch_without_evidence_store_is_explicit(store, bridge):
    set_evidence_store(None)
    try:
        with pytest.raises(ValueError, match="evidence store"):
            _exec("research.web_fetch", {
                "url": "https://example.com/page", "researchId": RID,
            })
    finally:
        set_evidence_store(store)


def test_claim_verify_uses_the_stored_evidence(store):
    result = _exec("research.claim_verify", {
        "researchId": RID, "claim": "Revenue grew 10%", "evidenceIds": ["e1"],
    })
    assert result["status"] == "PARTIALLY_SUPPORTED"
    assert result["supported"] is False
    assert result["claim"]["evidenceIds"] == ["e1"]


def test_claim_verify_rejects_an_unknown_evidence_id(store):
    with pytest.raises(ValueError, match="unknown evidence"):
        _exec("research.claim_verify", {
            "researchId": RID, "claim": "Revenue grew 10%", "evidenceIds": ["missing"],
        })


def _network_ir(node_type: str, config: dict) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_research", "name": "Research",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "web", "type": node_type, "version": "1.0.0", "config": config, "layout": {"x": 0, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "web", "targetHandle": "query"},
            {"id": "e2", "source": "web", "sourceHandle": "results", "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["network.egress"],
    })


def test_web_nodes_need_an_explicit_network_grant():
    ir = _network_ir("research.web_search", {"query": "inflation"})
    denied = compile_workflow(ir, REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "permission_denied" for d in denied.diagnostics)
    allowed = compile_workflow(ir, REGISTRY, RunGrants(
        test_run=False, granted_capabilities=frozenset({"network.egress"}), allow_network=True,
    ))
    assert allowed.executable is True
