"""Wave C research nodes: external ingest + run comparison."""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.research_nodes import set_evidence_store
from harness.persistence import AgentMemoryStore
from harness.research.web_store import EvidenceStore

REGISTRY = build_default_registry()
BASE = "r_base"
COMPARE = "r_compare"
OTHER = "r_other"
QUESTION = "Did revenue grow?"


def _evidence(evidence_id, **overrides):
    row = {
        "evidenceId": evidence_id,
        "sourceId": f"s_{evidence_id}",
        "sourceUrl": f"https://example.com/{evidence_id}",
        "sourceType": "company",
        "claimText": "Revenue grew 10%",
        "rawText": f"body {evidence_id}",
        "retrievedAt": "2026-10-25T00:00:00Z",
        "publishedAt": "2026-10-20T00:00:00Z",
        "contentHash": f"h_{evidence_id}",
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
    for rid in (BASE, COMPARE):
        evidence.save_run({
            "researchId": rid, "question": QUESTION,
            "state": "COMPLETED", "status": "OK", "answer": "Revenue grew.",
        })
    evidence.save_run({
        "researchId": OTHER, "question": "Did margins expand?",
        "state": "COMPLETED", "status": "OK",
    })
    for rid, rows in (
        (BASE, [_evidence("e1"), _evidence("e2", contentHash="h_e2")]),
        (COMPARE, [
            _evidence("e1b", contentHash="h_e1"),
            _evidence("e3", contentHash="h_e3"),
        ]),
    ):
        for row in rows:
            evidence.save_evidence(row, research_id=rid)
    evidence.save_claim(BASE, {
        "id": "c1", "text": "Revenue grew", "kind": "FACT",
        "status": "SUPPORTED", "confidence": 0.9,
    })
    evidence.save_claim(COMPARE, {
        "id": "c1b", "text": "Revenue grew", "kind": "FACT",
        "status": "CONTRADICTED", "confidence": 0.2,
    })
    evidence.save_claim(COMPARE, {
        "id": "c2", "text": "Margins expanded", "kind": "FACT",
        "status": "UNSUPPORTED", "confidence": 0.0,
    })
    evidence.save_conflict(BASE, {
        "id": "cf1", "metric": "revenue", "period": "2025",
        "status": "UNRESOLVED", "material": True, "candidates": [],
    })
    evidence.save_conflict(COMPARE, {
        "id": "cf1b", "metric": "revenue", "period": "2025",
        "status": "RESOLVED", "material": False, "candidates": [],
    })
    evidence.save_conflict(COMPARE, {
        "id": "cf2", "metric": "margin", "period": "2025",
        "status": "UNRESOLVED", "material": True, "candidates": [],
    })
    evidence.save_source({
        "sourceId": "s_a", "canonicalUrl": "https://example.com/e1",
    }, research_id=BASE)
    evidence.save_source({
        "sourceId": "s_b", "canonicalUrl": "https://other.test/e3",
    }, research_id=COMPARE)
    set_evidence_store(evidence)
    try:
        yield evidence
    finally:
        set_evidence_store(None)
        memory.close()


def _exec(node_type, config=None, inputs=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config or {},
    ))


def _external_payload():
    return {
        "question": "Did cloud revenue grow?",
        "answer": "An external model says yes.",
        "evidence": [{
            "evidenceId": "ev_ext_1",
            "kind": "web",
            "summary": "Cloud revenue was $10 billion",
            "source": {
                "source": "mcp:vendor",
                "url": "https://vendor.test/cloud",
                "publishedAt": "2026-01-01",
                "validationStatus": "valid",
            },
            "objects": [{"name": "cloud_revenue", "value": 10, "unit": "billion"}],
        }],
        "claims": [{
            "text": "Cloud revenue was $10 billion",
            "evidenceIds": ["ev_ext_1"],
            "status": "SUPPORTED",
        }],
    }


def test_ingest_marks_rows_external_and_never_verified(store):
    result = _exec("research.ingest", {
        "researchId": "r_ingested", "sourceLabel": "mcp:vendor",
    }, {"research": _external_payload()})
    assert result["summary"]["createdRun"] is True
    assert result["summary"]["verified"] is False
    rows = store.list_evidence("r_ingested")
    assert rows[0]["provenance"]["external"] is True
    assert rows[0]["provenance"]["eclipseVerified"] is False
    assert rows[0]["provenance"]["origin"] == "mcp:vendor"
    assert rows[0]["contentTrust"] == "UNTRUSTED"
    claims = store.list_claims("r_ingested")
    assert claims[0]["status"] == "SUPPORTED"
    links = store.list_claim_evidence(claims[0]["id"])
    assert links[0]["evidenceId"] == "ev_ext_1"


def test_ingest_never_copies_an_external_answer_as_the_run_answer(store):
    _exec("research.ingest", {"researchId": "r_ingested"}, {"research": _external_payload()})
    run = store.get_run("r_ingested")
    assert run["status"] == "INGESTED"
    assert run["answer"] is None


def test_ingest_is_idempotent(store):
    first = _exec("research.ingest", {"researchId": "r_ingested"}, {"research": _external_payload()})
    second = _exec("research.ingest", {"researchId": "r_ingested"}, {"research": _external_payload()})
    assert first["evidenceCount"] == second["evidenceCount"] == 1
    assert len(store.list_evidence("r_ingested")) == 1


def test_ingest_skips_rows_without_a_url_and_reports_them(store):
    payload = {"question": "q", "evidence": [{"summary": "no url"}]}
    result = _exec("research.ingest", {"researchId": "r_skipped"}, {"research": payload})
    assert result["summary"]["skipped"] == 1
    assert "http" in result["summary"]["skippedRows"][0]["reason"]


def test_ingest_requires_an_id_or_question(store):
    with pytest.raises(ValueError, match="researchId"):
        _exec("research.ingest", {}, {"research": {"evidence": []}})


def test_ingest_derives_a_run_id_from_the_question(store):
    result = _exec("research.ingest", {}, {"research": _external_payload()})
    assert result["researchId"].startswith("r_")
    assert store.get_run(result["researchId"])["question"] == "Did cloud revenue grow?"


def test_diff_reports_evidence_claims_conflicts_and_sources(store):
    result = _exec("research.diff", {
        "baseId": BASE, "compareId": COMPARE, "useSnapshots": False,
    })
    summary = result["summary"]
    assert summary["addedEvidence"] == 1  # h_e3 is new; h_e1 exists in both
    assert summary["removedEvidence"] == 1  # h_e2 only in the base
    assert summary["statusChanges"] == 1
    assert result["diff"]["claims"]["statusChanges"][0] == {
        "text": "Revenue grew", "from": "SUPPORTED", "to": "CONTRADICTED",
    }
    assert summary["openedConflicts"] == 1
    assert summary["resolvedConflicts"] == 1
    assert summary["addedSources"] == 1


def test_diff_refuses_incomparable_questions(store):
    with pytest.raises(ValueError, match="incomparable"):
        _exec("research.diff", {"baseId": BASE, "compareId": OTHER})


def test_diff_requires_both_runs(store):
    with pytest.raises(ValueError, match="baseId and compareId"):
        _exec("research.diff", {"baseId": BASE})
    with pytest.raises(ValueError, match="was not found"):
        _exec("research.diff", {"baseId": BASE, "compareId": "missing"})


def test_diff_prefers_snapshots_when_present(store):
    store.create_snapshot(BASE, {"evidence": [_evidence("e1", contentHash="h_e1")]})
    store.create_snapshot(COMPARE, {"evidence": [
        _evidence("e1b", contentHash="h_e1"),
        _evidence("e3", contentHash="h_e3"),
    ]})
    result = _exec("research.diff", {
        "baseId": BASE, "compareId": COMPARE, "useSnapshots": True,
    })
    assert result["diff"]["usedSnapshots"] is True
    assert result["summary"]["removedEvidence"] == 0
    assert result["summary"]["addedEvidence"] == 1
