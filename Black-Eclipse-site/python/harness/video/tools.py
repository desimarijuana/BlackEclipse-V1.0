"""Agent-facing video production tools.

Typed tools on the SAME shared `ToolRegistry` as every other toolset, so schema
validation, events, timeouts and the audit trail apply unchanged. They are thin
adapters over `VideoService`: every operation that touches the renderer is a
queued Execution Fabric job — the tools submit and return handles, and the read
tools report status.

Nothing here fabricates success: an unbuilt worker, a missing FFmpeg tree, a
failed inspection or a refused project is a structured error, never a claimed
video. All tools are `read`/`low`: they queue Fabric jobs and write only into
the confined video workspace and the Artifact Center — the same class as the
`ml_*` and `document_create` tools, and they are NOT part of any effectful
tuple in `code/policy.py`.
"""

from __future__ import annotations

from typing import Any

from .models import VideoError

VIDEO_TOOLS: tuple[str, ...] = (
    "video_capabilities",
    "video_create_project",
    "video_list_projects",
    "video_validate_project",
    "video_render_draft",
    "video_render_final",
    "video_inspect",
    "video_job_status",
    "video_list_jobs",
    "video_cancel_job",
)


def _service() -> Any:
    from .service import get_video_service  # noqa: PLC0415

    service = get_video_service()
    if service is None:
        raise VideoError("RUNTIME_UNAVAILABLE", "the video pipeline is not available")
    return service


def _owner(ctx: Any) -> str:
    return str(getattr(ctx, "workspace_id", None) or "local")


def _error(tool: str, exc: Exception) -> tuple[str, Any]:
    code = getattr(exc, "code", "VIDEO_ERROR")
    return (f"{tool} — error [{code}]: {exc}",
            {"status": "error", "tool": tool, "error": {"code": code, "message": str(exc)}})


async def video_capabilities(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        caps = _service().capabilities()
        if caps["ready"]:
            summary = (
                f"Video pipeline ready; project kinds: {', '.join(caps['projectKinds'])} "
                "(the built-in title card). Drafts render in seconds; final renders "
                "register an Artifact Center entry."
            )
        else:
            problems = caps["environment"].get("problems") or ["unknown problem"]
            summary = f"Video pipeline is NOT ready: {problems[0]}"
        return (summary, {"status": "ok", **caps})
    except Exception as exc:  # noqa: BLE001
        return _error("video_capabilities", exc)


async def video_create_project(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        project = _service().create_project(
            name=str(args.get("name") or ""),
            kind=str(args.get("kind") or "title_card"),
            spec=args.get("spec") if isinstance(args.get("spec"), dict) else None,
        )
        return (
            f"created video project {project['name']!r} ({project['id']}, kind {project['kind']})",
            {"status": "ok", "project": project},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_create_project", exc)


async def video_list_projects(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        projects = _service().list_projects()
        return (f"{len(projects)} video project(s)", {"status": "ok", "projects": projects})
    except Exception as exc:  # noqa: BLE001
        return _error("video_list_projects", exc)


async def video_validate_project(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        report = _service().validate_project(str(args.get("projectId") or ""))
        state = "valid" if report["valid"] else "INVALID"
        detail = f"; problems: {'; '.join(report['problems'])}" if report["problems"] else ""
        return (
            f"project {report['project']['id']} is {state}{detail}",
            {"status": "ok", **report},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_validate_project", exc)


async def video_render_draft(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        handle = await _service().render_draft(
            str(args.get("projectId") or ""), owner=_owner(ctx)
        )
        return (
            f"draft render submitted as job {handle.get('jobId')} — poll video_job_status "
            "(drafts are half-resolution and finish in seconds)",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_render_draft", exc)


async def video_render_final(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        handle = await _service().render_final(
            str(args.get("projectId") or ""), owner=_owner(ctx)
        )
        return (
            f"final render submitted as job {handle.get('jobId')} — poll video_job_status; "
            "the finished MP4 is registered in the Artifact Center",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_render_final", exc)


async def video_inspect(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        job_id = str(args.get("jobId") or "") or None
        project_id = str(args.get("projectId") or "") or None
        handle = await _service().inspect_video(job_id=job_id, project_id=project_id)
        return (
            f"frame inspection submitted as job {handle.get('jobId')} — poll video_job_status",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_inspect", exc)


async def video_job_status(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        job_id = str(args.get("jobId") or "")
        job = _service().get_job(job_id)
        if job is None:
            raise VideoError("JOB_NOT_FOUND", f"video job {job_id!r} was not found")
        pct = int(float(job.get("progress") or 0) * 100)
        text = f"job {job_id}: {job.get('status')} ({pct}%)"
        output = job.get("output")
        if isinstance(output, dict) and isinstance(output.get("artifact"), dict):
            text += f" — artifact {output['artifact'].get('id')}"
        if job.get("error"):
            text += f" — error: {job['error']}"
        return (text, {"status": "ok", "job": job})
    except Exception as exc:  # noqa: BLE001
        return _error("video_job_status", exc)


async def video_list_jobs(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        project_id = str(args.get("projectId") or "") or None
        jobs = _service().list_jobs(project_id=project_id, limit=int(args.get("limit", 50)))
        return (f"{len(jobs)} video job(s)", {"status": "ok", "jobs": jobs})
    except Exception as exc:  # noqa: BLE001
        return _error("video_list_jobs", exc)


async def video_cancel_job(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        job_id = str(args.get("jobId") or "")
        result = await _service().cancel_job(job_id)
        return (
            f"cancellation for {job_id}: {result.get('status') or 'unknown'} "
            f"(hardCancelled={bool(result.get('hardCancelled'))})",
            {"status": "ok", "cancellation": result},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_cancel_job", exc)


def register_video_tools(registry: Any) -> list[str]:
    from ..tools import ToolDefinition  # noqa: PLC0415

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 10_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout, version="1.0.0",
        ))

    _def(
        "video_capabilities",
        "Report whether the video pipeline is ready (worker binary built, FFmpeg tree "
        "present) and what it can render. Call this FIRST for any video request; if it "
        "is not ready, say why instead of attempting a render.",
        video_capabilities, {"type": "object", "properties": {}}, 15_000,
    )
    _def(
        "video_create_project",
        "Create a video project. The ONLY supported kind today is `title_card` (the "
        "built-in BlackEclipse title card); custom scenes and storyboards are not "
        "implemented yet — do not promise them.",
        video_create_project, {"type": "object", "properties": {
            "name": {"type": "string", "description": "Short project name taken from the user's request."},
            "kind": {"type": "string", "enum": ["title_card"]},
            "spec": {"type": "object", "description": "Reserved for the Phase 4 storyboard schema."},
        }, "required": ["name"]},
    )
    _def(
        "video_list_projects", "List video projects.",
        video_list_projects, {"type": "object", "properties": {}},
    )
    _def(
        "video_validate_project",
        "Validate a video project (spec problems + environment readiness) before "
        "rendering. A project with problems is refused by the renderer.",
        video_validate_project, {"type": "object", "properties": {
            "projectId": {"type": "string"},
        }, "required": ["projectId"]}, 30_000,
    )
    _def(
        "video_render_draft",
        "Queue a half-resolution draft render (a job on the Execution Fabric; usually "
        "seconds). Poll video_job_status until terminal, then video_inspect the result.",
        video_render_draft, {"type": "object", "properties": {
            "projectId": {"type": "string"},
        }, "required": ["projectId"]}, 30_000,
    )
    _def(
        "video_render_final",
        "Queue the full-resolution final render; on success the MP4 is registered in "
        "the Artifact Center (minutes on the CPU backend). Poll video_job_status for "
        "the artifact id. Never claim the video exists before it SUCCEEDS.",
        video_render_final, {"type": "object", "properties": {
            "projectId": {"type": "string"},
        }, "required": ["projectId"]}, 30_000,
    )
    _def(
        "video_inspect",
        "Queue a frame inspection of a completed render (missing fonts, clipped text, "
        "invalid frames). Pass the render's jobId, or a projectId to inspect its latest "
        "successful render.",
        video_inspect, {"type": "object", "properties": {
            "jobId": {"type": "string"}, "projectId": {"type": "string"},
        }}, 30_000,
    )
    _def(
        "video_job_status",
        "Status, progress, result and artifact id of one video job.",
        video_job_status, {"type": "object", "properties": {
            "jobId": {"type": "string"},
        }, "required": ["jobId"]},
    )
    _def(
        "video_list_jobs",
        "List recent video jobs (optionally filtered by project).",
        video_list_jobs, {"type": "object", "properties": {
            "projectId": {"type": "string"}, "limit": {"type": "integer"},
        }},
    )
    _def(
        "video_cancel_job",
        "Request cancellation of a queued or running video job (a running render is "
        "stopped immediately).",
        video_cancel_job, {"type": "object", "properties": {
            "jobId": {"type": "string"},
        }, "required": ["jobId"]}, 15_000,
    )
    return list(VIDEO_TOOLS)


__all__ = ["VIDEO_TOOLS", "register_video_tools"]
