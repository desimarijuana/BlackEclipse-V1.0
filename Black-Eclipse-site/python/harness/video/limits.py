"""Resource limits for the video pipeline (Phase 8).

A render loop can be driven by an agent, a schedule, or a user clicking again;
without a cap, a bug (or a very determined reviewer) can queue hundreds of
jobs against one project. This module is the ONE place that decides whether a
project may accept another job — pure policy, no rendering.

The cap counts QUEUED + RUNNING jobs (the Fabric's non-terminal states). It is
deliberately per project, not global: another project's work never starves.
"""

from __future__ import annotations

from typing import Any

from .models import VIDEO_JOB_TYPE, VideoError


def check_queue_depth(
    manager: Any, project_id: str, *, cap: int,
) -> None:
    """Refuse a submit when the project already has `cap` non-terminal jobs.

    A listing failure returns (a submit is never blocked by an observability
    call); a genuine overage raises ``TOO_MANY_PENDING`` naming the cap.
    """
    limit = max(1, int(cap))
    try:
        jobs = manager.list_jobs(type=VIDEO_JOB_TYPE, limit=200)
    except Exception:  # noqa: BLE001 - never block work on a listing failure
        return
    pending = [
        job for job in jobs
        if (job.get("input") or {}).get("projectId") == project_id
        and not job.get("terminal")
    ]
    if len(pending) >= limit:
        raise VideoError(
            "TOO_MANY_PENDING",
            f"project {project_id!r} already has {len(pending)} queued/running video "
            f"job(s) (cap {limit}); wait for them to finish or cancel one",
        )


__all__ = ["check_queue_depth"]
