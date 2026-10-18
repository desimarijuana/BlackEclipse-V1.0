"""Execution Fabric integration for the video pipeline.

Rendering is long, CPU-bound and must never block the interactive runtime.
This module registers a dedicated video worker on its own queue so a job gets
real isolation: a timeout, a bounded concurrency slot, hard cancellation,
progress events and restart recovery — while the actual work stays in the
EXISTING layers: the `VideoService` (projects, workspaces, artifact
registration) and the `VideoRunner` (the isolated Rust process).

The worker is a thin adapter: it never re-implements rendering, and it never
runs inline. `title_card`/storyboard expansion also stays upstream — the
handler just executes the requested action against the payload.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..fabric.models import WorkerOutcome
from .config import VideoConfig, get_video_config
from .models import VIDEO_QUEUE, VIDEO_WORKER_KIND

log = logging.getLogger("harness.video.fabric")


async def _video_handler(ctx: Any) -> WorkerOutcome:
    from .service import get_video_service  # noqa: PLC0415

    service = get_video_service()
    if service is None:
        return WorkerOutcome(
            status="failed", error="the video pipeline is not installed",
            error_class="RUNTIME_UNAVAILABLE",
        )
    payload = dict(ctx.job.input or {})
    payload["jobId"] = ctx.job.id
    action = str(payload.get("action") or "render").strip().lower()
    if action == "render":
        result = await service.run_render_job(
            payload, cancel_event=ctx.cancel_event, progress=ctx.report_progress
        )
    elif action == "inspect":
        result = await service.run_inspect_job(
            payload, cancel_event=ctx.cancel_event, progress=ctx.report_progress
        )
    else:
        return WorkerOutcome(
            status="failed", error=f"unknown video action {action!r}",
            error_class="INVALID_INPUT",
        )
    status = str(result.get("status") or "failed")
    if status == "completed":
        return WorkerOutcome(
            status="succeeded", output=result,
            metrics={"action": action, "mode": result.get("mode")},
        )
    if status == "cancelled":
        return WorkerOutcome(
            status="cancelled", error=result.get("error") or "cancelled by operator",
            error_class="CANCELLED",
        )
    if status == "timed_out":
        return WorkerOutcome(
            status="timed_out", error=result.get("error") or "the video job timed out",
            error_class="TIMEOUT",
        )
    return WorkerOutcome(
        status="failed", error=result.get("error") or "the video job failed",
        error_class=result.get("errorClass") or "VIDEO_ERROR",
    )


def build_video_worker(service: Any = None, config: Optional[VideoConfig] = None) -> Optional[Any]:
    """Construct the video worker (or None when the pipeline is disabled)."""
    cfg = config or get_video_config()
    if not cfg.enabled:
        return None
    from ..fabric.workers import FunctionWorker  # noqa: PLC0415

    return FunctionWorker(
        VIDEO_WORKER_KIND, [VIDEO_QUEUE], _video_handler, service=service,
        concurrency=max(1, cfg.max_concurrent), timeout_ms=cfg.worker_timeout_ms,
        name="video",
    )


__all__ = ["build_video_worker"]
