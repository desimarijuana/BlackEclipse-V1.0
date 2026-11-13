"""Explainable hybrid memory ranking with separate namespaces.

**STATUS: helper for the W5.3 hybrid path.** Production ranking now lives in
`retrieval.retrieve_memories`, which uses `bm25.BM25Index` (corpus-level IDF)
behind `HARNESS_MEMORY_HYBRID`. This module remains the namespace/weight
explanation seam and the bounded single-document scorer; it does not authorize
recall on its own. When the flag is off, `retrieval` uses its original
deterministic `_score` and this module does not influence anything.

This module adds an EXPLICIT, deterministic hybrid score and a namespace model to
memory retrieval. It does not authorize anything: it reorders only memories that
already passed the authoritative scope/status/expiry/recall-policy filter, and a
semantic component can only nudge an already-lexically-relevant memory — never
surface an excluded one.

Namespaces keep different content categories apart so a preference is not scored
against a session summary or a skill definition. This is a *logical* namespace
(a deterministic mapping from memory type/scope), not a second vector index —
persistent vector infrastructure is deliberately out of scope.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Optional

# Logical namespaces. Do not mix content categories in one ranking bucket.
NAMESPACES = (
    "preference",
    "project_fact",
    "correction",
    "workflow",
    "skill",
    "session_summary",
)

# Weights. Lexical/authority dominate; semantic is a bounded tie-break.
WEIGHTS = {
    "lexical": 1.0,
    "bm25": 0.5,
    "semantic": 0.35,
    "authority": 0.4,
    "scope": 0.2,
    "recency": 0.3,
    "access": 0.15,
}


def namespace_for(memory_type: str, scope: Optional[str] = None) -> str:
    """Map a memory record to its logical namespace (deterministic)."""
    kind = (memory_type or "").lower()
    if kind in ("preference", "constraint"):
        return "preference"
    if kind in ("correction", "correction_candidate"):
        return "correction"
    if kind in ("procedural", "workflow"):
        return "workflow"
    if kind in ("skill", "skill_candidate", "skill_patch"):
        return "skill"
    if kind in ("summary", "session_summary"):
        return "session_summary"
    if scope == "user":
        return "preference"
    return "project_fact"


def _terms(text: str) -> list[str]:
    return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split() if t]


def bm25_score(query: str, document: str, *, k1: float = 1.2, b: float = 0.75) -> float:
    """A small, self-contained BM25 between one query and one document.

    Single-document IDF collapses; this is a bounded lexical overlap score used
    only as one hybrid component, never as an authorization signal.
    """
    query_terms = _terms(query)
    doc_terms = _terms(document)
    if not query_terms or not doc_terms:
        return 0.0
    doc_counts = Counter(doc_terms)
    avg_len = max(1.0, float(len(doc_terms)))
    score = 0.0
    for term in set(query_terms):
        freq = doc_counts.get(term, 0)
        if not freq:
            continue
        denom = freq + k1 * (1 - b + b * (len(doc_terms) / avg_len))
        score += (freq * (k1 + 1)) / denom
    # Normalize by the number of distinct query terms to keep it in [0, ~1].
    return min(1.0, score / max(1, len(set(query_terms))))


def _recency_score(stamp: Optional[str], *, now: float) -> float:
    if not stamp:
        return 0.0
    try:
        import datetime

        parsed = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        age_days = max(0.0, (now - parsed.timestamp()) / 86400.0)
        return round(math.exp(-age_days / 30.0), 4)
    except Exception:  # noqa: BLE001 - an unparseable stamp is neutral
        return 0.0


def hybrid_score(
    memory: dict[str, Any],
    *,
    query: str,
    lexical: float = 0.0,
    semantic: Optional[float] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """The bounded hybrid score for ONE already-authorized memory.

    Returns the score plus its components (for explainable diagnostics). Scope is
    assumed already enforced by the caller; it contributes only a small positive
    bonus when it matches, never a filter bypass.
    """
    import time

    now = now if now is not None else time.time()
    bm25 = bm25_score(query, memory.get("content") or "")
    authority = 0.0 if (memory.get("authority") or "explicit") == "automatic" else 1.0
    verified = 1.0 if memory.get("verification") == "verified" else 0.0
    scope_bonus = 1.0 if memory.get("scope") == "user" else 0.5
    recency = _recency_score(
        memory.get("lastConfirmedAt") or memory.get("updatedAt") or memory.get("createdAt"), now=now
    )
    access = min(1.0, math.log1p(int(memory.get("accessCount") or 0)) / 3.0)
    # A semantic component is advisory only and bounded; absence contributes 0.
    semantic_component = float(semantic) if semantic is not None else 0.0
    if not (0.0 <= semantic_component <= 1.0):
        semantic_component = 0.0

    total = (
        WEIGHTS["lexical"] * float(lexical)
        + WEIGHTS["bm25"] * bm25
        + WEIGHTS["semantic"] * semantic_component
        + WEIGHTS["authority"] * authority
        + WEIGHTS["scope"] * scope_bonus
        + WEIGHTS["recency"] * recency
        + WEIGHTS["access"] * access
        + 0.1 * verified
    )
    return {
        "total": round(total, 6),
        "namespace": namespace_for(memory.get("memoryType") or "", memory.get("scope")),
        "components": {
            "lexical": round(float(lexical), 4),
            "bm25": round(bm25, 4),
            "semantic": round(semantic_component, 4),
            "authority": authority,
            "scope": scope_bonus,
            "recency": recency,
            "access": round(access, 4),
            "verified": verified,
        },
    }


def rank_hybrid(
    memories: list[dict[str, Any]],
    *,
    query: str,
    lexical_by_id: Optional[dict[str, float]] = None,
    semantic_by_id: Optional[dict[str, float]] = None,
    namespace: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Rank already-authorized memories by the hybrid score.

    When `namespace` is set, only memories in that namespace are ranked (the
    separate-namespace rule). The result is a new list of
    `{memoryId, score, namespace, components}` in descending order with a stable
    id tie-break, so the ordering is deterministic.
    """
    lexical_by_id = lexical_by_id or {}
    semantic_by_id = semantic_by_id or {}
    scored: list[dict[str, Any]] = []
    for memory in memories:
        mem_ns = namespace_for(memory.get("memoryType") or "", memory.get("scope"))
        if namespace and mem_ns != namespace:
            continue
        result = hybrid_score(
            memory,
            query=query,
            lexical=lexical_by_id.get(memory.get("id") or "", 0.0),
            semantic=semantic_by_id.get(memory.get("id") or ""),
        )
        scored.append({
            "memoryId": memory.get("id"),
            "score": result["total"],
            "namespace": mem_ns,
            "components": result["components"],
        })
    scored.sort(key=lambda c: (-c["score"], c["memoryId"] or ""))
    return scored


__all__ = [
    "NAMESPACES",
    "WEIGHTS",
    "bm25_score",
    "hybrid_score",
    "namespace_for",
    "rank_hybrid",
]
