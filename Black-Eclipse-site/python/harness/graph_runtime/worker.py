"""Fabric worker for Graph Studio runs.

The visual workflow runtime is synchronous (it runs a deterministic layer
scheduler) while the Execution Fabric is async. This worker is the ONE bridge:
it runs `GraphService.execute_job` in the loop's thread pool, forwards
cancellation into a `threading.Event`, and lets the Fabric own the durable job
(lease, retry, dead-letter, restart recovery).

A graph run's own record is authoritative. A graph that fails a node is a
SUCCEEDED Fabric job whose run row is FAILED — the Fabric must not retry a
deterministic graph failure. A crashed worker is a different case: the durable
job is requeued and `execute_job` resumes from node checkpoints.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from ..fabric.models import QueueName, WorkerKind, WorkerOutcome
from ..fabric.workers import BaseWorker, WorkerContext
from .model import RunStatus


class GraphWorker(BaseWorker):
    kind = WorkerKind.GRAPH.value
    queues = (QueueName.GRAPH.value,)
    concurrency = 2
    timeout_ms = 3_600_000

    def __init__(self, service: Any) -> None:
        super().__init__(service, concurrency=2)

    async def handle(self, ctx: WorkerContext) -> WorkerOutcome:
        graph_service = getattr(self.service, "graphs", None)
        if graph_service is None:
            return WorkerOutcome(
                status="failed", error="the graph runtime is unavailable",
                error_class="RUNTIME_UNAVAILABLE",
            )
        payload = dict(ctx.job.input or {})
        run_id = str(payload.get("runId") or "")
        cancel = threading.Event()
        done = asyncio.Event()

        async def watch() -> None:
            while not done.is_set():
                if ctx.cancelled:
                    cancel.set()
                    return
                await asyncio.sleep(0.2)

        watcher = asyncio.create_task(watch())
        loop = asyncio.get_running_loop()
        try:
            run = await loop.run_in_executor(
                None,
                lambda: graph_service.execute_job(
                    payload, cancel_event=cancel, job_id=ctx.job.id,
                ),
            )
        except asyncio.CancelledError:
            # The executor checks the event between nodes and persists a
            # cancelled run; the abandoned worker thread finishes on its own.
            cancel.set()
            return WorkerOutcome(status="cancelled", error="graph run cancelled", error_class="CANCELLED")
        except Exception as exc:  # noqa: BLE001 - a run failure is data, not a crash
            ctx.log("graph.run.failed", {"runId": run_id, "error": str(exc)[:1000]})
            return WorkerOutcome(
                status="failed", error=str(exc)[:2000],
                error_class="GRAPH_ERROR", retryable=False,
            )
        finally:
            done.set()
            watcher.cancel()

        if run is None:
            return WorkerOutcome(
                status="succeeded",
                output={"runId": run_id, "status": "already-terminal"},
            )
        ctx.log("graph.run.finished", {"runId": run.id, "status": run.status.value})
        return WorkerOutcome(
            status="succeeded",
            output={
                "runId": run.id,
                "status": run.status.value,
                "graphFailed": run.status != RunStatus.SUCCEEDED,
            },
        )


__all__ = ["GraphWorker"]
