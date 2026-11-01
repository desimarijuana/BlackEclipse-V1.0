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
    DeferredWait,
    ExecutionPlan,
    GraphRun,
    MAX_PREVIEW_CHARS,
    MAX_SUBWORKFLOW_DEPTH,
    NodeRun,
    NodeStatus,
    PortKind,
    RunDeferred,
    RunEvent,
    RunStatus,
    RunStopRequest,
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


_MISSING = object()


def _numeric_state(value: Any) -> float:
    """A bounded numeric projection for a loop condition.

    A scalar is used directly; an object is read from `value`/`state`/`result`.
    Anything else is 0, so a malformed body stops the loop instead of spinning.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "state", "result"):
            if key in value:
                return _numeric_state(value[key])
    return 0.0


def _loop_scope(state: Any, index: int) -> dict[str, float]:
    """Names a loop condition can read.

    The legacy numeric projection (`value`) stays for compatibility, but a body
    that returns an object also exposes its numeric and boolean fields, so a
    `{done: true}` state can be tested (`done != 1`) instead of silently reading
    as 0 and exiting on the first iteration.
    """
    scope: dict[str, float] = {"index": float(index), "iterations": float(index)}
    if isinstance(state, bool):
        scope["value"] = 1.0 if state else 0.0
    elif isinstance(state, (int, float)):
        scope["value"] = float(state)
    elif isinstance(state, dict):
        for key, value in state.items():
            if isinstance(value, bool):
                scope[str(key)] = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                scope[str(key)] = float(value)
        scope.setdefault("value", _numeric_state(state))
    else:
        scope["value"] = 0.0
    return scope


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


# Ports whose required value may come from a config field instead of a wire or
# a node literal. Mirrors the TS validator and the executors' fallbacks.
_CONFIG_FALLBACK_PORTS: dict[str, str] = {
    "data.json.parse": "text",
    "data.dataset.save": "value",
    "data.dataset.load": "ref",
}
_CONFIG_FALLBACK_KEYS: dict[str, str] = {
    "data.json.parse": "text",
    "data.dataset.save": "valueJson",
    "data.dataset.load": "ref",
}


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
        model_settings: Optional[dict[str, Any]] = None,
        callback_base_url: str = "",
        callback_token: Optional[str] = None,
        user_id: str = "local",
        on_subworkflow: Optional[Callable[[GraphRun], None]] = None,
        load_child_run: Optional[Callable[[str], Optional[dict[str, Any]]]] = None,
        allow_defer: bool = False,
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
        self._model_settings = model_settings
        self._callback_base_url = callback_base_url
        self._callback_token = callback_token
        self._user_id = user_id
        self._on_subworkflow = on_subworkflow
        # Loop iterations use a durable child run per iteration as their
        # checkpoint. The service supplies this loader; a nested executor
        # inherits it.
        self._load_child_run = load_child_run
        self._allow_defer = allow_defer
        self._deferred: Optional[DeferredWait] = None
        # Set by `logic.stop`: the node still succeeds (so `stops_run` skips the
        # rest), and this carries the status/message the run should finish with.
        self._stop_request: Optional[dict[str, Any]] = None
        self._terminal_outputs: dict[str, Any] = {}

        self._inputs_map = plan_inputs(ir)
        # Reverse of the wiring: which (node, control handle) pairs actually go
        # somewhere. Used to report a branch that fired into nothing.
        self._outgoing: dict[tuple[str, str], int] = {}
        for edge in ir.edges:
            key = (edge.source, edge.source_handle)
            self._outgoing[key] = self._outgoing.get(key, 0) + 1
        self._nodes = {node.id: node for node in ir.nodes}
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
        node = self._nodes.get(node_id)
        literals = node.input_values if node is not None else {}
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
            # A wire wins; otherwise a node-level literal fills the port. A
            # literal is authoritative even when it is `None`/`false`, so test
            # presence with `in`, not truthiness.
            if not produced and port.id in literals:
                value = literals[port.id]
                produced = True
            # A config field may supply the required value (the executor reads
            # it). It must count as satisfied here or the node would be skipped.
            if not produced and not port.optional and node is not None:
                fallback_port = _CONFIG_FALLBACK_PORTS.get(node.type)
                fallback_key = _CONFIG_FALLBACK_KEYS.get(node.type)
                if fallback_port == port.id and fallback_key is not None:
                    configured = node.config.get(fallback_key)
                    if isinstance(configured, str) and configured.strip():
                        produced = True
            if not produced and not port.optional:
                unsatisfied.append(port.name)
            resolved[port.id] = value
        return resolved, unsatisfied

    # ── a single node ──────────────────────────────────────────────────────

    def _control_state(self, node_id: str) -> dict[str, bool]:
        """Which WIRED control inputs fired. Unwired control inputs are absent.

        Control ports gate execution, not values: a wired input counts when an
        upstream node succeeded AND fired that handle.
        """
        definition = self._defs[node_id]
        state: dict[str, bool] = {}
        for port in definition.inputs:
            if port.kind != PortKind.CONTROL:
                continue
            wires = self._inputs_map.get(f"{node_id}:{port.id}", [])
            if not wires:
                continue
            state[port.id] = any(
                self._node_runs.get(source_id) is not None
                and self._node_runs[source_id].status == NodeStatus.SUCCEEDED
                and source_handle in self._fired.get(source_id, set())
                for source_id, source_handle in wires
            )
        return state

    def _control_satisfied(self, node_id: str) -> bool:
        """A node that declares CONTROL inputs runs only when an upstream node
        fired one of them. Nodes without control inputs are unaffected."""
        state = self._control_state(node_id)
        if not state:
            # An UNWIRED control input gates nothing — the node runs on dataflow
            # alone (e.g. a standalone `wait` or `stop`).
            return True
        return any(state.values())

    def _control_skip_reason(self, node_id: str) -> str:
        """Name the wires that did not fire, so a skip is actionable."""
        definition = self._defs[node_id]
        names = {port.id: port.name for port in definition.inputs}
        state = self._control_state(node_id)
        missing = [
            f'"{names.get(port_id, port_id)}" from {source_id}'
            for port_id, fired in state.items()
            if not fired
            for source_id, _handle in self._inputs_map.get(f"{node_id}:{port_id}", [])
        ]
        if not missing:
            return "its control input did not fire"
        return f'its control input did not fire ({", ".join(sorted(set(missing)))} was skipped)'


    def _control_fired(self, node_id: str, definition: NodeDef) -> dict[str, bool]:
        """Deprecated alias for `_control_state`; kept for callers added mid-merge."""
        return self._control_state(node_id)

    def _report_dead_branch(self, node_id: str, definition: NodeDef, fired: list[str]) -> None:
        """Say so when a branch decision went nowhere.

        Only nodes with MORE THAN ONE control output are a decision (`condition`,
        `switch`). A node that fires a single `done` has not chosen between
        alternatives, so an unwired `done` is not a mistake and stays quiet.
        """
        control_outs = [p for p in definition.outputs if p.kind == PortKind.CONTROL]
        if len(control_outs) < 2 or not fired:
            return
        if any(self._outgoing.get((node_id, name)) for name in fired):
            return
        labels = []
        for name in fired:
            port = definition.output_port(name)
            labels.append(port.name if port is not None else name)
        self._emit(
            "node.log",
            f"branch {', '.join(labels)} fired but nothing is connected to it — the run continues with no effect",
            node_id,
        )

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
            record.error = self._control_skip_reason(node_id)
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
            except DeferredWait as exc:
                # A durable wait succeeded (checkpointed) and the RUN pauses; the
                # Fabric job is requeued instead of holding this worker thread.
                record.duration_ms = int((time.monotonic() - started) * 1000)
                deferred_outputs = dict(exc.outputs)
                deferred_fired = deferred_outputs.pop("_control", [])
                record.outputs = {key: _preview(value) for key, value in deferred_outputs.items()}
                record.status = NodeStatus.SUCCEEDED
                record.finished_at = now_iso()
                self._outputs[node_id] = deferred_outputs
                fired_names = (
                    [str(name) for name in deferred_fired]
                    if isinstance(deferred_fired, list) else []
                )
                self._fired[node_id] = set(fired_names)
                self._emit(
                    "node.deferred",
                    f"paused for {exc.wake_after_seconds:.3f}s; the job will resume",
                    node_id,
                )
                self._notify_node(record, dict(deferred_outputs), fired_names, False, None)
                self._deferred = exc
                return
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
                fired_names = [str(name) for name in fired] if isinstance(fired, list) else []
                # A node may end the RUN with an explicit outcome (`logic.stop`).
                # It is a reserved key exactly like `_control`: never an output.
                stop_request = result.pop("_stop", None) if isinstance(result, dict) else None
                if isinstance(stop_request, dict):
                    self._stop_request = RunStopRequest.model_validate(stop_request).model_dump()
                skip_reason = result.pop("_skip", None) if isinstance(result, dict) else None
                if isinstance(skip_reason, str) and skip_reason:
                    # A node asked to be SKIPPED (e.g. an `all` gate whose inputs
                    # did not all fire). Its outputs never become available, so
                    # downstream data nodes are skipped like any other branch.
                    record.status = NodeStatus.SKIPPED
                    record.error = skip_reason
                    record.error_code = "skipped_by_node"
                    record.finished_at = now_iso()
                    self._fired[node_id] = set()
                    self._outputs.pop(node_id, None)
                    self._emit("node.skipped", skip_reason, node_id)
                    self._notify_node(record, {}, [], False, None)
                    return
                declared_controls = {
                    port.id for port in definition.outputs if port.kind == PortKind.CONTROL
                }
                undeclared = sorted({name for name in fired_names if name not in declared_controls})
                # Firing a name that is not a declared control output would route
                # to nowhere and look like a successful branch. Refuse it.
                problem = (
                    f"fired control output(s) that are not declared: {', '.join(undeclared)}"
                    if undeclared
                    else self._validate_outputs(node_id, definition, result)
                )
                if problem is None:
                    self._fired[node_id] = set(fired_names)
                    self._report_dead_branch(node_id, definition, fired_names)
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
            workflow_id=self._plan.workflow_id,
            inputs=inputs,
            config=config,
            emit=lambda message: self._emit("node.log", message, node_id),
            run_input=self._run_input,
            model_settings=self._model_settings,
            callback_base_url=self._callback_base_url,
            callback_token=self._callback_token,
            user_id=self._user_id,
            allow_defer=self._allow_defer,
            allow_network=self._grants.allow_network,
            test_run=self._grants.test_run,
            control_fired=self._control_state(node_id),
            should_cancel=self._cancel.is_set,
        )

        def call() -> dict[str, Any]:
            if definition.orchestrated:
                if definition.type in ("flow.for_each", "flow.repeat", "flow.while"):
                    return self._run_loop(node_id, inputs, config, definition)
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

    def _loop_condition(self, expression: str, state: Any, index: int) -> bool:
        from .nodes import evaluate_formula  # noqa: PLC0415 - avoids an import cycle

        try:
            return evaluate_formula(expression, _loop_scope(state, index)) != 0
        except Exception as exc:  # noqa: BLE001 - a bad condition is a node error
            raise ValueError(f"loop condition failed: {exc}") from exc

    def _child_output(self, child_run_id: str) -> Any:
        if self._load_child_run is None:
            return _MISSING
        record = self._load_child_run(child_run_id)
        if not isinstance(record, dict):
            return _MISSING
        if record.get("status") != RunStatus.SUCCEEDED.value:
            return _MISSING
        if "output" not in record:
            return _MISSING
        return record.get("output")

    def _run_loop(
        self,
        node_id: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
        definition: NodeDef,
    ) -> dict[str, Any]:
        """Run a pinned body workflow under an explicit iteration/time bound.

        Each iteration is a durable child run (`<parent>:<node>:i<N>`). On a
        resumed parent, a succeeded child output is reused, so completed
        iterations are never re-executed.
        """
        kind = definition.type
        workflow_id = str(config.get("workflowId") or "").strip()
        try:
            version = int(config.get("version", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("loop body version must be a whole number") from exc
        if not workflow_id:
            raise ValueError("a loop needs a pinned body workflow")
        if version < 1:
            raise ValueError("loop body version must be pinned (>= 1)")
        key = f"{workflow_id}@{version}"
        if key not in self._subworkflows:
            raise ValueError(f"loop body {key} was not supplied to this run")

        if kind == "flow.repeat":
            raw_limit = config.get("count", 1)
        else:
            raw_limit = config.get("maxIterations", 100)
        try:
            limit = max(1, min(int(raw_limit), 1_000))
        except (TypeError, ValueError) as exc:
            raise ValueError("loop iteration bound must be a number") from exc
        try:
            duration_ms = max(0, int(config.get("maxDurationMs", 0) or 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("loop duration bound must be a number") from exc
        continue_on_error = bool(config.get("continueOnError", False))
        condition = str(config.get("condition") or "value > 0")

        items: list[Any] = []
        if kind == "flow.for_each":
            raw_items = inputs.get("items")
            if not isinstance(raw_items, list):
                raise ValueError("flow.for_each needs an array on its items input")
            items = raw_items
            stopped = len(items) > limit
            items = items[:limit]
            iterations_to_run = len(items)
        else:
            stopped = limit < (
                int(config.get("count", 1) or 1) if kind == "flow.repeat"
                else int(config.get("maxIterations", 100) or 100)
            )
            iterations_to_run = limit

        state = inputs.get("input")
        results: list[Any] = []
        iterations = 0
        failures = 0
        started = time.monotonic()
        for index in range(iterations_to_run):
            if self._cancel.is_set():
                stopped = True
                break
            if duration_ms and (time.monotonic() - started) * 1000.0 >= duration_ms:
                stopped = True
                break
            if kind == "flow.for_each":
                item = items[index]
            elif kind == "flow.repeat":
                item = state
            else:
                if not self._loop_condition(condition, state, index):
                    break
                item = state

            child_id = f"{self._run_id}:{node_id}:i{index}"
            prior = self._child_output(child_id)
            try:
                if prior is not _MISSING:
                    output = prior
                    self._emit("node.log", f"loop iteration {index + 1} reused", node_id)
                else:
                    result = self._run_subworkflow(
                        node_id, {"input": item}, config, definition, iteration=index,
                    )
                    output = result.get("output")
                results.append(output)
                state = output
                iterations += 1
            except ValueError as exc:
                if not continue_on_error:
                    raise
                failures += 1
                results.append({"error": str(exc)})
                iterations += 1

        if kind == "flow.for_each":
            self._emit(
                "node.log",
                f"{iterations} iteration(s), {failures} failed"
                + (", stopped early" if stopped else ""),
                node_id,
            )
            return {
                "results": results,
                "iterations": iterations,
                "stopped": stopped,
                "_control": ["done"],
            }
        self._emit(
            "node.log",
            f"{iterations} iteration(s), {failures} failed"
            + (", stopped early" if stopped else ""),
            node_id,
        )
        return {
            "state": state,
            "iterations": iterations,
            "stopped": stopped,
            "_control": ["done"],
        }

    def _run_subworkflow(
        self,
        node_id: str,
        inputs: dict[str, Any],
        config: dict[str, Any],
        definition: NodeDef,
        *,
        iteration: Optional[int] = None,
        prior_output: Any = _MISSING,
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
        child_run_id = f"{self._run_id}:{node_id}" + (
            f":i{iteration}" if iteration is not None else ""
        )
        if prior_output is not _MISSING:
            return {"output": prior_output, "runId": child_run_id, "reused": True}
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
            run_id=child_run_id,
            grants=self._grants,
            cancel_event=self._cancel,
            on_event=relay,
            owner_id=self._owner_id,
            workflow_version=version,
            subworkflows=self._subworkflows,
            run_input=inputs.get("input"),
            depth=self._depth + 1,
            subworkflow_stack=stack,
            on_subworkflow=self._on_subworkflow,
            load_child_run=self._load_child_run,
            user_id=self._user_id,
        )
        run = nested.execute()
        if self._on_subworkflow is not None:
            try:
                self._on_subworkflow(run)
            except Exception:  # noqa: BLE001 - persistence must never break the parent
                pass
        if run.status != RunStatus.SUCCEEDED:
            raise ValueError(f"subworkflow {key} {run.status.value}: {run.error or 'failed'}")
        self._emit("node.log", f"child {key} succeeded in {run.duration_ms} ms", node_id)
        return {"output": run.output, "runId": run.id, "_control": ["done"]}

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

            if self._deferred is not None:
                break

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

        deferred = self._deferred
        if deferred is None:
            # Mark every node that can no longer run.
            self._settle_remaining(succeeded)

        cancelled = self._cancel.is_set()
        failed = any(r.status == NodeStatus.FAILED for r in self._node_runs.values())
        stop = self._stop_request
        stop_failed = bool(stop and str(stop.get("status") or "") == "failed")
        if deferred is not None:
            status = RunStatus.QUEUED
        else:
            status = RunStatus.CANCELLED if cancelled else (
                RunStatus.FAILED if (failed or stop_failed) else RunStatus.SUCCEEDED
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        if deferred is not None:
            self._emit(
                "run.deferred",
                f"paused for {deferred.wake_after_seconds:.3f}s; the job will resume",
            )
        elif status == RunStatus.SUCCEEDED:
            self._emit("run.succeeded", f"completed in {duration_ms} ms")
        elif status == RunStatus.CANCELLED:
            self._emit("run.cancelled", "run cancelled")
        elif stop_failed:
            self._emit("run.stopped", str(stop.get("message") or "run stopped"))
        else:
            first = next((r for r in self._node_runs.values() if r.status == NodeStatus.FAILED), None)
            self._emit("run.failed", first.error if first and first.error else "one or more nodes failed")

        terminal_values = dict(self._terminal_outputs)
        output: Any = None
        if len(terminal_values) == 1:
            output = next(iter(terminal_values.values()))
        elif terminal_values:
            output = terminal_values

        run_error = next(
            (r.error for r in self._node_runs.values() if r.status == NodeStatus.FAILED), None,
        )
        if stop_failed:
            run_error = str(stop.get("message") or "run stopped")

        run = GraphRun(
            id=self._run_id,
            workflowId=self._plan.workflow_id,
            workflowVersion=self._workflow_version,
            irVersion=self._plan.ir_version,
            mode=self._plan.mode,
            testRun=self._grants.test_run,
            status=status,
            startedAt=started_at,
            finishedAt=None if deferred is not None else now_iso(),
            durationMs=duration_ms,
            error=run_error,
            ownerId=self._owner_id,
            output=output,
            nodeRuns=[self._node_runs[n.node_id] for n in sorted(self._plan.nodes, key=lambda p: (p.layer, p.node_id))],
            events=self._events,
            plan=self._plan,
        )
        if deferred is not None:
            raise RunDeferred(run, deferred.wake_after_seconds)
        return run

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
