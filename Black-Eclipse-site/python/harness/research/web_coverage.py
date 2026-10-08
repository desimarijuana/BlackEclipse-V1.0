"""Sub-question coverage scoring for the web research engine.

Layered, and the method is disclosed to the caller (`coverageMethod`):

  1. `semantic` — embedding similarity, when an embedding runtime is available;
  2. `idf`      — IDF-weighted term overlap (deterministic, no model). A
                  sub-question matches only when its DISTINCTIVE terms are
                  corroborated, not merely any single token;
  3. `keyword`  — conservative any-token corroboration (last resort).

This is a COVERAGE signal, never a claim that an answer is correct. Extracted
from `web_engine` to keep that orchestrator under the size ceiling; behavior is
unchanged.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from .web_contracts import Evidence, WebResearchMandate

_COVERAGE_SIM_THRESHOLD = 0.62
_IDF_COVERAGE_THRESHOLD = 0.5

_STOP_TOKENS = frozenset(
    {"the", "and", "for", "with", "that", "this", "from", "what", "when", "where",
     "how", "who", "why", "does", "did", "are", "was", "were", "will", "latest",
     "current", "about", "into", "over", "news", "research", "analyze", "analysis"}
)


def _question_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", (text or "").lower()) if t not in _STOP_TOKENS}


def _keyword_answered(mandate: WebResearchMandate, evidence: list[Evidence]) -> int:
    """Fallback-of-the-fallback: a sub-question is answered when any significant
    keyword appears in an admissible evidence item's text/title/metric."""
    if not mandate.subQuestions:
        return 0
    haystacks: list[str] = []
    for ev in evidence:
        haystacks.append(ev.rawText.lower())
        if isinstance(ev.provenance, dict):
            haystacks.append(str(ev.provenance.get("title") or "").lower())
            haystacks.append(str(ev.provenance.get("metric") or "").lower())
        haystacks.append((ev.claimText or "").lower())
    blob = " ".join(haystacks)
    if not blob.strip():
        return 0
    answered = 0
    for sq in mandate.subQuestions:
        tokens = _question_tokens(sq.question)
        if tokens and any(token in blob for token in tokens):
            answered += 1
    return answered


def _evidence_docs(evidence: list[Evidence]) -> list[str]:
    docs: list[str] = []
    for ev in evidence:
        parts = [ev.rawText or "", (ev.claimText or "")]
        if isinstance(ev.provenance, dict):
            parts.append(str(ev.provenance.get("title") or ""))
            parts.append(str(ev.provenance.get("metric") or ""))
        docs.append(" ".join(parts).lower())
    return docs


def _idf_answered(mandate: WebResearchMandate, evidence: list[Evidence]) -> Optional[tuple[int, list[float]]]:
    """Distributional coverage: an IDF-weighted overlap score per sub-question.

    Unlike the keyword fallback (any single token present), this weights each
    question token by how rare it is across the retrieved evidence, so a question
    matches only when its DISTINCTIVE terms are corroborated — a real, deterministic
    improvement over substring matching that needs no model. Returns (answered,
    per-question scores) or None when there are no sub-questions.
    """
    if not mandate.subQuestions or not evidence:
        return None
    docs = [d for d in _evidence_docs(evidence) if d.strip()]
    if not docs:
        return None
    tokenized = [set(re.findall(r"[a-z0-9]{3,}", d)) for d in docs]
    n = len(tokenized)
    df: dict[str, int] = {}
    for toks in tokenized:
        for t in toks:
            df[t] = df.get(t, 0) + 1

    def idf(t: str) -> float:
        return math.log((1 + n) / (1 + df.get(t, 0))) + 1.0

    answered = 0
    scores: list[float] = []
    for sq in mandate.subQuestions:
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", sq.question.lower()) if t not in _STOP_TOKENS}
        if not q_tokens:
            scores.append(0.0)
            continue
        total = sum(idf(t) for t in q_tokens)
        best = 0.0
        for toks in tokenized:
            hit = sum(idf(t) for t in q_tokens if t in toks)
            if total:
                best = max(best, hit / total)
        scores.append(round(best, 4))
        if best >= _IDF_COVERAGE_THRESHOLD:
            answered += 1
    return answered, scores


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _semantic_answered(
    mandate: WebResearchMandate, evidence: list[Evidence]
) -> Optional[tuple[int, list[float]]]:
    """Optional embedding-based coverage. Returns (answered, per-question scores)
    or None when no embedding runtime is available — the caller then falls back to
    the IDF/keyword layers. Never raises."""
    if not mandate.subQuestions or not evidence:
        return None
    try:
        from ..model_runtime.embeddings import embed_texts  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - embeddings are optional
        return None
    try:
        questions = [sq.question for sq in mandate.subQuestions]
        docs = [(ev.rawText or "")[:2000] for ev in evidence]
        q_vecs = embed_texts(questions)
        d_vecs = embed_texts(docs)
        if not q_vecs or not d_vecs:
            return None
        answered = 0
        scores: list[float] = []
        for qv in q_vecs:
            best = 0.0
            for dv in d_vecs:
                best = max(best, _cosine(qv, dv))
            scores.append(round(best, 4))
            if best >= _COVERAGE_SIM_THRESHOLD:
                answered += 1
        return answered, scores
    except Exception:  # noqa: BLE001 - a model failure is an offline fallback, never a crash
        return None


def answered_questions(mandate: WebResearchMandate, evidence: list[Evidence]) -> tuple[int, str, list[float]]:
    """Count sub-questions with corroborating evidence.

    Returns `(answered, method, perQuestionScores)`. Prefers semantic embedding
    similarity when available; else IDF-weighted overlap; else keyword
    corroboration. This is a coverage signal, NOT a correctness claim.
    """
    semantic = _semantic_answered(mandate, evidence)
    if semantic is not None:
        answered, scores = semantic
        return answered, "semantic", scores
    idf = _idf_answered(mandate, evidence)
    if idf is not None:
        answered, scores = idf
        return answered, "idf", scores
    return _keyword_answered(mandate, evidence), "keyword", []


__all__ = [
    "answered_questions",
    "_keyword_answered",
    "_idf_answered",
    "_semantic_answered",
    "_cosine",
    "_STOP_TOKENS",
    "_COVERAGE_SIM_THRESHOLD",
    "_IDF_COVERAGE_THRESHOLD",
]
