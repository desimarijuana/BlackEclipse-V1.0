"""Shared helpers for the search agent tools."""

from __future__ import annotations

from typing import Any, Optional

from .contracts import SearchScope


def service_for(ctx: Any) -> Optional[Any]:
    """Resolve the per-run SearchService (attached by the graph) and configure it
    with the run's model credentials. Returns None when unavailable."""
    service = getattr(ctx, "search", None)
    if service is None:
        return None
    settings = getattr(ctx, "model_settings", None)
    if settings is not None:
        try:
            service.configure(settings)
        except Exception:  # noqa: BLE001 - configuration must never break a tool call
            pass
    return service


def scope_for(ctx: Any) -> SearchScope:
    """The authorization scope for a run: its workspace + owner.

    Never operator/unrestricted — an agent retrieves only public rows plus rows in
    its own workspace or owned by the run's user.
    """
    return SearchScope(
        workspace_id=getattr(ctx, "workspace_id", None),
        owner_id=getattr(ctx, "user_id", None),
        visibilities=("public", "workspace", "private"),
    )


__all__ = ["scope_for", "service_for"]
