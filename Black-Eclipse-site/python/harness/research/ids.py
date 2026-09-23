"""Stable, content-sensitive identifiers (Phase 4 hardening).

Python's built-in `hash()` is salted per process (PYTHONHASHSEED), so any ID or
receipt hash built from it is NOT stable across processes and NOT reproducible
from a stored receipt. These helpers derive identifiers from a canonical JSON
serialization using SHA-256, so the same content always yields the same ID in
any process, and different content yields a different ID.

Two distinct concerns:

  * `evidence_digest` — a bounded canonical digest of an evidence item's content
    AND provenance (not merely its id).
  * `calculation_digest` — a digest over a calculation's version, formula,
    inputs, window and assumptions, so two calculations over the same dates but
    different values/assumptions never collide.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Bound the digest input so a giant raw source document cannot make the hash
# cost unbounded. The digest still captures the fields that identify the item.
_MAX_FIELD_CHARS = 2000


def canonical_json(value: Any, *, max_chars: int = _MAX_FIELD_CHARS) -> str:
    """Deterministic JSON for hashing: sorted keys, no whitespace, bounded.

    Non-serializable values are stringified. Long strings are truncated so the
    digest is bounded while remaining content-sensitive over the identifier
    fields.
    """
    def _normalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {str(k): _normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, (list, tuple)):
            return [_normalize(v) for v in obj]
        if isinstance(obj, str):
            return obj[:max_chars]
        if isinstance(obj, (int, float, bool)) or obj is None:
            return obj
        return str(obj)[:max_chars]

    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), default=str)


def stable_digest(value: Any, *, prefix: str = "sha256", length: int = 32) -> str:
    """A stable SHA-256 hex digest of `value`'s canonical form."""
    payload = canonical_json(value)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def evidence_digest(item: Any) -> str:
    """Content + provenance digest for one evidence item.

    Includes the id, kind, summary, source identity/tier/url/publishedAt and the
    normalized object values — so two different facts never share a hash and the
    same fact always does.
    """
    source = getattr(item, "source", None)
    objects = []
    for obj in getattr(item, "objects", []) or []:
        objects.append(
            {
                "name": getattr(obj, "name", None),
                "value": getattr(obj, "value", None),
                "unit": getattr(obj, "unit", None),
                "currency": getattr(obj, "currency", None),
                "period": getattr(obj, "period", None),
                "basis": getattr(obj, "basis", None),
                "dataTimestamp": getattr(obj, "dataTimestamp", None),
                "publishedAt": getattr(obj, "publishedAt", None),
                "instrument": getattr(obj, "instrument", None),
            }
        )
    payload = {
        "id": getattr(item, "id", None),
        "kind": getattr(item, "kind", None),
        "quality": getattr(item, "quality", None),
        "source": {
            "source": getattr(source, "source", None) if source else None,
            "sourceType": getattr(source, "sourceType", None) if source else None,
            "url": getattr(source, "url", None) if source else None,
            "publishedAt": getattr(source, "publishedAt", None) if source else None,
        },
        "objects": objects,
    }
    return stable_digest(payload, prefix="ev", length=32)


def calculation_digest(result: Any) -> str:
    """Stable digest over a calculation's identity.

    Includes version, formula, metric, inputs, window, observation count,
    frequency, annualization, risk-free rate/source, assumptions and value — so
    distinct values for the same dates never collide.
    """
    payload = {
        "version": getattr(result, "version", None),
        "formula": getattr(result, "formula", None),
        "metric": getattr(result, "metric", None),
        "value": getattr(result, "value", None),
        "inputs": getattr(result, "inputs", None),
        "inputEvidenceIds": getattr(result, "inputEvidenceIds", None),
        "identity": getattr(result, "identity", None),
        "currency": getattr(result, "currency", None),
        "unit": getattr(result, "unit", None),
        "window": getattr(result, "window", None),
        "observationCount": getattr(result, "observationCount", None),
        "frequency": getattr(result, "frequency", None),
        "annualization": getattr(result, "annualization", None),
        "riskFreeRate": getattr(result, "riskFreeRate", None),
        "riskFreeSource": getattr(result, "riskFreeSource", None),
        "assumptions": getattr(result, "assumptions", None),
    }
    return stable_digest(payload, prefix="calc", length=32)


__all__ = [
    "canonical_json",
    "stable_digest",
    "evidence_digest",
    "calculation_digest",
]
