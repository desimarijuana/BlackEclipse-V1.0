"""Graph runtime service — compile, run, inspect, cancel.

The ONE entry point the API (and later the agent tools) use. It owns the node
registry, the run store and the in-flight run registry; the executor stays a
pure, per-run object.

Runs are started on a background thread so the HTTP call returns immediately
with a run id the UI can poll — and so a cancel is meaningful. Intermediate
progress is kept in memory (event-derived node statuses) and merged into the
persisted record on read; the finished run is written once.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import now_iso
from .compiler import RunGrants, compile_workflow
from .executor import GraphExecutor, ResumeState
from .model import (
    ExecutionPlan,
    GraphRun,
    NodeRun,
    NodeStatus,
    RunEvent,
    RunStatus,
    Severity,
    WorkflowIR,
)
from .nodes import build_default_registry
from .registry import NodeRegistry
from .store import GraphRunStore

log = logging.getLogger("harness.graph_runtime.service")


class GraphCompileError(Exception):
    """A graph could not be compiled. Carries the full plan (with diagnostics)."""

    def __init__(self, plan: ExecutionPlan) -> None:
        errors = [d for d in plan.diagnostics if d.severity == Severity.ERROR]
        first = errors[0].message if errors else "the graph could not be compiled"
        super().__init__(first)
        self.plan = plan
        self.errors = errors


@dataclass
class _LiveRun:
    run_id: str
    cancel: threading.Event
    thread: threading.Thread
    node_status: dict[str, str] = field(default_factory=dict)


class GraphService:
    def __init__(self, store: GraphRunStore, registry: Optional[NodeRegistry] = None) -> None:
        self._store = store
        self._registry = registry or build_default_registry()
        self._live: dict[str, _LiveRun] = {}
        self._lock = threading.Lock()
        self._fabric: Any = None

    def set_fabric(self, fabric: Any) -> None:
        """Bind the Execution Fabric; runs then dispatch as durable jobs."""
        self._fabric = fabric

    # ── compile ────────────────────────────────────────────────────────────

    def compile(
        self,
        ir: WorkflowIR,
        grants: Optional[RunGrants] = None,
        subworkflows: Optional[dict[str, WorkflowIR]] = None,
    ) -> ExecutionPlan:
        return compile_workflow(ir, self._registry, grants, subworkflows)

    # ── run ────────────────────────────────────────────────────────────────

    def _event_callback(self, run_id: str, live: Optional[_LiveRun] = None):
        def on_event(event: RunEvent) -> None:
            try:
                self._store.save_event(run_id, event)
            except Exception:  # noqa: BLE001 - observability must never break a run
                log.debug("graph event persist failed", exc_info=True)
            if live is not None and event.node_id:
                mapping = {
                    "node.started": NodeStatus.RUNNING.value,
                    "node.succeeded": NodeStatus.SUCCEEDED.value,
                    "node.failed": NodeStatus.FAILED.value,
                    "node.cancelled": NodeStatus.CANCELLED.value,
                    "node.skipped": NodeStatus.SKIPPED.value,
                    "node.retry": NodeStatus.RUNNING.value,
                }
                status = mapping.get(event.kind)
                if status:
                    live.node_status[event.node_id] = status
        return on_event

    def _node_callback(self, run_id: str):
        def on_node(
            record: NodeRun,
            outputs: dict[str, Any],
            fired: list[str],
            terminal_done: bool,
            terminal_value: Any,
        ) -> None:
            try:
                self._store.save_node_run(
                    run_id, record, outputs=outputs, fired=fired,
                    terminal_done=terminal_done, terminal_value=terminal_value,
                )
            except Exception:  # noqa: BLE001 - a checkpoint must never break a run
                log.debug("graph node checkpoint failed", exc_info=True)
        return on_node

    @staticmethod
    def _grants_payload(grants: RunGrants) -> dict[str, Any]:
        return {
            "testRun": grants.test_run,
            "grantedCapabilities": sorted(grants.granted_capabilities),
            "allowNetwork": grants.allow_network,
            "allowTrading": grants.allow_trading,
        }

    @staticmethod
    def _grants_from_payload(payload: dict[str, Any]) -> RunGrants:
        return RunGrants(
            test_run=bool(payload.get("testRun", True)),
            granted_capabilities=frozenset(payload.get("grantedCapabilities") or ()),
            allow_network=bool(payload.get("allowNetwork", False)),
            allow_trading=bool(payload.get("allowTrading", False)),
        )

    def _job_payload(
        self,
        ir: WorkflowIR,
        *,
        run_id: str,
        workflow_version: Optional[int],
        owner_id: str,
        grants: RunGrants,
        subworkflows: Optional[dict[str, WorkflowIR]],
        run_input: Any,
    ) -> dict[str, Any]:
        return {
            "ir": ir.model_dump(by_alias=True),
            "subworkflows": {
                key: value.model_dump(by_alias=True)
                for key, value in (subworkflows or {}).items()
            },
            "runId": run_id,
            "workflowVersion": workflow_version,
            "ownerId": owner_id,
            "runInput": run_input,
            "grants": self._grants_payload(grants),
        }

    def run_sync(
        self,
        ir: WorkflowIR,
        *,
        workflow_version: Optional[int] = None,
        owner_id: str = "local",
        grants: Optional[RunGrants] = None,
        subworkflows: Optional[dict[str, WorkflowIR]] = None,
        run_input: Any = None,
    ) -> GraphRun:
        """Compile + execute + persist on the CALLING thread. Deterministic."""
        grants = grants or RunGrants()
        plan = self.compile(ir, grants, subworkflows)
        if not plan.executable:
            raise GraphCompileError(plan)
        run_id = GraphRunStore.new_run_id()
        starting = GraphRun(
            id=run_id, workflowId=ir.id, workflowVersion=workflow_version,
            irVersion=plan.ir_version, mode=plan.mode, testRun=grants.test_run,
            status=RunStatus.RUNNING, startedAt=now_iso(), ownerId=owner_id, plan=plan,
        )
        self._store.create_run(starting)
        executor = GraphExecutor(
            ir, plan, self._registry,
            run_id=run_id, grants=grants, owner_id=owner_id,
            workflow_version=workflow_version,
            subworkflows=subworkflows, run_input=run_input,
            on_event=self._event_callback(run_id),
            on_node_finished=self._node_callback(run_id),
        )
        try:
            run = executor.execute()
        except Exception as exc:  # noqa: BLE001 - persist a failed run, then re-raise
            failed = starting.model_copy(update={
                "status": RunStatus.FAILED,
                "finished_at": now_iso(),
                "error": f"{type(exc).__name__}: {exc}",
            })
            self._store.finish_run(failed)
            raise
        self._store.finish_run(run)
        return run

    def start_run(
        self,
        ir: WorkflowIR,
        *,
        workflow_version: Optional[int] = None,
        owner_id: str = "local",
        grants: Optional[RunGrants] = None,
        subworkflows: Optional[dict[str, WorkflowIR]] = None,
        run_input: Any = None,
    ) -> dict[str, Any]:
        """Compile, persist a QUEUED row and dispatch.

        With the Execution Fabric available the run is submitted as a DURABLE
        graph job (restart-surviving, resumable). Without it, the legacy
        in-process thread is used and the run is still fully persisted.
        """
        grants = grants or RunGrants()
        plan = self.compile(ir, grants, subworkflows)
        if not plan.executable:
            raise GraphCompileError(plan)

        run_id = GraphRunStore.new_run_id()
        starting = GraphRun(
            id=run_id,
            workflowId=ir.id,
            workflowVersion=workflow_version,
            irVersion=plan.ir_version,
            mode=plan.mode,
            testRun=grants.test_run,
            status=RunStatus.QUEUED,
            startedAt=now_iso(),
            ownerId=owner_id,
            plan=plan,
        )
        self._store.create_run(starting)

        if self._fabric is not None:
            payload = self._job_payload(
                ir, run_id=run_id, workflow_version=workflow_version,
                owner_id=owner_id, grants=grants,
                subworkflows=subworkflows, run_input=run_input,
            )
            timeout_ms = max(60_000, min(3_600_000, ir.settings.timeout_ms or 3_600_000))
            try:
                result = asyncio.run(self._fabric.submit(
                    "graph", payload,
                    mode="DURABLE", queue="graph", worker_kind="graph",
                    timeout_ms=timeout_ms, max_attempts=2, user_id=owner_id,
                    correlation_id=run_id,
                ))
                job_id = result.get("jobId") if isinstance(result, dict) else None
                if job_id:
                    self._store.set_job_id(run_id, job_id)
                return self.get_run(run_id) or starting.model_dump(by_alias=True)
            except RuntimeError:
                # Called from inside a running event loop: fall through to the
                # in-process path rather than blocking that loop.
                log.warning("fabric submit unavailable in this context; using in-process graph run")
            except Exception:  # noqa: BLE001 - the graph must still run
                log.warning("fabric graph submit failed; using in-process run", exc_info=True)

        cancel = threading.Event()
        live = _LiveRun(run_id=run_id, cancel=cancel, thread=None)  # type: ignore[arg-type]
        for plan_node in plan.nodes:
            live.node_status[plan_node.node_id] = NodeStatus.PENDING.value
        self._store.mark_running(run_id)
        with self._lock:
            self._live[run_id] = live

        def worker() -> None:
            try:
                executor = GraphExecutor(
                    ir, plan, self._registry,
                    run_id=run_id, grants=grants, cancel_event=cancel,
                    on_event=self._event_callback(run_id, live),
                    on_node_finished=self._node_callback(run_id),
                    owner_id=owner_id,
                    workflow_version=workflow_version,
                    subworkflows=subworkflows, run_input=run_input,
                )
                run = executor.execute()
                self._store.finish_run(run)
            except Exception as exc:  # noqa: BLE001 - never lose a run record
                log.warning("graph run %s crashed", run_id, exc_info=True)
                failed = starting.model_copy(update={
                    "status": RunStatus.FAILED,
                    "finished_at": now_iso(),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                self._store.finish_run(failed)
            finally:
                with self._lock:
                    self._live.pop(run_id, None)

        thread = threading.Thread(target=worker, name=f"graph-run-{run_id}", daemon=True)
        live.thread = thread
        thread.start()
        return self.get_run(run_id) or starting.model_dump(by_alias=True)

    def execute_job(
        self,
        payload: dict[str, Any],
        *,
        cancel_event: threading.Event,
        job_id: Optional[str] = None,
    ) -> Optional[GraphRun]:
        """Execute one Fabric graph job (called by the GraphWorker).

        The job payload is the durable source of truth. Node checkpoints let a
        requeued job resume instead of re-running completed work.
        """
        ir = WorkflowIR.model_validate(payload.get("ir"))
        subworkflows = {
            key: WorkflowIR.model_validate(value)
            for key, value in (payload.get("subworkflows") or {}).items()
        }
        grants = self._grants_from_payload(payload.get("grants") or {})
        run_id = str(payload.get("runId") or GraphRunStore.new_run_id())
        existing = self._store.get_run(run_id)
        if existing is not None and existing.get("status") in (
            RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value,
        ):
            return None

        plan = self.compile(ir, grants, subworkflows)
        if not plan.executable:
            error = next((d.message for d in plan.diagnostics if d.severity == Severity.ERROR), "invalid graph")
            failed = GraphRun(
                id=run_id, workflowId=ir.id,
                workflowVersion=payload.get("workflowVersion"),
                irVersion=plan.ir_version, mode=plan.mode, testRun=grants.test_run,
                status=RunStatus.FAILED, startedAt=now_iso(), finishedAt=now_iso(),
                error=error, ownerId=str(payload.get("ownerId") or "local"), plan=plan,
            )
            if existing is None:
                self._store.create_run(failed)
            self._store.finish_run(failed)
            raise GraphCompileError(plan)

        if existing is None:
            # A durable job can outlive a deleted/never-created run row; rebuild
            # the minimum record needed to persist the result.
            starting = GraphRun(
                id=run_id, workflowId=ir.id,
                workflowVersion=payload.get("workflowVersion"),
                irVersion=plan.ir_version, mode=plan.mode, testRun=grants.test_run,
                status=RunStatus.RUNNING, startedAt=now_iso(),
                ownerId=str(payload.get("ownerId") or "local"), plan=plan,
            )
            self._store.create_run(starting)
        if job_id:
            self._store.set_job_id(run_id, job_id)

        resume_data = self._store.load_resume(run_id)
        resume = None
        if resume_data.get("nodes"):
            if resume_data.get("complete"):
                resume = ResumeState(
                    nodes=resume_data["nodes"],
                    outputs=resume_data["outputs"],
                    fired=resume_data["fired"],
                    terminal=resume_data["terminal"],
                )
            else:
                log.warning("graph run %s has a non-resumable checkpoint; starting fresh", run_id)

        self._store.mark_running(run_id)
        executor = GraphExecutor(
            ir, plan, self._registry,
            run_id=run_id, grants=grants, cancel_event=cancel_event,
            on_event=self._event_callback(run_id),
            on_node_finished=self._node_callback(run_id),
            owner_id=str(payload.get("ownerId") or "local"),
            workflow_version=payload.get("workflowVersion"),
            subworkflows=subworkflows,
            run_input=payload.get("runInput"),
            resume=resume,
        )
        try:
            run = executor.execute()
        except Exception as exc:  # noqa: BLE001 - persist, then let the worker classify
            failed = GraphRun(
                id=run_id, workflowId=ir.id,
                workflowVersion=payload.get("workflowVersion"),
                irVersion=plan.ir_version, mode=plan.mode, testRun=grants.test_run,
                status=RunStatus.FAILED, startedAt=now_iso(), finishedAt=now_iso(),
                error=f"{type(exc).__name__}: {exc}",
                ownerId=str(payload.get("ownerId") or "local"), plan=plan,
            )
            self._store.finish_run(failed)
            raise
        self._store.finish_run(run)
        return run

    # ── inspection ─────────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        record = self._store.get_run(run_id)
        if record is None:
            return None
        with self._lock:
            live = self._live.get(run_id)
        if live is not None and record.get("status") == RunStatus.RUNNING.value:
            record["nodeStatus"] = dict(live.node_status)
        return record

    def list_runs(self, workflow_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._store.list_runs(workflow_id, limit)

    def events_since(self, run_id: str, after_id: int = 0, limit: int = 1_000) -> list[dict[str, Any]]:
        return self._store.events_since(run_id, after_id, limit)

    def cancel(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            live = self._live.get(run_id)
        if live is not None:
            live.cancel.set()

        record = self.get_run(run_id)
        if record is None:
            return None
        job_id = record.get("jobId")
        if job_id and self._fabric is not None:
            try:
                asyncio.run(self._fabric.cancel(job_id))
            except RuntimeError:
                log.warning("fabric cancel unavailable in this context; relying on the live cancel event")
            except Exception:  # noqa: BLE001 - cancellation must still return the run
                log.warning("fabric graph cancel failed", exc_info=True)
        # A queued job may never start; mark the run cancelled now. A running
        # worker will overwrite this with its own terminal status.
        if record.get("status") in (RunStatus.QUEUED.value, RunStatus.RUNNING.value):
            self._store.mark_cancelled(run_id)
        return self.get_run(run_id)


__all__ = ["GraphService", "GraphCompileError"]
