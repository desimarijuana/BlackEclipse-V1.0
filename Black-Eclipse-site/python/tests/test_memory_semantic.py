"""Optional local semantic contradiction candidates (Phases 3–4, 7–8).

The semantic layer may ONLY surface a review candidate. It can never supersede,
activate, archive or delete; it never bypasses scope/status/type/subject/privacy/
authority; it is local, bounded, fail-safe, and off by default. Lexical-only
behaviour must be identical when it is disabled or unavailable.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory import semantic


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-sem-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _pref(service, content, **kw):
    kw.setdefault("source", "explicit_user")
    kw.setdefault("scope", "user")
    kw.setdefault("scope_id", "u1")
    kw.setdefault("subject", "answer-style")
    return service.write_memory(memory_type="preference", content=content, **kw)


# ── Backend behaviour ───────────────────────────────────────────────────────


def test_default_backend_is_local_and_available():
    status = semantic.backend_status()
    assert status["available"] is True
    assert status["backend"] == "char-ngram"


def test_similarity_is_deterministic_and_bounded():
    backend = semantic.get_backend()
    a = backend.similarity("I prefer concise answers", "I prefer concise answers")
    b = backend.similarity("I prefer concise answers", "I prefer concise answers")
    assert a == b
    assert 0.0 <= a <= 1.0
    assert backend.similarity("I prefer concise answers", "the weather is nice") < 0.5


def test_find_candidates_disabled_by_policy():
    result = semantic.find_candidates(
        content="I prefer concise answers",
        same_dimension=[{"id": "m1", "content": "I prefer detailed answers"}],
        settings={"semantic_conflict_enabled": False},
    )
    assert result.available is False
    assert result.candidates == []


def test_find_candidates_unavailable_backend_is_fail_safe():
    result = semantic.find_candidates(
        content="I prefer concise answers",
        same_dimension=[{"id": "m1", "content": "I prefer detailed answers"}],
        settings={"semantic_conflict_enabled": True},
        backend_name="none",
    )
    assert result.available is False
    assert result.candidates == []


def test_find_candidates_respects_threshold_and_max():
    same = [
        {"id": "m1", "content": "I prefer concise answers with citations"},
        {"id": "m2", "content": "I prefer concise answers with citations and links"},
        {"id": "m3", "content": "the weather in Karachi is hot"},
    ]
    result = semantic.find_candidates(
        content="I prefer concise answers with citations",
        same_dimension=same,
        settings={
            "semantic_conflict_enabled": True,
            "semantic_conflict_threshold": 0.6,
            "semantic_conflict_max_candidates": 1,
            "semantic_conflict_timeout_ms": 500,
            "semantic_conflict_max_index": 500,
        },
    )
    assert result.available is True
    assert len(result.candidates) <= 1
    assert all(c.score >= 0.6 for c in result.candidates)


def test_find_candidates_truncates_large_index():
    same = [{"id": f"m{i}", "content": "I prefer concise answers"} for i in range(10)]
    result = semantic.find_candidates(
        content="I prefer concise answers",
        same_dimension=same,
        settings={
            "semantic_conflict_enabled": True,
            "semantic_conflict_threshold": 0.5,
            "semantic_conflict_max_candidates": 5,
            "semantic_conflict_max_index": 3,
            "semantic_conflict_timeout_ms": 500,
        },
    )
    assert result.truncated is True


def test_timeout_is_bounded_and_reported():
    # A backend whose similarity blocks past the deadline.
    class SlowBackend:
        name = "slow"; version = "test"
        def available(self): return True
        def similarity(self, a, b):
            import time; time.sleep(0.05)
            return 1.0

    semantic.register_backend(SlowBackend())
    try:
        result = semantic.find_candidates(
            content="x",
            same_dimension=[{"id": f"m{i}", "content": "y"} for i in range(20)],
            settings={
                "semantic_conflict_enabled": True,
                "semantic_conflict_threshold": 0.1,
                "semantic_conflict_max_candidates": 5,
                "semantic_conflict_max_index": 500,
                "semantic_conflict_timeout_ms": 20,
            },
            backend_name="slow",
        )
        assert result.timedOut is True
    finally:
        semantic.register_backend(semantic.CharNgramBackend())


# ── Service integration — never supersedes, only proposes for review ────────


def test_disabled_semantic_leaves_lexical_behavior_unchanged(service):
    # Off by default: a lexical conflict still proposes, an unrelated write stays
    # active, exactly as lexical-only.
    old = _pref(service, "I prefer concise answers")
    conflict = _pref(service, "I prefer detailed answers")
    assert conflict["status"] == "proposed"
    assert service.store.get_memory(old["id"])["status"] == "active"


def test_semantic_candidate_never_supersedes_only_proposes(service):
    # Enable semantic detection. Two same-dimension memories with no lexical
    # opposition must not be superseded by similarity — at most proposed.
    service.policy.set("semantic_conflict_enabled", True)
    first = _pref(service, "I prefer concise answers with citations")
    second = _pref(service, "I prefer concise answers with citations and links")
    # Whatever the outcome, the first is never superseded by semantic similarity.
    stored = service.store.get_memory(first["id"])
    assert stored["status"] == "active"


def test_semantic_candidate_never_activates_a_proposal(service):
    service.policy.set("semantic_conflict_enabled", True)
    first = _pref(service, "I prefer concise answers")
    second = _pref(service, "I prefer detailed answers")
    # A contradiction (lexical here) is proposed, never active.
    assert second["status"] == "proposed"
    assert service.store.get_memory(first["id"])["status"] == "active"


def test_semantic_candidate_never_bypasses_scope(service):
    service.policy.set("semantic_conflict_enabled", True)
    u2 = service.write_memory(
        memory_type="preference", content="I prefer concise answers with citations",
        source="explicit_user", scope="user", scope_id="u2", subject="answer-style",
    )
    new = _pref(service, "I prefer concise answers with citations and links")
    # Different scope owner is never a candidate and never superseded.
    assert service.store.get_memory(u2["id"])["status"] == "active"
    assert new["status"] == "active"


def test_semantic_candidate_never_turns_financial_fact_into_memory(service):
    service.policy.set("semantic_conflict_enabled", True)
    from harness.eclipse_memory.decision import authorize_proposal

    decision = authorize_proposal(
        content="AAPL share price is 190", provenance="ui_save", user_id="u1",
    )
    assert decision.outcome == "ignore"
    assert decision.financial is True


def test_semantic_failure_falls_back_to_lexical(service, monkeypatch):
    service.policy.set("semantic_conflict_enabled", True)

    def _boom(*_a, **_k):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(semantic, "find_candidates", _boom)
    old = _pref(service, "I prefer concise answers")
    # Lexical conflict still works even though the semantic layer raised.
    conflict = _pref(service, "I prefer detailed answers")
    assert conflict["status"] == "proposed"
    assert service.store.get_memory(old["id"])["status"] == "active"


def test_automatic_never_supersedes_explicit_with_semantic_enabled(service):
    service.policy.set("semantic_conflict_enabled", True)
    explicit = _pref(service, "I prefer concise answers")
    automatic = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    assert automatic["status"] == "proposed"
    assert service.store.get_memory(explicit["id"])["status"] == "active"


def test_index_clears_consistently_with_reset(service):
    # The semantic layer holds no persistent index in v1 (computed per write), so
    # a memory reset leaves no stale index. Confirm reset + a follow-up write do
    # not error and lexical detection remains correct.
    from harness.eclipse_memory.transfer import reset_memory

    _pref(service, "I prefer concise answers")
    reset_memory(service.store, confirm=True, backup_first=False)
    assert service.store.list_memories(include_inactive=True) == []
    first = _pref(service, "I prefer concise answers")
    conflict = _pref(service, "I prefer detailed answers")
    assert conflict["status"] == "proposed"
    assert service.store.get_memory(first["id"])["status"] == "active"
