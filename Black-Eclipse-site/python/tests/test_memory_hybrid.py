"""Milestone 7 — hybrid ranking and logical namespaces.

These tests assert the deterministic, candidate-only properties: namespaces keep
categories separate, hybrid components are bounded, semantic similarity only
nudges an already-present memory, and no semantic signal can authorize anything.
"""

from __future__ import annotations

from harness.eclipse_memory.hybrid import (
    NAMESPACES,
    WEIGHTS,
    bm25_score,
    hybrid_score,
    namespace_for,
    rank_hybrid,
)


def test_namespace_mapping_is_deterministic():
    assert namespace_for("preference") == "preference"
    assert namespace_for("constraint") == "preference"
    assert namespace_for("correction") == "correction"
    assert namespace_for("procedural") == "workflow"
    assert namespace_for("summary") == "session_summary"
    assert namespace_for("semantic", "user") == "preference"
    assert namespace_for("semantic", "general") == "project_fact"
    for value in (namespace_for(t) for t in ("preference", "semantic", "correction")):
        assert value in NAMESPACES


def test_bm25_is_bounded_and_monotonic():
    assert 0.0 <= bm25_score("reporting currency", "reporting currency PKR") <= 1.0
    assert bm25_score("reporting currency", "reporting currency PKR") > bm25_score(
        "reporting currency", "unrelated content"
    )
    assert bm25_score("", "anything") == 0.0
    assert bm25_score("x", "") == 0.0


def test_hybrid_malformed_semantic_is_ignored():
    memory = {"id": "m1", "content": "User prefers concise answers.", "memoryType": "preference"}
    normal = hybrid_score(memory, query="concise answers", lexical=0.8)
    malformed = hybrid_score(memory, query="concise answers", lexical=0.8, semantic=float("nan"))
    assert malformed["components"]["semantic"] == 0.0
    assert malformed["total"] == normal["total"]


def test_hybrid_semantic_only_nudges():
    memory = {"id": "m1", "content": "User prefers concise answers.", "memoryType": "preference"}
    low = hybrid_score(memory, query="concise answers", lexical=0.5, semantic=0.0)
    high = hybrid_score(memory, query="concise answers", lexical=0.5, semantic=1.0)
    # Semantic can raise the score but only by its bounded weight.
    assert high["total"] > low["total"]
    assert (high["total"] - low["total"]) <= WEIGHTS["semantic"] + 1e-6


def test_rank_hybrid_is_deterministic_and_namespaced():
    memories = [
        {"id": "p1", "content": "User prefers concise answers.", "memoryType": "preference"},
        {"id": "f1", "content": "Project uses PKR reporting.", "memoryType": "semantic"},
        {"id": "p2", "content": "User prefers concise answers always.", "memoryType": "preference"},
    ]
    ranked = rank_hybrid(memories, query="concise answers", namespace="preference")
    ids = [r["memoryId"] for r in ranked]
    assert "f1" not in ids  # namespace-separated
    assert ids[0] in ("p1", "p2")
    assert ranked == rank_hybrid(memories, query="concise answers", namespace="preference")


def test_rank_hybrid_empty_is_safe():
    assert rank_hybrid([], query="anything") == []


def test_hybrid_components_present():
    memory = {"id": "m1", "content": "Prefers concise answers.", "memoryType": "preference",
              "authority": "automatic", "accessCount": 3, "scope": "user"}
    result = hybrid_score(memory, query="concise")
    for key in ("lexical", "bm25", "semantic", "authority", "scope", "recency", "access", "verified"):
        assert key in result["components"]
    # An automatic memory scores authority 0 (explicit is preferred).
    assert result["components"]["authority"] == 0.0
