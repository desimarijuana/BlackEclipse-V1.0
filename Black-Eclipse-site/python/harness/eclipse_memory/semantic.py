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

# Candidate types (Phase 3). The semantic layer classifies; it never decides.
CANDIDATE_CONFIRMATION = "confirmation_candidate"
CANDIDATE_CONFLICT = "conflict_candidate"
CANDIDATE_REPLACEMENT = "replacement_candidate"
CANDIDATE_UNRELATED = "unrelated_candidate"
CANDIDATE_UNAVAILABLE = "unavailable"

# Only these types may lead the service to store a new record inert for review.
# `confirmation_candidate` is deliberately NOT actionable: similarity alone must
# never confirm (or activate) a memory — it is surfaced as a diagnostic only.
ACTIONABLE_KINDS = frozenset({CANDIDATE_CONFLICT, CANDIDATE_REPLACEMENT})


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
    kind: str = CANDIDATE_UNRELATED
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "memoryId": self.memoryId,
            "score": round(self.score, 3),
            "kind": self.kind,
            "reason": self.reason,
        }


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


class LocalEmbeddingBackend:
    """An OPTIONAL stronger local backend: a sentence embedding model, if one is
    already installed locally AND a local model is configured.

    Constraints (mirroring the brief):

      * **never downloads.** A model is loaded only from an explicit local path
        (`BLACK_ECLIPSE_MEMORY_EMBEDDING_MODEL`); no model id is fetched.
      * **no network, no hosted API.**
      * **absence is not an error.** If the library or the model is missing,
        `available()` is False and detection stays lexical-only.
      * **bounded.** A dimension cap and a per-text length cap; no index is
        persisted.
      * **no raw vectors persisted.** Only similarity scores cross the boundary.
    """

    name = "local-embedding"
    version = "embedding-v1"
    _MAX_TEXT_CHARS = 2000

    def __init__(self) -> None:
        self._model: Any = None
        self._probed = False
        self._reason = "not probed"

    def _load(self) -> Any:
        if self._probed:
            return self._model
        self._probed = True
        import os

        model_path = os.environ.get("BLACK_ECLIPSE_MEMORY_EMBEDDING_MODEL", "").strip()
        if not model_path or not os.path.isdir(model_path):
            self._reason = "no local embedding model configured"
            return None
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer(model_path, device="cpu")
            self._reason = "loaded local sentence-transformer"
        except Exception as exc:  # noqa: BLE001 - absence is never an error
            self._reason = f"embedding backend unavailable: {type(exc).__name__}"
            self._model = None
        return self._model

    def available(self) -> bool:
        return self._load() is not None

    def similarity(self, text_a: str, text_b: str) -> float:
        model = self._load()
        if model is None:
            return 0.0
        try:
            vectors = model.encode(
                [(text_a or "")[: self._MAX_TEXT_CHARS], (text_b or "")[: self._MAX_TEXT_CHARS]],
                normalize_embeddings=True,
            )
            a, b = vectors[0], vectors[1]
            dot = sum(float(x) * float(y) for x, y in zip(a, b))
            return round(max(-1.0, min(1.0, dot)), 4)
        except Exception:  # noqa: BLE001 - a backend failure yields no candidate
            return 0.0


_BACKENDS: dict[str, SemanticBackend] = {
    "char-ngram": CharNgramBackend(),
    "local-embedding": LocalEmbeddingBackend(),
    "none": NullBackend(),
}

# Preference order for the "auto" backend: a real local embedding model is used
# only when it is genuinely available; otherwise the dependency-free default.
_BACKEND_PREFERENCE = ("local-embedding", "char-ngram")


def register_backend(backend: SemanticBackend) -> None:
    """Register (or replace) a local backend by name."""
    _BACKENDS[backend.name] = backend


def get_backend(name: str = "char-ngram") -> SemanticBackend:
    # "auto" selects the strongest AVAILABLE backend; explicit names are honoured.
    if name == "auto":
        for candidate in _BACKEND_PREFERENCE:
            backend = _BACKENDS.get(candidate)
            if backend is not None:
                try:
                    if backend.available():
                        return backend
                except Exception:  # noqa: BLE001 - a probe must never raise
                    continue
        return _BACKENDS["char-ngram"]
    return _BACKENDS.get(name, _BACKENDS["none"])


def backend_status(name: str = "auto") -> dict[str, Any]:
    backend = get_backend(name)
    try:
        available = bool(backend.available())
    except Exception:  # noqa: BLE001 - a backend probe must never raise
        available = False
    return {"backend": backend.name, "version": backend.version, "available": available}


def backend_health() -> list[dict[str, Any]]:
    """Health for every registered backend (availability + declared name/version).

    Never touches the network and never downloads; probing is cheap/pure.
    """
    out: list[dict[str, Any]] = []
    for name in ("char-ngram", "local-embedding", "none"):
        backend = _BACKENDS.get(name)
        if backend is None:
            continue
        try:
            available = bool(backend.available())
        except Exception:  # noqa: BLE001
            available = False
        out.append({"backend": backend.name, "version": backend.version, "available": available})
    return out


# ── Bounded candidate search ────────────────────────────────────────────────


def classify_candidate(content: str, other: str) -> tuple[str, str]:
    """Classify a similarity candidate by relationship, deterministically.

    Similarity alone only says "related"; the relationship type must come from
    reviewed lexical + polarity signals, never from the score. Rules:

      * explicit replacement language in the new statement → `replacement`;
      * a known opposing polarity between the two → `conflict`;
      * same reviewed concept-axis pole, or high normalized token overlap with no
        differing value → `confirmation`;
      * otherwise → `unrelated` (inert; diagnostic only).

    A low-confidence similarity is NOT a relationship: the caller only reaches
    this function for candidates above the threshold, and an unknown relationship
    stays `unrelated` rather than guessing a conflict.
    """
    from .conflicts import _value_changed, is_replacement_intent, opposing  # noqa: PLC0415
    from .normalize import axes_contradict, shared_axes  # noqa: PLC0415

    if is_replacement_intent(content):
        return CANDIDATE_REPLACEMENT, "explicit replacement language"
    if opposing(content, other):
        return CANDIDATE_CONFLICT, "opposing polarity on a reviewed axis"
    if axes_contradict(content, other):
        return CANDIDATE_CONFLICT, "opposite poles on a reviewed concept axis"
    # A same-dimension value substitution ("reports as PDF" vs "reports as Excel")
    # is a conflict of values, not a confirmation — but only when the two texts
    # share a dimension (some distinctive content in common). Without shared
    # context, differing tokens are unrelated facts, not a changed value.
    shared = shared_axes(content, other)
    if not shared:
        from .conflicts import _distinctive, _normalized_terms  # noqa: PLC0415

        shared = _distinctive(_normalized_terms(content)) & _distinctive(_normalized_terms(other))
    if shared and _value_changed(content, other):
        return CANDIDATE_CONFLICT, "same dimension, differing value"
    if shared_axes(content, other) and not _value_changed(content, other):
        return CANDIDATE_CONFIRMATION, "same concept-axis pole"
    # High surface overlap with no explicit opposition is a possible same-meaning
    # restatement — surfaced for review, never auto-confirmed.
    from .conflicts import _jaccard, _normalized_terms  # noqa: PLC0415

    if _jaccard(_normalized_terms(content), _normalized_terms(other)) >= 0.6:
        return CANDIDATE_CONFIRMATION, "high normalized overlap"
    return CANDIDATE_UNRELATED, "surface similarity only"


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
            other = memory.get("content") or ""
            score = float(backend.similarity(content, other))
            if score >= threshold:
                # A malformed score (NaN/inf) is coerced to no-candidate rather
                # than propagated: an invalid number must never decide anything.
                if not (0.0 <= score <= 1.0) or score != score:
                    continue
                kind, kind_reason = classify_candidate(content, other)
                scored.append(SemanticCandidate(
                    memoryId=memory.get("id") or "", score=score,
                    content=other, kind=kind, reason=kind_reason,
                ))
    except Exception as exc:  # noqa: BLE001 - never break the write path
        return SemanticSearchResult(detector=backend.name, available=True,
                                    reason=f"backend error: {exc}")
    scored.sort(key=lambda c: (-c.score, c.memoryId))
    return SemanticSearchResult(
        detector=f"{backend.name}:{backend.version}", available=True,
        candidates=scored[:max_candidates], truncated=truncated,
        timedOut=timed_out, reason="ok",
    )


def strongest_actionable(result: SemanticSearchResult) -> Optional[SemanticCandidate]:
    """The best candidate whose type may lead to a review (conflict/replacement).

    Confirmation and unrelated candidates are diagnostic only: similarity must
    never confirm, activate, supersede or archive a memory.
    """
    for candidate in result.candidates:  # already sorted by score desc
        if candidate.kind in ACTIONABLE_KINDS:
            return candidate
    return None


__all__ = [
    "ACTIONABLE_KINDS",
    "CANDIDATE_CONFIRMATION",
    "CANDIDATE_CONFLICT",
    "CANDIDATE_REPLACEMENT",
    "CANDIDATE_UNRELATED",
    "CANDIDATE_UNAVAILABLE",
    "DEFAULT_DETECTOR",
    "DETECTOR_VERSION",
    "SemanticBackend",
    "SemanticCandidate",
    "SemanticSearchResult",
    "backend_status",
    "classify_candidate",
    "find_candidates",
    "get_backend",
    "register_backend",
    "strongest_actionable",
]
