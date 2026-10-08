"""Result merging, conflict detection and the Supervisor/QA stage."""

from __future__ import annotations

from harness.a2a.results import detect_conflicts, merge_results
from harness.a2a.supervisor import qa_checklist, review_results
from harness.a2a.model import A2AResult, Finding

from a2a_helpers import make_service


def _result(agent, claim, value_claim=None, *, status="COMPLETED", evidence=None, confidence=0.8):
    finding = Finding(claim=value_claim or claim, confidence=confidence,
                      evidence_refs=list(evidence or []))
    return A2AResult(agent_id=agent, status=status, findings=[finding])


def test_dedupes_identical_claims():
    results = [
        A2AResult(agent_id="a", status="COMPLETED",
                  findings=[Finding(claim="Revenue grew 18%", confidence=0.9, evidence_refs=["e1"])]),
        A2AResult(agent_id="b", status="COMPLETED",
                  findings=[Finding(claim="Revenue grew 18%", confidence=0.8, evidence_refs=["e2"])]),
    ]
    merged = merge_results(results, evidence_exists=lambda r: True)
    assert len(merged.findings) == 1
    assert merged.dropped_duplicates == 1


def test_detects_numeric_conflict():
    results = [
        _result("valuation-agent", "TSLA fair value is $320", value_claim="TSLA fair value is $320"),
        _result("risk-agent", "TSLA fair value is $280", value_claim="TSLA fair value is $280"),
    ]
    conflicts = detect_conflicts(results)
    assert len(conflicts) == 1
    assert len(conflicts[0].candidates) == 2
    assert conflicts[0].status == "UNRESOLVED"


def test_no_false_conflict_for_different_subjects():
    results = [
        _result("a", "NVDA fair value is $120"),
        _result("b", "AMD fair value is $180"),
    ]
    assert detect_conflicts(results) == []


def test_unsupported_claims_are_flagged_not_promoted():
    merged = merge_results([_result("a", "Revenue grew 18%", evidence=[])])
    assert merged.unsupported_claims
    assert merged.findings[0].confidence <= 0.4


def test_evidence_refs_verified_against_store():
    verified = merge_results(
        [_result("a", "Revenue grew 18%", evidence=["ev_1"])],
        evidence_exists=lambda ref: ref == "ev_1",
    )
    assert not verified.unsupported_claims
    unverified = merge_results(
        [_result("a", "Revenue grew 18%", evidence=["ev_bogus"])],
        evidence_exists=lambda ref: False,
    )
    assert unverified.unsupported_claims


def test_coverage_and_confidence_bounded():
    merged = merge_results([
        _result("a", "x is 1", evidence=["e1"]),
        A2AResult(agent_id="b", status="FAILED"),
    ], evidence_exists=lambda r: True)
    assert merged.coverage == 0.5
    assert 0.0 <= merged.confidence <= 1.0


# ── supervisor / QA ───────────────────────────────────────────────────────────


def test_supervisor_pass(tmp_path):
    service, _, _ = make_service(tmp_path)
    results = [
        {"agentId": "valuation-agent", "status": "COMPLETED",
         "findings": [{"claim": "TSLA fair value is $320", "confidence": 0.8,
                       "evidenceRefs": ["ev_1"]}]},
    ]
    report = service.supervise("r", results=results)
    assert report["verdict"] == "PASS"


def test_supervisor_rework_on_failure():
    report = review_results([
        A2AResult(agent_id="a", status="COMPLETED", findings=[Finding(claim="ok", evidence_refs=["e"])]),
        A2AResult(agent_id="b", status="FAILED"),
    ], evidence_exists=lambda r: True)
    assert report.verdict.value == "REWORK_REQUIRED"
    assert report.rework_task_ids == [None] or report.rework_task_ids == []


def test_supervisor_rework_on_unsupported():
    report = review_results([_result("a", "Unbacked claim", evidence=[])])
    assert report.verdict.value == "REWORK_REQUIRED"


def test_supervisor_blocked_on_empty():
    report = review_results([])
    assert report.verdict.value == "BLOCKED"


def test_qa_checklist_discloses():
    checklist = qa_checklist([
        A2AResult(agent_id="a", status="COMPLETED",
                  findings=[Finding(claim="x is 1", evidence_refs=["e1"])]),
        A2AResult(agent_id="b", status="COMPLETED",
                  findings=[Finding(claim="x is 2", evidence_refs=["e2"])]),
    ], evidence_exists=lambda r: True)
    assert checklist["verdict"] in ("PASS", "REWORK_REQUIRED")
    assert checklist["conflicts"]  # the disagreement is disclosed
