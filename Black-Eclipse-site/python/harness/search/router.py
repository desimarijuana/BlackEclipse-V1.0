"""Search router — chooses the retrieval strategy for a query.

Not every financial question should hit vector search. A request for a number
("NVDA FY2026 revenue") is served by the structured financial engine plus
keyword/entity search; a conceptual research question ("what factors are driving
AI infrastructure demand?") is served by hybrid/semantic search. The router makes
that choice deterministic and explainable, and can decompose a complex question
into sub-questions for the Evidence & Research engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .contracts import SearchMode

_HOW_MUCH_RE = re.compile(r"\b(how (much|many)|what (was|were|is|are) the|revenue|earnings|eps|"
                          r"price|market cap|dividend|p/e|pe ratio|margin[s]?)\b", re.I)
_WHY_RE = re.compile(r"\b(why|what (factors|drove|drove|is driving|are driving)|explain|"
                     r"how does|how do|impact of|implications?|outlook|thesis|risk)\b", re.I)
_COMPARE_RE = re.compile(r"\b(compare|versus|vs\.?|relative to|against each other|difference between)\b", re.I)
_IDENTIFIER_RE = re.compile(r"\b([A-Z]{1,5})\b|\b[A-Za-z]+:[A-Za-z0-9.]+\b")

_FINANCIAL_SUBQUESTIONS = ("revenue", "gross margin", "operating margin", "cogs",
                           "pricing", "product mix", "management commentary", "guidance")


@dataclass
class RouteDecision:
    mode: str
    reason: str
    structured_first: bool = False
    decompose: bool = False
    sub_queries: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "structuredFirst": self.structured_first,
            "decompose": self.decompose,
            "subQueries": self.sub_queries,
            "entities": self.entities,
        }


def _has_entity(query: str) -> bool:
    return bool(_IDENTIFIER_RE.search(query or ""))


def route_query(query: str, *, default_mode: str = SearchMode.HYBRID.value) -> RouteDecision:
    text = (query or "").strip()
    if not text:
        return RouteDecision(mode=default_mode, reason="empty query")

    numeric = bool(_HOW_MUCH_RE.search(text))
    conceptual = bool(_WHY_RE.search(text))
    compare = bool(_COMPARE_RE.search(text))
    entity = _has_entity(text)

    if numeric and not conceptual:
        return RouteDecision(
            mode=SearchMode.KEYWORD.value,
            reason="quantitative question: structured financial engine + keyword/entity search",
            structured_first=True,
            entities=_entities(text),
        )
    if conceptual:
        decision = RouteDecision(
            mode=SearchMode.HYBRID.value,
            reason="conceptual research question: hybrid semantic + keyword search",
            decompose=True,
            sub_queries=decompose(text) if compare or _is_complex(text) else [],
            entities=_entities(text),
        )
        return decision
    if compare:
        return RouteDecision(
            mode=SearchMode.HYBRID.value,
            reason="comparison: hybrid search with decomposition",
            decompose=True,
            sub_queries=decompose(text),
            entities=_entities(text),
        )
    if entity and len(text.split()) <= 4:
        return RouteDecision(
            mode=SearchMode.HYBRID.value,
            reason="short entity query: entity-aware hybrid search",
            structured_first=True,
            entities=_entities(text),
        )
    return RouteDecision(mode=default_mode, reason="default hybrid retrieval", entities=_entities(text))


def _entities(query: str) -> list[str]:
    found = []
    for match in _IDENTIFIER_RE.finditer(query or ""):
        token = (match.group(0) or "").strip()
        if token and token not in found:
            found.append(token)
    return found[:8]


def _is_complex(query: str) -> bool:
    return len(query.split()) >= 12 or query.count("?") >= 1 and len(query.split()) >= 8


def decompose(query: str) -> list[str]:
    """Deterministic decomposition of a complex research question.

    Produces focused sub-queries for the Evidence & Research engine: the head
    question plus a small set of finance-specific angles when the topic is about
    margins/why-certain-questions. Never an unbounded LLM fan-out.
    """
    text = (query or "").strip()
    if not text:
        return []
    sub_queries: list[str] = [text]
    # Split on explicit conjunctions/commas into clauses for comparison questions.
    clauses = [c.strip() for c in re.split(r";|,\s+and\s+|\band\b(?!\s+the\b)|\bvs\.?\b", text) if c.strip()]
    for clause in clauses:
        if 4 <= len(clause.split()) and clause.lower() != text.lower():
            sub_queries.append(clause)
    if _WHY_RE.search(text) and re.search(r"margin|cogs|profit", text, re.I):
        for angle in _FINANCIAL_SUBQUESTIONS[:5]:
            candidate = f"{text} — {angle}"
            if candidate not in sub_queries:
                sub_queries.append(candidate)
    # Bounded, deduplicated.
    seen: set[str] = set()
    out: list[str] = []
    for item in sub_queries:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:8]


__all__ = ["RouteDecision", "decompose", "route_query"]
