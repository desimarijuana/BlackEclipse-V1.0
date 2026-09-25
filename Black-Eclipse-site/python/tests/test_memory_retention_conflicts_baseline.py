"""Baseline behaviour pin for retention and conflict handling (Phase 1 audit).

These tests record the behaviour traced in
`docs/harness/memory-retention-conflict-audit.md` BEFORE hardening, so the
changes in later phases are measured against a known baseline. They assert the
*contract* (automatic vs explicit, timestamp exclusion, scope/subject
non-conflicts) — the parts that must not regress — rather than incidental
details that the hardening is intended to change.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-audit-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def test_authority_is_derived_from_source(service):
    automatic = service.write_memory(
        memory_type="semantic", content="Learned fact", source="execution_lesson",
        scope="general",
    )
    explicit = service.write_memory(
        memory_type="semantic", content="Stated fact", source="manual", scope="general",
    )
    assert automatic["authority"] == "automatic"
    assert explicit["authority"] == "explicit"


def test_automatic_memory_gets_retention_expiry_explicit_does_not(service):
    service.policy.set("retention_days", 7)
    automatic = service.write_memory(
        memory_type="semantic", content="Automatic lesson", source="execution_lesson",
        scope="general",
    )
    explicit = service.write_memory(
        memory_type="semantic", content="Explicit fact", source="manual", scope="general",
    )
    assert automatic["expiresAt"] is not None
    assert explicit["expiresAt"] is None


def test_retrieval_excludes_due_memory_by_timestamp_without_sweep(service):
    memory = service.write_memory(
        memory_type="semantic", content="Due automatic fact", source="execution_lesson",
        scope="general", expires_at="2000-01-01T00:00:00.000Z",
    )
    # No sweep has run; the row is still 'active' but must not be recalled.
    assert service.store.get_memory(memory["id"])["status"] == "active"
    result = service.retrieve(query="due automatic fact", actor_scope="user")
    assert all(m["id"] != memory["id"] for m in result.memories)
    reasons = {e["id"]: e["reason"] for e in result.diagnostics["excluded"]}
    assert reasons.get(memory["id"]) == "expired"


def test_explicit_and_different_scopes_do_not_conflict(service):
    u1 = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    u2 = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u2", subject="answer-style",
    )
    assert u1["status"] == "active"
    assert u2["status"] == "active"


def test_observation_and_preference_on_same_topic_do_not_conflict(service):
    observation = service.write_memory(
        memory_type="observation", content="The user asked about concise answers twice.",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    preference = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    # Different memory types on the same subject are not contradictory.
    assert observation["status"] == "active"
    assert preference["status"] == "active"
