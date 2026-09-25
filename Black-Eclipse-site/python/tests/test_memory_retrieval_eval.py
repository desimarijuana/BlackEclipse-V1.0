"""Memory retrieval evaluation — the versioned labeled set, baseline metrics,
scope/status/privacy authority and explainable diagnostics.

This locks in recorded behaviour so a retrieval change cannot silently regress
recall, leak scope, or start recalling superseded facts.
"""

from __future__ import annotations

import os
import tempfile

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.eval import load_dataset, run_evaluation
from harness.eclipse_memory.retrieval import retrieve_memories


def test_eval_dataset_is_versioned():
    dataset = load_dataset()
    assert dataset["name"] == "memory-retrieval"
    assert dataset["version"] >= 1
    assert dataset["cases"]


def test_baseline_recall_precision_and_safety():
    report = run_evaluation()
    metrics = report["metrics"]
    # The recorded baseline: recall must stay complete, and no case may leak a
    # scope, recall a forbidden memory, or pull topical noise into a no-match.
    assert metrics["recall"] == 1.0
    assert metrics["scopeLeakage"] == 0
    assert metrics["forbiddenHits"] == 0
    assert metrics["noMatchClean"] is True
    assert metrics["precision"] >= 0.5
    assert metrics["overBudgetCases"] == 0


def test_superseded_memory_is_never_recalled():
    report = run_evaluation()
    case = next(c for c in report["cases"] if c["caseId"] == "superseded-not-recalled")
    assert case["forbiddenHits"] == []
    assert case["recall"] == 1.0


def test_scope_boundary_case_leaks_nothing():
    report = run_evaluation()
    case = next(c for c in report["cases"] if c["caseId"] == "scope-boundary")
    assert case["scopeLeaks"] == []
    assert case["forbiddenHits"] == []


# ── Explainable diagnostics ─────────────────────────────────────────────────


def _service():
    directory = tempfile.mkdtemp(prefix="be-diag-")
    return EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))


def test_diagnostics_explain_inclusion_and_exclusion():
    service = _service()
    try:
        service.write_memory(
            memory_type="semantic", content="The benchmark rate is 5 percent",
            source="manual", scope="general",
        )
        service.write_memory(
            memory_type="semantic", content="An unrelated fact about shipping lanes",
            source="manual", scope="general",
        )
        result = retrieve_memories(service.store, query="benchmark rate", actor_scope="user")
        diagnostics = result.diagnostics
        # The relevant memory is selected with a stated reason.
        assert any("benchmark" in r.lower() or "keyword match" in r.lower()
                   for r in diagnostics["selectionReasons"])
        # The irrelevant memory is excluded with an explainable reason.
        assert any("relevance" in e["reason"] for e in diagnostics["excluded"])
    finally:
        service.close()


def test_retrieval_never_broadens_scope_for_semantic_style():
    service = _service()
    try:
        service.write_memory(
            memory_type="preference", content="u1 prefers dark mode",
            source="explicit_user", scope="user", scope_id="u1",
        )
        result = retrieve_memories(service.store, query="dark mode", actor_scope="user")
        # No scope_id => the actor is not u1 => u1's preference is not returned.
        assert all(m.get("scopeId") != "u1" for m in result.memories)
    finally:
        service.close()
