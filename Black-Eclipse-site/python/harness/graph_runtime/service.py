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

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import now_iso
from .compiler import RunGrants, compile_workflow
from .executor import GraphExecutor
from .model import ExecutionPlan, GraphRun, NodeStatus, RunEvent, RunStatus, Severity, WorkflowIR
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

    # ── compile ────────────────────────────────────────────────────────────

    def compile(self, ir: WorkflowIR, grants: Optional[RunGrants] = None) -> ExecutionPlan:
        return compile_workflow(ir, self._registry, grants)

    # ── run ────────────────────────────────────────────────────────────────

    def run_sync(
        self,
        ir: WorkflowIR,
        *,
        workflow_version: Optional[int] = None,
        owner_id: str = "local",
        grants: Optional[RunGrants] = None,
    ) -> GraphRun:
        """Compile + execute + persist on the CALLING thread. Deterministic."""
        grants = grants or RunGrants()
        plan = self.compile(ir, grants)
        if not plan.executable:
            raise GraphCompileError(plan)
        run_id = GraphRunStore.new_run_id()
        executor = GraphExecutor(
            ir, plan, self._registry,
            run_id=run_id, grants=grants, owner_id=owner_id,
            workflow_version=workflow_version,
        )
        run = executor.execute()
        self._store.create_run(run)
        self._store.finish_run(run)
        return run

    def start_run(
        self,
        ir: WorkflowIR,
        *,
        workflow_version: Optional[int] = None,
        owner_id: str = "local",
        grants: Optional[RunGrants] = None,
    ) -> dict[str, Any]:
        """Compile, persist a `running` row and execute on a background thread."""
        grants = grants or RunGrants()
        plan = self.compile(ir, grants)
        if not plan.executable:
            raise GraphCompileError(plan)

        run_id = GraphRunStore.new_run_id()
        cancel = threading.Event()
        live = _LiveRun(run_id=run_id, cancel=cancel, thread=None)  # type: ignore[arg-type]
        for plan_node in plan.nodes:
            live.node_status[plan_node.node_id] = NodeStatus.PENDING.value

        starting = GraphRun(
            id=run_id,
            workflowId=ir.id,
            workflowVersion=workflow_version,
            irVersion=plan.ir_version,
            mode=plan.mode,
            testRun=grants.test_run,
            status=RunStatus.RUNNING,
            startedAt=now_iso(),
            ownerId=owner_id,
            plan=plan,
        )
        self._store.create_run(starting)
        with self._lock:
            self._live[run_id] = live

        def on_event(event: RunEvent) -> None:
            if event.node_id:
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

        def worker() -> None:
            try:
                executor = GraphExecutor(
                    ir, plan, self._registry,
                    run_id=run_id, grants=grants, cancel_event=cancel,
                    on_event=on_event, owner_id=owner_id,
                    workflow_version=workflow_version,
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

    def cancel(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            live = self._live.get(run_id)
        if live is not None:
            live.cancel.set()
        return self.get_run(run_id)


__all__ = ["GraphService", "GraphCompileError"]
