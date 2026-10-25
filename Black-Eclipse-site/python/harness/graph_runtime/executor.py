"""Deterministic graph executor.

Runs an :class:`ExecutionPlan` against the model graph. The scheduler is
layer-based (the compiler's parallelizable groups) with a deterministic order
inside each layer, so two runs of the same graph with the same inputs produce
byte-identical node outputs.

Lifecycle per node: ``pending → ready → running → succeeded | failed |
cancelled`` (plus ``skipped`` for nodes downstream of a failure). Retries,
per-node timeouts and cancellation are enforced HERE — not in the editor and not
by the node.

What this module deliberately does NOT do yet: durability across process
restarts and cross-process workers. That is Phase 4, built on the existing
Execution Fabric; this executor is the deterministic in-process runtime that
Phase 4 will wrap.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..persistence import now_iso
from .compiler import RunGrants, compile_workflow, plan_inputs
from .model import (
    ExecutionPlan,
    GraphRun,
    MAX_PREVIEW_CHARS,
    MAX_SUBWORKFLOW_DEPTH,
    NodeRun,
    NodeStatus,
    PortKind,
    RunEvent,
    RunStatus,
    SideEffect,
    WorkflowIR,
)
from .registry import NodeDef, NodeExecContext, NodeRegistry, validate_port_value


@dataclass
class ResumeState:
    """Successful node checkpoints for a run that should resume, not restart."""

    nodes: dict[str, NodeRun] = field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    fired: dict[str, list[str]] = field(default_factory=dict)
    terminal: dict[str, Any] = field(default_factory=dict)
    complete: bool = True


def _preview(value: Any) -> Any:
    """A bounded, JSON-safe preview of a value for the run record."""
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= MAX_PREVIEW_CHARS:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return {"_truncated": True, "preview": text[:MAX_PREVIEW_CHARS]}


class GraphExecutor:
    """Execute one plan. Construct per run; not reused."""

    def __init__(
        self,
        ir: WorkflowIR,
        plan: ExecutionPlan,
        registry: NodeRegistry,
        *,
        run_id: str,
        grants: Optional[RunGrants] = None,
        cancel_event: Optional[threading.Event] = None,
        on_event: Optional[Callable[[RunEvent], None]] = None,
        owner_id: str = "local",
        workflow_version: Optional[int] = None,
        subworkflows: Optional[dict[str, WorkflowIR]] = None,
        run_input: Any = None,
        depth: int = 0,
        subworkflow_stack: tuple[str, ...] = (),
        resume: Optional[ResumeState] = None,
        on_node_finished: Optional[
            Callable[[NodeRun, dict[str, Any], list[str], bool, Any], None]
        ] = None,
    ) -> None:
        self._ir = ir
        self._plan = plan
        self._registry = registry
        self._run_id = run_id
        self._grants = grants or RunGrants()
        self._cancel = cancel_event or threading.Event()
        self._on_event = on_event
        self._owner_id = owner_id
        self._workflow_version = workflow_version
        self._subworkflows = subworkflows or {}
        self._run_input = run_input
        self._depth = depth
        self._subworkflow_stack = subworkflow_stack
        self._resume = resume or ResumeState()
        self._on_node_finished = on_node_finished
        self._terminal_outputs: dict[str, Any] = {}

        self._inputs_map = plan_inputs(ir)
        self._outputs: dict[str, dict[str, Any]] = {}  # node_id → {handle: value}
        # Control outputs a node FIRED (`_control` in its result). Control ports
        # gate execution; they never carry values.
        self._fired: dict[str, set[str]] = {}
        self._defs: dict[str, NodeDef] = {}
        for plan_node in plan.nodes:
            definition = registry.get(plan_node.node_type, plan_node.version)
            if definition is not None:
                self._defs[plan_node.node_id] = definition

        self._node_runs: dict[str, NodeRun] = {}
        for plan_node in plan.nodes:
            definition = self._defs.get(plan_node.node_id)
            self._node_runs[plan_node.node_id] = NodeRun(
                nodeId=plan_node.node_id,
                nodeType=plan_node.node_type,
                label=(definition.label if definition else plan_node.node_type),
                status=NodeStatus.PENDING,
                layer=plan_node.layer,
            )
        # Resume: seed completed nodes, their full outputs and fired control
        # names. The scheduler only runs PENDING nodes, so a completed node is
        # never re-executed.
        for node_id, record in self._resume.nodes.items():
            if node_id not in self._node_runs:
                continue
            self._node_runs[node_id] = record
            self._outputs[node_id] = self._resume.outputs.get(node_id, {})
            self._fired[node_id] = set(self._resume.fired.get(node_id, []))
            if node_id in self._resume.terminal:
                self._terminal_outputs[node_id] = self._resume.terminal[node_id]
        self._events: list[RunEvent] = []

    # ── logging ────────────────────────────────────────────────────────────

    def _emit(self, kind: str, message: str = "", node_id: Optional[str] = None) -> None:
        event = RunEvent(at=now_iso(), kind=kind, nodeId=node_id, message=message)
        self._events.append(event)
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:  # noqa: BLE001 - an observer must never break a run
                pass

    def _notify_node(
        self,
        record: NodeRun,
        outputs: dict[str, Any],
        fired: list[str],
        terminal_done: bool,
        terminal_value: Any,
    ) -> None:
        if self._on_node_finished is None:
            return
        try:
            self._on_node_finished(record, outputs, fired, terminal_done, terminal_value)
        except Exception:  # noqa: BLE001 - a persistence observer must never break a run
            pass

    # ── input resolution ───────────────────────────────────────────────────

    def _resolve_inputs(self, node_id: str) -> tuple[dict[str, Any], list[str]]:
        """Resolve every input from the outputs of writers that SUCCEEDED.
        Returns the values plus the names of required inputs no successful
        upstream produced — a node whose input never materialized is skipped,
        never run with a silently-null placeholder."""
        definition = self._defs[node_id]
        resolved: dict[str, Any] = {}
        unsatisfied: list[str] = []
        for port in definition.inputs:
            if port.kind == PortKind.CONTROL:
                continue
            writers = self._inputs_map.get(f"{node_id}:{port.id}", [])
            value: Any = None
            produced = False
            for source_id, source_handle in writers:  # last successful writer wins
                record = self._node_runs.get(source_id)
                if record is None or record.status != NodeStatus.SUCCEEDED:
                    continue
                outputs = self._outputs.get(source_id)
                if outputs is not None and source_handle in outputs:
                    value = outputs[source_handle]
                    produced = True
            if not produced and not port.optional and writers:
                unsatisfied.append(port.name)
            resolved[port.id] = value
        return resolved, unsatisfied

    # ── a single node ──────────────────────────────────────────────────────

    def _control_satisfied(self, node_id: str) -> bool:
        """A node that declares CONTROL inputs runs only when an upstream node
        fired one of them. Nodes without control inputs are unaffected."""
        definition = self._defs[node_id]
        control_inputs = [p for p in definition.inputs if p.kind == PortKind.CONTROL]
        if not control_inputs:
            return True
        wired = [f"{node_id}:{port.id}" for port in control_inputs if self._inputs_map.get(f"{node_id}:{port.id}")]
        if not wired:
            # An UNWIRED control input gates nothing — the node runs on dataflow
            # alone (e.g. a standalone `wait` or `stop`).
            return True
        for key in wired:
            for source_id, source_handle in self._inputs_map.get(key, []):
                source = self._node_runs.get(source_id)
                if (
                    source is not None
                    and source.status == NodeStatus.SUCCEEDED
                    and source_handle in self._fired.get(source_id, set())
                ):
                    return True
        return False

    def _run_node(self, node_id: str) -> None:
        record = self._node_runs[node_id]
        definition = self._defs[node_id]

        if self._cancel.is_set():
            record.status = NodeStatus.CANCELLED
            self._emit("node.cancelled", "run cancelled before execution", node_id)
            self._notify_node(record, {}, [], False, None)
            return

        if not self._control_satisfied(node_id):
            record.status = NodeStatus.SKIPPED
            record.error = "its control input did not fire"
            record.error_code = "control_not_fired"
            record.finished_at = now_iso()
            self._emit("node.skipped", record.error, node_id)
            self._notify_node(record, {}, [], False, None)
            return

        try:
            inputs, unsatisfied = self._resolve_inputs(node_id)
        except Exception as exc:  # noqa: BLE001
            self._fail(node_id, f"input resolution failed: {exc}", "input_resolution")
            return

        if unsatisfied:
            record.status = NodeStatus.SKIPPED
            record.error = f"upstream did not produce required input(s): {', '.join(unsatisfied)}"
            record.error_code = "upstream_failed"
            record.finished_at = now_iso()
            self._emit("node.skipped", record.error, node_id)
            self._notify_node(record, {}, [], False, None)
            return

        record.status = NodeStatus.READY
        record.inputs = {key: _preview(value) for key, value in inputs.items()}

        config = _effective_config(definition, self._ir, node_id)
        attempt = 0
        last_error: Optional[str] = None
        while attempt < max(1, definition.max_attempts):
            attempt += 1
            record.attempt = attempt
            record.status = NodeStatus.RUNNING
            record.started_at = now_iso()
            started = time.monotonic()
            self._emit("node.started", f"{definition.label} (attempt {attempt})", node_id)
            try:
                result = self._invoke(node_id, inputs, config, definition)
            except _NodeTimeout as exc:
                record.duration_ms = int((time.monotonic() - started) * 1000)
                last_error = f"timed out after {exc.timeout_ms} ms"
                record.error_code = "timeout"
            except Exception as exc:  # noqa: BLE001 - a node failure is data, not a crash
                record.duration_ms = int((time.monotonic() - started) * 1000)
                last_error = f"{type(exc).__name__}: {exc}"
                record.error_code = "execution_error"
            else:
                record.duration_ms = int((time.monotonic() - started) * 1000)
                # Control outputs are declared as `_control` in the result and
                # are never carried as values.
                fired = result.pop("_control", []) if isinstance(result, dict) else []
                problem = self._validate_outputs(node_id, definition, result)
                if problem is None:
                    fired_names = [str(name) for name in fired] if isinstance(fired, list) else []
                    self._fired[node_id] = set(fired_names)
                    self._outputs[node_id] = result
                    terminal_done = bool(definition.terminal)
                    terminal_value = None
                    if terminal_done:
                        terminal_value = inputs["value"] if "value" in inputs else (inputs or None)
                        self._terminal_outputs[node_id] = terminal_value
                    record.outputs = {key: _preview(value) for key, value in result.items()}
                    record.status = NodeStatus.SUCCEEDED
                    record.finished_at = now_iso()
                    record.error = None
                    self._emit("node.succeeded", f"{definition.label} in {record.duration_ms} ms", node_id)
                    self._notify_node(record, result, fired_names, terminal_done, terminal_value)
                    return
                last_error = problem
                record.error_code = "output_schema"

            record.error = last_error
            if attempt < max(1, definition.max_attempts) and not self._cancel.is_set():
                self._emit("node.retry", last_error, node_id)
                continue
            break

        record.status = NodeStatus.CANCELLED if self._cancel.is_set() else NodeStatus.FAILED
        record.finished_at = now_iso()
        self._emit("node.failed", record.error or "failed", node_id)
        self._notify_node(record, {}, [], False, None)

    def _invoke(
        self,
        node_id: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
        definition: NodeDef,
    ) -> dict[str, Any]:
        """Run the executor with a HARD per-node timeout.

        The executor runs in a dedicated single-thread pool; `future.result`
        with the node timeout returns control even if a (buggy) executor never
        finishes, so a bad node cannot hang the whole run.
        """
        context = NodeExecContext(
            node_id=node_id,
            run_id=self._run_id,
            mode=self._plan.mode,
            inputs=inputs,
            config=config,
            emit=lambda message: self._emit("node.log", message, node_id),
            run_input=self._run_input,
        )

        def call() -> dict[str, Any]:
            if definition.orchestrated:
                return self._run_subworkflow(node_id, inputs, config, definition)
            if definition.executor is None:  # pragma: no cover - compile refuses these
                raise RuntimeError(f"node type {definition.type} has no executor")
            return definition.executor(context)

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"graph-{node_id}")
        future = pool.submit(call)
        try:
            return future.result(timeout=definition.timeout_ms / 1000.0)
        except TimeoutError as exc:
            future.cancel()
            raise _NodeTimeout(definition.timeout_ms) from exc
        finally:
            # `wait=False`: a timed-out thread is abandoned (documented); daemon
            # threads die with the process and pure executors hold no resources.
            pool.shutdown(wait=False, cancel_futures=True)

    def _run_subworkflow(
        self,
        node_id: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
        definition: NodeDef,
    ) -> dict[str, Any]:
        """Execute a pinned subworkflow with the SAME grants and a bounded depth.

        A nested run cannot widen authority: it receives the parent's grants,
        so its own compiler enforces the same test-run/effect envelope. Cycles
        are refused here AND by the front-door bundle loader.
        """
        workflow_id = str(config.get("workflowId") or "").strip()
        try:
            version = int(config.get("version", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("subworkflow version must be a whole number") from exc
        if not workflow_id:
            raise ValueError("subworkflow workflowId is required")
        if version < 1:
            raise ValueError("subworkflow version must be pinned (>= 1)")
        key = f"{workflow_id}@{version}"
        if key in self._subworkflow_stack:
            raise ValueError(f"subworkflow cycle detected: {' -> '.join((*self._subworkflow_stack, key))}")
        if self._depth >= MAX_SUBWORKFLOW_DEPTH:
            raise ValueError(f"subworkflow nesting exceeds the maximum depth ({MAX_SUBWORKFLOW_DEPTH})")
        sub_ir = self._subworkflows.get(key)
        if sub_ir is None:
            raise ValueError(f"subworkflow {key} was not supplied to this run")

        stack = (*self._subworkflow_stack, key)
        plan = compile_workflow(
            sub_ir, self._registry, self._grants, self._subworkflows,
            _depth=self._depth + 1, _stack=stack,
        )
        if not plan.executable:
            error = next((d.message for d in plan.diagnostics if d.severity.value == "error"), None)
            raise ValueError(f"subworkflow {key} is not executable: {error or 'invalid graph'}")

        def relay(event: RunEvent) -> None:
            if event.kind.startswith("run."):
                self._emit("subworkflow.event", f"{key}: {event.kind} {event.message}".strip(), node_id)

        nested = GraphExecutor(
            sub_ir, plan, self._registry,
            run_id=f"{self._run_id}:{node_id}",
            grants=self._grants,
            cancel_event=self._cancel,
            on_event=relay,
            owner_id=self._owner_id,
            workflow_version=version,
            subworkflows=self._subworkflows,
            run_input=inputs.get("input"),
            depth=self._depth + 1,
            subworkflow_stack=stack,
        )
        run = nested.execute()
        if run.status != RunStatus.SUCCEEDED:
            raise ValueError(f"subworkflow {key} {run.status.value}: {run.error or 'failed'}")
        return {"output": run.output, "runId": run.id}

    def _validate_outputs(self, node_id: str, definition: NodeDef, result: Any) -> Optional[str]:
        if not isinstance(result, dict):
            return f"executor returned {type(result).__name__}, expected a mapping of output ports"
        for port in definition.outputs:
            if port.kind == PortKind.CONTROL:
                continue
            if port.id not in result:
                return f'missing declared output "{port.id}" ({port.type.value})'
            problem = validate_port_value(port.type, result[port.id])
            if problem is not None:
                return f'output "{port.id}" is invalid: {problem}'
        return None

    def _fail(self, node_id: str, message: str, code: str) -> None:
        record = self._node_runs[node_id]
        record.status = NodeStatus.FAILED
        record.error = message
        record.error_code = code
        record.finished_at = now_iso()
        self._emit("node.failed", message, node_id)
        self._notify_node(record, {}, [], False, None)

    # ── run ────────────────────────────────────────────────────────────────

    def execute(self) -> GraphRun:
        started_at = now_iso()
        started = time.monotonic()
        self._emit("run.started", f"{self._plan.workflow_id} in {self._plan.mode.value} mode")
        if self._resume.nodes:
            self._emit("run.resumed", f"resuming with {len(self._resume.nodes)} completed node(s)")

        deadline: Optional[float] = None
        if self._ir.settings.timeout_ms:
            deadline = started + self._ir.settings.timeout_ms / 1000.0

        succeeded = True
        for layer in self._plan.layers:
            if self._cancel.is_set():
                break
            if deadline is not None and time.monotonic() > deadline:
                succeeded = False
                self._emit("run.timeout", f"run exceeded its {self._ir.settings.timeout_ms} ms budget")
                break

            runnable = [node_id for node_id in layer if self._node_runs[node_id].status == NodeStatus.PENDING]
            if not runnable:
                continue
            workers = max(1, min(self._ir.settings.max_concurrency, len(runnable)))
            if workers == 1:
                for node_id in runnable:
                    self._run_node(node_id)
            else:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="graph-layer") as pool:
                    list(pool.map(self._run_node, runnable))

            if any(self._node_runs[node_id].status == NodeStatus.FAILED for node_id in runnable):
                succeeded = False
                if self._ir.settings.fail_fast:
                    self._emit("run.fail_fast", "failFast is on; stopping after the first failing layer")
                    break

            stopper = next(
                (
                    node_id for node_id in runnable
                    if self._node_runs[node_id].status == NodeStatus.SUCCEEDED
                    and self._defs[node_id].stops_run
                ),
                None,
            )
            if stopper is not None:
                self._emit("run.stopped", f"stopped by {stopper}; downstream nodes will be skipped", stopper)
                break

        # Mark every node that can no longer run.
        self._settle_remaining(succeeded)

        cancelled = self._cancel.is_set()
        failed = any(r.status == NodeStatus.FAILED for r in self._node_runs.values())
        status = RunStatus.CANCELLED if cancelled else (RunStatus.FAILED if failed else RunStatus.SUCCEEDED)
        duration_ms = int((time.monotonic() - started) * 1000)
        if status == RunStatus.SUCCEEDED:
            self._emit("run.succeeded", f"completed in {duration_ms} ms")
        elif status == RunStatus.CANCELLED:
            self._emit("run.cancelled", "run cancelled")
        else:
            first = next((r for r in self._node_runs.values() if r.status == NodeStatus.FAILED), None)
            self._emit("run.failed", first.error if first and first.error else "one or more nodes failed")

        terminal_values = dict(self._terminal_outputs)
        output: Any = None
        if len(terminal_values) == 1:
            output = next(iter(terminal_values.values()))
        elif terminal_values:
            output = terminal_values

        return GraphRun(
            id=self._run_id,
            workflowId=self._plan.workflow_id,
            workflowVersion=self._workflow_version,
            irVersion=self._plan.ir_version,
            mode=self._plan.mode,
            testRun=self._grants.test_run,
            status=status,
            startedAt=started_at,
            finishedAt=now_iso(),
            durationMs=duration_ms,
            error=next((r.error for r in self._node_runs.values() if r.status == NodeStatus.FAILED), None),
            ownerId=self._owner_id,
            output=output,
            nodeRuns=[self._node_runs[n.node_id] for n in sorted(self._plan.nodes, key=lambda p: (p.layer, p.node_id))],
            events=self._events,
            plan=self._plan,
        )

    def _settle_remaining(self, succeeded: bool) -> None:
        """Nodes left pending after a failure/stop become `skipped`; after
        cancellation they are `cancelled`."""
        cancelled = self._cancel.is_set()
        for record in self._node_runs.values():
            if record.status in (NodeStatus.PENDING, NodeStatus.READY):
                record.status = NodeStatus.CANCELLED if cancelled else NodeStatus.SKIPPED
                record.finished_at = now_iso()
                self._emit(
                    "node.cancelled" if cancelled else "node.skipped",
                    "run stopped before this node ran",
                    record.node_id,
                )


class _NodeTimeout(Exception):
    def __init__(self, timeout_ms: int) -> None:
        super().__init__(f"timed out after {timeout_ms} ms")
        self.timeout_ms = timeout_ms


def _effective_config(definition: NodeDef, ir: WorkflowIR, node_id: str) -> dict[str, Any]:
    """The node's config with declared defaults filled. Re-coerced at execution
    time so the executor never depends on the compiler's copy."""
    from .registry import coerce_config  # noqa: PLC0415 - local to avoid an import cycle at module load

    node = ir.node(node_id)
    return coerce_config(definition, node.config if node else {})


__all__ = ["GraphExecutor", "ResumeState"]
