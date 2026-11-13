"""Corpus-level BM25 for memory retrieval (W5.3).

The old ``hybrid.bm25_score`` scored one query against one document, so IDF
collapsed to a constant. This module builds a real index over the eligible
candidate set: term frequency, document frequency, and average document length
are all computed over the same corpus the query is ranked against.

It is deterministic, dependency-free, and **only a ranking signal**. It never
decides authorization, status, scope, or relevance on its own; the caller's
gate still decides whether a memory is eligible and whether it carries a
topical signal.

Empty query or empty corpus ⇒ every score is 0.0. A document with no query term
scores 0.0. Scores are normalized to ``[0, 1]`` so they can be added to the
existing bounded relevance score without changing its scale.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Mapping, Optional

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens. No stemming (the caller normalizes)."""
    return [token for token in _TOKEN_RE.findall((text or "").lower()) if token]


class BM25Index:
    """A small in-memory BM25 index over a fixed candidate corpus."""

    def __init__(
        self, documents: Mapping[str, str], *, k1: float = 1.2, b: float = 0.75,
    ) -> None:
        self.k1 = float(k1)
        self.b = float(b)
        self._ids: list[str] = []
        self._counts: list[Counter[str]] = []
        self._lengths: list[int] = []
        document_frequency: Counter[str] = Counter()
        for doc_id, text in documents.items():
            tokens = tokenize(text)
            counts = Counter(tokens)
            self._ids.append(str(doc_id))
            self._counts.append(counts)
            self._lengths.append(len(tokens))
            for term in counts:
                document_frequency[term] += 1
        self._n = len(self._ids)
        self._avg_length = (
            sum(self._lengths) / self._n if self._n else 0.0
        )
        # BM25 IDF with a floor at 0: a term in every document is not a signal.
        self._idf: dict[str, float] = {
            term: (
                0.0 if df >= self._n  # present everywhere ⇒ no discriminative power
                else max(0.0, math.log(1.0 + (self._n - df + 0.5) / (df + 0.5)))
            )
            for term, df in document_frequency.items()
        }

    def __len__(self) -> int:
        return self._n

    def scores(self, query: str) -> dict[str, float]:
        """BM25 for every document, normalized to ``[0, 1]``."""
        terms = tokenize(query)
        if not terms or not self._n:
            return {doc_id: 0.0 for doc_id in self._ids}
        raw: list[float] = []
        for counts, length in zip(self._counts, self._lengths):
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                idf = self._idf.get(term, 0.0)
                if idf <= 0.0:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * (length / (self._avg_length or 1.0))
                )
                score += idf * (frequency * (self.k1 + 1.0)) / denominator
            raw.append(score)
        peak = max(raw) if raw else 0.0
        if peak <= 0.0:
            return {doc_id: 0.0 for doc_id in self._ids}
        return {
            doc_id: round(value / peak, 6)
            for doc_id, value in zip(self._ids, raw)
        }


def bm25_scores(
    query: str, documents: Mapping[str, str], *, k1: float = 1.2, b: float = 0.75,
) -> dict[str, float]:
    """Convenience: build an index for one query and return normalized scores."""
    return BM25Index(documents, k1=k1, b=b).scores(query)


def score_documents(
    query: str, documents: Iterable[tuple[str, str]],
) -> dict[str, float]:
    """Iterable-friendly wrapper (used when a caller has rows, not a dict)."""
    return bm25_scores(query, {str(doc_id): text for doc_id, text in documents})


__all__ = ["BM25Index", "bm25_scores", "score_documents", "tokenize"]
