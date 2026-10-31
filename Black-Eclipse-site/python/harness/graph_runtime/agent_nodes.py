"""Agent nodes.

The graph node is a thin adapter over the EXISTING agent run plane
(`AgenticService.run`): it does not create a second agent loop, model adapter or
tool registry. `bootstrap.py` binds a runner at boot so tests can substitute a
fake and the runtime does not import the whole service here.

Model credentials are held in memory for the run and are never written into the
durable Fabric job payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_DELEGATE_TASKS = 6

AgentRunner = Callable[[NodeExecContext, dict[str, Any], str], dict[str, Any]]
PlanRunner = Callable[[NodeExecContext, str], dict[str, Any]]
_runner: Optional[AgentRunner] = None
_plan_runner: Optional[PlanRunner] = None


def set_agent_runner(runner: Optional[AgentRunner]) -> None:
    global _runner
    _runner = runner


def set_plan_runner(runner: Optional[PlanRunner]) -> None:
    global _plan_runner
    _plan_runner = runner


def _tasks(context: NodeExecContext) -> list[dict[str, str]]:
    raw = context.inputs.get("tasks")
    if raw is None:
        text = str(context.config.get("tasksJson") or "").strip()
        if not text:
            raise ValueError("agent.delegate needs a tasks array or configured tasksJson")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"tasksJson is not valid JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise ValueError("tasks must be a non-empty array")
    limit = max(1, min(int(context.config.get("maxTasks", 4)), MAX_DELEGATE_TASKS))
    if len(raw) > limit:
        raise ValueError(f"agent.delegate is bounded to {limit} task(s) (got {len(raw)})")
    out: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            objective = item.strip()
            title = f"Task {index + 1}"
        elif isinstance(item, dict):
            objective = str(item.get("objective") or item.get("query") or "").strip()
            title = str(item.get("title") or f"Task {index + 1}").strip()
        else:
            raise ValueError(f"task {index + 1} must be a string or an object")
        if not objective:
            raise ValueError(f"task {index + 1} has no objective")
        if len(objective) > 2_000:
            raise ValueError(f"task {index + 1} exceeds 2 000 characters")
        out.append({"title": title[:120], "objective": objective})
    return out


# The agent run plane reports a successful turn as `completed` (see
# `schemas.RunStatus`). `succeeded` is accepted too so substitute runtimes and
# older fakes keep working.
RUN_SUCCESS_STATUSES = frozenset({"completed", "succeeded"})


def agent_run_identity(
    store: Any,
    base_id: str,
    *,
    lineage: Any = None,
) -> tuple[str, Optional[str]]:
    """Pick the agent-plane run id and a resume checkpoint, if one exists.

    A graph node that is re-executed after a process restart must re-enter the
    SAME agent run when that run has a durable checkpoint. Without a checkpoint
    (or after a terminal run) it gets a fresh id, so the agent plane never
    rejects a retry as a duplicate.
    """
    prior = store.get_run(base_id) if store is not None else None
    if prior is not None:
        status = str(prior.get("status") or "")
        if status not in ("completed", "failed", "cancelled"):
            if lineage is None:
                from ..run_lineage import RunLineage  # noqa: PLC0415

                lineage = RunLineage(store)
            checkpoint = lineage.latest_checkpoint(base_id)
            if checkpoint:
                return base_id, str(checkpoint["id"])
        return f"{base_id}:{uuid.uuid4().hex[:6]}", None
    return base_id, None


def agent_result_payload(result: Any) -> dict[str, Any]:
    """Project an agent-plane RunResult onto the node's declared outputs.

    This is the ONE place the run-status vocabulary is interpreted. It used to
    live inline in `bootstrap._agent_runner` and accepted only `succeeded`,
    which turned every real (completed) agent turn into a node failure.
    """
    status = getattr(result.status, "value", str(result.status))
    if status not in RUN_SUCCESS_STATUSES:
        error = getattr(result, "error", None)
        message = getattr(error, "message", None) or status
        raise ValueError(f"agent run {status}: {message}")
    finding = {
        "text": getattr(result, "output", None) or "",
        "runId": getattr(result, "runId", None),
        "status": status,
        "research": getattr(result, "research", None),
        "tokens": getattr(result, "totalTokens", None),
        "toolCalls": getattr(result, "toolCalls", None),
    }
    return {"finding": finding, "evidence": getattr(result, "research", None) or {}}


def exec_research_agent(context: NodeExecContext) -> dict[str, Any]:
    objective = str(
        context.inputs.get("query") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.research needs a query input or a configured objective")
    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    config = {
        "agent": str(context.config.get("agent") or "eclipse-agent"),
        "objective": objective,
        "maxSteps": int(context.config.get("maxSteps", 8)),
    }
    result = _runner(context, config, objective)
    if not isinstance(result, dict):
        raise ValueError("the agent runner returned no structured result")
    return result


def exec_plan_agent(context: NodeExecContext) -> dict[str, Any]:
    objective = str(
        context.inputs.get("objective") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.plan needs an objective input or a configured objective")
    if _plan_runner is None:
        raise ValueError("the step planner is not configured in this graph runtime")
    plan = _plan_runner(context, objective)
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        raise ValueError("the step planner returned no structured plan")
    context.emit(f"planned {len(plan['steps'])} step(s)")
    return {
        "plan": plan,
        "steps": plan["steps"],
        "summary": {
            "stepCount": len(plan["steps"]),
            "rationale": plan.get("rationale") or "",
        },
    }


def exec_delegate_agent(context: NodeExecContext) -> dict[str, Any]:
    tasks = _tasks(context)
    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    agent = str(context.config.get("agent") or "eclipse-agent")
    max_steps = int(context.config.get("maxSteps", 8))
    findings: list[dict[str, Any]] = []
    failed = 0
    for index, task in enumerate(tasks):
        context.emit(f"delegating {index + 1}/{len(tasks)}: {task['title']}")
        try:
            result = _runner(context, {
                "agent": agent,
                "objective": task["objective"],
                "maxSteps": max_steps,
            }, task["objective"])
            if not isinstance(result, dict):
                raise ValueError("the agent runner returned no structured result")
            findings.append({
                "title": task["title"],
                "objective": task["objective"],
                "status": "succeeded",
                "finding": result.get("finding"),
                "evidence": result.get("evidence"),
            })
        except Exception as exc:  # noqa: BLE001 - one failed part is a partial answer
            failed += 1
            findings.append({
                "title": task["title"],
                "objective": task["objective"],
                "status": "failed",
                "error": str(exc),
            })
    succeeded = len(findings) - failed
    status = "OK" if failed == 0 else ("PARTIAL" if succeeded else "FAILED")
    context.emit(f"delegated {succeeded}/{len(findings)} task(s), status {status}")
    return {
        "findings": findings,
        "summary": {
            "status": status,
            "total": len(findings),
            "succeeded": succeeded,
            "failed": failed,
        },
    }


def build_agent_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="agent.research", version="1.0.0", label="Research agent",
            category="agent",
            # Optional: the configured `objective` is a valid alternative, and
            # `exec_research_agent` prefers the input when one is wired.
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="evidence", name="Evidence", type=PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("agentVersion", "integer", 0, minimum=0, maximum=1_000_000),
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_research_agent,
            metadata={
                "docs": (
                    "Runs the EXISTING agent runtime for one bounded turn. Requires "
                    "an operator run with network + agent.run grants; the front door "
                    "resolves model settings into memory, never into the durable job."
                ),
            },
        ),
        NodeDef(
            type="agent.plan", version="1.0.0", label="Plan steps",
            category="agent",
            inputs=(PortDef(id="objective", name="Objective", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="plan", name="Plan", type=PortType.OBJECT),
                PortDef(id="steps", name="Steps", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("objective", "string", "", max_length=2_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=300_000,
            executor=exec_plan_agent,
            metadata={
                "docs": (
                    "One bounded model call that returns 1-8 independent steps. It does "
                    "not execute them; wire the steps into agent.delegate or the graph."
                ),
            },
        ),
        NodeDef(
            type="agent.delegate", version="1.0.0", label="Delegate tasks",
            category="agent",
            inputs=(PortDef(id="tasks", name="Tasks", type=PortType.ARRAY, optional=True),),
            outputs=(
                PortDef(id="findings", name="Findings", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("tasksJson", "string", "", max_length=20_000),
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("agentVersion", "integer", 0, minimum=0, maximum=1_000_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
                ConfigField("maxTasks", "integer", 4, minimum=1, maximum=MAX_DELEGATE_TASKS),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_delegate_agent,
            metadata={
                "docs": (
                    "Runs each task as one bounded turn on the existing agent plane. "
                    "A failed part is reported as failed; partial answers are explicit."
                ),
            },
        ),
    ]


__all__ = [
    "RUN_SUCCESS_STATUSES",
    "agent_result_payload",
    "agent_run_identity",
    "build_agent_nodes",
    "set_agent_runner",
    "set_plan_runner",
    "exec_research_agent",
    "exec_plan_agent",
    "exec_delegate_agent",
]
