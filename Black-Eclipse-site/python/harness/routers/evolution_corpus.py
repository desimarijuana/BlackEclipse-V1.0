"""Read-only operator surfaces for the evaluation corpus and rotation.

The corpus files are the authority; these routes expose the committed manifest,
its verification, the authoring audit and a rotation PREVIEW. Rotating or
rewriting a dataset is a deliberate CLI action (`npm run rsl:rotate -- --apply`),
never an HTTP mutation.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import APIRouter, Depends

from ..deps import require_operator

router = APIRouter(tags=["evolution"])


def _compact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "manifestVersion", "recordedAt", "taskCount", "datasetCount",
        "bySplit", "oracleCount", "oracleCoverage", "canaryCount", "liveOnly",
    )
    compact = {key: manifest.get(key) for key in keys}
    compact["datasets"] = [
        {
            "name": item.get("name"),
            "version": item.get("version"),
            "taskCount": item.get("taskCount"),
            "bySplit": item.get("bySplit"),
            "oracleCount": item.get("oracleCount"),
            "canaryCount": item.get("canaryCount"),
            "liveOnly": item.get("liveOnly"),
        }
        for item in manifest.get("datasets") or []
    ]
    return compact


@router.get("/evolution/corpus")
def corpus_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The committed corpus manifest, its verification and the authoring audit."""
    from ..evaluation.corpus import (  # noqa: PLC0415 - read path only
        build_manifest,
        validate_tasks,
        verify_manifest,
    )

    manifest = build_manifest()
    verification = verify_manifest()
    audit = validate_tasks(strict=False)
    return {
        "success": True,
        "manifest": _compact_manifest(manifest),
        "verification": {
            "ok": bool(verification.get("ok")),
            "checked": verification.get("checked"),
            "mismatches": verification.get("mismatches") or [],
        },
        "audit": {
            "ok": bool(audit.get("ok")),
            "counts": audit.get("counts"),
            "errorCount": len(audit.get("errors") or []),
        },
    }


@router.get("/evolution/corpus/rotation")
def rotation_preview(
    quarter: str = "",
    count: int = 12,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """A deterministic rotation plan. It never writes a dataset."""
    from ..evaluation.rotation import plan_rotation  # noqa: PLC0415

    label = str(quarter or "").strip()
    if not label:
        now = _dt.datetime.now(_dt.timezone.utc)
        label = f"{now.year}Q{((now.month - 1) // 3) + 1}"
    plan = plan_rotation(quarter=label, count=count)
    return {"success": True, "quarter": label, "plan": plan, "applied": False}


__all__ = ["router"]
