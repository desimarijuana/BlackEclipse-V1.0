"""Optional LOCAL semantic candidate detection for contradiction review.

This is a *candidate* aid, never a decision-maker. It can only surface
same-dimension memories that a new statement may relate to; the deterministic
lexical + authority rules in `conflicts.py` still decide, and nothing here can
supersede, activate, archive or delete a memory.

Design constraints (see `docs/harness/memory-contradiction-detection.md`):

  * **local & zero-config** — no network, no hosted API, no runtime model
    download. The default backend is dependency-free.
  * **fail-safe** — if the backend is unavailable, disabled, times out, or the
    index is over budget, it returns no candidates and lexical detection proceeds
    unchanged. It never raises into the write path.
  * **bounded** — a similarity threshold, a maximum candidate count, a maximum
    indexed set, and a wall-clock timeout, all policy-controlled.
  * **authorization-neutral** — the caller passes only memories that already
    passed scope/status/type/dimension/authority filtering; this module never
    widens that set.
  * **no embeddings persisted** — only a numeric score and ids cross the
    boundary; raw vectors are never stored.

Backends are pluggable: a future local model (e.g. a bundled ONNX/sentence
embedding) can implement `SemanticBackend` and register without changing the
caller. The default `CharNgramBackend` uses character n-gram cosine similarity,
which is pure-Python, dependency-free and deterministic — it captures
surface-level paraphrase similarity without any download.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

DETECTOR_VERSION = "semantic-v1"
DEFAULT_DETECTOR = "lexical-v1"


class SemanticBackend(Protocol):
    """A local similarity backend. `available` must be cheap and side-effect-free."""

    name: str
    version: str

    def available(self) -> bool:  # pragma: no cover - protocol
        ...

    def similarity(self, text_a: str, text_b: str) -> float:  # pragma: no cover
        ...


@dataclass
class SemanticCandidate:
    memoryId: str
    score: float
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"memoryId": self.memoryId, "score": round(self.score, 3)}


@dataclass
class SemanticSearchResult:
    detector: str
    available: bool
    candidates: list[SemanticCandidate] = field(default_factory=list)
    reason: str = ""
    timedOut: bool = False
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "available": self.available,
            "candidates": [c.to_dict() for c in self.candidates],
            "reason": self.reason,
            "timedOut": self.timedOut,
            "truncated": self.truncated,
        }


# ── Default dependency-free backend ─────────────────────────────────────────


def _ngrams(text: str, n: int = 3) -> Counter:
    cleaned = " ".join(
        "".join(ch for ch in token if ch.isalnum())
        for token in (text or "").lower().split()
    )
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return Counter()
    if len(cleaned) <= n:
        return Counter({cleaned: 1})
    return Counter(cleaned[i:i + n] for i in range(len(cleaned) - n + 1))


class CharNgramBackend:
    """Character n-gram cosine similarity — local, dependency-free, deterministic.

    It is intentionally modest: it finds surface-level paraphrase similarity and
    never claims word-level meaning. That is acceptable because it only proposes
    candidates for the deterministic decision; a weak score simply yields no
    candidate, which is the safe direction.
    """

    name = "char-ngram"
    version = DETECTOR_VERSION

    @staticmethod
    def _cosine(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[g] * b[g] for g in common)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def available(self) -> bool:
        return True

    def similarity(self, text_a: str, text_b: str) -> float:
        return round(self._cosine(_ngrams(text_a), _ngrams(text_b)), 4)


class NullBackend:
    """A backend that is never available — used to force lexical-only."""

    name = "none"
    version = DETECTOR_VERSION

    def available(self) -> bool:
        return False

    def similarity(self, text_a: str, text_b: str) -> float:  # noqa: ARG002
        return 0.0


_BACKENDS: dict[str, SemanticBackend] = {
    "char-ngram": CharNgramBackend(),
    "none": NullBackend(),
}


def register_backend(backend: SemanticBackend) -> None:
    """Register (or replace) a local backend by name."""
    _BACKENDS[backend.name] = backend


def get_backend(name: str = "char-ngram") -> SemanticBackend:
    return _BACKENDS.get(name, _BACKENDS["none"])


def backend_status(name: str = "char-ngram") -> dict[str, Any]:
    backend = get_backend(name)
    try:
        available = bool(backend.available())
    except Exception:  # noqa: BLE001 - a backend probe must never raise
        available = False
    return {"backend": backend.name, "version": backend.version, "available": available}


# ── Bounded candidate search ────────────────────────────────────────────────


def find_candidates(
    *,
    content: str,
    same_dimension: list[dict[str, Any]],
    settings: dict[str, Any],
    backend_name: str = "char-ngram",
) -> SemanticSearchResult:
    """Return bounded semantic candidates among already-authorized memories.

    `same_dimension` MUST already be filtered by scope, status, memory type,
    subject dimension and authority by the caller — this function never
    authorizes. Every failure path returns `available=False` / no candidates so
    lexical detection is unaffected.
    """
    if not settings.get("semantic_conflict_enabled"):
        return SemanticSearchResult(detector=DEFAULT_DETECTOR, available=False,
                                    reason="disabled by policy")
    backend = get_backend(backend_name)
    try:
        if not backend.available():
            return SemanticSearchResult(detector=DEFAULT_DETECTOR, available=False,
                                        reason="backend unavailable")
    except Exception:  # noqa: BLE001 - availability probe must never raise
        return SemanticSearchResult(detector=DEFAULT_DETECTOR, available=False,
                                    reason="backend error")

    try:
        threshold = float(settings.get("semantic_conflict_threshold", 0.72))
        max_candidates = int(settings.get("semantic_conflict_max_candidates", 5))
        max_index = int(settings.get("semantic_conflict_max_index", 500))
        timeout_ms = int(settings.get("semantic_conflict_timeout_ms", 50))
    except Exception:  # noqa: BLE001 - a bad setting falls back to safe defaults
        threshold, max_candidates, max_index, timeout_ms = 0.72, 5, 500, 50

    truncated = len(same_dimension) > max_index
    pool = same_dimension[:max_index]
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    scored: list[SemanticCandidate] = []
    timed_out = False
    try:
        for memory in pool:
            if time.monotonic() > deadline:
                timed_out = True
                break
            score = float(backend.similarity(content, memory.get("content") or ""))
            if score >= threshold:
                scored.append(SemanticCandidate(
                    memoryId=memory.get("id") or "", score=score,
                    content=memory.get("content") or "",
                ))
    except Exception as exc:  # noqa: BLE001 - never break the write path
        return SemanticSearchResult(detector=backend.name, available=True,
                                    reason=f"backend error: {exc}")
    scored.sort(key=lambda c: -c.score)
    return SemanticSearchResult(
        detector=f"{backend.name}:{backend.version}", available=True,
        candidates=scored[:max_candidates], truncated=truncated,
        timedOut=timed_out, reason="ok",
    )


__all__ = [
    "DEFAULT_DETECTOR",
    "DETECTOR_VERSION",
    "SemanticBackend",
    "SemanticCandidate",
    "SemanticSearchResult",
    "backend_status",
    "find_candidates",
    "get_backend",
    "register_backend",
]
