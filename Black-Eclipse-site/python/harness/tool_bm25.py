"""W3.3 — the small, pure BM25 ranker behind `tool_search`.

Deliberately dependency-free and separate from `eclipse_memory/hybrid.py` (an
experimental module with a different corpus and a different lifecycle). This is
a retrieval primitive for the TOOL catalogue only: name, tags, description and
domain. There is no index to build or persist — a run's registry is small
enough that scoring at query time is the honest, deterministic choice.

Field weighting is expressed by repeating a field's tokens before BM25 runs:
name ×4, tags ×2, description ×1, domain ×1. That keeps the ranker one corpus
with one IDF table instead of four ad-hoc score components.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Tokens that carry no retrieval signal in a tool query.
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "into", "is", "it", "of", "on", "or", "the", "this", "to",
    "tool", "use", "with",
})

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

#: BM25 parameters. Standard defaults; no tuning per deployment.
K1 = 1.2
B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase, split snake_case/camelCase and non-alphanumerics, drop noise."""
    spaced = _CAMEL.sub(" ", str(text or ""))
    return [
        token
        for token in _NON_ALNUM.split(spaced.lower())
        if len(token) >= 2 and token not in STOPWORDS
    ]


def _weighted_tokens(tool: Any) -> list[str]:
    name = str(getattr(tool, "name", "") or "")
    tags = " ".join(str(tag) for tag in (getattr(tool, "tags", ()) or ()))
    description = str(getattr(tool, "description", "") or "")
    domain = str(getattr(tool, "domain", "") or "")
    tokens = tokenize(name) * 4
    tokens += tokenize(tags) * 2
    tokens += tokenize(description)
    tokens += tokenize(domain)
    return tokens


@dataclass
class BM25Index:
    """A deterministic BM25 index over a tool registry's current contents."""

    tools: list[Any]
    _docs: list[list[str]] = field(default_factory=list, init=False)
    _df: dict[str, int] = field(default_factory=dict, init=False)
    _avg_len: float = 0.0

    def __post_init__(self) -> None:
        self._docs = [_weighted_tokens(tool) for tool in self.tools]
        for tokens in self._docs:
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1
        total = sum(len(tokens) for tokens in self._docs)
        self._avg_len = (total / len(self._docs)) if self._docs else 0.0

    @property
    def size(self) -> int:
        return len(self._docs)

    def score(self, query: str, index: int) -> float:
        """BM25 score for one document. Public so the caller can compose boosts."""
        tokens = self._docs[index]
        if not tokens or not query:
            return 0.0
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        n = len(self._docs)
        avg = self._avg_len or 1.0
        for term in tokenize(query):
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = self._df.get(term, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            denom = tf + K1 * (1 - B + B * (len(tokens) / avg))
            score += idf * (tf * (K1 + 1)) / denom
        return score

    def search(self, query: str, limit: int) -> list[tuple[float, Any]]:
        """Top `limit` scoring tools, stable by tool name on ties."""
        scored = [
            (self.score(query, index), tool)
            for index, tool in enumerate(self.tools)
        ]
        scored = [(score, tool) for score, tool in scored if score > 0]
        scored.sort(key=lambda item: (-item[0], str(getattr(item[1], "name", ""))))
        return scored[: max(0, limit)]


def exact_name_rank(query: str, tool: Any) -> int:
    """Deterministic exact/prefix boost applied on top of BM25.

    100 = exact name, 80 = name starts with the query, 60 = query inside the
    name. A model that already knows the name must never get a fuzzy result.
    """
    q = str(query or "").strip().lower()
    name = str(getattr(tool, "name", "") or "").lower()
    if not q:
        return 0
    if q == name:
        return 100
    if name.startswith(q):
        return 80
    if q in name:
        return 60
    return 0


def rank_tools(query: str, tools: Iterable[Any], limit: int) -> list[Any]:
    """The one ranking entry point used by `tool_search`."""
    ordered = list(tools)
    index = BM25Index(ordered)
    boosted: list[tuple[float, Any]] = []
    for position, tool in enumerate(ordered):
        boost = exact_name_rank(query, tool)
        bm25 = index.score(query, position)
        if boost or bm25 > 0:
            boosted.append((boost + bm25, tool))
    boosted.sort(key=lambda item: (-item[0], str(getattr(item[1], "name", ""))))
    return [tool for _score, tool in boosted[: max(0, limit)]]


__all__ = [
    "B",
    "BM25Index",
    "K1",
    "STOPWORDS",
    "exact_name_rank",
    "rank_tools",
    "tokenize",
]
