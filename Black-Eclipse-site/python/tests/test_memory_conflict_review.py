"""Conflict-resolution review + actions (Phase 4 of the remaining-gaps plan).

Every resolution must be auditable and reversible; semantic similarity must
never automatically replace or confirm a memory.
"""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _pair(service):
    """Two same-subject preferences that conflict (detailed vs concise).

    `allow_duplicate` bypasses the write-time auto-conflict handling so the test
    can drive the REVIEW flow explicitly (two active competing records).
    """
    a = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer style",
        allow_duplicate=True,
    )
    b = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer style",
        allow_duplicate=True,
    )
    return a, b


def test_conflict_review_returns_side_by_side(service):
    a, b = _pair(service)
    # Link them so the review sees each other.
    service.store.add_link(a["id"], b["id"], "conflict")
    review = service.conflict_review(a["id"])
    assert review is not None
    assert review["memoryId"] == a["id"]
    assert review["self"]["content"]
    peer_ids = [p["id"] for p in review["peers"]]
    assert b["id"] in peer_ids
    peer = next(p for p in review["peers"] if p["id"] == b["id"])
    for field in ("content", "memoryType", "scope", "authority", "provenance",
                  "confidence", "createdAt", "accessCount"):
        assert field in peer
    assert "recommendation" in review
    assert set(review["actions"]) == {"keep", "supersede", "merge", "confirm_both", "dismiss", "defer"}


def test_keep_changes_nothing_but_marks_reviewed(service):
    a, _ = _pair(service)
    result = service.resolve_conflict(a["id"], "keep")
    assert result["ok"] is True
    assert service.store.get_memory(a["id"])["status"] == "active"


def test_supersede_is_auditable_and_reversible(service):
    a, b = _pair(service)
    result = service.resolve_conflict(a["id"], "supersede", target_id=b["id"])
    assert result["ok"] is True
    assert service.store.get_memory(b["id"])["status"] == "superseded"
    assert service.store.get_memory(b["id"])["supersededBy"] == a["id"]
    # Reversible: restore brings it back.
    restored = service.store.restore_memory(b["id"])
    assert restored["status"] == "active"
    assert any(e["type"] == "memory.conflict_resolved"
               for e in service.store.list_memory_events(limit=100))


def test_confirm_both_links_compatible(service):
    a, b = _pair(service)
    result = service.resolve_conflict(a["id"], "confirm_both", target_id=b["id"])
    assert result["ok"] is True
    assert service.store.get_memory(a["id"])["status"] == "active"
    assert service.store.get_memory(b["id"])["status"] == "active"
    links = service.store.list_links(a["id"])
    assert any(link["relation"] == "compatible" for link in links)


def test_dismiss_rejects_target_not_self(service):
    a, b = _pair(service)
    result = service.resolve_conflict(a["id"], "dismiss", target_id=b["id"])
    assert result["ok"] is True
    assert service.store.get_memory(b["id"])["status"] == "rejected"
    assert service.store.get_memory(a["id"])["status"] == "active"


def test_merge_creates_new_and_supersedes_both(service):
    a, b = _pair(service)
    result = service.resolve_conflict(
        a["id"], "merge", target_id=b["id"],
        merged_content="I prefer answers that are concise but complete",
    )
    assert result["ok"] is True
    merged_id = result["mergedInto"]
    merged = service.store.get_memory(merged_id)
    assert merged["status"] == "active"
    assert service.store.get_memory(a["id"])["status"] == "superseded"
    assert service.store.get_memory(b["id"])["status"] == "superseded"
    assert service.store.get_memory(a["id"])["supersededBy"] == merged_id


def test_unknown_action_is_refused(service):
    a, _ = _pair(service)
    result = service.resolve_conflict(a["id"], "obliterate")
    assert result["ok"] is False


def test_missing_target_is_refused(service):
    a, _ = _pair(service)
    result = service.resolve_conflict(a["id"], "supersede", target_id="mem_does_not_exist")
    assert result["ok"] is False


def test_conflict_decision_recorded_in_journey(service):
    from harness.learning_graph import build_learning_journey

    a, b = _pair(service)
    service.resolve_conflict(a["id"], "supersede", target_id=b["id"])
    graph = build_learning_journey(service.store, scope_id="u1")
    assert any(e["relation"] == "superseded_by" for e in graph["edges"])
