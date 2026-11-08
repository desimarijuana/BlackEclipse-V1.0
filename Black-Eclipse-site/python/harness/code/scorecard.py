"""The self-build scorecard (Phase 22 / S6).

The claim "Eclipse can build Eclipse" is an anecdote until it is measured. This
module derives a small, honest scorecard from facts the runtime ALREADY records:

  * a build is a run with a ``session.created`` checkpoint;
  * a checked build has a ``land.verified`` checkpoint (the first one decides
    "passed first time");
  * a landing has a ``land.promoted`` checkpoint;
  * a rollback has a ``land.rolled_back`` checkpoint;
  * steps and tokens come from the ``HarnessRun`` row;
  * time-to-first-change is the gap between ``task.created`` and the first
    ``patch.applied``.

A dimension with no data is the string ``UNKNOWN`` - never ``0``. There is no
blended "improvement score": each number is shown with its own denominator, so a
small sample cannot hide behind a big one.

No new store: this reads the ONE run lineage.
"""

from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

UNKNOWN = "UNKNOWN"

#: Checkpoint kinds this module reads. They are written by the routers/tasks.
SESSION_CREATED = "session.created"
LAND_VERIFIED = "land.verified"
LAND_PROMOTED = "land.promoted"
LAND_ROLLED_BACK = "land.rolled_back"
TASK_CREATED = "task.created"
PATCH_APPLIED = "patch.applied"


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _mean(values: list[float]) -> Any:
    return round(sum(values) / len(values), 2) if values else UNKNOWN


def _median(values: list[float]) -> Any:
    return round(statistics.median(values), 1) if values else UNKNOWN


def _same_path(left: str, right: str) -> bool:
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))
    except (OSError, ValueError):
        return left == right


def build_scorecard(
    store: Any, *, window_days: int = 30, limit: int = 200,
    now: Optional[datetime] = None, project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Derive the scorecard. Never raises on a malformed row; names the holes.

    A build is any run that left a code workspace and a ``session.created``
    checkpoint — a Code task or a chat build. ``project_root`` narrows it to one
    project (the checkout recorded when the workspace was allocated), so "how is
    Eclipse doing on THIS repo" is a different question from "across everything".
    """
    from ..code.store import CodeWorkspaceStore  # noqa: PLC0415
    from ..run_lineage import RunLineage  # noqa: PLC0415

    days = max(1, min(int(window_days), 365))
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=days)
    lineage = RunLineage(store)
    code_store = CodeWorkspaceStore(store)

    builds = 0
    checked = 0
    first_pass = 0
    landed = 0
    rolled_back = 0
    steps: list[float] = []
    tokens = 0
    first_diff: list[float] = []
    runs = 0
    by_model: dict[str, dict[str, Any]] = {}

    for run in store.list_runs(limit=max(1, min(int(limit), 200))):
        created = _parse_iso(run.get("createdAt"))
        if created is not None and created < cutoff:
            continue
        run_id = str(run.get("id") or "")
        # A code run always left a workspace row; a finance/chat turn did not.
        # The row also names the PROJECT, which is what the filter needs.
        try:
            workspaces = code_store.list_workspaces(run_id=run_id, limit=1)
        except Exception:  # noqa: BLE001 - a store hiccup is "no attribution"
            workspaces = []
        if not workspaces:
            # A legacy code run (its agent id) still counts globally; a chat turn
            # with no workspace at all is not code work and is skipped.
            if str(run.get("agentId") or "") != "code-agent":
                continue
        project = str((workspaces[0] or {}).get("checkoutRoot") or "") if workspaces else ""
        if project_root and not _same_path(project, str(project_root)):
            continue
        runs += 1
        checkpoints = lineage.list_checkpoints(run_id)
        kinds = [str(item.get("kind") or "") for item in checkpoints]
        if SESSION_CREATED not in kinds:
            continue
        builds += 1
        steps.append(float(run.get("modelSteps") or 0))
        tokens += int(run.get("totalTokens") or 0)
        provider = str(run.get("provider") or "unknown")
        model = str(run.get("model") or "unknown")
        entry = by_model.setdefault(f"{provider}/{model}", {
            "provider": provider, "model": model, "builds": 0,
            "checked": 0, "firstPassChecks": 0, "landed": 0, "rolledBack": 0,
        })
        entry["builds"] += 1

        verifies = [item for item in checkpoints if item.get("kind") == LAND_VERIFIED]
        if verifies:
            checked += 1
            entry["checked"] += 1
            first = (verifies[0].get("payload") or {})
            if first.get("ok") is True:
                first_pass += 1
                entry["firstPassChecks"] += 1
        if LAND_PROMOTED in kinds:
            landed += 1
            entry["landed"] += 1
        if LAND_ROLLED_BACK in kinds:
            rolled_back += 1
            entry["rolledBack"] += 1

        started = next((item for item in checkpoints if item.get("kind") == TASK_CREATED), None)
        applied = next((item for item in checkpoints if item.get("kind") == PATCH_APPLIED), None)
        # `patch.applied` is not yet written by every edit path; the promoted
        # marker is a real change boundary and keeps the metric measurable.
        if applied is None:
            applied = next((item for item in checkpoints if item.get("kind") == LAND_PROMOTED), None)
        if started and applied:
            start_at = _parse_iso(started.get("createdAt"))
            applied_at = _parse_iso(applied.get("createdAt"))
            if start_at and applied_at and applied_at >= start_at:
                first_diff.append((applied_at - start_at).total_seconds())

    metrics = {
        "runs": runs,
        "builds": builds,
        "checked": checked,
        "firstPassChecks": first_pass,
        "landed": landed,
        "rolledBack": rolled_back,
        "successRate": round(landed / builds, 3) if builds else UNKNOWN,
        "rollbackRate": round(rolled_back / landed, 3) if landed else UNKNOWN,
        "firstPassRate": round(first_pass / checked, 3) if checked else UNKNOWN,
        "averageSteps": _mean(steps),
        "totalTokens": tokens if builds else UNKNOWN,
        "medianTimeToFirstChangeSeconds": _median(first_diff),
        # Not recorded anywhere yet. Named, not faked.
        "costUsd": UNKNOWN,
        "humanEditsAfterLanding": UNKNOWN,
    }
    return {
        "windowDays": days,
        "checkedAt": current.isoformat(),
        "projectRoot": str(project_root) if project_root else None,
        "metrics": metrics,
        "byModel": sorted(by_model.values(), key=lambda item: item["builds"], reverse=True),
        "unmeasured": ["costUsd", "humanEditsAfterLanding"],
    }


__all__ = [
    "LAND_PROMOTED",
    "LAND_ROLLED_BACK",
    "LAND_VERIFIED",
    "PATCH_APPLIED",
    "SESSION_CREATED",
    "TASK_CREATED",
    "UNKNOWN",
    "build_scorecard",
]
