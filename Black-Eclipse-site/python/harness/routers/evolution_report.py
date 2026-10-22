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
    from ..self_improvement.report import (  # noqa: PLC0415
        DigestStore,
        build_digest,
        render_markdown,
    )

    digest = build_digest(
        service.store,
        days=max(1, min(int(days), 365)),
        scope=scope,
        limit=max(1, min(int(limit), 50)),
    )
    try:
        DigestStore(service.store).record(digest)
    except Exception:  # noqa: BLE001 - a digest is diagnostics, never a failure
        pass
    return {"success": True, "digest": digest, "markdown": render_markdown(digest)}


@router.get("/evolution/surface-lab/candidates")
def surface_lab_candidates(
    limit: int = 10, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """The surface candidates the lab STAGED (inert, evidence only)."""
    from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

    rows = [
        row for row in EvolutionStore(service.store).list_candidates(limit=200)
        if str(row.get("sourceCategory") or "") == "surface-lab"
    ]
    return {
        "success": True,
        "candidates": [
            {
                "id": row.get("id"),
                "status": row.get("status"),
                "problemStatement": row.get("problemStatement"),
                "createdAt": row.get("createdAt"),
                "scope": (row.get("surfaceConfig") or {}).get("scope"),
                "snapshotDigest": (row.get("surfaceConfig") or {}).get(
                    "snapshot", {}
                ).get("sourceDigest"),
            }
            for row in rows[: max(1, min(int(limit), 50))]
        ],
    }


@router.get("/evolution/replay/digest")
def replay_digest(
    limit: int = 20, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """How much REAL-RUN evidence the store holds, and what the corpus covers.

    The corpus ships authored replay fixtures; the store holds the candidates
    mined from REAL production runs. Neither leaves the machine: the digest is a
    count, never the run text.
    """
    from ..evaluation.store import EvaluationStore  # noqa: PLC0415
    from ..evaluation.tasks import load_all_builtin, select_tasks  # noqa: PLC0415

    corpus = load_all_builtin()
    replay_tasks = [
        task for task in select_tasks(corpus, split="optimization")
        if str((task.metadata or {}).get("replay") or "") == "True"
        or task.id.startswith("replay.")
    ]
    rows = EvaluationStore(service.store).list_candidates(limit=200)
    by_status: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "success": True,
        "corpusReplayTasks": len(replay_tasks),
        "minedCandidates": by_status,
        "recent": [
            {
                "id": row.get("id"),
                "status": row.get("status"),
                "category": row.get("category"),
                "createdAt": row.get("createdAt"),
            }
            for row in rows[: max(1, min(int(limit), 50))]
        ],
    }


__all__ = ["router"]
