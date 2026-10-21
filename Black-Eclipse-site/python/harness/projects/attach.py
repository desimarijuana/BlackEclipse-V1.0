"""Auto-populate a project from what a run actually produced.

A project is only useful if it fills itself up. The policy here is small and
explicit:

- a run that names a project **records itself** in that project (a `note`
  member carrying the run id, its status and a bounded excerpt of its answer);
- every **artifact the run produced** joins the project as an `artifact`
  member;
- a run that produced nothing adds nothing but its own note.

The policy is deliberately conservative: it attaches what the run *made*, never
what the run *mentioned*. The user's own `project_attach` calls are untouched.

Nothing here can fail a run. A project that does not exist, an artifact
service that is not configured, a member that cannot be written — all of it is
reported and swallowed, because a finished answer must not be lost to a
bookkeeping step.
"""

from __future__ import annotations

from typing import Any, Optional

#: The excerpt of an answer kept in the note.
MAX_EXCERPT_CHARS = 280


def _excerpt(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= MAX_EXCERPT_CHARS:
        return clean
    return clean[:MAX_EXCERPT_CHARS] + "…"


def attach_run_to_project(
    project_store: Any,
    artifact_service: Any,
    *,
    project_id: Optional[str],
    run_id: str,
    status: str = "completed",
    output: str = "",
    steps: Optional[int] = None,
) -> dict[str, Any]:
    """Record a finished run and its artifacts in its project.

    Returns a small report: what was attached, and why anything was not.
    """
    report: dict[str, Any] = {
        "projectId": project_id,
        "runId": run_id,
        "attached": [],
        "skipped": [],
    }
    if not project_id or project_store is None:
        report["skipped"].append({"reason": "no_project"})
        return report
    try:
        project = project_store.get(str(project_id))
    except Exception:  # noqa: BLE001 - a store read must never break a run
        report["skipped"].append({"reason": "project_unreadable"})
        return report
    if project is None:
        report["skipped"].append({"reason": "no_such_project"})
        return report

    existing = set()
    try:
        existing = {m.ref for m in project_store.members(project.id)}
    except Exception:  # noqa: BLE001
        existing = set()

    # 1. the run itself
    note_ref = f"run:{run_id}"
    if note_ref not in existing:
        try:
            member = project_store.attach(
                project.id, "note", note_ref,
                label=f"run {run_id} · {status}",
                meta={"runId": run_id, "status": status,
                      "steps": steps, "excerpt": _excerpt(output)},
            )
            report["attached"].append({"kind": "note", "id": member.id,
                                       "ref": note_ref})
        except Exception as exc:  # noqa: BLE001
            report["skipped"].append({"reason": "note_not_attached",
                                      "detail": str(exc)[:200]})

    # 2. the artifacts the run produced
    if artifact_service is None:
        report["skipped"].append({"reason": "no_artifact_service"})
        return report
    try:
        from ..artifacts.model import ListArtifactsQuery

        page = artifact_service.list(ListArtifactsQuery(run_id=str(run_id)),
                                     owner_id=None)
        artifacts = list(getattr(page, "artifacts", []) or [])
    except Exception:  # noqa: BLE001 - an artifact read must never break a run
        report["skipped"].append({"reason": "artifacts_unreadable"})
        return report

    for artifact in artifacts:
        ref = str(getattr(artifact, "id", "") or "")
        if not ref or ref in existing:
            continue
        try:
            member = project_store.attach(
                project.id, "artifact", ref,
                label=str(getattr(artifact, "name", "") or ""),
                meta={"runId": run_id,
                      "category": str(getattr(getattr(artifact, "category", None),
                                             "value", "") or "")},
            )
            report["attached"].append({"kind": "artifact", "id": member.id, "ref": ref})
        except Exception as exc:  # noqa: BLE001
            report["skipped"].append({"reason": "artifact_not_attached",
                                      "ref": ref, "detail": str(exc)[:200]})
    return report


async def attach_run_to_project_for_run(
    request: Any,
    project_store: Any,
    artifact_service: Any,
    output: str = "",
    final_state: Any = None,
) -> dict[str, Any]:
    """The run's end-of-run hook: record the run and its artifacts in its project.

    Best-effort by construction - a finished answer must never be lost to a
    bookkeeping step, so every failure here is swallowed and reported.
    """
    project_id = getattr(request, "projectId", None)
    if not project_id or project_store is None:
        return {"projectId": project_id, "attached": [], "skipped": []}
    try:
        return attach_run_to_project(
            project_store, artifact_service,
            project_id=project_id, run_id=str(getattr(request, "runId", "") or ""),
            status="completed", output=output,
            steps=(final_state or {}).get("step", 0) if isinstance(final_state, dict) else None,
        )
    except Exception:  # noqa: BLE001 - a project write must never break a run
        return {"projectId": project_id, "attached": [], "skipped": []}


__all__ = ["MAX_EXCERPT_CHARS", "attach_run_to_project", "attach_run_to_project_for_run"]
