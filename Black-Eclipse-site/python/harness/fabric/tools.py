"""LLM-facing tools for the Execution Fabric.

These register on the SAME tool registry as every other subsystem, so validation,
permission and effect authorization apply unchanged. They are thin wrappers over
the ONE ExecutionManager, so the agent and the UI can never disagree about what
is running.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry

TOOL_NAMES = (
    "fabric_submit",
    "fabric_job_status",
    "fabric_jobs_list",
    "fabric_job_cancel",
    "fabric_jobs_children",
    "fabric_dlq_list",
    "fabric_job_retry",
    "fabric_workers",
    "fabric_stats",
)

_manager: Any = None


def set_fabric_manager(manager: Any) -> None:
    global _manager
    _manager = manager


def get_fabric_manager() -> Any:
    return _manager


def _require_manager() -> Any:
    if _manager is None:
        raise RuntimeError("the Execution Fabric is unavailable")
    return _manager


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


async def _submit(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    job_type = str(args.get("type") or "tool")
    payload: dict[str, Any] = {}
    for key in ("input", "tool", "args", "query", "objective", "agentId", "automationId"):
        if args.get(key) is not None:
            payload[key] = args[key]
    result = await manager.submit(
        job_type, payload,
        mode=args.get("mode"), queue=args.get("queue"), priority=args.get("priority"),
        agent_id=args.get("agentId"), task_id=args.get("taskId"),
        session_id=args.get("sessionId"), user_id=args.get("userId"),
        idempotency_key=args.get("idempotencyKey"),
        parent_job_id=args.get("parentJobId"),
        metadata={"source": "agent"},
    )
    return _dumps(result), result


async def _status(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    job_id = str(args.get("jobId") or "")
    job = manager.get(job_id)
    if job is None:
        return f"No job {job_id!r}.", {"jobId": job_id, "found": False}
    return _dumps({k: job.get(k) for k in ("jobId", "type", "status", "queue", "progress", "attempts")}), job


async def _list(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    jobs = manager.list_jobs(
        queue=args.get("queue"), status=args.get("status"), type=args.get("type"),
        limit=int(args.get("limit") or 50),
    )
    return _dumps({"jobs": jobs}), {"jobs": jobs}


async def _cancel(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    result = await manager.cancel(str(args.get("jobId") or ""))
    return _dumps(result), result


async def _children(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    jobs = manager.children(str(args.get("jobId") or ""), limit=int(args.get("limit") or 100))
    return _dumps({"jobs": jobs}), {"jobs": jobs}


async def _dlq(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    jobs = manager.dlq(limit=int(args.get("limit") or 50))
    return _dumps({"deadLetters": jobs}), {"deadLetters": jobs}


async def _retry(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    result = await manager.retry(str(args.get("jobId") or ""))
    return _dumps(result), result


async def _workers(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    status = manager.worker_manager.status()
    return _dumps(status), status


async def _stats(args: dict[str, Any], _ctx: ToolContext) -> tuple[str, Any]:
    manager = _require_manager()
    stats = manager.stats()
    return _dumps(stats), stats


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def register_fabric_tools(registry: ToolRegistry) -> list[str]:
    """Register the fabric tools. Idempotent per name (returns the ones added)."""
    definitions = [
        ToolDefinition(
            name="fabric_submit", description="Submit a unit of work to the Eclipse Execution Fabric. "
            "Set mode to DIRECT/CONCURRENT/BACKGROUND/DURABLE (defaults by type).",
            input_schema=_obj({
                "type": {"type": "string", "description": "job type: tool, agent, research, browser, market, quant, python, code, plugin, notification, automation, event"},
                "mode": {"type": "string", "enum": ["DIRECT", "CONCURRENT", "BACKGROUND", "DURABLE"]},
                "queue": {"type": "string"}, "priority": {"type": "string"},
                "tool": {"type": "string"}, "args": {"type": "object"},
                "query": {"type": "string"}, "objective": {"type": "string"},
                "agentId": {"type": "string"}, "automationId": {"type": "string"},
                "idempotencyKey": {"type": "string"}, "sessionId": {"type": "string"},
            }, ["type"]),
            handler=_submit, permission="read", risk="low", timeout_ms=900_000, long_running=True,
        ),
        ToolDefinition(
            name="fabric_job_status", description="Get the status of a Fabric job by id.",
            input_schema=_obj({"jobId": {"type": "string"}}, ["jobId"]),
            handler=_status, permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_jobs_list", description="List Fabric jobs, optionally filtered.",
            input_schema=_obj({"queue": {"type": "string"}, "status": {"type": "string"},
                               "type": {"type": "string"}, "limit": {"type": "integer"}}),
            handler=_list, permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_job_cancel", description="Cancel a Fabric job, propagating to the worker.",
            input_schema=_obj({"jobId": {"type": "string"}}, ["jobId"]),
            handler=_cancel, permission="read", risk="low", timeout_ms=15_000,
        ),
        ToolDefinition(
            name="fabric_jobs_children", description="List child jobs of a Fabric job.",
            input_schema=_obj({"jobId": {"type": "string"}, "limit": {"type": "integer"}}, ["jobId"]),
            handler=_children, permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_dlq_list", description="List dead-lettered Fabric jobs.",
            input_schema=_obj({"limit": {"type": "integer"}}),
            handler=_dlq, permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_job_retry", description="Re-queue a failed/timed-out/dead-lettered job.",
            input_schema=_obj({"jobId": {"type": "string"}}, ["jobId"]),
            handler=_retry, permission="read", risk="low", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_workers", description="Show Fabric workers, queue depths and health.",
            input_schema=_obj({}),
            handler=_workers, permission="read", risk="none", timeout_ms=10_000,
        ),
        ToolDefinition(
            name="fabric_stats", description="Show Execution Fabric queue/status statistics.",
            input_schema=_obj({}),
            handler=_stats, permission="read", risk="none", timeout_ms=10_000,
        ),
    ]
    added: list[str] = []
    for definition in definitions:
        if registry.get(definition.name) is None:
            registry.register(definition)
            added.append(definition.name)
    return added


__all__ = ["TOOL_NAMES", "get_fabric_manager", "register_fabric_tools", "set_fabric_manager"]
