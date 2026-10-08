"""The model-facing A2A tools.

Registered on the SAME `ToolRegistry` as every other tool, so argument validation,
the permission/effect gate and timeouts apply unchanged. Each handler resolves the
per-run `A2AService` from the `ToolContext` (rebuilt from `ctx.memory_store` and
`ctx.bus`, exactly like the task and orchestration tools — no new ToolContext
fields, no change to `execute_run`).

Permission is `read`: an A2A message/delegation is agent-local runtime state, not
an external data mutation (the same rule the `memory` and `task_*` tools follow).
A real-world EFFECT still requires the per-action approval whenever it is finally
executed by the runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .model import A2AResult, MessagePriority, MessageType
from .service import A2AError, A2AService

log = logging.getLogger("harness.a2a.tools")

#: The A2A tool surface. Spread into `ECLIPSE_AGENT.tools` so the default agent
#: can orchestrate; other agents reach them only if their definition allows it.
A2A_TOOLS: tuple[str, ...] = (
    "delegate_task",
    "spawn_agent",
    "send_message",
    "receive_message",
    "wait_agent",
    "cancel_agent",
    "merge_results",
    "ask_agent",
    "broadcast_message",
    "get_agent",
    "list_agents",
    "get_agent_status",
    "get_task_status",
    "get_task_result",
    "request_review",
    "request_approval",
    "report_failure",
)


class _ContextHost:
    """The minimal host an `A2AService` needs, built from a live ToolContext."""

    def __init__(self, ctx: ToolContext) -> None:
        self.store = ctx.memory_store
        self.bus = getattr(ctx, "bus", None)
        self.evidence_store = getattr(ctx, "evidence_store", None)
        self.registry = getattr(ctx, "tool_registry", None)
        self.tasks = None

    def run(self, *_args: Any, **_kwargs: Any):  # pragma: no cover - not executed here
        raise RuntimeError("the per-run A2A host does not execute runs")


_CACHE: dict[tuple[str, int], A2AService] = {}
_MAX_CACHED = 64


def a2a_for(ctx: ToolContext) -> A2AService:
    """The per-run A2A service, cached by (runId, store identity)."""
    key = (ctx.run_id or "anonymous", id(ctx.memory_store))
    service = _CACHE.get(key)
    if service is None:
        if len(_CACHE) >= _MAX_CACHED:
            _CACHE.pop(next(iter(_CACHE)))
        service = A2AService(_ContextHost(ctx))
        _CACHE[key] = service
    return service


def forget_a2a(run_id: str) -> None:
    for key in [k for k in _CACHE if k[0] == run_id]:
        _CACHE.pop(key, None)


def _sender(ctx: ToolContext) -> str:
    return getattr(ctx, "agent_id", None) or "eclipse-agent"


def _ok(text: str, data: dict[str, Any]) -> tuple[str, Any]:
    return text, {"status": "ok", **data}


def _refused(exc: A2AError) -> tuple[str, Any]:
    return f"Couldn't do that: {exc.reason}", {
        "status": "refused", "code": exc.code, "reason": exc.reason, "detail": exc.detail,
    }


# ── delegation handlers ─────────────────────────────────────────────────────────


async def delegate_task_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = await service.delegate_task(
            sender_agent_id=_sender(ctx), run_id=ctx.run_id,
            objective=str(args.get("objective") or ""),
            target_agent_id=args.get("agentId"), capability=args.get("capability"),
            context=str(args.get("context") or ""),
            tool_subset=args.get("tools"), priority=str(args.get("priority") or "NORMAL"),
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok(
        f"Delegated to {result['childAgentId']} as task {result['taskId']}.",
        {"delegation": result},
    )


async def spawn_agent_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    overrides = {
        k: args[k] for k in ("name", "systemInstructions", "tools") if args.get(k) is not None
    }
    try:
        result = await service.spawn_agent(
            sender_agent_id=_sender(ctx), run_id=ctx.run_id,
            base_agent_id=str(args.get("baseAgentId") or "research-agent"),
            objective=str(args.get("objective") or ""),
            overrides=overrides, context=str(args.get("context") or ""),
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok(
        f"Spawned {result['spawnedAgentId']} for task {result['taskId']}.",
        {"delegation": result},
    )


# ── messaging handlers ──────────────────────────────────────────────────────────


async def send_message_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        envelope = service.send_message(
            sender_agent_id=_sender(ctx), recipient_agent_id=args.get("recipientAgentId"),
            message_type=str(args.get("type") or MessageType.STATUS.value),
            payload=args.get("payload") or {}, run_id=ctx.run_id,
            task_id=args.get("taskId"), priority=str(args.get("priority") or "NORMAL"),
            evidence_refs=args.get("evidenceRefs"),
        )
    except A2AError as exc:
        return _refused(exc)
    except Exception as exc:  # noqa: BLE001 - a protocol error is a refusal
        return f"That message was refused: {exc}", {"status": "refused", "code": "A2A_PROTOCOL"}
    return _ok(f"Sent {envelope.type.value} to {envelope.recipient_agent_id or 'all'}.", {
        "messageId": envelope.id, "type": envelope.type.value,
        "correlationId": envelope.correlation_id,
    })


async def receive_message_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    messages = service.receive_message(recipient_agent_id=_sender(ctx), limit=int(args.get("limit") or 20))
    return _ok(f"{len(messages)} message(s).", {"messages": messages})


async def ask_agent_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = await service.ask_agent(
            sender_agent_id=_sender(ctx),
            recipient_agent_id=str(args.get("recipientAgentId") or ""),
            question=str(args.get("question") or ""), run_id=ctx.run_id,
            wait=bool(args.get("wait")), timeout_s=float(args.get("timeoutS") or 60.0),
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok(
        f"Asked {args.get('recipientAgentId')}; answer task {result['answerTaskId']}.",
        {"question": result},
    )


async def broadcast_message_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    result = service.broadcast_message(
        sender_agent_id=_sender(ctx), message_type=str(args.get("type") or MessageType.STATUS.value),
        payload=args.get("payload") or {}, run_id=ctx.run_id,
        priority=str(args.get("priority") or "NORMAL"),
    )
    return _ok(f"Broadcast {result['type']}.", result)


async def wait_agent_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        status = await service.wait_agent(
            task_id=str(args.get("taskId") or ""), timeout_s=float(args.get("timeoutS") or 60.0),
        )
    except A2AError as exc:
        return _refused(exc)
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't wait: {exc}", {"status": "error", "code": "A2A_TASK_UNAVAILABLE"}
    return _ok(f"Task is {status['status']}.", {"task": status})


async def cancel_agent_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    result = await service.cancel_agent(
        run_id=ctx.run_id, task_id=args.get("taskId"),
        delegation_id=args.get("delegationId"), reason=str(args.get("reason") or ""),
    )
    return _ok(f"Cancelled {len(result['cancelledTaskIds'])} task(s).", result)


async def merge_results_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    raw = args.get("results")
    if not isinstance(raw, list) or not raw:
        return "Provide a non-empty list of results to merge.", {"status": "error", "code": "INVALID_INPUT"}
    try:
        merged = service.merge_results(raw)
    except Exception as exc:  # noqa: BLE001
        return f"That merge failed: {exc}", {"status": "error", "code": "INVALID_INPUT"}
    return _ok(merged.get("summary") or "Merged.", {"merged": merged})


# ── introspection handlers ────────────────────────────────────────────────────────


async def get_agent_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        agent = service.get_agent(str(args.get("agentId") or ""))
    except A2AError as exc:
        return _refused(exc)
    return _ok(f"{agent['name']} ({agent['status']}).", {"agent": agent})


async def list_agents_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    agents = service.list_agents(status=args.get("status"))
    return _ok(f"{len(agents)} agent(s).", {"agents": agents})


async def get_agent_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        status = service.agent_status(str(args.get("agentId") or ""))
    except A2AError as exc:
        return _refused(exc)
    return _ok(f"{status['agentId']}: {status['status']}.", {"agent": status})


async def get_task_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        status = service.get_task_status(str(args.get("taskId") or ""))
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't read that task: {exc}", {"status": "error", "code": "A2A_TASK_UNAVAILABLE"}
    return _ok(f"Task is {status['status']}.", {"task": status})


async def get_task_result_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = service.get_task_result(str(args.get("taskId") or ""))
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't read that task: {exc}", {"status": "error", "code": "A2A_TASK_UNAVAILABLE"}
    return _ok(f"Task is {result['status']}.", {"task": result})


# ── review / approval / failure ───────────────────────────────────────────────────


async def request_review_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = service.request_review(
            sender_agent_id=_sender(ctx), run_id=ctx.run_id, subject=str(args.get("subject") or ""),
            task_id=args.get("taskId"), target_agent_id=str(args.get("agentId") or "qa-agent"),
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok("Requested a review.", result)


async def request_approval_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = service.request_approval(
            sender_agent_id=_sender(ctx), run_id=ctx.run_id, subject=str(args.get("subject") or ""),
            kind=str(args.get("kind") or "action"), task_id=args.get("taskId"),
            detail=args.get("detail") or {},
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok("Approval requested.", result)


async def report_failure_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = a2a_for(ctx)
    try:
        result = service.report_failure(
            sender_agent_id=_sender(ctx), run_id=ctx.run_id, task_id=args.get("taskId"),
            error=str(args.get("error") or "unspecified failure"),
            error_class=str(args.get("errorClass") or "A2A_FAILURE"),
        )
    except A2AError as exc:
        return _refused(exc)
    return _ok("Failure reported.", result)


# ── schemas / registration ─────────────────────────────────────────────────────

def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [],
            "additionalProperties": False}


def _str(desc: str = "") -> dict[str, Any]:
    return {"type": "string", "description": desc} if desc else {"type": "string"}


_PRIORITY = {"type": "string", "enum": [p.value for p in MessagePriority]}
_MESSAGE_TYPES = {"type": "string", "enum": [t.value for t in MessageType]}


def _definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="delegate_task",
            description=(
                "Delegate one independent piece of work to a specialist agent. Returns a "
                "durable task handle immediately (non-blocking); the scheduler runs it. "
                "Name a target agent or a capability and the registry picks a capable agent."
            ),
            input_schema=_obj({
                "objective": _str("The one independent objective for the target agent."),
                "agentId": _str("A specific target agent id (optional)."),
                "capability": _str("A capability noun; the registry selects an agent (optional)."),
                "context": _str("Background only this sub-task needs."),
                "tools": {"type": "array", "items": {"type": "string"}},
                "priority": _PRIORITY,
            }, ["objective"]),
            handler=delegate_task_handler,
        ),
        ToolDefinition(
            name="spawn_agent",
            description=(
                "Spawn a temporary specialist from a base agent, inheriting only the "
                "intersection of your tools and capabilities, then delegate work to it."
            ),
            input_schema=_obj({
                "baseAgentId": _str("The agent profile to specialize."),
                "objective": _str("The objective for the spawned agent."),
                "name": _str("Optional display name."),
                "systemInstructions": _str("Optional extra instructions (narrowing only)."),
                "tools": {"type": "array", "items": {"type": "string"}},
                "context": _str("Background for the spawned agent."),
            }, ["baseAgentId", "objective"]),
            handler=spawn_agent_handler,
        ),
        ToolDefinition(
            name="send_message",
            description="Send a typed A2A message to another agent (or all agents).",
            input_schema=_obj({
                "type": _MESSAGE_TYPES,
                "recipientAgentId": _str("Omit to broadcast."),
                "payload": {"type": "object"},
                "taskId": _str(),
                "priority": _PRIORITY,
                "evidenceRefs": {"type": "array", "items": {"type": "string"}},
            }, ["type"]),
            handler=send_message_handler,
        ),
        ToolDefinition(
            name="receive_message",
            description="Claim and read pending A2A messages addressed to you.",
            input_schema=_obj({"limit": {"type": "integer"}}),
            handler=receive_message_handler,
        ),
        ToolDefinition(
            name="ask_agent",
            description="Ask another agent a structured question; it becomes a delegated task.",
            input_schema=_obj({
                "recipientAgentId": _str(), "question": _str(),
                "wait": {"type": "boolean"}, "timeoutS": {"type": "number"},
            }, ["recipientAgentId", "question"]),
            handler=ask_agent_handler,
        ),
        ToolDefinition(
            name="broadcast_message",
            description="Broadcast a typed message to every active agent.",
            input_schema=_obj({"type": _MESSAGE_TYPES, "payload": {"type": "object"}, "priority": _PRIORITY},
                              ["type"]),
            handler=broadcast_message_handler,
        ),
        ToolDefinition(
            name="wait_agent",
            description="Wait (event-driven, non-blocking) for a delegated task to reach a terminal state.",
            input_schema=_obj({"taskId": _str(), "timeoutS": {"type": "number"}}, ["taskId"]),
            handler=wait_agent_handler,
        ),
        ToolDefinition(
            name="cancel_agent",
            description="Cancel a delegated task (or all of a run's delegations).",
            input_schema=_obj({"taskId": _str(), "delegationId": _str(), "reason": _str()}),
            handler=cancel_agent_handler,
        ),
        ToolDefinition(
            name="merge_results",
            description=(
                "Merge structured agent results: normalizes, deduplicates, links evidence, "
                "detects conflicts and computes confidence. Never concatenates prose."
            ),
            input_schema=_obj({
                "results": {"type": "array", "items": {"type": "object"}},
            }, ["results"]),
            handler=merge_results_handler,
        ),
        ToolDefinition(
            name="get_agent",
            description="Read one agent definition from the registry.",
            input_schema=_obj({"agentId": _str()}, ["agentId"]),
            handler=get_agent_handler,
        ),
        ToolDefinition(
            name="list_agents",
            description="List registered agents and their capabilities.",
            input_schema=_obj({"status": _str("Optional status filter.")}),
            handler=list_agents_handler,
        ),
        ToolDefinition(
            name="get_agent_status",
            description="Read an agent's status, health and active delegation count.",
            input_schema=_obj({"agentId": _str()}, ["agentId"]),
            handler=get_agent_status_handler,
        ),
        ToolDefinition(
            name="get_task_status",
            description="Read a delegated task's status and readiness.",
            input_schema=_obj({"taskId": _str()}, ["taskId"]),
            handler=get_task_status_handler,
        ),
        ToolDefinition(
            name="get_task_result",
            description="Read a delegated task's result, output reference and artifacts.",
            input_schema=_obj({"taskId": _str()}, ["taskId"]),
            handler=get_task_result_handler,
        ),
        ToolDefinition(
            name="request_review",
            description="Ask the QA/review agent to review a subject or task.",
            input_schema=_obj({"subject": _str(), "taskId": _str(), "agentId": _str()}, ["subject"]),
            handler=request_review_handler,
        ),
        ToolDefinition(
            name="request_approval",
            description="Request an explicit approval for an approval-gated action (e.g. trading).",
            input_schema=_obj({"subject": _str(), "kind": _str(), "taskId": _str(),
                               "detail": {"type": "object"}}, ["subject"]),
            handler=request_approval_handler,
        ),
        ToolDefinition(
            name="report_failure",
            description="Report a task failure to the orchestrator so the workflow can react.",
            input_schema=_obj({"error": _str(), "taskId": _str(), "errorClass": _str()}, ["error"]),
            handler=report_failure_handler,
        ),
    ]


def register_a2a_tools(registry: ToolRegistry) -> list[str]:
    """Register the A2A tools, skipping any name already taken. Returns names added."""
    names: list[str] = []
    for tool in _definitions():
        if registry.get(tool.name) is not None:
            continue
        registry.register(tool)
        names.append(tool.name)
    return names


__all__ = [
    "A2A_TOOLS",
    "a2a_for",
    "forget_a2a",
    "register_a2a_tools",
]
