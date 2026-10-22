"""The RSL operator digest route group.

A separate, small route group (like `evolution_drift.py` and
`evolution_models.py`) so the operator surfaces can grow without growing the
main evolution router. Every route is operator-gated.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from ..deps import require_operator, service

router = APIRouter(tags=["evolution"])


@router.get("/evolution/rsl/report")
def rsl_report(
    days: int = 7,
    scope: Optional[str] = None,
    limit: int = 10,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """What the self-improvement loop did, what it cost, and where it drifts."""
    from ..self_improvement.report import build_digest, render_markdown  # noqa: PLC0415

    digest = build_digest(
        service.store,
        days=max(1, min(int(days), 365)),
        scope=scope,
        limit=max(1, min(int(limit), 50)),
    )
    return {"success": True, "digest": digest, "markdown": render_markdown(digest)}


__all__ = ["router"]
