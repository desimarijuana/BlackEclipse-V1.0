"""Contradiction and replacement handling — deterministic, lexical, no model.

Correctness:
  1. explicit replacement supersedes the old memory (linked, retained);
  2. an ambiguous contradiction never creates a second active truth — the new
     statement is inert (`proposed`) for review;
  3. a correction supersedes the target and records the wrong→right pair;
  4. an identical statement is de-duplicated (confirmation, not a conflict);
  5. explicit vs automatically-learned conflict resolves to the explicit fact;
  6. different scopes never conflict (scope isolation is authoritative).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.conflicts import detect_conflict, is_replacement_intent, opposing


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-conflict-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _write(service, content, **kw):
    kw.setdefault("memory_type", "preference")
    kw.setdefault("source", "explicit_user")
    kw.setdefault("scope", "user")
    kw.setdefault("scope_id", "u1")
    kw.setdefault("subject", "answer-style")
    return service.write_memory(content=content, **kw)


# ── conflict detection unit behaviour ───────────────────────────────────────


def test_replacement_intent_detection():
    assert is_replacement_intent("I prefer detailed answers now")
    assert is_replacement_intent("I changed my mind, use detailed answers instead")
    assert not is_replacement_intent("I prefer concise answers")


def test_opposing_pairs():
    assert opposing("I prefer concise answers", "I prefer detailed answers")
    assert opposing("always include sources", "never include sources")
    assert not opposing("I prefer concise answers", "user prefers candlestick charts")


def test_detect_conflict_ignores_different_scopes():
    assessment = detect_conflict(
        memory_type="preference", scope="user", scope_id="u1", subject="answer-style",
        content="I prefer detailed answers now",
        existing=[{
            "id": "m2", "memoryType": "preference", "scope": "user", "scopeId": "u2",
            "subject": "answer-style", "content": "I prefer concise answers",
            "status": "active", "authority": "explicit",
        }],
    )
    assert assessment.conflict is False


# ── explicit replacement ────────────────────────────────────────────────────


def test_explicit_replacement_supersedes_old(service):
    old = _write(service, "I prefer concise answers")
    new = _write(service, "I prefer detailed answers now")
    assert new["status"] == "active"
    old_now = service.store.get_memory(old["id"])
    assert old_now["status"] == "superseded"
    assert old_now["supersededBy"] == new["id"]
    assert old_now["statusReason"]


def test_explicit_replacement_recalls_only_new(service):
    old = _write(service, "I prefer concise answers")
    new = _write(service, "I prefer detailed answers now")
    result = service.retrieve(
        query="answer style preference", actor_scope="user", scope_id="u1",
    )
    ids = [m["id"] for m in result.memories]
    assert new["id"] in ids
    assert old["id"] not in ids


def test_replacement_across_authority(service):
    # An explicit replacement of an automatically learned memory supersedes it.
    learned = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    assert learned["authority"] == "automatic"
    new = _write(service, "I prefer detailed answers now")
    assert service.store.get_memory(learned["id"])["status"] == "superseded"
    assert service.store.get_memory(new["id"])["status"] == "active"


def test_explicit_contradicts_automatic_without_replacement_wording(service):
    # Requirement 4: an explicit statement beats an automatic one even with no
    # "now"/"instead" wording. The learned record is superseded, not left active.
    learned = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    assert learned["authority"] == "automatic"
    explicit = _write(service, "I prefer detailed answers")
    assert explicit["status"] == "active"
    assert service.store.get_memory(learned["id"])["status"] == "superseded"
    assert service.store.get_memory(learned["id"])["supersededBy"] == explicit["id"]
    # The conflict is explained with the authority reason.
    reasons = [e.get("data", {}).get("reason") for e in service.store.list_memory_events()
               if e["type"] == "memory.conflict_superseded"]
    assert "explicit authority overrides automatic" in reasons


def test_automatic_contradicts_explicit_never_becomes_active_truth(service):
    # Requirement 5: an automatic memory contradicting an explicit one is inert.
    explicit = _write(service, "I prefer concise answers")
    automatic = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    assert automatic["status"] == "proposed"
    assert service.store.get_memory(explicit["id"])["status"] == "active"
    reasons = [e.get("data", {}).get("reason") for e in service.store.list_memory_events()
               if e["type"] == "memory.conflict_needs_review"]
    assert "automatic conflict requires review" in reasons


def test_two_explicit_contradictions_do_not_both_become_active(service):
    # Requirement 6: two ambiguous explicit contradictions — the new one is
    # proposed for review, never a second active truth.
    first = _write(service, "I prefer concise answers")
    second = _write(service, "I prefer detailed answers")
    assert second["status"] == "proposed"
    assert service.store.get_memory(first["id"])["status"] == "active"
    assert len(service.store.list_memories(include_inactive=False)) == 1
    # Explicit reason recorded.
    reasons = [e.get("data", {}).get("reason") for e in service.store.list_memory_events()
               if e["type"] == "memory.conflict_needs_review"]
    assert "ambiguous explicit contradiction" in reasons


# ── ambiguous contradiction ─────────────────────────────────────────────────


def test_ambiguous_contradiction_is_inert_not_active(service):
    old = _write(service, "I prefer concise answers")
    second = _write(service, "I prefer detailed answers")
    # The ambiguous second statement does NOT become a second active truth.
    assert second["status"] == "proposed"
    assert service.store.get_memory(old["id"])["status"] == "active"
    result = service.retrieve(query="answer style preference", actor_scope="user", scope_id="u1")
    ids = [m["id"] for m in result.memories]
    assert old["id"] in ids
    assert second["id"] not in ids


def test_ambiguous_conflict_emits_review_event(service):
    _write(service, "I prefer concise answers")
    _write(service, "I prefer detailed answers")
    events = [e["type"] for e in service.store.list_memory_events()]
    assert "memory.conflict_needs_review" in events


# ── same statement deduplication ────────────────────────────────────────────


def test_identical_statement_is_not_a_conflict(service):
    first = _write(service, "I prefer concise answers")
    again = _write(service, "I prefer concise answers")
    assert again["id"] == first["id"]
    assert again["status"] == "active"
    assert len(service.store.list_memories(include_inactive=False)) == 1


# ── correction path ─────────────────────────────────────────────────────────


def test_correction_supersedes_and_links(service):
    from harness.eclipse_memory.intent import MemoryIntent

    old = _write(service, "I prefer concise answers")
    intent = MemoryIntent(
        action="correct", content="I prefer detailed answers", subject="answer-style",
        scope="user", metadata={"priorAssistantText": "I prefer concise answers"},
    )
    result = service.apply_explicit_intent(intent, user_id="u1")
    assert result["action"] == "corrected"
    assert result["superseded"] == old["id"]
    corrected = result["memory"]
    assert corrected["memoryType"] == "correction"
    assert service.store.get_memory(old["id"])["status"] == "superseded"


# ── explicit vs automatic conflict ──────────────────────────────────────────


def test_explicit_wins_over_automatic(service):
    # Explicit first, then an automatic observation that contradicts it.
    explicit = _write(service, "I prefer concise answers")
    automatic = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    # The automatic observation is inert (needs review); the explicit fact stays.
    assert automatic["status"] == "proposed"
    assert service.store.get_memory(explicit["id"])["status"] == "active"


def test_conflict_across_different_scopes_is_allowed(service):
    # Same content/subject but different scope owner: not a conflict.
    u1 = _write(service, "I prefer concise answers")
    u2 = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u2", subject="answer-style",
    )
    assert u2["id"] != u1["id"]
    assert service.store.get_memory(u1["id"])["status"] == "active"
    assert u2["status"] == "active"


def test_related_subject_alias_is_the_same_dimension(service):
    # A subject stated under a related alias key is the same dimension.
    from harness.eclipse_memory.conflicts import same_dimension

    assert same_dimension("answer-style", "answer-style")
    # "currency" and "reporting-currency" share the alias vocabulary.
    assert same_dimension("currency", "reporting-currency")
    # An unknown/absent key never matches.
    assert not same_dimension("charts", "answer-style")
    assert not same_dimension(None, "answer-style")


def test_unrelated_subjects_do_not_conflict(service):
    # Two different dimensions that share only generic vocabulary are not a
    # conflict (a missed conflict is preferable to replacing unrelated memory).
    charts = _write(service, "I prefer candlestick charts", subject="charts")
    answers = _write(service, "I prefer concise answers", subject="answer-style")
    assert charts["status"] == "active"
    assert answers["status"] == "active"


def test_proposed_conflicts_are_never_injected(service):
    # Requirement 11/12: a proposed conflict must never reach recall.
    first = _write(service, "I prefer concise answers")
    second = _write(service, "I prefer detailed answers")
    assert second["status"] == "proposed"
    result = service.retrieve(query="answer style preference", actor_scope="user", scope_id="u1")
    ids = [m["id"] for m in result.memories]
    assert second["id"] not in ids
    assert first["id"] in ids


# ── retrieval safety net ────────────────────────────────────────────────────


def test_retrieval_guard_keeps_highest_authority(service):
    # Simulate legacy data with two active contradictory rows (bypasses the write
    # path by editing status directly): explicit must win over automatic.
    explicit = _write(service, "I prefer concise answers")
    automatic = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    # Force the automatic row back to active to emulate pre-fix data.
    service.store.update_memory(automatic["id"], status="active")
    result = service.retrieve(query="answer style preference", actor_scope="user", scope_id="u1")
    ids = [m["id"] for m in result.memories]
    assert explicit["id"] in ids
    assert automatic["id"] not in ids
