"""Bounded repair policy for failed video jobs (Phase 6).

A render can fail for two very different reasons, and they get different,
DELIBERATELY BOUNDED responses:

1. **Transient infrastructure failures** — a market-data fetch that blipped
   (`DATA_UNAVAILABLE`), a worker that could not be spawned (`WORKER_UNAVAILABLE`).
   The render job retries those internally, at most `VideoConfig.transient_retries`
   extra attempts (recorded in the output as `retries`), then fails for real.

2. **Content / determinism failures** — `INSPECTION_FAILED`, `RENDER_FAILED`,
   `INVALID_*`, `TIMEOUT`. Retrying an unchanged spec would just repeat the same
   result, so the failure goes back to the author: revise via
   `video_update_project` (or `video_render_repair` with a new spec) and render
   again. That loop is capped HERE: a repair render must reference the failed
   job it repairs (`repairOf`), and the chain may not exceed
   `MAX_REPAIR_ATTEMPTS` repairs. Past the cap the service refuses with
   `REPAIR_LIMIT_REACHED` and the diagnostics are what the user/agent reports —
   never another silent retry.

The module is pure policy: it reads job records and plans/validates, it never
renders, updates or submits anything.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .models import VideoError

#: How many repairs one failure line may accumulate (repair-of-repair-of-…).
MAX_REPAIR_ATTEMPTS = 2

#: Cycle guard for walking a repair chain.
MAX_REPAIR_CHAIN_HOPS = 32

#: Failure classes where a bounded same-spec retry is the honest response.
TRANSIENT_ERROR_CLASSES: tuple[str, ...] = ("DATA_UNAVAILABLE", "WORKER_UNAVAILABLE")


def is_transient(error_class: Optional[str]) -> bool:
    """True when re-running the same request may plausibly succeed."""
    return str(error_class or "").strip().upper() in TRANSIENT_ERROR_CLASSES


def diagnostics_from_job(
    job: Optional[dict[str, Any]], report: Optional[dict[str, Any]] = None,
    *, limit: int = 5,
) -> dict[str, Any]:
    """A compact summary of what a failed job reported — the diagnostics a
    repair responds to. Never invented: everything comes off the job record or
    its persisted ``report.json`` (the Fabric keeps no output row for a failed
    job, so the report is the evidence of record for inspection findings)."""
    job = job if isinstance(job, dict) else {}
    output = job.get("output") if isinstance(job.get("output"), dict) else {}
    report = report if isinstance(report, dict) else {}
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    details = report.get("details") if isinstance(report.get("details"), dict) else {}
    inspection: dict[str, Any] = {}
    for candidate in (
        output.get("inspection"),
        result.get("inspection"),
        (details.get("inspection") if isinstance(details.get("inspection"), dict) else {}),
    ):
        if isinstance(candidate, dict) and candidate.get("findings") is not None:
            inspection = candidate
            break
    findings: list[dict[str, Any]] = []
    for finding in list(inspection.get("findings") or [])[:limit]:
        if isinstance(finding, dict):
            findings.append({
                "severity": finding.get("severity"),
                "message": str(finding.get("message") or "")[:300],
            })
        else:
            findings.append({"message": str(finding)[:300]})
    return {
        "errorClass": job.get("errorClass") or output.get("errorClass") or result.get("errorClass"),
        "error": str(job.get("error") or output.get("error") or result.get("error") or "")[:500] or None,
        "findings": findings,
    }


def failure_line(jobs: Iterable[dict[str, Any]], job_id: str, *, limit: int = MAX_REPAIR_CHAIN_HOPS) -> set[str]:
    """Every job connected to `job_id` by `repairOf` links, in BOTH directions.

    The failure LINE is a connected component: the failed job, the repairs it
    spawned, the failures those repairs produced, their repairs, and so on.
    Walking both directions is what makes the cap un-evadable — re-referencing
    the original failure after a failed repair stays inside the same line.
    """
    jobs_list = [job for job in jobs if isinstance(job, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = {}
    parent_of: dict[str, str] = {}
    for job in jobs_list:
        key = str(job.get("id") or job.get("jobId") or "")
        if not key:
            continue
        by_id[key] = job
        parent = str((job.get("input") or {}).get("repairOf") or "")
        if parent:
            parent_of[key] = parent
            children.setdefault(parent, []).append(key)

    seen: set[str] = set()
    queue = [str(job_id or "")]
    while queue and len(seen) < limit:
        node = queue.pop()
        if not node or node in seen:
            continue
        seen.add(node)
        neighbours = list(children.get(node, []))
        parent = parent_of.get(node)
        if parent:
            neighbours.append(parent)
        queue.extend(neighbours)
    return seen


def repair_attempts(jobs: Iterable[dict[str, Any]], of_job_id: str) -> int:
    """How many repairs ALREADY exist in this failure line."""
    jobs_list = [job for job in jobs if isinstance(job, dict)]
    line = failure_line(jobs_list, of_job_id)
    count = 0
    for job in jobs_list:
        key = str(job.get("id") or job.get("jobId") or "")
        parent = str((job.get("input") or {}).get("repairOf") or "")
        if key in line and parent:
            count += 1
    return count


def check_repair_allowed(jobs: Iterable[dict[str, Any]], of_job_id: str) -> int:
    """The attempt number a new repair of `of_job_id` would be, or a refusal.

    Raises ``REPAIR_LIMIT_REACHED`` when the failure line already used its
    budget — the explicit terminal state of the bounded repair loop.
    """
    used = repair_attempts(jobs, of_job_id)
    if used >= MAX_REPAIR_ATTEMPTS:
        raise VideoError(
            "REPAIR_LIMIT_REACHED",
            f"this failure line already used its {MAX_REPAIR_ATTEMPTS} repair attempts "
            f"({used} recorded); report the job's diagnostics to the user instead of "
            "retrying again",
        )
    return used + 1


def validate_repair_target(parent: Optional[dict[str, Any]], project_id: str) -> None:
    """A repair may only reference a FAILED/TIMED_OUT render of the same project."""
    if parent is None:
        raise VideoError("JOB_NOT_FOUND", "the job to repair was not found")
    if (parent.get("input") or {}).get("action") != "render":
        raise VideoError("INVALID_STATE", "only a render job can be repaired")
    if str((parent.get("input") or {}).get("projectId") or "") != str(project_id or ""):
        raise VideoError("INVALID_STATE", "the failed job belongs to a different project")
    status = str(parent.get("status") or "")
    if status == "SUCCEEDED":
        raise VideoError("INVALID_STATE", "that render succeeded — there is nothing to repair")
    if status == "CANCELLED":
        raise VideoError("INVALID_STATE", "that render was cancelled, not failed — re-render instead")
    if status not in ("FAILED", "TIMED_OUT"):
        raise VideoError(
            "INVALID_STATE",
            f"that job is {status or 'not terminal'} — only a failed or timed-out render can be repaired",
        )


__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "MAX_REPAIR_CHAIN_HOPS",
    "TRANSIENT_ERROR_CLASSES",
    "check_repair_allowed",
    "diagnostics_from_job",
    "failure_line",
    "is_transient",
    "repair_attempts",
    "validate_repair_target",
]
