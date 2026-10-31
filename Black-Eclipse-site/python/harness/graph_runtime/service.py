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
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import now_iso
from .compiler import RunGrants, compile_workflow
from .executor import GraphExecutor, ResumeState
from .model import (
    ExecutionMode,
    ExecutionPlan,
    GraphRun,
    NodeRun,
    NodeStatus,
    RunDeferred,
    RunEvent,
    RunStatus,
    Severity,
    SideEffect,
    WorkflowIR,
)
from .nodes import build_default_registry
from .registry import (
    NodeExecContext,
    NodeRegistry,
    coerce_config,
    validate_config,
    validate_port_value,
)
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


class NodeTestError(Exception):
    """A single-node test was refused or failed before it could run."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


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
        # Front-door-resolved credentials live in memory only. They are never
        # included in `_job_payload` (which Fabric persists on disk).
        self._model_settings: dict[str, dict[str, Any]] = {}

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

    # ── single-node test ───────────────────────────────────────────────────

    def test_node(
        self,
        *,
        node_type: str,
        version: Optional[str],
        config: Any,
        inputs: Any,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
        owner_id: str = "local",
    ) -> dict[str, Any]:
        """Run ONE registered node with explicit inputs — never a graph.

        This is the editor's "Test node" action. It is intentionally narrow:
        the executor is pure, the hard per-node timeout is enforced, and the
        safe envelope allows only `none`/`read` side effects. Network, write,
        trading, model and local-write nodes are refused here; they must be
        tested through an authorized run so a "test" can never act on the world.
        """
        definition = self._registry.get(node_type, version)
        if definition is None:
            raise NodeTestError(f'Unknown node type "{node_type}".', 404)
        if definition.orchestrated:
            raise NodeTestError(
                "This node runs as a nested graph (subworkflow/loop); test it with a full run.",
                400,
            )
        if definition.executor is None:
            raise NodeTestError("This node has no executor.", 400)
        if not isinstance(config, dict):
            raise NodeTestError("config must be an object.", 400)
        if not isinstance(inputs, dict):
            raise NodeTestError("inputs must be an object keyed by input port id.", 400)

        problems = validate_config(definition, config)
        if problems:
            raise NodeTestError("; ".join(problems), 400)

        if definition.side_effects not in (SideEffect.NONE, SideEffect.READ):
            raise NodeTestError(
                f'"{definition.type}" has the "{definition.side_effects.value}" side effect. '
                "A per-node test runs in a safe envelope; use an authorized run to test it.",
                403,
            )

        for port in definition.inputs:
            if not port.optional and port.id not in inputs:
                raise NodeTestError(f'Missing required input "{port.id}".', 400)
            if port.id in inputs:
                problem = validate_port_value(port.type, inputs[port.id])
                if problem:
                    raise NodeTestError(f'input "{port.id}": {problem}', 400)

        logs: list[str] = []
        context = NodeExecContext(
            node_id="node-test",
            run_id="node-test",
            mode=mode,
            inputs=inputs,
            config=coerce_config(definition, config),
            emit=logs.append,
            user_id=owner_id,
            test_run=True,
        )
        started = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="node-test")
        future = pool.submit(definition.executor, context)
        try:
            outputs = future.result(timeout=definition.timeout_ms / 1000.0)
        except TimeoutError as exc:
            raise NodeTestError(
                f"Node timed out after {definition.timeout_ms} ms.",
                408,
            ) from exc
        except Exception as exc:  # noqa: BLE001 - report the executor failure as a test result
            raise NodeTestError(f"{type(exc).__name__}: {exc}", 400) from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        if not isinstance(outputs, dict):
            raise NodeTestError("The executor returned a non-object result.", 500)
        for port in definition.outputs:
            if port.id in outputs:
                problem = validate_port_value(port.type, outputs[port.id])
                if problem:
                    raise NodeTestError(f'output "{port.id}": {problem}', 500)

        return {
            "ok": True,
            "node": {
                "type": definition.type,
                "version": definition.version,
                "label": definition.label,
                "category": definition.category,
                "sideEffects": definition.side_effects.value,
                "timeoutMs": definition.timeout_ms,
            },
            "outputs": outputs,
            "logs": logs,
            "durationMs": int((time.monotonic() - started) * 1000),
        }

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

    def _persist_subworkflow(self, run: GraphRun) -> None:
        """Give a nested subworkflow run its own durable, inspectable row."""
        try:
            self._store.create_run(run)
            for record in run.node_runs:
                self._store.save_node_run(run.id, record)
            for event in run.events:
                self._store.save_event(run.id, event)
            self._store.finish_run(run)
        except Exception:  # noqa: BLE001 - child persistence must never break the parent
            log.debug("subworkflow persistence failed", exc_info=True)

    @staticmethod
    def _grants_payload(grants: RunGrants) -> dict[str, Any]:
        return {
            "testRun": grants.test_run,
            "grantedCapabilities": sorted(grants.granted_capabilities),
            "allowNetwork": grants.allow_network,
            "allowTrading": grants.allow_trading,
            "allowWrite": grants.allow_write,
            "allowedWriteScopes": sorted(grants.allowed_write_scopes),
            "allowLiveTrading": grants.allow_live_trading,
        }

    @staticmethod
    def _grants_from_payload(payload: dict[str, Any]) -> RunGrants:
        return RunGrants(
            test_run=bool(payload.get("testRun", True)),
            granted_capabilities=frozenset(payload.get("grantedCapabilities") or ()),
            allow_network=bool(payload.get("allowNetwork", False)),
            allow_trading=bool(payload.get("allowTrading", False)),
            allow_write=bool(payload.get("allowWrite", False)),
            allowed_write_scopes=frozenset(payload.get("allowedWriteScopes") or ()),
            allow_live_trading=bool(payload.get("allowLiveTrading", False)),
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
        callback_base_url: str = "",
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
            # A durable job outlives the process that started it. The worker
            # re-resolves model credentials from the front door on resume; the
            # secret itself is never written into this payload.
            "callbackBaseUrl": callback_base_url,
        }

    def _resolve_model_settings(
        self, run_id: str, payload: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Re-resolve model credentials after a restart.

        The vault lives in the Next front door. A durable worker calls the
        run-scoped credentials route with the operator secret; the key is held
        in memory for this process only and is never persisted in the job.
        """
        base = str(
            payload.get("callbackBaseUrl")
            or os.environ.get("HARNESS_CALLBACK_URL")
            or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
        ).rstrip("/")
        if not base:
            return None
        token = os.environ.get("CRON_SECRET") or ""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Harness-Operator"] = token
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"{base}/api/graph-runs/{run_id}/credentials",
                    headers=headers,
                    json={},
                )
            if response.status_code != 200:
                log.warning(
                    "graph credentials re-resolution failed for %s: HTTP %s",
                    run_id, response.status_code,
                )
                return None
            data = response.json()
            settings = data.get("modelSettings") if isinstance(data, dict) else None
            return settings if isinstance(settings, dict) else None
        except Exception:  # noqa: BLE001 - the node fails honestly without credentials
            log.warning("graph credentials re-resolution failed for %s", run_id, exc_info=True)
            return None

    def run_sync(
        self,
        ir: WorkflowIR,
        *,
        workflow_version: Optional[int] = None,
        owner_id: str = "local",
        grants: Optional[RunGrants] = None,
        subworkflows: Optional[dict[str, WorkflowIR]] = None,
        run_input: Any = None,
        model_settings: Optional[dict[str, Any]] = None,
        callback_base_url: str = "",
        callback_token: Optional[str] = None,
        user_id: str = "local",
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
            model_settings=model_settings,
            callback_base_url=callback_base_url,
            callback_token=callback_token,
            user_id=user_id,
            on_subworkflow=self._persist_subworkflow,
            load_child_run=self._store.get_run,
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
        model_settings: Optional[dict[str, Any]] = None,
        callback_base_url: str = "",
        callback_token: Optional[str] = None,
        user_id: str = "local",
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
        if model_settings:
            self._model_settings[run_id] = model_settings

        if self._fabric is not None:
            payload = self._job_payload(
                ir, run_id=run_id, workflow_version=workflow_version,
                owner_id=owner_id, grants=grants,
                subworkflows=subworkflows, run_input=run_input,
                callback_base_url=callback_base_url,
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
                    model_settings=model_settings,
                    callback_base_url=callback_base_url,
                    callback_token=callback_token,
                    user_id=user_id,
                    on_subworkflow=self._persist_subworkflow,
                    load_child_run=self._store.get_run,
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
                self._model_settings.pop(run_id, None)
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
        model_settings = self._model_settings.get(run_id)
        if model_settings is None and "agent.run" in plan.required_capabilities:
            # The job survived a restart: the in-memory credentials are gone, so
            # ask the front door to resolve them again. Never persisted here.
            model_settings = self._resolve_model_settings(run_id, payload)
            if model_settings:
                self._model_settings[run_id] = model_settings
        callback_base_url = (
            str(payload.get("callbackBaseUrl") or "")
            or os.environ.get("HARNESS_CALLBACK_URL")
            or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
        )
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
            model_settings=model_settings,
            callback_base_url=callback_base_url,
            callback_token=os.environ.get("CRON_SECRET"),
            user_id=str(payload.get("ownerId") or "local"),
            on_subworkflow=self._persist_subworkflow,
            load_child_run=self._store.get_run,
            allow_defer=True,
        )
        try:
            run = executor.execute()
        except RunDeferred as deferred:
            # The wait node is checkpointed and the run row is QUEUED. The worker
            # requeues the Fabric job at the wake time; model settings stay in
            # memory so the resumed run keeps its credentials.
            self._store.finish_run(deferred.run)
            return deferred
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
            self._model_settings.pop(run_id, None)
            raise
        self._store.finish_run(run)
        self._model_settings.pop(run_id, None)
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

    def health(self, *, window_hours: int = 24) -> dict[str, Any]:
        return self._store.health(window_hours=window_hours)

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
