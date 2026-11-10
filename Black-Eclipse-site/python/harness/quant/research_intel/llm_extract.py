"""Span-checked model extraction.

The model may propose fields, but a field is accepted only when its quote is
present verbatim in the source document. A proposal without a quote is rejected
and named in `rejected`. The deterministic validator then decides whether the
merged specification is complete.

This module never calls a model. The caller supplies the proposal; that keeps the
check deterministic and testable offline.
"""

from __future__ import annotations

import re
from typing import Any

from .schema import merge_structured, normalize_spec

_FIELDS = (
    "name", "family", "objective", "inputs", "parameters", "equations",
    "estimation", "assumptions", "outputs", "validation", "limitations",
    "references", "unresolved",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _quote_ok(quote: str, text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 12 and q in _norm(text)


def apply_proposal(
    draft: dict[str, Any],
    proposal: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    """Merge only proposal fields whose quote exists in the source text."""
    if not isinstance(proposal, dict):
        return {"draft": draft, "verified": [], "rejected": ["proposal must be an object"]}
    quotes = proposal.get("quotes") if isinstance(proposal.get("quotes"), dict) else {}
    verified: dict[str, Any] = {}
    accepted: list[str] = []
    rejected: list[str] = []

    for field in _FIELDS:
        if field not in proposal:
            continue
        value = proposal[field]
        if field == "equations":
            equations = []
            for i, eq in enumerate(value if isinstance(value, list) else []):
                if not isinstance(eq, dict):
                    rejected.append(f"equations[{i}] is not an object")
                    continue
                source = eq.get("source") if isinstance(eq.get("source"), dict) else {}
                quote = str(source.get("quote") or eq.get("quote") or "")
                if not _quote_ok(quote, text):
                    rejected.append(f"equations[{i}] has no quote found in the document")
                    continue
                equations.append({**eq, "source": {**source, "quote": quote}})
            if equations:
                verified[field] = equations
                accepted.append(field)
            continue

        quote = str(quotes.get(field) or "")
        if not _quote_ok(quote, text):
            rejected.append(f"{field} has no quote found in the document")
            continue
        verified[field] = value
        accepted.append(field)

    merged = normalize_spec(merge_structured(draft, verified))
    merged["provenance"] = dict(merged.get("provenance") or {})
    merged["provenance"]["extraction"] = "llm_span_checked"
    merged["provenance"]["acceptedFields"] = accepted
    merged["provenance"]["rejectedFields"] = rejected
    return {"draft": merged, "verified": accepted, "rejected": rejected}


__all__ = ["apply_proposal"]
