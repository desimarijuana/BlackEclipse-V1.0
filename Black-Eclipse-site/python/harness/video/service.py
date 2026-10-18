"""The video job layer: projects, draft/final renders and inspection.

Rendering is slow and CPU-bound, so every operation that touches the Rust
worker is a QUEUED Execution-Fabric job (type ``video``) — never inline. This
service is the ONE door to those jobs: it resolves projects, owns the
per-job workspace layout, maps render progress into Fabric progress, runs the
post-render inspection gate and registers final renders into the Artifact
Center.

The Fabric worker handler in ``video/fabric.py`` calls
``run_render_job`` / ``run_inspect_job`` with the job's cancel event and
progress callback; the Fabric owns durability, retries, cancellation and
recovery around it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from ..persistence import now_iso
from .config import VideoConfig, get_video_config
from .models import SUPPORTED_PROJECT_KINDS, VIDEO_JOB_TYPE, VideoError
from .projects import VideoProjectStore
from .runner import VideoRunner

log = logging.getLogger("harness.video")

_MODE_DRAFT = "draft"
_MODE_FINAL = "final"


class VideoService:
    def __init__(
        self,
        *,
        config: Optional[VideoConfig] = None,
        runner: Optional[VideoRunner] = None,
        projects: Optional[VideoProjectStore] = None,
        artifact_provider: Optional[Callable[[], Any]] = None,
        manager_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._config = config or get_video_config()
        self._runner = runner or VideoRunner(self._config)
        self._projects = projects or VideoProjectStore(
            self._config.resolve_video_root() / "projects"
        )
        self._artifact_provider = artifact_provider
        self._manager_provider = manager_provider

    # ── dependencies ─────────────────────────────────────────────────────────

    def _manager(self) -> Any:
        if self._manager_provider is not None:
            manager = self._manager_provider()
        else:
            from ..fabric.tools import get_fabric_manager  # noqa: PLC0415

            manager = get_fabric_manager()
        if manager is None:
            raise VideoError(
                "RUNTIME_UNAVAILABLE",
                "the Execution Fabric is unavailable; video jobs cannot be queued",
            )
        return manager

    def _artifact_service(self) -> Any:
        if self._artifact_provider is None:
            return None
        try:
            return self._artifact_provider()
        except Exception:  # noqa: BLE001 - a missing artifact layer is honest
            return None

    # ── projects ─────────────────────────────────────────────────────────────

    def create_project(
        self, *, name: str, kind: str = "title_card", spec: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return self._projects.create(name=name, kind=kind, spec=spec)

    def get_project(self, project_id: str) -> dict[str, Any]:
        project = self._projects.get(project_id)
        if project is None:
            raise VideoError("PROJECT_NOT_FOUND", f"project {project_id!r} was not found")
        return project

    def list_projects(self) -> list[dict[str, Any]]:
        return self._projects.list()

    def validate_project(self, project_id: str) -> dict[str, Any]:
        """Spec problems + environment readiness in one honest report."""
        project = self.get_project(project_id)
        problems = self._projects.validate(project)
        environment = self._runner.environment_report()
        problems = problems + list(environment["problems"])
        return {
            "valid": not problems,
            "problems": problems,
            "warnings": list(environment["warnings"]),
            "environment": environment,
            "project": project,
        }

    def capabilities(self) -> dict[str, Any]:
        """What the pipeline can honestly do right now (readiness + limits)."""
        environment = self._runner.environment_report()
        return {
            "enabled": bool(self._config.enabled),
            "ready": bool(environment["ready"]),
            "projectKinds": list(SUPPORTED_PROJECT_KINDS),
            "environment": environment,
            "limits": {
                "maxConcurrent": self._config.max_concurrent,
                "draftTimeoutMs": self._config.draft_timeout_ms,
                "finalTimeoutMs": self._config.final_timeout_ms,
                "inspectTimeoutMs": self._config.inspect_timeout_ms,
            },
        }

    # ── job API ──────────────────────────────────────────────────────────────

    async def render_draft(
        self, project_id: str, *, owner: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self._submit_render(
            project_id, mode=_MODE_DRAFT, owner=owner, idempotency_key=idempotency_key
        )

    async def render_final(
        self, project_id: str, *, owner: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self._submit_render(
            project_id, mode=_MODE_FINAL, owner=owner, idempotency_key=idempotency_key
        )

    async def _submit_render(
        self, project_id: str, *, mode: str, owner: Optional[str],
        idempotency_key: Optional[str],
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        timeout_ms = (
            self._config.final_timeout_ms if mode == _MODE_FINAL else self._config.draft_timeout_ms
        )
        payload = {
            "action": "render",
            "mode": mode,
            "projectId": project["id"],
            "projectName": project["name"],
            "projectKind": project["kind"],
            "owner": owner,
        }
        handle = await self._manager().submit(
            VIDEO_JOB_TYPE,
            payload,
            timeout_ms=timeout_ms,
            idempotency_key=idempotency_key,
            metadata={"source": "video", "kind": f"render_{mode}", "projectId": project["id"]},
        )
        handle["projectId"] = project["id"]
        handle["mode"] = mode
        return handle

    async def inspect_video(
        self, *, job_id: Optional[str] = None, project_id: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> dict[str, Any]:
        """Queue a frame inspection of a completed render.

        Pass the render's ``job_id``, or a ``project_id`` to inspect its latest
        successful render.
        """
        if job_id:
            source = self.get_job(job_id)
            if source is None:
                raise VideoError("JOB_NOT_FOUND", f"job {job_id!r} was not found")
            if (source.get("input") or {}).get("action") != "render":
                raise VideoError("INVALID_STATE", "inspect needs a render job id")
            if source.get("status") != "SUCCEEDED":
                raise VideoError(
                    "INVALID_STATE",
                    f"job {job_id!r} is {source.get('status')}, not a completed render",
                )
        elif project_id:
            self.get_project(project_id)
            source = self._latest_render_job(project_id)
            if source is None:
                raise VideoError(
                    "INVALID_STATE",
                    f"project {project_id!r} has no successful render to inspect yet",
                )
        else:
            raise VideoError("INVALID_INPUT", "pass a job_id or a project_id")
        output_path = str(((source.get("output") or {}).get("outputPath")) or "")
        if not output_path:
            raise VideoError("INVALID_STATE", "the render job recorded no output path")
        confined = self._confined(output_path)
        payload = {
            "action": "inspect",
            "outputPath": str(confined),
            "sourceJobId": source.get("id") or source.get("jobId"),
            "projectId": (source.get("input") or {}).get("projectId"),
            "owner": owner,
        }
        handle = await self._manager().submit(
            VIDEO_JOB_TYPE,
            payload,
            timeout_ms=self._config.inspect_timeout_ms,
            metadata={"source": "video", "kind": "inspect", "projectId": payload.get("projectId")},
        )
        return handle

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._manager().get(job_id)

    def list_jobs(
        self, *, project_id: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        jobs = self._manager().list_jobs(type=VIDEO_JOB_TYPE, limit=int(limit))
        if project_id:
            jobs = [
                j for j in jobs
                if (j.get("input") or {}).get("projectId") == project_id
            ]
        return jobs

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        return await self._manager().cancel(job_id)

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifacts = self._artifact_service()
        if artifacts is None:
            raise VideoError("RUNTIME_UNAVAILABLE", "the Artifact Center is unavailable")
        from ..artifacts.service import ArtifactError  # noqa: PLC0415

        try:
            artifact = artifacts.get(artifact_id)
        except ArtifactError as exc:
            raise VideoError(exc.code, exc.message) from exc
        if artifact is None:
            raise VideoError("ARTIFACT_NOT_FOUND", f"artifact {artifact_id!r} was not found")
        if hasattr(artifact, "to_dict"):
            return artifact.to_dict()
        return _artifact_summary(artifact)

    # ── worker-side execution (called by the Fabric handler) ─────────────────

    async def run_render_job(
        self,
        payload: dict[str, Any],
        *,
        cancel_event: Optional[asyncio.Event] = None,
        progress: Optional[Callable[..., None]] = None,
    ) -> dict[str, Any]:
        mode = str(payload.get("mode") or _MODE_DRAFT).strip().lower()
        project_id = str(payload.get("projectId") or "")
        job_id = str(payload.get("jobId") or "manual")
        workspace = self._config.resolve_video_root() / "jobs" / job_id
        result: dict[str, Any] = {
            "status": "failed", "action": "render", "mode": mode,
            "projectId": project_id or None,
        }
        try:
            if mode not in (_MODE_DRAFT, _MODE_FINAL):
                raise VideoError("INVALID_INPUT", f"unknown render mode {mode!r}")
            project = self._projects.get(project_id) if project_id else None
            if project is None:
                raise VideoError("PROJECT_NOT_FOUND", f"project {project_id!r} was not found")
            problems = self._projects.validate(project)
            if problems:
                raise VideoError("INVALID_PROJECT", "; ".join(problems))

            workspace.mkdir(parents=True, exist_ok=True)
            out_path = workspace / ("final.mp4" if mode == _MODE_FINAL else "draft.mp4")
            timeout_ms = (
                self._config.final_timeout_ms if mode == _MODE_FINAL else self._config.draft_timeout_ms
            )
            self._progress(progress, 0.0, f"rendering the {mode} video")
            render = await self._runner.render(
                out_path=out_path, draft=(mode == _MODE_DRAFT), timeout_ms=timeout_ms,
                cancel_event=cancel_event, progress=progress, progress_scale=0.9,
                cwd=workspace,
            )
            if not render["ok"]:
                result.update(
                    status=render["status"], error=render.get("error"),
                    errorClass=render.get("errorClass"),
                )
                return self._finish_report(workspace, payload, result, {"render": render})
            result.update(
                outputPath=render["outputPath"], width=render.get("width"),
                height=render.get("height"), frames=render.get("frames"),
                durationSeconds=render.get("endSeconds"),
                renderSeconds=render.get("elapsedSeconds"),
                sizeBytes=render.get("sizeBytes"),
            )
            if cancel_event is not None and cancel_event.is_set():
                result.update(status="cancelled", error="cancelled by operator",
                              errorClass="CANCELLED")
                return self._finish_report(workspace, payload, result, {"render": render})

            self._progress(progress, 0.92, "inspecting the rendered frames")
            inspection = await self._runner.inspect(
                timeout_ms=self._config.inspect_timeout_ms, cancel_event=cancel_event,
                cwd=workspace,
            )
            findings = list(inspection.get("findings") or [])
            result["inspection"] = {
                "ok": bool(inspection.get("ok")),
                "checkedFrames": inspection.get("checkedFrames"),
                "findings": findings[:20],
                "findingsTotal": len(findings),
            }
            if not inspection["ok"]:
                self._apply_inspection_failure(result, inspection, findings)
                return self._finish_report(
                    workspace, payload, result, {"render": render, "inspection": inspection}
                )

            artifact = None
            if mode == _MODE_FINAL:
                self._progress(progress, 0.97, "registering the video artifact")
                try:
                    artifact = self._register_artifact(
                        project=project, out_path=Path(render["outputPath"]), mode=mode,
                        job_id=job_id, render=render, inspection=inspection,
                        owner=payload.get("owner"),
                    )
                except VideoError as exc:
                    result.update(
                        status="failed",
                        error=f"the video rendered but could not be registered: {exc.message}",
                        errorClass="ARTIFACT_REGISTRATION_FAILED",
                    )
                    return self._finish_report(
                        workspace, payload, result,
                        {"render": render, "inspection": inspection},
                    )
            result.update(
                status="completed",
                artifact=_artifact_summary(artifact) if artifact is not None else None,
            )
            self._progress(progress, 1.0, f"{mode} render complete")
            return self._finish_report(
                workspace, payload, result, {"render": render, "inspection": inspection}
            )
        except VideoError as exc:
            result.update(status="failed", error=exc.message, errorClass=exc.code)
        except Exception as exc:  # noqa: BLE001 - a worker failure is data
            result.update(status="failed", error=str(exc)[:1500], errorClass="VIDEO_ERROR")
        return self._finish_report(workspace, payload, result, {})

    async def run_inspect_job(
        self,
        payload: dict[str, Any],
        *,
        cancel_event: Optional[asyncio.Event] = None,
        progress: Optional[Callable[..., None]] = None,
    ) -> dict[str, Any]:
        job_id = str(payload.get("jobId") or "manual")
        workspace = self._config.resolve_video_root() / "jobs" / job_id
        result: dict[str, Any] = {
            "status": "failed", "action": "inspect",
            "sourceJobId": payload.get("sourceJobId"),
        }
        try:
            output_path = str(payload.get("outputPath") or "")
            if not output_path:
                raise VideoError("INVALID_INPUT", "an inspect job needs an outputPath")
            confined = self._confined(output_path)
            self._progress(progress, 0.1, "inspecting the rendered frames")
            inspection = await self._runner.inspect(
                timeout_ms=self._config.inspect_timeout_ms, cancel_event=cancel_event,
                cwd=confined.parent,
            )
            findings = list(inspection.get("findings") or [])
            result.update(
                checkedFrames=inspection.get("checkedFrames"),
                findings=findings[:20],
                findingsTotal=len(findings),
                ok=bool(inspection.get("ok")),
            )
            if inspection["ok"]:
                result["status"] = "completed"
                self._progress(progress, 1.0, "inspection clean")
            else:
                self._apply_inspection_failure(result, inspection, findings)
            return self._finish_report(workspace, payload, result, {"inspection": inspection})
        except VideoError as exc:
            result.update(status="failed", error=exc.message, errorClass=exc.code)
        except Exception as exc:  # noqa: BLE001
            result.update(status="failed", error=str(exc)[:1500], errorClass="VIDEO_ERROR")
        return self._finish_report(workspace, payload, result, {})

    # ── internals ────────────────────────────────────────────────────────────

    def _apply_inspection_failure(
        self, result: dict[str, Any], inspection: dict[str, Any], findings: list[Any]
    ) -> None:
        status = inspection.get("status")
        if status == "timed_out":
            result.update(status="timed_out",
                          error=inspection.get("error") or "inspection timed out",
                          errorClass="TIMEOUT")
            return
        if status == "cancelled":
            result.update(status="cancelled", error="cancelled by operator",
                          errorClass="CANCELLED")
            return
        detail = ""
        if findings:
            first = findings[0]
            if isinstance(first, dict):
                detail = str(first.get("message") or first.get("detail") or first)[:300]
            else:
                detail = str(first)[:300]
        result.update(
            status="failed",
            error=(
                f"the rendered video failed inspection: {detail}"
                if detail else
                f"the rendered video failed inspection: {inspection.get('error') or 'problems reported'}"
            ),
            errorClass="INSPECTION_FAILED",
        )

    def _register_artifact(
        self, *, project: dict[str, Any], out_path: Path, mode: str, job_id: str,
        render: dict[str, Any], inspection: dict[str, Any], owner: Optional[str],
    ) -> Any:
        artifacts = self._artifact_service()
        if artifacts is None:
            raise VideoError(
                "RUNTIME_UNAVAILABLE",
                "the Artifact Center is unavailable; the final render cannot be registered",
            )
        from ..artifacts.model import ArtifactSourceType  # noqa: PLC0415

        findings = list(inspection.get("findings") or [])
        metadata = {
            "videoJobId": job_id,
            "projectId": project["id"],
            "projectKind": project["kind"],
            "mode": mode,
            "width": render.get("width"),
            "height": render.get("height"),
            "frames": render.get("frames"),
            "durationSeconds": render.get("endSeconds"),
            "elapsedSeconds": render.get("elapsedSeconds"),
            "worker": "fframes",
            "workerVersion": "1.2.0",
            "inspection": {
                "ok": bool(inspection.get("ok")),
                "checkedFrames": inspection.get("checkedFrames"),
                "findings": len(findings),
            },
        }
        return artifacts.register_path(
            out_path,
            name=f"{project['name']}.mp4",
            owner_id=owner or "local",
            description=(
                f"Rendered by the fframes video worker (project {project['id']}, {mode})."
            ),
            source_type=ArtifactSourceType.JOB,
            source_tool="video",
            idempotency_key=f"video-artifact:{job_id}",
            tags=["video", "fframes"],
            metadata=metadata,
        )

    def _latest_render_job(self, project_id: str) -> Optional[dict[str, Any]]:
        try:
            jobs = self._manager().list_jobs(type=VIDEO_JOB_TYPE, limit=200)
        except VideoError:
            return None
        candidates = [
            j for j in jobs
            if (j.get("input") or {}).get("projectId") == project_id
            and (j.get("input") or {}).get("action") == "render"
            and j.get("status") == "SUCCEEDED"
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda j: j.get("createdAt") or 0)
        return candidates[-1]

    def _confined(self, path_str: str) -> Path:
        root = self._config.resolve_video_root().resolve()
        try:
            path = Path(path_str).resolve()
        except Exception as exc:  # noqa: BLE001
            raise VideoError("INVALID_INPUT", f"unresolvable path {path_str!r}") from exc
        if not (path == root or root in path.parents):
            raise VideoError(
                "INVALID_INPUT", "refusing to touch a file outside the video workspace"
            )
        if not path.is_file():
            raise VideoError("NOT_FOUND", f"no rendered file at {path}")
        return path

    def _finish_report(
        self, workspace: Path, payload: dict[str, Any], result: dict[str, Any],
        details: dict[str, Any],
    ) -> dict[str, Any]:
        report_path = workspace / "report.json"
        result["reportPath"] = str(report_path)
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            report = {
                "request": dict(payload),
                "result": dict(result),
                "details": details,
                "writtenAt": now_iso(),
            }
            tmp = report_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, report_path)
        except Exception:  # noqa: BLE001 - a report is an audit aid, never a failure source
            pass
        return result

    @staticmethod
    def _progress(callback: Optional[Callable[..., None]], fraction: float,
                  message: Optional[str] = None) -> None:
        if callback is None:
            return
        try:
            callback(fraction, message)
        except Exception:  # noqa: BLE001
            pass


def _artifact_summary(artifact: Any) -> dict[str, Any]:
    category = getattr(artifact, "category", None)
    return {
        "id": getattr(artifact, "id", None),
        "name": getattr(artifact, "name", None),
        "mimeType": getattr(artifact, "mime_type", None),
        "sizeBytes": getattr(artifact, "size_bytes", None),
        "category": getattr(category, "value", category),
        "checksum": getattr(artifact, "checksum", None),
    }


_default_service: Optional[VideoService] = None


def set_video_service(service: Optional[VideoService]) -> None:
    global _default_service
    _default_service = service


def get_video_service() -> Optional[VideoService]:
    return _default_service


__all__ = ["VideoService", "get_video_service", "set_video_service"]
