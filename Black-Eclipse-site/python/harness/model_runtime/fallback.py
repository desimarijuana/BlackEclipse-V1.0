"""Fallback acceptance policy (W1)."""

from __future__ import annotations

import os
from typing import Optional

from .types import ModelInfo


def fallback_quality_allowed(primary: Optional[ModelInfo], fallback: Optional[ModelInfo]) -> bool:
    """Whether a cross-provider fallback is an acceptable quality trade.

    Declared quality is a coarse prior, not a benchmark claim. If either side
    is unknown we allow the fallback (the operator already opted in). If both
    are known and the fallback is materially worse, refuse unless the operator
    explicitly opted into degraded fallback.
    """
    if (os.environ.get("HARNESS_MODEL_FALLBACK_ALLOW_DEGRADED") or "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        return True
    if primary is None or fallback is None:
        return True
    p = primary.performance.quality
    f = fallback.performance.quality
    if p is None or f is None:
        return True
    return f >= (p - 0.20)


__all__ = ["fallback_quality_allowed"]
