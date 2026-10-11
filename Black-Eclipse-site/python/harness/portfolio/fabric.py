"""Execution Fabric integration for long portfolio simulations.

Walk-forward rebalancing simulations re-estimate a covariance matrix at every
decision date and can run for many assets/years; they must not block the
interactive runtime. This registers a dedicated `portfolio` worker on its own
queue (timeout, bounded concurrency, cancellation, progress) that invokes the
SAME deterministic `rebalancing_simulation` the HTTP surface and agent tools use.
It never re-implements the simulation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("harness.portfolio.fabric")

PORTFOLIO_JOB_TYPE = "portfolio_simulation"
PORTFOLIO_QUEUE = "portfolio"
PORTFOLIO_WORKER_KIND = "portfolio"
DEFAULT_TIMEOUT_MS = 300_000


def _outcome(status: str, output: Any = None, error: Optional[str] = None,
             error_class: Optional[str] = None) -> Any:
    from ..fabric.models import WorkerOutcome  # noqa: PLC0415

    return WorkerOutcome(status=status, output=output, error=error, error_class=error_class)


async def _handler(ctx: Any) -> Any:
    from .simulation import rebalancing_simulation  # noqa: PLC0415

    payload = dict(ctx.job.input or {})
    ctx.report_progress(0.0, "starting simulation")
    result = rebalancing_simulation(
        payload.get("price_series") or {},
        schedule=payload.get("schedule") or "quarterly",
        method=payload.get("method") or "risk_parity",
        constraints_payload=payload.get("constraints") or {},
        lookback=int(payload.get("lookback") or 252),
        initial_capital=float(payload.get("initial_capital") or 1.0),
        cost_rate=float(payload.get("cost_rate") or 0.0),
        cancel_event=getattr(ctx, "cancel_event", None),
        progress=getattr(ctx, "report_progress", None),
        time_budget_s=(DEFAULT_TIMEOUT_MS / 1000.0),
    )
    status = result.get("status")
    if status == "cancelled":
        return _outcome("cancelled", error="cancelled by operator", error_class="CANCELLED")
    if status == "timed_out":
        return _outcome("timed_out", error=result.get("reason"), error_class="TIME_BUDGET_EXCEEDED")
    if not result.get("available"):
        return _outcome("failed", error=result.get("reason") or "simulation failed",
                        error_class="PORTFOLIO_SIMULATION_ERROR")
    return _outcome("succeeded", output=result)


def build_portfolio_worker(service: Any) -> Any:
    from ..fabric.workers import FunctionWorker  # noqa: PLC0415

    return FunctionWorker(
        PORTFOLIO_WORKER_KIND, [PORTFOLIO_QUEUE], _handler, service=service,
        concurrency=1, timeout_ms=DEFAULT_TIMEOUT_MS, name="portfolio",
    )


def _manager() -> Any:
    from ..fabric.tools import get_fabric_manager  # noqa: PLC0415

    manager = get_fabric_manager()
    if manager is None:
        raise RuntimeError("the Execution Fabric is unavailable; run the simulation inline")
    return manager


async def submit_simulation(payload: dict[str, Any], *, mode: str = "BACKGROUND",
                            timeout_ms: Optional[int] = None) -> dict[str, Any]:
    manager = _manager()
    return await manager.submit(
        PORTFOLIO_JOB_TYPE, dict(payload), mode=mode,
        timeout_ms=timeout_ms or DEFAULT_TIMEOUT_MS,
        metadata={"source": "portfolio", "kind": "simulation"},
    )


def get_simulation_job(job_id: str) -> Optional[dict[str, Any]]:
    manager = _manager()
    job = manager.get(job_id)
    if job is None:
        return None
    if isinstance(job, dict):
        data = dict(job)
    elif hasattr(job, "to_dict"):
        data = job.to_dict()
    else:
        data = {k: getattr(job, k, None) for k in (
            "id", "type", "queue", "status", "progress", "attempts", "output",
            "error", "error_class", "created_at", "completed_at")}
    if "jobId" not in data and "id" in data:
        data["jobId"] = data["id"]
    return data


async def cancel_simulation(job_id: str) -> dict[str, Any]:
    return await _manager().cancel(job_id)


__all__ = [
    "build_portfolio_worker", "submit_simulation", "get_simulation_job",
    "cancel_simulation", "PORTFOLIO_JOB_TYPE",
]
