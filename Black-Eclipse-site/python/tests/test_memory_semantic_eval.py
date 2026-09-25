"""Dedicated semantic evaluation + typed candidates + reliability (Phases 1–9).

Locks in: the semantic dataset/gate, the false-confirmation safety fix, typed
semantic candidate classification (similarity never confirms/supersedes), the
optional backend fallback, retrieval tie-break safety, and the operational
status counters. Safety floors are absolute at every setting.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory import semantic
from harness.eclipse_memory.eval.semantic import (
    SEMANTIC_THRESHOLDS,
    check_semantic_thresholds,
    load_semantic_dataset,
    run_semantic_evaluation,
)


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-semv2-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


# ── Dataset + gate ──────────────────────────────────────────────────────────


def test_semantic_dataset_is_versioned():
    dataset = load_semantic_dataset()
    assert dataset["name"] == "memory-semantic"
    assert dataset["version"] >= 1
    assert dataset["cases"]


def test_semantic_eval_gate_passes_with_absolute_safety():
    report = run_semantic_evaluation()
    gate = check_semantic_thresholds(report)
    assert gate["passed"], gate["failures"]
    for mode in ("lexicalOnly", "semanticEnabled"):
        metrics = report[mode]["metrics"]
        assert metrics["scopeLeakage"] == 0
        assert metrics["unauthorizedSupersessions"] == 0
        assert metrics["automaticOverExplicit"] == 0
        assert metrics["secretStored"] == 0
        assert metrics["financialStored"] == 0
        assert metrics["falseConflictRate"] == 0.0


def test_semantic_thresholds_are_absolute():
    assert SEMANTIC_THRESHOLDS["scopeLeakage"] == 0
    assert SEMANTIC_THRESHOLDS["unauthorizedSupersessions"] == 0
    assert SEMANTIC_THRESHOLDS["secretStored"] == 0
    assert SEMANTIC_THRESHOLDS["financialStored"] == 0


# ── False-confirmation safety fix (deterministic, lexical) ──────────────────


@pytest.mark.parametrize("old,new,subject", [
    ("I prefer reports delivered as PDF", "I prefer reports delivered as Excel", "report-format"),
    ("Notify me about fills by email", "Notify me about fills by SMS", "alert-channel"),
    ("Rebalance my portfolio quarterly", "Rebalance my portfolio monthly", "rebalance-cadence"),
    ("Size positions by drawdown", "Size positions by value at risk", "sizing-method"),
    ("Show times in 24-hour format", "Show times in 12-hour AM/PM", "time-format"),
])
def test_value_substitution_is_never_silently_confirmed(service, old, new, subject):
    first = service.write_memory(
        memory_type="preference", content=old, source="explicit_user",
        scope="user", scope_id="u1", subject=subject,
    )
    second = service.write_memory(
        memory_type="preference", content=new, source="explicit_user",
        scope="user", scope_id="u1", subject=subject,
    )
    # The existing record remains active and untouched; the new value is inert.
    assert service.store.get_memory(first["id"])["status"] == "active"
    assert second["id"] != first["id"]
    assert second["status"] == "proposed"


def test_same_value_paraphrase_still_confirms(service):
    first = service.write_memory(
        memory_type="preference", content="I like short answers", source="explicit_user",
        scope="user", scope_id="u1", subject="answer-style",
    )
    again = service.write_memory(
        memory_type="preference", content="Keep responses brief", source="explicit_user",
        scope="user", scope_id="u1", subject="answer-style",
    )
    assert again["id"] == first["id"]
    assert again["lastConfirmedAt"] is not None


# ── Typed semantic candidates ───────────────────────────────────────────────


def test_classify_candidate_types():
    assert semantic.classify_candidate(
        "I prefer reports as Excel", "I prefer reports as PDF"
    )[0] in (semantic.CANDIDATE_CONFLICT,)
    assert semantic.classify_candidate(
        "I changed my mind, use light theme", "I prefer dark mode"
    )[0] == semantic.CANDIDATE_REPLACEMENT
    assert semantic.classify_candidate(
        "Keep it brief", "Keep answers short"
    )[0] == semantic.CANDIDATE_CONFIRMATION
    assert semantic.classify_candidate(
        "I prefer concise answers", "The weather is nice"
    )[0] == semantic.CANDIDATE_UNRELATED


def test_similarity_never_confirms_or_supersedes(service):
    service.policy.set("semantic_conflict_enabled", True)
    service.policy.set("semantic_conflict_threshold", 0.3)
    first = service.write_memory(
        memory_type="preference", content="I prefer reports as PDF",
        source="explicit_user", scope="user", scope_id="u1", subject="report-format",
    )
    # A near-identical confirmation candidate must never be auto-confirmed by the
    # semantic layer alone (the deterministic lexical path decides confirmation).
    second = service.write_memory(
        memory_type="preference", content="I prefer reports as PDF files",
        source="explicit_user", scope="user", scope_id="u1", subject="report-format",
    )
    assert service.store.get_memory(first["id"])["status"] == "active"
    assert second["id"] == first["id"]  # lexical duplicate confirmation


def test_strongest_actionable_ignores_confirmation_and_unrelated():
    result = semantic.SemanticSearchResult(
        detector="test", available=True,
        candidates=[
            semantic.SemanticCandidate("m1", 0.99, "x", semantic.CANDIDATE_CONFIRMATION),
            semantic.SemanticCandidate("m2", 0.98, "y", semantic.CANDIDATE_UNRELATED),
        ],
    )
    assert semantic.strongest_actionable(result) is None
    result.candidates.append(
        semantic.SemanticCandidate("m3", 0.90, "z", semantic.CANDIDATE_CONFLICT)
    )
    assert semantic.strongest_actionable(result).memoryId == "m3"


# ── Optional backend + reliability (Phase 8) ────────────────────────────────


def test_backend_health_reports_all_without_network():
    health = {b["backend"]: b for b in semantic.backend_health()}
    assert "char-ngram" in health
    assert health["char-ngram"]["available"] is True


def test_auto_backend_falls_back_to_char_ngram_when_embedding_absent():
    # No embedding model configured → auto resolves to the dependency-free default.
    backend = semantic.get_backend("auto")
    assert backend.name == "char-ngram"


def test_malformed_score_is_dropped():
    class NaNBackend:
        name = "nan"; version = "test"
        def available(self): return True
        def similarity(self, a, b): return float("nan")

    semantic.register_backend(NaNBackend())
    try:
        result = semantic.find_candidates(
            content="x", same_dimension=[{"id": "m1", "content": "y"}],
            settings={
                "semantic_conflict_enabled": True,
                "semantic_conflict_threshold": 0.0,
            },
            backend_name="nan",
        )
        assert result.candidates == []
    finally:
        semantic.register_backend(semantic.CharNgramBackend())


def test_backend_exception_is_fail_safe(service, monkeypatch):
    service.policy.set("semantic_conflict_enabled", True)

    def _boom(*_a, **_k):
        raise RuntimeError("crash")

    monkeypatch.setattr(semantic, "find_candidates", _boom)
    memory = service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    assert memory["status"] == "active"


def test_threshold_and_limit_bounds_enforced(service):
    from harness.eclipse_memory.policy import PolicyError

    with pytest.raises(PolicyError):
        service.policy.set("semantic_conflict_threshold", 5)
    with pytest.raises(PolicyError):
        service.policy.set("semantic_conflict_max_candidates", 0)
    with pytest.raises(PolicyError):
        service.policy.set("semantic_conflict_backend", "cloud")


# ── Retrieval tie-break safety (Phase 5) ────────────────────────────────────


def test_semantic_tiebreak_never_surfaces_excluded_or_other_scope(service):
    service.policy.set("semantic_recall_tiebreak", True)
    # Another user's memory must never be recalled, even with the tie-break on.
    service.write_memory(
        memory_type="preference", content="u2 prefers log-scale charts",
        source="explicit_user", scope="user", scope_id="u2", subject="chart-scale",
    )
    service.write_memory(
        memory_type="semantic", content="The benchmark rate history for the report",
        source="manual", scope="user", scope_id="u1", subject="benchmark",
    )
    result = service.retrieve(query="chart scale preference", actor_scope="user", scope_id="u1")
    assert all(m.get("scopeId") != "u2" for m in result.memories)


def test_semantic_tiebreak_preserves_lexical_set(service):
    service.policy.set("semantic_recall_tiebreak", True)
    service.write_memory(
        memory_type="semantic", content="Benchmark rate history notes",
        source="manual", scope="user", scope_id="u1", subject="benchmark",
    )
    # A no-match query with the tie-break on must still be clean.
    result = service.retrieve(query="quantum entanglement", actor_scope="user", scope_id="u1")
    assert all(m["memoryType"] in ("preference", "constraint") for m in result.memories)


# ── Operational status (Phase 6) ────────────────────────────────────────────


def test_semantic_status_reports_controls_and_counters(service):
    status = service.semantic_status()
    assert status["mode"] == "lexical"
    assert "controls" in status
    assert status["controls"]["enabled"] is False
    assert "threshold" in status["controls"]
    assert "stats" in status
    assert status["stats"]["available"] is True
    assert any(b["backend"] == "char-ngram" for b in status["backends"])


def test_semantic_status_unavailable_backend_is_honest(service, monkeypatch):
    service.policy.set("semantic_conflict_enabled", True)
    monkeypatch.setattr(semantic, "backend_status", lambda *a, **k: {
        "backend": "none", "version": "v", "available": False,
    })
    status = service.semantic_status()
    assert status["mode"] == "lexical+semantic-unavailable"
    assert status["semanticAvailable"] is False


def test_diagnostics_never_store_raw_text(service):
    service.policy.set("semantic_conflict_enabled", True)
    service.policy.set("semantic_conflict_threshold", 0.3)
    secret_text = "My private note about the quarterly strategy"
    service.write_memory(
        memory_type="preference", content=secret_text,
        source="explicit_user", scope="user", scope_id="u1", subject="note-style",
    )
    service.write_memory(
        memory_type="preference", content="My private note about the annual strategy",
        source="explicit_user", scope="user", scope_id="u1", subject="note-style",
    )
    events = service.store.list_memory_events(limit=200)
    for event in events:
        if event["type"].startswith("memory.semantic"):
            serialized = str(event["data"])
            assert secret_text not in serialized


# ── More Phase 8 reliability cases ──────────────────────────────────────────


def test_backend_timeout_falls_back_and_reports(service):
    class SlowBackend:
        name = "slow2"; version = "test"
        def available(self): return True
        def similarity(self, a, b):
            import time; time.sleep(0.05)
            return 1.0

    semantic.register_backend(SlowBackend())
    try:
        result = semantic.find_candidates(
            content="I prefer concise answers",
            same_dimension=[{"id": f"m{i}", "content": "I prefer detailed answers"} for i in range(20)],
            settings={
                "semantic_conflict_enabled": True,
                "semantic_conflict_threshold": 0.1,
                "semantic_conflict_timeout_ms": 20,
            },
            backend_name="slow2",
        )
        assert result.timedOut is True
        # A timed-out search returns only the candidates scored within the bound;
        # it never raises and never scans the whole pool.
        assert len(result.candidates) <= 1
    finally:
        semantic.register_backend(semantic.CharNgramBackend())


def test_reset_and_restore_leave_semantic_state_consistent(service):
    from harness.eclipse_memory.transfer import reset_memory

    service.policy.set("semantic_conflict_enabled", True)
    first = service.write_memory(
        memory_type="preference", content="I prefer reports as PDF",
        source="explicit_user", scope="user", scope_id="u1", subject="report-format",
    )
    reset_memory(service.store, confirm=True, backup_first=False)
    # Policy survives reset (it is not memory domain); a fresh conflicting write
    # still behaves deterministically.
    second = service.write_memory(
        memory_type="preference", content="I prefer reports as PDF",
        source="explicit_user", scope="user", scope_id="u1", subject="report-format",
    )
    assert second["id"] != first["id"]
    assert len(service.store.list_memories(include_inactive=True)) == 1


def test_semantic_disabled_mode_never_stores_candidate(service):
    # Default (disabled): a same-dimension near-match is not proposed by semantic.
    service.write_memory(
        memory_type="preference", content="I prefer reports as PDF",
        source="explicit_user", scope="user", scope_id="u1", subject="report-format",
    )
    events = service.store.list_memory_events(limit=100)
    assert not any(e["type"] == "memory.semantic_candidate" for e in events)
    assert not any(e["type"] == "memory.semantic_diagnostics" for e in events)


def test_rebuild_route_is_honest_and_operator_authorized(monkeypatch):
    import os
    import tempfile

    os.environ.setdefault(
        "ECLIPSE_MEMORY_DB_PATH",
        os.path.join(tempfile.mkdtemp(prefix="be-sem-rebuild-"), "eclipse-memory.db"),
    )
    from fastapi.testclient import TestClient
    from harness import main as main_module

    with TestClient(main_module.app) as client:
        res = client.post("/eclipse-memory/semantic/rebuild", json={})
        # Loopback TestClient is an operator, so this succeeds and is honest.
        assert res.status_code == 200
        body = res.json()
        assert body["persistentIndex"] is False
        assert body["rebuilt"] is False

