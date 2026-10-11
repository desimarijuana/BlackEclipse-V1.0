"""Execution Fabric integration for the ML Research Lab.

Training is long, CPU-bound and must never block the interactive runtime. This
module registers a dedicated ML worker on its own queue so a job gets real
isolation: a timeout, a resource-bounded concurrency slot, hard cancellation and
progress events — while still invoking the SAME deterministic pipeline the HTTP
surface and agent tools use (`service.run_experiment_job`).

The worker deliberately does NOT re-implement training; it is a thin adapter over
the service layer.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import MLConfig, get_ml_config

log = logging.getLogger("harness.ml.fabric")

ML_JOB_TYPE = "ml"
ML_QUEUE = "ml"
ML_WORKER_KIND = "ml"


def _worker_outcome(ctx: Any, status: str, output: Any = None, error: Optional[str] = None,
                    error_class: Optional[str] = None) -> Any:
    from ..fabric.models import WorkerOutcome  # noqa: PLC0415

    return WorkerOutcome(status=status, output=output, error=error, error_class=error_class)


async def _ml_handler(ctx: Any) -> Any:
    """Fabric handler: run one training experiment with the job's cancel event."""
    from . import service as S  # noqa: PLC0415

    payload = dict(ctx.job.input or {})
    ctx.report_progress(0.0, "starting training")
    outcome = await S.run_experiment_job(
        payload, owner=payload.get("owner"),
        cancel_event=ctx.cancel_event, progress=ctx.report_progress,
    )
    status = outcome.get("status")
    if status == "cancelled":
        return _worker_outcome(ctx, "cancelled", error="cancelled by operator",
                               error_class="CANCELLED")
    if status == "timed_out":
        return _worker_outcome(ctx, "timed_out", error=outcome.get("error"),
                               error_class="TIME_BUDGET_EXCEEDED")
    if status != "completed":
        return _worker_outcome(ctx, "failed", error=outcome.get("error") or "training failed",
                               error_class=outcome.get("errorCode") or "ML_ERROR")
    # Return a COMPACT summary as the job output; the full run result is already
    # persisted as a hash-addressed ML artifact (the Fabric output column is
    # bounded, so large payloads must never go there).
    result = outcome.get("result") or {}
    summary = {
        "status": "completed",
        "experimentId": outcome.get("experimentId"),
        "runId": outcome.get("runId"),
        "artifactId": outcome.get("artifactId"),
        "pooledMetrics": result.get("pooledMetrics"),
        "finalEvaluation": result.get("finalEvaluation"),
        "registered": outcome.get("registered"),
    }
    return _worker_outcome(ctx, "succeeded", output=summary)


def build_ml_worker(service: Any, config: Optional[MLConfig] = None) -> Optional[Any]:
    """Construct the ML worker (or None when the engine is disabled)."""
    cfg = config or get_ml_config()
    if not cfg.enabled:
        return None
    from ..fabric.workers import FunctionWorker  # noqa: PLC0415

    worker = FunctionWorker(
        ML_WORKER_KIND, [ML_QUEUE], _ml_handler, service=service,
        concurrency=max(1, cfg.max_concurrent), timeout_ms=cfg.worker_timeout_ms,
        name="ml",
    )
    return worker


# ── submission / status helpers (used by service + tools) ────────────────────


def _manager() -> Any:
    from ..fabric.tools import get_fabric_manager  # noqa: PLC0415

    manager = get_fabric_manager()
    if manager is None:
        raise RuntimeError("the Execution Fabric is unavailable; ML training runs inline")
    return manager


async def submit_ml_experiment(payload: dict[str, Any], *, owner: Optional[str] = None,
                               mode: str = "BACKGROUND", timeout_ms: Optional[int] = None) -> dict[str, Any]:
    """Enqueue a training experiment on the ML worker and return its job handle.

    Idempotent per payload: re-submitting an identical experiment while one is
    live coalesces onto the existing job.
    """
    manager = _manager()
    cfg = get_ml_config()
    job_payload = dict(payload)
    if owner:
        job_payload["owner"] = owner
    return await manager.submit(
        ML_JOB_TYPE, job_payload, mode=mode,
        timeout_ms=timeout_ms or cfg.worker_timeout_ms,
        metadata={"source": "ml", "kind": "experiment"},
    )


def _job_to_dict(job: Any) -> dict[str, Any]:
    if job is None:
        return {}
    if isinstance(job, dict):
        return job
    if hasattr(job, "to_dict"):
        return job.to_dict()
    return {k: getattr(job, k, None) for k in (
        "id", "type", "queue", "status", "progress", "attempts", "output", "error",
        "error_class", "created_at", "completed_at")}


def get_ml_job(job_id: str) -> Optional[dict[str, Any]]:
    manager = _manager()
    job = manager.get(job_id)
    if job is None:
        return None
    data = _job_to_dict(job)
    if "jobId" not in data and "id" in data:
        data["jobId"] = data["id"]
    return data


def list_ml_jobs(limit: int = 50) -> list[dict[str, Any]]:
    manager = _manager()
    jobs = manager.list_jobs(type=ML_JOB_TYPE, limit=int(limit))
    out = []
    for job in jobs or []:
        data = _job_to_dict(job)
        if "jobId" not in data and "id" in data:
            data["jobId"] = data["id"]
        out.append(data)
    return out


async def cancel_ml_job(job_id: str) -> dict[str, Any]:
    manager = _manager()
    return await manager.cancel(job_id)


__all__ = [
    "build_ml_worker",
    "submit_ml_experiment",
    "get_ml_job",
    "list_ml_jobs",
    "cancel_ml_job",
    "ML_JOB_TYPE",
]
