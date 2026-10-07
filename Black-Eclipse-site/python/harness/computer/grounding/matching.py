"""Pure grounding matchers.

Scoring an element against a query is pure and dependency-free so the grounding
behaviour is testable without an OS, a screen or a model. The score combines an
exact-name match, a token overlap, a role match and a visibility/enabled bonus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


@dataclass
class GroundingQuery:
    """A normalized grounding request."""

    intent: str = ""
    name: Optional[str] = None
    role: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    relative: Optional[str] = None       # e.g. "the row for AAPL"
    index: Optional[int] = None          # pick the Nth match (1-based)
    prefer_method: Optional[str] = None

    @property
    def needle(self) -> str:
        return (self.name or self.text or self.intent or "").strip()

    def to_dict(self) -> dict:
        return {
            "intent": self.intent, "name": self.name, "role": self.role,
            "text": self.text, "value": self.value, "relative": self.relative,
            "index": self.index,
        }


def score_element(query: GroundingQuery, element: dict) -> float:
    """Score an element dict ({role,name,value,enabled,...}) against a query. 0..1."""
    name = str(element.get("name") or "")
    value = str(element.get("value") or "")
    role = str(element.get("role") or "").lower()
    score = 0.0
    matched = False

    needle = query.needle.lower()
    name_l = name.lower()
    value_l = value.lower()

    if needle:
        if name_l == needle:
            score += 0.7
            matched = True
        elif needle in name_l:
            score += 0.55
            matched = True
        else:
            q_tokens = set(_tokens(needle))
            e_tokens = set(_tokens(name) + _tokens(value))
            if q_tokens and e_tokens:
                overlap = len(q_tokens & e_tokens) / len(q_tokens)
                if overlap:
                    score += 0.5 * overlap
                    matched = True
        if value_l and needle in value_l:
            score += 0.1
            matched = True

    if query.role:
        wanted_role = query.role.lower()
        if role == wanted_role:
            score += 0.25
            matched = True
        elif wanted_role in role:
            score += 0.1
            matched = True

    if query.text and query.text.lower() in (name_l + " " + value_l):
        score += 0.1
        matched = True

    # The enabled/bounds bonuses are only meaningful ON TOP OF a real match; on
    # their own they must never make an unrelated element look like a target.
    if matched:
        if element.get("enabled", True):
            score += 0.05
        if element.get("bounds"):
            score += 0.05

    return min(1.0, score)


def rank_elements(query: GroundingQuery, elements: list[dict]) -> list[tuple[float, dict]]:
    """Rank elements by descending score, dropping zero-score entries."""
    scored = [(score_element(query, e), e) for e in elements]
    scored = [(s, e) for s, e in scored if s > 0.0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def is_ambiguous(scored: list[tuple[float, dict]], *, margin: float = 0.08) -> bool:
    """Two near-equal top scores mean the target is ambiguous (ask the user)."""
    if len(scored) < 2:
        return False
    return (scored[0][0] - scored[1][0]) < margin and scored[0][0] < 0.9


__all__ = ["GroundingQuery", "is_ambiguous", "rank_elements", "score_element"]
