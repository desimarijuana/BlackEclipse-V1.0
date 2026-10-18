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
    "video_update_project",
    "video_list_projects",
    "video_validate_project",
    "video_resolve_data",
    "video_preview",
    "video_render_draft",
    "video_render_final",
    "video_render_repair",
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


def _execution_context(ctx: Any) -> dict[str, Any]:
    """Where a produced artifact belongs: the conversation (private id when the
    run opted in, else the chat session id), the run, and the agent. All
    optional — a tool called without a run context still queues real jobs, the
    artifact is just not conversation-associated."""
    conversation_id = getattr(ctx, "conversation_id", None) or getattr(ctx, "session_id", None)
    return {
        "conversationId": str(conversation_id) if conversation_id else None,
        "runId": str(getattr(ctx, "run_id", None) or "") or None,
        "agentId": str(getattr(ctx, "agent_id", None) or "") or None,
    }


def _push_job(ctx: Any, handle: dict[str, Any], *, kind: str) -> None:
    """Hand a queued job to the run's video collector so the chat renders a
    live job card (progress → player/download). Best-effort by contract: a
    collector failure must never break the tool call."""
    sink = getattr(ctx, "video_sink", None)
    if sink is None:
        return
    try:
        record: dict[str, Any] = {
            "jobId": handle.get("jobId"),
            "projectId": handle.get("projectId"),
            "projectName": handle.get("projectName"),
            "kind": kind,
            "mode": handle.get("mode"),
        }
        if kind == "repair":
            record["ofJobId"] = (handle.get("repair") or {}).get("ofJobId")
        sink(record)
    except Exception:  # noqa: BLE001 - collection must never break a tool call
        pass


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
            f"created video project {project['name']!r} ({project['id']}, kind {project['kind']}, "
            f"revision {project.get('revision', 1)})",
            {"status": "ok", "project": project},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_create_project", exc)


async def video_update_project(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        project = _service().update_project(
            str(args.get("projectId") or ""),
            name=str(args["name"]) if args.get("name") is not None else None,
            spec=args.get("spec") if isinstance(args.get("spec"), dict) else None,
        )
        return (
            f"updated video project {project['id']} -> revision {project.get('revision', 1)} "
            "(re-render to see the change)",
            {"status": "ok", "project": project},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_update_project", exc)


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


async def video_resolve_data(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        manifest = await _service().resolve_project_data(str(args.get("projectId") or ""))
        bindings = list(manifest.get("bindings") or [])
        parts = []
        for binding in bindings[:5]:
            symbol = binding.get("symbol") or ""
            what = binding.get("field") or binding.get("interval") or ""
            shown = binding.get("display") or (
                f"{binding.get('rows')} bars" if binding.get("rows") else ""
            )
            parts.append(f"scenes[{binding.get('sceneIndex')}] {symbol} {what} -> {shown}".strip())
        text = (
            f"resolved {len(bindings)} binding(s)"
            + (" — STALE data present" if manifest.get("stale") else "")
            + ("; ".join(["", *parts]) if parts else "")
        )
        return (text, {"status": "ok", "evidence": manifest})
    except Exception as exc:  # noqa: BLE001
        return _error("video_resolve_data", exc)


async def video_preview(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        handle = await _service().preview_project(
            str(args.get("projectId") or ""),
            owner=_owner(ctx),
            count=args.get("count") if isinstance(args.get("count"), int) else None,
            width=args.get("width") if isinstance(args.get("width"), int) else None,
            frames=args.get("frames") is not False,
            context=_execution_context(ctx),
        )
        _push_job(ctx, handle, kind="preview")
        return (
            f"preview submitted as job {handle.get('jobId')} — it renders a PNG contact "
            "sheet (plus one frame per scene) into the Artifact Center and reports any "
            "frame findings; no video is rendered. Poll video_job_status, then look at "
            "the image artifacts / findings before paying for a draft or final render",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_preview", exc)


async def video_render_draft(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        handle = await _service().render_draft(
            str(args.get("projectId") or ""), owner=_owner(ctx),
            context=_execution_context(ctx),
        )
        _push_job(ctx, handle, kind="render")
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
            str(args.get("projectId") or ""), owner=_owner(ctx),
            context=_execution_context(ctx),
        )
        _push_job(ctx, handle, kind="render")
        return (
            f"final render submitted as job {handle.get('jobId')} — poll video_job_status; "
            "the finished MP4 is registered in the Artifact Center",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_render_final", exc)


async def video_render_repair(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        handle = await _service().render_repair(
            str(args.get("projectId") or ""),
            of_job_id=str(args.get("ofJobId") or ""),
            spec=args.get("spec") if isinstance(args.get("spec"), dict) else None,
            name=str(args["name"]) if args.get("name") is not None else None,
            owner=_owner(ctx),
            context=_execution_context(ctx),
        )
        _push_job(ctx, handle, kind="repair")
        repair_info = handle.get("repair") or {}
        return (
            f"repair render submitted as job {handle.get('jobId')}: repair attempt "
            f"{repair_info.get('attempt')} of {repair_info.get('maxAttempts')} for failed job "
            f"{repair_info.get('ofJobId')} — poll video_job_status; if this repair fails too, "
            "report the diagnostics to the user instead of retrying again",
            {"status": "ok", "job": handle},
        )
    except Exception as exc:  # noqa: BLE001
        return _error("video_render_repair", exc)


async def video_inspect(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        job_id = str(args.get("jobId") or "") or None
        project_id = str(args.get("projectId") or "") or None
        handle = await _service().inspect_video(job_id=job_id, project_id=project_id)
        _push_job(ctx, handle, kind="inspect")
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
        "Create a video project. Kind `storyboard` takes a spec that must match the "
        "versioned storyboard schema (schemaVersion 2 — scene types intro/metric/"
        "candlestick/comparison/timeline/quote/outro; see the video-production skill). "
        "Kind `title_card` renders the built-in BlackEclipse title card and takes no "
        "spec. Nothing is rendered by this tool; validate before rendering.",
        video_create_project, {"type": "object", "properties": {
            "name": {"type": "string", "description": "Short project name taken from the user's request."},
            "kind": {"type": "string", "enum": ["title_card", "storyboard"]},
            "spec": {"type": "object", "description": "The storyboard spec (required for kind `storyboard`)."},
        }, "required": ["name"]},
    )
    _def(
        "video_update_project",
        "Revise an existing video project (rename and/or replace its storyboard spec); "
        "the revision counter is bumped so a re-render is traceable. Re-rendering after "
        "an update produces the new version — nothing else needs rebuilding.",
        video_update_project, {"type": "object", "properties": {
            "projectId": {"type": "string"},
            "name": {"type": "string"},
            "spec": {"type": "object", "description": "The replacement storyboard spec."},
        }, "required": ["projectId"]},
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
        "video_resolve_data",
        "Resolve a storyboard's data bindings NOW through the Market Data Gateway, "
        "without rendering: what each bound figure will show, its provider, retrieval "
        "time, units and freshness. Use it to verify figures before a render; missing "
        "data is reported as an error, never invented. Stale data resolves but is "
        "flagged in the video and the manifest — tell the user when delivering.",
        video_resolve_data, {"type": "object", "properties": {
            "projectId": {"type": "string"},
        }, "required": ["projectId"]}, 60_000,
    )
    _def(
        "video_preview",
        "Render a PNG contact sheet — and one frame per scene for storyboards — WITHOUT "
        "producing a video: the fastest way to review layout, text clipping and fonts "
        "before a draft or final render. The images register in the Artifact Center "
        "(image category) and frame findings come back in the job output. Use this "
        "before any first draft, and whenever the user should see the look before "
        "paying for a render.",
        video_preview, {"type": "object", "properties": {
            "projectId": {"type": "string"},
            "count": {"type": "integer", "description": "contact-sheet frames (2-24, default 8)"},
            "width": {"type": "integer", "description": "per-frame width in px (160-960, default 480)"},
            "frames": {"type": "boolean", "description": "also render one frame per scene (default true)"},
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
        "video_render_repair",
        "Repair a FAILED render, bounded: pass the failed job id (`ofJobId`) and, when the "
        "failure is about the content or frames (INSPECTION_FAILED / RENDER_FAILED), the "
        "revised storyboard spec — the revision is bumped and a new render is queued linked "
        "to the failure. At most 2 repairs per failure line, then the service refuses "
        "(REPAIR_LIMIT_REACHED): report the diagnostics to the user instead of retrying. "
        "For transient failures (DATA_UNAVAILABLE / WORKER_UNAVAILABLE) a spec-less retry "
        "is allowed. Never use it on a SUCCEEDED or CANCELLED job.",
        video_render_repair, {"type": "object", "properties": {
            "projectId": {"type": "string"},
            "ofJobId": {"type": "string", "description": "the FAILED render job this repair responds to"},
            "spec": {"type": "object", "description": "The revised storyboard spec (required for content failures)."},
            "name": {"type": "string", "description": "Optional new project name."},
        }, "required": ["projectId", "ofJobId"]}, 30_000,
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
