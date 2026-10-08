"""Synchronous embedding helper for callers outside the async search pipeline.

``research/web_coverage.py`` imports ``embed_texts`` from here for its optional
semantic coverage layer. It is a thin, best-effort adapter over the search
layer's ``EmbeddingService``: when no embedding provider is configured (the
default in a zero-config install) it returns ``None`` and the caller falls back
to its IDF/keyword layers. It never raises.
"""

from __future__ import annotations

import asyncio
from typing import Optional

_SERVICE = None


def get_embedding_service():
    """The process-wide embedding service for non-search callers."""
    global _SERVICE
    if _SERVICE is None:
        try:
            from ..search.config import load_config  # noqa: PLC0415
            from ..search.embeddings.service import EmbeddingService  # noqa: PLC0415

            service = EmbeddingService(load_config())
            service.configure(None)
            _SERVICE = service
        except Exception:  # noqa: BLE001 - embeddings are optional everywhere
            _SERVICE = None
    return _SERVICE


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Embed texts synchronously, or return None when unavailable.

    Returns one vector per input (failed entries are dropped). Never raises: any
    failure is an honest "semantic unavailable" signal for the caller.
    """
    service = get_embedding_service()
    if service is None or not service.available or not texts:
        return None
    try:
        outcome = asyncio.run(service.embed_texts(list(texts)))
    except RuntimeError:
        # Already inside a running event loop: cannot block on it synchronously.
        return None
    except Exception:  # noqa: BLE001
        return None
    return [v for v in outcome.vectors if v is not None]


def embeddings_available() -> bool:
    service = get_embedding_service()
    return bool(service is not None and service.available)


__all__ = ["embed_texts", "embeddings_available", "get_embedding_service"]
