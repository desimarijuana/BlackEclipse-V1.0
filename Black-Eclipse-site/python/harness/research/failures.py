"""Retrieval failure classification (Phase 4 + Prompt-2 extra).

Not all retrieval failures are equal. The coverage gate and a future workflow
node need to distinguish timeout / provider failure / no coverage / incomplete /
stale / entity ambiguity / invalid response / conflict, so fallback can be
*targeted* rather than "search the web for everything".

This is a deterministic mapping from a `FinancialRetrievalResult` (or a
`SourceOutcome`) to one classification. It never fabricates a status: an
unrecognized failure is `unknown`.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

FailureClass = Literal[
    "timeout",
    "provider_failure",
    "no_coverage",
    "incomplete",
    "stale",
    "ambiguous_entity",
    "invalid_response",
    "conflicting",
    "unknown",
]

# Substrings that map a warning/error string to a class. Ordered: first match wins.
_HINTS: list[tuple[str, FailureClass]] = [
    ("timed out", "timeout"),
    ("timeout", "timeout"),
    ("ambiguous", "ambiguous_entity"),
    ("not covered", "no_coverage"),
    ("not_covered", "no_coverage"),
    ("no source", "no_coverage"),
    ("unavailable", "no_coverage"),
    ("incomplete", "incomplete"),
    ("truncat", "incomplete"),
    ("stale", "stale"),
    ("conflict", "conflicting"),
    ("invalid", "invalid_response"),
    ("failed", "provider_failure"),
    ("error", "provider_failure"),
]


def _from_texts(texts: list[str]) -> Optional[FailureClass]:
    for text in texts:
        lowered = text.lower()
        for needle, klass in _HINTS:
            if needle in lowered:
                return klass
    return None


def classify_failure(result: Any) -> FailureClass:
    """Classify why a retrieval did not satisfy its request.

    Accepts a `FinancialRetrievalResult` or a `SourceOutcome` (duck-typed).
    """
    if result is None:
        return "unknown"

    status = str(getattr(result, "status", "") or "").upper()
    if status == "AMBIGUOUS":
        return "ambiguous_entity"
    if getattr(result, "incomplete", False):
        return "incomplete"
    if getattr(result, "conflicts", None):
        return "conflicting"
    if status == "CONFLICTING":
        return "conflicting"
    if status == "INVALID":
        return "invalid_response"
    if getattr(result, "degraded", False) and "stale" in str(getattr(result, "degradation", "")).lower():
        return "stale"

    texts = [str(w) for w in (getattr(result, "warnings", None) or [])]
    error = getattr(result, "error", None)
    if error:
        texts.append(str(error))
    hint = _from_texts(texts)
    if hint:
        return hint

    if status == "UNAVAILABLE":
        return "no_coverage"
    return "unknown"


__all__ = ["FailureClass", "classify_failure"]
