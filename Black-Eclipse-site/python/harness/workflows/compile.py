"""Compile a Workflow onto the EXISTING execution graph (Harness closeout Phase 5).

The workflow does NOT construct its own tool loop, registry or model adapter. A
step invokes the SAME `execute_run` a chat turn uses. A step's tool scope is
enforced at the SAME seam as today — the `allowed=` argument of
`ToolRegistry.execute` — by composing an `AgentConfig` whose tool allowlist is the
INTERSECTION of the workflow agent's allowlist and the step's declared tools. A
denied call is a structured `TOOL_FORBIDDEN` visible in the trace.

Budgets (maxSteps/maxToolCalls/run timeout) and cancellation propagate: each step
inherits the run's cancel event and the shared retrieval cache, and a cancelled
workflow ends in EXACTLY ONE terminal status.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..agents import get_agent
from ..events import EventBus, RunEmitter
from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, RunRequest
from ..tools import DataBridge, ToolRegistry

log = logging.getLogger("harness.workflows.compile")


def _resolve_agent_config(request: RunRequest) -> AgentConfig:
    if request.agent is not None:
        return request.agent
    return get_agent(request.agentId or "eclipse-agent")


def _narrow_allowlist(agent: AgentConfig, step_tools: Optional[list[str]]) -> Optional[list[str]]:
    """The step's effective tool allowlist = agent allowlist ∩ step tools.

    A step may only NARROW the agent's allowlist, never widen it. When the agent
    has no allowlist (None = all tools) the step's tools become the allowlist; when
    the step declares no tools, the agent's allowlist is inherited unchanged.
    """
    if step_tools is None:
        return agent.tools
    if agent.tools is None:
        return list(step_tools)
    allowed = set(agent.tools)
    return [t for t in step_tools if t in allowed]


def _step_agent(base: AgentConfig, step_tools: Optional[list[str]], step_id: str) -> AgentConfig:
    narrowed = _narrow_allowlist(base, step_tools)
    return base.model_copy(update={"id": base.id, "tools": narrowed})


def _topological_order(workflow: Any) -> list[str]:
    """Deterministic order: a step runs after every dependency."""
    remaining = {s.id: set(s.depends_on) for s in workflow.steps}
    ordered: list[str] = []
    while remaining:
        ready = sorted(sid for sid, deps in remaining.items() if not deps)
        if not ready:
            break  # a cycle — validation rejects this before compile
        for sid in ready:
            ordered.append(sid)
            remaining.pop(sid)
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered


def _evaluate_condition(condition: dict[str, Any], outputs: dict[str, str]) -> bool:
    """A declared, deterministic comparison over prior-step output. Never code."""
    source = str(condition.get("from", ""))
    text = outputs.get(source, "")
    op = str(condition.get("op", "contains"))
    value = str(condition.get("value", ""))
    if op == "contains":
        return value in text
    if op == "not_contains":
        return value not in text
    if op == "equals":
        return text.strip() == value
    if op == "non_empty":
        return bool(text.strip())
    return False


class WorkflowResult:
    """The bounded result of a workflow run (exactly one terminal status)."""

    def __init__(self, workflow_id: str, status: str) -> None:
        self.workflowId = workflow_id  # noqa: N815
        self.status = status
        self.steps: list[dict[str, Any]] = []
        self.outputs: dict[str, str] = {}
        self.runIds: list[str] = []  # noqa: N815
        self.error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflowId": self.workflowId,
            "status": self.status,
            "steps": self.steps,
            "outputs": dict(self.outputs),
            "runIds": list(self.runIds),
            "error": self.error,
        }


async def compile_workflow(
    workflow: Any,
    base_request: RunRequest,
    registry: ToolRegistry,
    data_bridge: DataBridge,
    store: AgentMemoryStore,
    *,
    bus: Optional[EventBus] = None,
    cancel_event: Optional[asyncio.Event] = None,
    retrieval_cache: Optional[Any] = None,
    memory_service: Optional[Any] = None,
    skill_registry: Optional[Any] = None,
    approvals: Optional[Any] = None,
    memory_router: Optional[Any] = None,
    mcp_manager: Optional[Any] = None,
) -> WorkflowResult:
    """Execute a workflow over the existing graph. Returns exactly one status."""
    from ..graph import execute_run  # noqa: PLC0415 - lazy to avoid a cycle

    result = WorkflowResult(workflow.id, "completed")
    base_agent = _resolve_agent_config(base_request)
    # The workflow run owns a PARENT HarnessRun row so its per-step events persist
    # (FK holds) and the lineage/explain surfaces can show the step tree. It is a
    # metadata row — the actual work happens in the child step runs.
    if store.get_run(base_request.runId) is None:
        store.create_run(
            base_request.runId, base_agent.id, base_request.input.model_dump(),
            base_request.userId, base_request.modelSettings.provider, base_request.modelSettings.model,
            session_id=base_request.sessionId, profile_id=base_request.profileId,
            project_id=base_request.projectId,
        )
    store.update_run(base_request.runId, status="running")
    # Record the workflow id on the parent row (lineage module owns the column).
    try:
        from ..run_lineage import RunLineage  # noqa: PLC0415

        RunLineage(store).set_run_parent(base_request.runId, base_request.parentRunId, workflow.id)
    except Exception:  # noqa: BLE001 - lineage is additive
        pass
    emitter = RunEmitter(base_request.runId, store, bus)
    ordered = _topological_order(workflow)
    executed: set[str] = set()
    outputs: dict[str, str] = {}
    cancelled = False

    async def _run_step(step: Any) -> None:
        nonlocal cancelled
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            return
        step_run_id = f"{base_request.runId}_{step.id}"
        # An approval step reuses the EXISTING single-use ApprovalStore: it claims
        # the exact server/tool/args approval exactly once; a replay fails.
        if step.kind == "approval":
            approval = step.approval or {}
            server = str(approval.get("server") or "")
            tool = str(approval.get("tool") or "")
            args = approval.get("args") or {}
            claimed = approvals.consume(server, tool, args) if approvals is not None else None
            ok = claimed is not None
            result.steps.append({"id": step.id, "kind": step.kind, "status": "completed" if ok else "refused",
                                 "approvalId": (claimed or {}).get("id")})
            if not ok:
                result.status = "failed"
                result.error = {"code": "TOOL_FORBIDDEN", "message": f"approval for {server}/{tool} not granted"}
                cancelled = True
            return

        if step.kind == "conditional":
            keep = _evaluate_condition(step.condition or {}, outputs)
            result.steps.append({"id": step.id, "kind": step.kind, "status": "completed" if keep else "skipped",
                                 "condition": step.condition})
            if not keep:
                # A skipped conditional does not run its branches.
                return

        step_agent = _step_agent(base_agent, step.tools, step.id)
        # Per-step observability on the EXISTING bus (no second bus). `started` is
        # a LIVE signal published to the bus only — the child run row does not
        # exist yet, so persisting it would violate the run FK; `completed` is
        # persisted on the child run id below (the row exists by then).
        started_emitter = RunEmitter(step_run_id, store, bus)
        started_emitter.emit_transient("workflow.step_started", {
            "workflowId": workflow.id, "stepId": step.id, "kind": step.kind,
            "scope": list(step.tools) if step.tools is not None else None,
        })
        step_request = base_request.model_copy(update={
            "runId": step_run_id,
            "agent": step_agent,
            "parentRunId": base_request.runId,
            "workflowId": workflow.id,
            "resumeFrom": None,
        })
        # Compose the step's input: its instruction replaces the query; prior
        # outputs are carried as labelled context (data, never instructions).
        context = dict(step_request.input.context or {})
        context["_workflow"] = {"workflowId": workflow.id, "stepId": step.id, "outputs": dict(outputs)}
        run_input = step_request.input.model_copy(update={
            "query": (step.instruction or step_request.input.query or "workflow step")[:4000],
            "context": context,
        })
        step_request = step_request.model_copy(update={"input": run_input})

        last_exc: Optional[Exception] = None
        for attempt in range(step.retry.max_attempts):
            try:
                outcome = await execute_run(
                    step_request, registry, data_bridge, store, bus,
                    cancel_event=cancel_event, retrieval_cache=retrieval_cache,
                    memory_service=memory_service, skill_registry=skill_registry,
                    approvals=approvals, memory_router=memory_router, mcp_manager=mcp_manager,
                )
                last_exc = None
                outputs[step.id] = outcome.output or ""
                result.outputs[step.id] = outcome.output or ""
                result.runIds.append(step_run_id)
                result.steps.append({
                    "id": step.id, "kind": step.kind, "status": outcome.status,
                    "runId": step_run_id, "toolCalls": outcome.toolCalls,
                    "scope": step.tools,
                })
                # Persisted on the STEP run id (the row exists now), so the step
                # tree is durable and the FK holds.
                await RunEmitter(step_run_id, store, bus).emit("workflow.step_completed", {
                    "workflowId": workflow.id, "stepId": step.id, "kind": step.kind,
                    "status": outcome.status, "runId": step_run_id,
                    "scope": list(step.tools) if step.tools is not None else None,
                })
                if outcome.status != "completed":
                    result.status = "failed"
                    result.error = {"code": outcome.error.code if outcome.error else "STEP_FAILED",
                                    "message": f"step {step.id} ended {outcome.status}"}
                    return
                return
            except asyncio.CancelledError:
                cancelled = True
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        if last_exc is not None:
            result.status = "failed"
            result.error = {"code": "STEP_ERROR", "message": f"step {step.id}: {last_exc}"}

    for step_id in ordered:
        if cancelled:
            break
        step = workflow.step(step_id)
        if step is None:
            continue
        if step.kind == "parallel" and step.branches:
            # Branches share the run's cancel event and retrieval cache.
            await asyncio.gather(*(
                _run_step(workflow.step(b)) for b in step.branches if workflow.step(b) is not None
            ))
            executed.add(step_id)
        else:
            await _run_step(step)
            executed.add(step_id)

    if cancelled and result.status == "completed":
        result.status = "cancelled"
    return result


async def run_workflow(*args: Any, **kwargs: Any) -> WorkflowResult:
    """Alias kept for symmetry with the front-door route."""
    return await compile_workflow(*args, **kwargs)


__all__ = ["compile_workflow", "run_workflow", "WorkflowResult"]
