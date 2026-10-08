"""Opt-in live embedding smoke check.

Contacts a REAL embedding provider (no mocks) to prove the semantic path works
end to end. It is deliberately opt-in and never part of the offline suite.

Enable with:

    HARNESS_SEARCH_EMBEDDING_PROVIDER=openai
    HARNESS_SEARCH_EMBEDDING_MODEL=text-embedding-3-small
    OPENAI_API_KEY=...            # or the provider's own env var
    BLACK_ECLIPSE_SEARCH_LIVE=1

Then:  python -m harness.search.live_smoke
Exit code 0 = pass or "not configured" (skip); 1 = a real failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

_QUERIES = [
    ("NVIDIA data center revenue grew on AI demand.", "NVIDIA AI cloud revenue"),
    ("Tesla margins compressed on pricing pressure.", "Tesla margin pricing pressure"),
]
_DISTRACTOR = "The FOMC left the federal funds rate unchanged."


def _configured() -> bool:
    if os.environ.get("BLACK_ECLIPSE_SEARCH_LIVE") not in ("1", "true", "yes", "on"):
        return False
    return bool(os.environ.get("HARNESS_SEARCH_EMBEDDING_PROVIDER"))


async def _run() -> dict[str, Any]:
    from .config import load_config
    from .embeddings.service import EmbeddingService

    config = load_config()
    service = EmbeddingService(config)
    service.configure(None)
    if not service.available:
        return {"ok": False, "configured": False, "reason": service.reason}

    texts = [a for a, _ in _QUERIES] + [q for _, q in _QUERIES] + [_DISTRACTOR]
    outcome = await service.embed_texts(texts)
    vectors = outcome.vectors
    if any(v is None for v in vectors):
        return {"ok": False, "configured": True, "reason": "one or more embeddings failed"}
    dims = len(vectors[0]) if vectors and vectors[0] else 0
    if dims != service.dimensions and service.dimensions:
        return {"ok": False, "configured": True, "reason": f"dimension mismatch: {dims} != {service.dimensions}"}
    if all(abs(x) < 1e-9 for x in (vectors[0] or [])):
        return {"ok": False, "configured": True, "reason": "embedding was all-zero"}

    def cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    relevant = cos(vectors[0], vectors[2])
    irrelevants = [cos(vectors[0], vectors[4])]
    passed = relevant > max(irrelevants)
    return {
        "ok": passed,
        "configured": True,
        "provider": service.provider_id,
        "model": service.model_id,
        "dimensions": dims,
        "relevantSimilarity": round(relevant, 4),
        "distractorSimilarity": round(irrelevants[0], 4),
        "reason": "" if passed else "relevant passage did not score above the distractor",
    }


def main() -> int:
    if not _configured():
        print("[search-live] not configured; set BLACK_ECLIPSE_SEARCH_LIVE=1 and an embedding provider. SKIP")
        return 0
    try:
        result = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - a live failure is a real failure
        print(f"[search-live] FAIL: {exc}")
        return 1
    if result.get("configured") is False:
        print(f"[search-live] provider unavailable: {result.get('reason')}. SKIP")
        return 0
    print(f"[search-live] {result}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]
