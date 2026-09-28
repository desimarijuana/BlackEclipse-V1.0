"""Phase 8 (final hardening) — compaction preservation and provenance.

Covers near-duplicates, contradictory/scoped/temporal records and authority
differences; originals remain recoverable; accepted merges show their source
records, preserve provenance/evidence, and are reversible; rejected proposals
produce no durable mutation; compaction never crosses scopes or merges conflicts.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.eval.compaction import (
    COMPACTION_THRESHOLDS,
    check_compaction_thresholds,
    run_compaction_eval,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _pref(service, content, *, subject="style", scope_id="u1", source="explicit_user"):
    return service.write_memory(
        memory_type="preference", content=content, source=source,
        scope="user", scope_id=scope_id, subject=subject, allow_duplicate=True,
    )


def test_eval_gate_passes():
    report = run_compaction_eval()
    gate = check_compaction_thresholds(report)
    assert gate["passed"] is True, gate["failures"]
    metrics = report["metrics"]
    assert metrics["crossScopeMerges"] == 0
    assert metrics["contradictoryMerges"] == 0
    assert metrics["lossyAcceptedMerges"] == 0
    assert metrics["missingEvidence"] == 0
    assert metrics["brokenChains"] == 0
    assert metrics["irreversibleMerges"] == 0
    assert report["version"] >= 2


def test_thresholds_include_provenance_and_reversibility():
    assert COMPACTION_THRESHOLDS["missingEvidence"] == 0
    assert COMPACTION_THRESHOLDS["brokenChains"] == 0
    assert COMPACTION_THRESHOLDS["irreversibleMerges"] == 0


def test_rejected_proposal_produces_no_durable_mutation(service):
    a = _pref(service, "I prefer concise answers in all responses")
    b = _pref(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    assert proposals
    before = {m["id"]: m["status"] for m in service.store.list_memories(limit=100, include_inactive=True)}
    result = service.reject_compaction(proposals[0]["id"])
    assert result["ok"] is True
    after = {m["id"]: m["status"] for m in service.store.list_memories(limit=100, include_inactive=True)}
    assert before == after
    assert service.store.get_memory(a["id"])["status"] == "active"
    assert service.store.get_memory(b["id"])["status"] == "active"


def test_accepted_merge_is_reversible_and_shows_sources(service):
    a = _pref(service, "I prefer concise answers in all responses")
    b = _pref(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    proposal = proposals[0]
    # The proposal shows the source records it is built from.
    assert proposal["evidence"]
    assert {e["id"] for e in proposal["evidence"]} == set(proposal["memberIds"])
    accepted = service.accept_compaction(proposal["id"])
    assert accepted["ok"] is True
    merged = service.store.get_memory(accepted["mergedInto"])
    # Originals are retained (superseded, not deleted) and linked.
    for member_id in proposal["memberIds"]:
        original = service.store.get_memory(member_id)
        assert original is not None
        assert original["status"] == "superseded"
    links = service.store.list_links(merged["id"])
    assert any(link["relation"] == "compacted_from" for link in links)
    # Reversible: the originals can be restored (never hard-deleted).
    for member_id in proposal["memberIds"]:
        restored = service.store.restore_memory(member_id)
        assert restored is not None
        assert restored["status"] == "active"


def test_merge_keeps_explicit_authority(service):
    # An explicit near-duplicate and an automatic near-duplicate: the merged
    # record must carry the stronger (explicit) authority, not the automatic one.
    _pref(service, "I prefer concise answers in all responses", source="explicit_user")
    _pref(service, "I prefer concise answers", source="execution_lesson")
    proposals = service.detect_compaction(persist=True)
    assert proposals
    accepted = service.accept_compaction(proposals[0]["id"])
    assert accepted["ok"] is True
    merged = service.store.get_memory(accepted["mergedInto"])
    assert (merged.get("authority") or "explicit") == "explicit"


def test_cross_scope_never_compacted(service):
    _pref(service, "I prefer concise answers", scope_id="u1")
    _pref(service, "I prefer concise answers", scope_id="u2")
    proposals = service.detect_compaction(persist=True)
    assert proposals == []


def test_contradictory_records_not_compacted(service):
    _pref(service, "I prefer concise answers")
    # A conflicting statement is stored inert (proposed), so there are not two
    # active near-duplicates to compact.
    _pref(service, "I prefer detailed answers")
    proposals = service.detect_compaction(persist=True)
    assert proposals == []
