"""Milestone 7 — real-usage measurement honesty.

The report is read-only, bounded, idempotent and content-free. Empty data yields
an honest empty report, never a zero-filled fake.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-usage-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def test_empty_report_is_honest_not_fake(service):
    report = service.usage_report(window_days=30)
    assert report["insufficientData"] is True
    assert report["durableWrites"]["totalDecisions"] == 0
    assert report["conflicts"]["raised"] == 0
    assert report["conflicts"]["falsePositiveRate"] is None
    assert report["readOnly"] is True


def test_report_writes_nothing(service):
    before = service.store._db.execute("SELECT COUNT(*) FROM MemoryEvent").fetchone()[0]
    service.usage_report(window_days=30)
    after = service.store._db.execute("SELECT COUNT(*) FROM MemoryEvent").fetchone()[0]
    assert before == after


def test_report_is_bounded_and_idempotent(service):
    a = service.usage_report(window_days=30)
    b = service.usage_report(window_days=30)
    assert a["windowDays"] == b["windowDays"] == 30
    assert a["readOnly"] is True


def test_counts_explicit_saves_and_suggestions(service):
    # The explicit-intent path emits `memory.explicit_saved`.
    service.apply_explicit_intent(
        {"action": "save", "content": "I prefer concise answers",
         "memoryType": "preference", "scope": "user", "scopeId": "u1"},
        user_id="u1",
    )
    # A suggestion is created through the decision path.
    from harness.eclipse_memory.decision import authorize_proposal

    decision = authorize_proposal(
        content="I prefer detailed answers", provenance="memory_tool",
        user_id="u1", memory_type="preference", scope="user", scope_id="u1",
    )
    service.commit_decision(decision, user_id="u1")
    report = service.usage_report(window_days=30)
    assert report["durableWrites"]["saved"] >= 1
    assert report["durableWrites"]["totalDecisions"] >= 1


def test_never_exposes_memory_content(service):
    secret = "My private note about the quarterly strategy"
    service.write_memory(
        memory_type="preference", content=secret,
        source="explicit_user", scope="user", scope_id="u1", subject="note-style",
    )
    report = service.usage_report(window_days=30)
    serialized = str(report)
    assert secret not in serialized


def test_likely_missed_conflicts_flags_same_dimension(service):
    # Two active records on the same subject/type/scope that did NOT conflict.
    service.write_memory(
        memory_type="semantic", content="Fact A about the benchmark",
        source="manual", scope="general", subject="benchmark",
    )
    service.store.save_memory(
        memory_type="semantic", scope="general", content="Fact B about the benchmark",
        subject="benchmark", source="manual", status="active",
    )
    report = service.usage_report(window_days=30)
    assert report["likelyMissedConflicts"]["count"] >= 1
    group = report["likelyMissedConflicts"]["groups"][0]
    assert group["subject"] == "benchmark"
    assert "memoryIds" in group
    # Only ids/subject/type, never content.
    assert "Fact A" not in str(report)


def test_conflict_resolution_counts(service):
    from harness.eclipse_memory.decision import authorize_proposal

    # A conflicting write is stored inert for review.
    service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    conflicting = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    assert conflicting["status"] == "proposed"
    report = service.usage_report(window_days=30)
    assert report["conflicts"]["pending"] >= 1


def test_ground_truth_labels_produce_real_precision(service):
    memory = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    assert service.label_conflict(memory["id"], "true_conflict")["ok"] is True
    other = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    service.label_conflict(other["id"], "false_positive")
    report = service.usage_report(window_days=30)
    assert report["conflicts"]["labeled"] == 2
    assert report["conflicts"]["labeledTrue"] == 1
    assert report["conflicts"]["labeledFalsePositive"] == 1
    assert report["conflicts"]["precision"] == 0.5
    assert report["smallSample"] is True


def test_relabel_takes_latest_judgement(service):
    memory = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    service.label_conflict(memory["id"], "false_positive")
    service.label_conflict(memory["id"], "true_conflict")
    report = service.usage_report(window_days=30)
    assert report["conflicts"]["labeled"] == 1
    assert report["conflicts"]["precision"] == 1.0


def test_rejects_unknown_label(service):
    memory = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    assert service.label_conflict(memory["id"], "maybe")["ok"] is False


def test_report_contains_trend_and_small_sample_flag(service):
    report = service.usage_report(window_days=30)
    assert "trend" in report
    assert report["smallSample"] is True


def test_trend_direction_insufficient_on_low_sample(service):
    report = service.usage_report(window_days=30)
    # No/insufficient usage → no confident direction asserted.
    assert report["trend"]["direction"] == "insufficient"
    assert report["trend"]["confident"] is False


def test_precision_interval_reported_with_labels(service):
    m1 = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    m2 = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    service.label_conflict(m1["id"], "true_conflict")
    service.label_conflict(m2["id"], "false_positive")
    report = service.usage_report(window_days=30)
    interval = report["conflicts"]["precisionInterval"]
    assert interval is not None
    assert interval[0] <= 0.5 <= interval[1]


def test_retired_semantic_policy_rows_are_cleaned_on_open():
    """Migration 24 removes dead semantic keys; a pre-change db still opens and
    keeps its real memory rows."""
    import sqlite3

    directory = tempfile.mkdtemp(prefix="be-usage-mig-")
    path = os.path.join(directory, "eclipse-memory.db")
    first = EclipseMemoryService(EclipseMemoryStore(path))
    first.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    # Simulate a pre-change row for a retired key, and rewind the migration
    # bookkeeping so the cleanup migration re-runs on the next open (exactly as a
    # real upgrade from an older database would).
    first.store._db.execute(
        "INSERT INTO MemoryPolicy (key, value, updatedAt) VALUES ('semantic_conflict_enabled', 'true', '2026-01-01T00:00:00Z')"
    )
    first.store._db.execute("DELETE FROM SchemaMigration WHERE version = 24")
    first.store._db.commit()
    first.close()

    reopened = EclipseMemoryService(EclipseMemoryStore(path))
    try:
        remaining = {
            row["key"] for row in reopened.store._db.execute(
                "SELECT key FROM MemoryPolicy"
            ).fetchall()
        }
        assert "semantic_conflict_enabled" not in remaining
        assert len(reopened.store.list_memories(include_inactive=True)) == 1
    finally:
        reopened.close()
