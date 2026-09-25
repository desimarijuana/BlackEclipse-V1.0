"""Expanded contradiction coverage (Phase 7): paraphrase, synonym, negation,
typo+contradiction, unfamiliar wording, and the safety/authority thresholds.

These exercise the REAL `EclipseMemoryService.write_memory` path (the whole
pipeline), not just the classifier, and lock in the release floors: zero scope
leakage, zero forbidden supersedes, zero automatic-over-explicit supersedes.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-contr-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _pref(service, content, *, authority="explicit", subject="answer-style", **kw):
    source = "explicit_user" if authority == "explicit" else "execution_lesson"
    return service.write_memory(
        memory_type="preference", content=content, source=source,
        scope="user", scope_id="u1", subject=subject, **kw,
    )


def _status(service, memory_id):
    return service.store.get_memory(memory_id)["status"]


# ── Paraphrased conflicts (unfamiliar wording) ──────────────────────────────


@pytest.mark.parametrize("first,second", [
    ("Keep it punchy", "Give me the full deep-dive every time"),
    ("I don't want any fluff", "Some elaboration is welcome"),
    ("Always give me the sources", "Please skip the citations"),
    ("Prefer numbers rounded", "Show me the exact unrounded figures"),
    ("Don't include any preamble", "A short intro is fine"),
    ("I prefer dark mode", "A bright light theme suits me better"),
])
def test_paraphrased_conflict_is_proposed_not_active(service, first, second):
    _pref(service, first)
    second_memory = _pref(service, second)
    # Never a second active truth: the new one is inert (proposed).
    assert second_memory["status"] == "proposed"
    assert len(service.store.list_memories(include_inactive=False)) == 1


def test_paraphrased_conflict_never_supersedes_without_replacement(service):
    first = _pref(service, "Keep it punchy")
    _pref(service, "Give me the full deep-dive every time")
    assert _status(service, first["id"]) == "active"


# ── Paraphrased confirmations ───────────────────────────────────────────────


@pytest.mark.parametrize("first,second", [
    ("I like short answers", "Keep responses brief"),
    ("I prefer concise answers with source links", "Keep answers brief and cite sources"),
])
def test_paraphrased_confirmation_does_not_duplicate(service, first, second):
    original = _pref(service, first)
    again = _pref(service, second)
    # Same meaning → confirmed, not a second active memory.
    assert again["status"] == "active"
    assert again["id"] == original["id"]
    assert again["lastConfirmedAt"] is not None


def test_identical_confirmation_reuses_record(service):
    first = _pref(service, "I prefer concise answers")
    again = _pref(service, "I prefer concise answers")
    assert again["id"] == first["id"]
    assert len(service.store.list_memories(include_inactive=False)) == 1


# ── Typo + contradiction ────────────────────────────────────────────────────


def test_typo_plus_contradiction(service):
    # A misspelling of "concise" still opposes "detailed".
    _pref(service, "I prefer concise answers")
    bad = _pref(service, "I prefer detailed anwsers", subject="answer-style")
    # The conflict may be caught lexically (detailed vs concise). Either way it
    # is never a second active truth.
    assert bad["status"] in ("proposed",)


# ── Negation ────────────────────────────────────────────────────────────────


def test_negation_flips_polarity(service):
    service.write_memory(
        memory_type="constraint", content="Always include sources", source="explicit_user",
        scope="user", scope_id="u1", subject="sources",
    )
    negated = service.write_memory(
        memory_type="constraint", content="Never include sources", source="explicit_user",
        scope="user", scope_id="u1", subject="sources",
    )
    assert negated["status"] == "proposed"


# ── Different subjects with similar language ────────────────────────────────


def test_similar_language_different_subjects_no_conflict(service):
    charts = _pref(service, "I like dark candlestick charts", subject="charts")
    theme = _pref(service, "I like dark mode", subject="theme")
    assert _status(service, charts["id"]) == "active"
    assert theme["status"] == "active"


# ── Authority floors ────────────────────────────────────────────────────────


def test_automatic_never_supersedes_explicit(service):
    explicit = _pref(service, "I prefer concise answers", authority="explicit")
    auto = _pref(service, "I prefer detailed answers", authority="automatic")
    assert auto["status"] == "proposed"
    assert _status(service, explicit["id"]) == "active"


def test_explicit_overrides_automatic(service):
    auto = _pref(service, "I prefer concise answers", authority="automatic")
    explicit = _pref(service, "I prefer detailed answers", authority="explicit")
    assert explicit["status"] == "active"
    assert _status(service, auto["id"]) == "superseded"


def test_two_explicit_contradictions_both_not_active(service):
    first = _pref(service, "I prefer concise answers")
    second = _pref(service, "I prefer detailed answers")
    assert second["status"] == "proposed"
    assert _status(service, first["id"]) == "active"
    assert len(service.store.list_memories(include_inactive=False)) == 1


# ── Scope isolation ─────────────────────────────────────────────────────────


def test_scope_isolation_no_cross_user_conflict(service):
    u2 = service.write_memory(
        memory_type="preference", content="I prefer concise answers", source="explicit_user",
        scope="user", scope_id="u2", subject="answer-style",
    )
    u1 = _pref(service, "I prefer detailed answers now")
    assert u2["status"] == "active"
    assert u1["status"] == "active"


# ── Legacy contradictory rows ───────────────────────────────────────────────


def test_legacy_contradictory_rows_recall_only_authoritative(service):
    explicit = _pref(service, "I prefer concise answers", authority="explicit")
    auto = _pref(service, "I prefer detailed answers", authority="automatic")
    # Force the automatic row active to emulate pre-fix legacy data.
    service.store.update_memory(auto["id"], status="active")
    result = service.retrieve(query="answer style preference", actor_scope="user", scope_id="u1")
    ids = [m["id"] for m in result.memories]
    assert explicit["id"] in ids
    assert auto["id"] not in ids
