"""Conservative memory compaction (Phase 5).

Proposals are inert; acceptance merges + supersedes (retained); nothing is
hard-deleted; contradictory or cross-scope records are never auto-merged.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.compaction import (
    detect_proposals,
    preservation_report,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _write(service, content, *, subject="style", scope="user", scope_id="u1", memory_type="preference"):
    return service.write_memory(
        memory_type=memory_type, content=content, source="explicit_user",
        scope=scope, scope_id=scope_id, subject=subject, allow_duplicate=True,
    )


def test_detects_near_duplicates(service):
    _write(service, "I prefer concise answers in all responses")
    _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=False)
    assert len(proposals) == 1
    assert len(proposals[0]["memberIds"]) >= 2


def test_does_not_group_across_scopes(service):
    _write(service, "I prefer concise answers", scope="user", scope_id="u1")
    _write(service, "I prefer concise answers", scope="user", scope_id="u2")
    proposals = service.detect_compaction(persist=False)
    assert proposals == []


def test_contradictory_records_are_not_merged(service):
    _write(service, "I prefer concise answers")
    _write(service, "I prefer detailed answers")
    proposals = service.detect_compaction(persist=False)
    assert proposals == []


def test_proposal_is_inert_until_accepted(service):
    a = _write(service, "I prefer concise answers in all responses")
    b = _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    assert len(proposals) == 1
    # Nothing changed yet.
    assert service.store.get_memory(a["id"])["status"] == "active"
    assert service.store.get_memory(b["id"])["status"] == "active"


def test_accept_merges_and_supersedes_but_retains(service):
    a = _write(service, "I prefer concise answers in all responses")
    b = _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    result = service.accept_compaction(proposals[0]["id"])
    assert result["ok"] is True
    merged = service.store.get_memory(result["mergedInto"])
    assert merged["status"] == "active"
    # Originals retained, not deleted.
    assert service.store.get_memory(a["id"])["status"] == "superseded"
    assert service.store.get_memory(b["id"])["status"] == "superseded"
    assert service.store.get_memory(a["id"])["supersededBy"] == result["mergedInto"]


def test_accept_is_reversible_via_restore(service):
    a = _write(service, "I prefer concise answers in all responses")
    _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    service.accept_compaction(proposals[0]["id"])
    restored = service.store.restore_memory(a["id"])
    assert restored["status"] == "active"


def test_reject_makes_no_durable_change(service):
    a = _write(service, "I prefer concise answers in all responses")
    b = _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    result = service.reject_compaction(proposals[0]["id"])
    assert result["ok"] is True
    assert service.store.get_memory(a["id"])["status"] == "active"
    assert service.store.get_memory(b["id"])["status"] == "active"


def test_lossy_merge_is_refused(service):
    _write(service, "I prefer concise answers in all responses always")
    _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    # Force a lossy merged content (drops a distinctive token).
    result = service.accept_compaction(proposals[0]["id"], merged_content="I prefer answers")
    assert result["ok"] is False
    assert "preservation" in result


def test_preservation_report_flags_lost_tokens():
    members = [{"content": "alpha beta gamma"}]
    report = preservation_report(members, "alpha beta")
    assert report["preserved"] is False
    assert "gamma" in report["lostTokens"]
    good = preservation_report(members, "alpha beta gamma delta")
    assert good["preserved"] is True


def test_accept_is_audited(service):
    _write(service, "I prefer concise answers in all responses")
    _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    service.accept_compaction(proposals[0]["id"])
    events = service.store.list_memory_events(limit=100)
    assert any(e["type"] == "memory.compaction_accepted" for e in events)
    assert any(e["type"] == "memory.compaction_proposed" for e in events)


def test_export_preserves_compaction_history(service, tmp_path):
    """The export document preserves the superseded originals' provenance, and
    the merged active fact survives an import round trip."""
    from harness.eclipse_memory.transfer import export_payload, import_payload
    from harness.eclipse_memory.store import EclipseMemoryStore

    _write(service, "I prefer concise answers in all responses")
    _write(service, "I prefer concise answers")
    proposals = service.detect_compaction(persist=True)
    accepted = service.accept_compaction(proposals[0]["id"])
    document = export_payload(service.store)

    # The export carries every record, including the superseded originals.
    statuses = {m.get("status") for m in document["memories"]}
    assert "superseded" in statuses
    assert "active" in statuses
    superseded_entries = [m for m in document["memories"] if m.get("status") == "superseded"]
    assert all(m.get("supersededBy") for m in superseded_entries)

    # The merged active fact round-trips through the gated import pipeline.
    other = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "other.db")))
    report = import_payload(other, document)
    assert report["imported"] >= 1
    assert any(m["status"] == "active" for m in other.store.list_memories(limit=100))
    other.close()


def test_compaction_preservation_eval_passes():
    from harness.eclipse_memory.eval.compaction import (
        check_compaction_thresholds,
        run_compaction_eval,
    )

    report = run_compaction_eval()
    gate = check_compaction_thresholds(report)
    assert gate["passed"] is True, gate["failures"]
    metrics = report["metrics"]
    assert metrics["crossScopeMerges"] == 0
    assert metrics["contradictoryMerges"] == 0
    assert metrics["lossyAcceptedMerges"] == 0
