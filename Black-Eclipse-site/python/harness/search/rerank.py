"""Second-stage reranking.

Retrieve a wide candidate set, rerank to a narrow top-K. The local reranker is a
deterministic lexical-coverage model — real and testable, no model call. Provider
rerankers (Cohere, Voyage) are registered only when a credential is present; a
provider failure degrades to the local reranker rather than dropping the results.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from .contracts import SearchHit

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*")


class Reranker:
    name = "local"

    def score(self, query: str, documents: list[str]) -> list[float]:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class LocalLexicalReranker(Reranker):
    """Deterministic reranker: query-term coverage + phrase + cohesion."""

    name = "local-lexical"

    def score(self, query: str, documents: list[str]) -> list[float]:
        terms = [t.lower() for t in _TOKEN_RE.findall(query or "") if len(t) > 1]
        if not terms:
            return [0.0 for _ in documents]
        scores: list[float] = []
        for doc in documents:
            lowered = (doc or "").lower()
            doc_terms = [t.lower() for t in _TOKEN_RE.findall(doc or "")]
            doc_set = set(doc_terms)
            coverage = sum(1 for t in terms if t in doc_set) / len(terms)
            frequency = sum(lowered.count(t) for t in terms) / max(1, len(doc_terms))
            phrase = 1.0 if query.strip().lower() in lowered else 0.0
            length_penalty = 1.0 / (1.0 + math.log1p(max(0, len(doc_terms) - 200) / 200.0))
            scores.append(round(0.6 * coverage + 0.2 * min(1.0, frequency) + 0.2 * phrase, 6) * length_penalty)
        return scores


class _ProviderReranker(Reranker):
    """Base for HTTP rerankers. Subclasses supply the endpoint + payload."""

    name = "provider"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def rerank_async(self, query: str, documents: list[str]) -> list[float]:
        import httpx  # noqa: PLC0415

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/rerank",
                headers=headers,
                json={"model": self._model, "query": query, "documents": documents, "top_n": len(documents)},
            )
            response.raise_for_status()
            data = response.json()
        scores = [0.0] * len(documents)
        for item in data.get("results", []) or data.get("data", []):
            index = int(item.get("index", 0) or 0)
            value = item.get("relevance_score", item.get("score", 0.0))
            if 0 <= index < len(scores):
                scores[index] = float(value)
        return scores


class CohereReranker(_ProviderReranker):
    name = "cohere"


class VoyageReranker(_ProviderReranker):
    name = "voyage"


def build_reranker(config: Any, settings: Any = None) -> Reranker:
    """Return a provider reranker when configured+credentialed, else local."""
    provider = (getattr(config, "rerank_provider", "") or "").strip().lower()
    if not provider:
        return LocalLexicalReranker()
    model = getattr(config, "rerank_model", "") or ""
    api_key = None
    base_url = None
    if settings is not None and getattr(settings, "provider", None) == provider:
        api_key = getattr(settings, "api_key", None)
        base_url = getattr(settings, "base_url", None)
    import os

    if provider == "cohere":
        api_key = api_key or os.environ.get("COHERE_API_KEY", "")
        base_url = base_url or "https://api.cohere.com/v2"
        model = model or "rerank-v3.5"
        if api_key:
            return CohereReranker(api_key=api_key, model=model, base_url=base_url)
    if provider == "voyage":
        api_key = api_key or os.environ.get("VOYAGE_API_KEY", "")
        base_url = base_url or "https://api.voyageai.com/v1"
        model = model or "rerank-2"
        if api_key:
            return VoyageReranker(api_key=api_key, model=model, base_url=base_url)
    return LocalLexicalReranker()


async def rerank_hits(
    hits: list[SearchHit], query: str, reranker: Reranker, *, top_k: int, score_weight: float
) -> list[SearchHit]:
    """Rerank and blend. Provider errors fall back to the local reranker."""
    if not hits or top_k <= 0:
        return []
    documents = [h.content for h in hits]
    scores: Optional[list[float]] = None
    if isinstance(reranker, _ProviderReranker):
        try:
            scores = await reranker.rerank_async(query, documents)
        except Exception:  # noqa: BLE001 - never lose results to a reranker outage
            scores = None
    if scores is None:
        scores = (reranker if isinstance(reranker, LocalLexicalReranker) else LocalLexicalReranker()).score(
            query, documents
        )
    ranked: list[SearchHit] = []
    for hit, score in zip(hits, scores):
        hit.rerank_score = float(score)
        # Blend reranker into the final score without discarding the retrieval
        # signal: a reranker is a re-ordering aid, not a silent replacement.
        hit.score = (1.0 - score_weight) * hit.score + score_weight * float(score)
        ranked.append(hit)
    ranked.sort(key=lambda h: (h.score, h.rerank_score or 0.0), reverse=True)
    return ranked[:top_k]


__all__ = ["CohereReranker", "LocalLexicalReranker", "Reranker", "VoyageReranker", "build_reranker", "rerank_hits"]
