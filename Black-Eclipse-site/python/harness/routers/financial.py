"""Financial Data Gateway HTTP routes.

Thin, operator-gated adapters over the SAME provider registry the retrieval layer
and the `financial_providers` agent tool use. The route reaches shared runtime
state only through `harness.deps.service`, so the UI, the agent and the router can
never disagree about which providers exist.

The registry holds NO credential value — only the reference (env var name). The
route reports `configured: null` for a credentialed provider; the front door (which
owns the vault) fills in presence. A secret never crosses into Python.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from ..deps import require_operator, service

router = APIRouter(tags=["financial"])


@router.get("/financial/providers")
async def list_providers(
    capability: Optional[str] = Query(default=None),
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Describe the configured financial providers and their capabilities."""
    registry = getattr(service, "provider_registry", None)
    if registry is None:
        # Build a fresh default registry so the surface is never empty just
        # because the service was constructed before the registry wire-up.
        from ..retrieval.registry import build_default_registry  # noqa: PLC0415

        registry = build_default_registry()
    if capability:
        providers = registry.by_capability(capability)
        return {
            "status": "OK",
            "capability": capability,
            "providers": [p.to_dict() for p in providers],
        }
    return {"status": "OK", "capability": None, **registry.summary()}


__all__ = ["router"]
