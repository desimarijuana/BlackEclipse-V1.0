"""Drift routes for the evolution operator surface.

Kept separate from `routers/evolution.py` after the route group crossed the size
budget. Same authorization boundary: every route requires the operator proof,
every read is bounded, and a candidate creation is the only write.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from ..deps import require_operator, service

router = APIRouter(tags=["evolution"])


def _surface_scopes() -> list[str]:
    from ..agents import AGENT_PRESETS  # noqa: PLC0415

    return ["global", *sorted(AGENT_PRESETS.keys())]


@router.get("/evolution/drift")
def evolution_drift(
    scope: Optional[str] = None,
    window: int = 30,
    baseline: int = 100,
    minSamples: int = 10,  # noqa: N803 - operator-facing name
    threshold: float = 0.10,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Production drift signal: recent terminal runs vs the preceding window."""
    from ..self_improvement.drift import detect_store_drift  # noqa: PLC0415

    return {
        "success": True,
        "availableScopes": _surface_scopes(),
        **detect_store_drift(
            service.store,
            scope=scope,
            window=max(1, min(int(window), 200)),
            baseline=max(1, min(int(baseline), 500)),
            min_samples=max(1, min(int(minSamples), 200)),
            threshold=max(0.0, min(float(threshold), 1.0)),
        ),
    }


@router.get("/evolution/drift/alerts")
def drift_alerts(
    limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Recent durable drift notifications from the event log (operator inbox)."""
    from ..event_system.emit import get_event_system  # noqa: PLC0415

    system = get_event_system()
    if system is None:
        return {"success": True, "alerts": []}
    try:
        events = system.store.query(type="notification.created", limit=max(1, min(int(limit), 200)))
    except Exception:  # noqa: BLE001 - an unreadable event log is an empty inbox
        return {"success": True, "alerts": []}
    alerts = [
        {
            "id": event.id,
            "at": event.timestamp,
            "scope": (event.payload or {}).get("scope"),
            "drop": (event.payload or {}).get("drop"),
            "title": (event.payload or {}).get("title"),
            "body": (event.payload or {}).get("body"),
        }
        for event in events
        if (event.payload or {}).get("kind") == "drift"
    ]
    return {"success": True, "alerts": alerts}


@router.get("/evolution/drift/scopes")
def evolution_drift_scopes(
    window: int = 30,
    baseline: int = 100,
    minSamples: int = 10,  # noqa: N803 - operator-facing name
    threshold: float = 0.10,
    includeGlobal: bool = True,  # noqa: N803 - operator-facing name
    scopes: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Read-only drift signal for every configured (or supplied) scope."""
    from ..self_improvement.drift import detect_store_drift  # noqa: PLC0415

    scopes = list(dict.fromkeys([
        *_surface_scopes(),
        *[item.strip() for item in str(scopes or "").split(",") if item.strip()],
    ]))
    signals = [
        {
            "scope": scope,
            "signal": detect_store_drift(
                service.store,
                scope=None if scope == "global" else scope,
                window=max(1, min(int(window), 200)),
                baseline=max(1, min(int(baseline), 500)),
                min_samples=max(1, min(int(minSamples), 200)),
                threshold=max(0.0, min(float(threshold), 1.0)),
            ),
        }
        for scope in scopes
        if includeGlobal or scope != "global"
    ]
    return {"success": True, "availableScopes": scopes, "signals": signals}


@router.get("/evolution/drift/history")
def evolution_drift_history(
    scope: Optional[str] = None,
    window: int = 30,
    baseline: int = 100,
    minSamples: int = 10,  # noqa: N803 - operator-facing name
    threshold: float = 0.10,
    limit: int = 12,
    step: Optional[int] = None,
    offset: int = 0,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Read-only drift signals at successive points in the existing run history."""
    from ..self_improvement.drift import drift_history  # noqa: PLC0415

    return {
        "success": True,
        "availableScopes": _surface_scopes(),
        **drift_history(
            service.store,
            scope=scope,
            window=max(1, min(int(window), 200)),
            baseline=max(1, min(int(baseline), 500)),
            min_samples=max(1, min(int(minSamples), 200)),
            threshold=max(0.0, min(float(threshold), 1.0)),
            limit=max(1, min(int(limit), 50)),
            step=max(1, min(int(step), 200)) if step is not None else None,
            offset=max(0, min(int(offset), 2000)),
        ),
    }


@router.post("/evolution/drift/candidate")
def create_drift_candidate(
    scope: Optional[str] = None,
    window: int = 30,
    baseline: int = 100,
    minSamples: int = 10,  # noqa: N803 - operator-facing name
    threshold: float = 0.10,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Materialize an inert drift candidate from the current signal (operator action)."""
    from ..self_improvement.drift import (  # noqa: PLC0415
        detect_store_drift,
        record_drift_candidate,
    )

    signal = detect_store_drift(
        service.store,
        scope=scope,
        window=max(1, min(int(window), 200)),
        baseline=max(1, min(int(baseline), 500)),
        min_samples=max(1, min(int(minSamples), 200)),
        threshold=max(0.0, min(float(threshold), 1.0)),
    )
    recorded = record_drift_candidate(service.store, signal)
    if recorded.get("created"):
        from ..event_system.emit import publish_event  # noqa: PLC0415

        publish_event(
            "self_improvement.drift_candidate_created",
            {
                "candidateId": (recorded.get("candidate") or {}).get("id"),
                "scope": signal.get("scope"),
                "anchor": signal.get("anchor"),
                "drop": signal.get("drop"),
            },
            source="self_improvement",
        )
    return {
        "success": True,
        "availableScopes": _surface_scopes(),
        "signal": signal,
        **recorded,
    }


__all__ = ["router"]
