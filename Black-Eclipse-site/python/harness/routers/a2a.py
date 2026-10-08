"""A2A route group.

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — this module never imports `main`.

EVERY route carries `require_operator` — reads AND mutations — exactly as the
tasks, jobs and MCP route groups do. The routes are a thin shell over
`A2AService`; they never mutate state themselves, so the registry state machine,
budget enforcement and approval gate apply to HTTP callers exactly as they do to
the agent tools.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..a2a.model import AgentDefinition, MessageType
from ..a2a.registry import RegistryError
from ..a2a.service import A2AError, A2AService
from ..deps import require_operator, service

router = APIRouter(tags=["a2a"])


def _a2a() -> A2AService:
    a2a = getattr(service, "a2a", None)
    if a2a is None:
        from ..a2a.bootstrap import install_a2a_layer  # noqa: PLC0415

        install_a2a_layer(service)
        a2a = getattr(service, "a2a", None)
    if a2a is None:
        raise HTTPException(status_code=503, detail="A2A runtime unavailable")
    return a2a


def _raise(exc: Exception) -> None:
    if isinstance(exc, RegistryError):
        code = 404 if exc.code == "AGENT_NOT_FOUND" else 400
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.reason})
    if isinstance(exc, A2AError):
        code = 404 if exc.code == "A2A_NO_AGENT" else 400
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.reason})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


# ── bodies ────────────────────────────────────────────────────────────────────


class DelegateBody(BaseModel):
    objective: str = Field(..., min_length=1)
    agentId: Optional[str] = None  # noqa: N815
    capability: Optional[str] = None
    context: str = ""
    tools: Optional[list[str]] = None
    priority: str = "NORMAL"
    rootRunId: Optional[str] = None  # noqa: N815


class SpawnBody(BaseModel):
    baseAgentId: str = Field(..., min_length=1)  # noqa: N815
    objective: str = Field(..., min_length=1)
    name: Optional[str] = None
    systemInstructions: Optional[str] = None  # noqa: N815
    tools: Optional[list[str]] = None
    context: str = ""
    rootRunId: Optional[str] = None  # noqa: N815


class MessageBody(BaseModel):
    senderAgentId: str = "eclipse-agent"  # noqa: N815
    recipientAgentId: Optional[str] = None  # noqa: N815
    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    runId: str = ""  # noqa: N815
    taskId: Optional[str] = None  # noqa: N815
    priority: str = "NORMAL"


class MergeBody(BaseModel):
    results: list[dict[str, Any]]
    runId: str = ""  # noqa: N815


class ApprovalBody(BaseModel):
    decision: str


# ── agent registry ─────────────────────────────────────────────────────────────


@router.get("/a2a/agents")
async def list_agents(status: Optional[str] = None, _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "agents": _a2a().list_agents(status=status)}


@router.get("/a2a/capabilities")
async def capability_index(_: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "capabilities": _a2a().capability_index()}


@router.get("/a2a/agents/{agent_id}")
async def get_agent(agent_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "agent": _a2a().get_agent(agent_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/a2a/agents/{agent_id}/status")
async def agent_status(agent_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "agent": _a2a().agent_status(agent_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/a2a/agents")
async def register_agent(body: AgentDefinition, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        saved = _a2a().registry.register_agent(body)
        return {"success": True, "agent": saved.to_public()}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/a2a/agents/{agent_id}/enable")
async def enable_agent(agent_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "agent": _a2a().registry.enable_agent(agent_id).to_public()}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/a2a/agents/{agent_id}/disable")
async def disable_agent(agent_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "agent": _a2a().registry.disable_agent(agent_id).to_public()}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.delete("/a2a/agents/{agent_id}")
async def delete_agent(agent_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "deleted": _a2a().registry.remove_agent(agent_id)}


# ── delegation ─────────────────────────────────────────────────────────────────


@router.post("/a2a/delegate")
async def delegate(body: DelegateBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = await _a2a().delegate_task(
            sender_agent_id="eclipse-orchestrator", run_id=body.rootRunId or "api",
            objective=body.objective, target_agent_id=body.agentId, capability=body.capability,
            context=body.context, tool_subset=body.tools, priority=body.priority,
            root_run_id=body.rootRunId,
        )
        return {"success": True, "delegation": result}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/a2a/spawn")
async def spawn(body: SpawnBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    overrides = {k: v for k, v in {
        "name": body.name, "systemInstructions": body.systemInstructions, "tools": body.tools,
    }.items() if v is not None}
    try:
        result = await _a2a().spawn_agent(
            sender_agent_id="eclipse-orchestrator", run_id=body.rootRunId or "api",
            base_agent_id=body.baseAgentId, objective=body.objective, overrides=overrides,
            context=body.context, root_run_id=body.rootRunId,
        )
        return {"success": True, "delegation": result}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/a2a/delegations")
async def list_delegations(runId: Optional[str] = None, _: Any = Depends(require_operator)) -> dict[str, Any]:  # noqa: N803
    a2a = _a2a()
    records = a2a.store.list_delegations(parent_run_id=runId, limit=200)
    return {"success": True, "delegations": [r.model_dump(by_alias=True) for r in records]}


# ── messages ───────────────────────────────────────────────────────────────────


@router.get("/a2a/messages")
async def list_messages(runId: Optional[str] = None, recipient: Optional[str] = None,  # noqa: N803
                        _: Any = Depends(require_operator)) -> dict[str, Any]:
    envelopes = _a2a().store.list_messages(run_id=runId, recipient=recipient, limit=200)
    return {"success": True, "messages": [e.to_row() for e in envelopes]}


@router.post("/a2a/messages")
async def send_message(body: MessageBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        envelope = _a2a().send_message(
            sender_agent_id=body.senderAgentId, recipient_agent_id=body.recipientAgentId,
            message_type=body.type, payload=body.payload, run_id=body.runId,
            task_id=body.taskId, priority=body.priority,
        )
        return {"success": True, "message": envelope.to_row()}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/a2a/messages/dead-letters")
async def dead_letters(_: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "deadLetters": _a2a().bus.dead_letters()}


# ── results / review / approvals ─────────────────────────────────────────────────


@router.post("/a2a/merge")
async def merge(body: MergeBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "merged": _a2a().merge_results(body.results)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/a2a/qa/{run_id}")
async def qa(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "report": _a2a().qa(run_id)}


@router.get("/a2a/approvals")
async def list_approvals(runId: Optional[str] = None, status: Optional[str] = None,  # noqa: N803
                         _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "approvals": _a2a().store.list_approvals(run_id=runId, status=status)}


@router.post("/a2a/approvals/{approval_id}/decide")
async def decide_approval(approval_id: str, body: ApprovalBody,
                          _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "approval": _a2a().decide_approval(approval_id, body.decision)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


# ── observability ───────────────────────────────────────────────────────────────


@router.get("/a2a/events/{run_id}")
async def list_events(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "events": _a2a().events(run_id)}


@router.get("/a2a/budget/{run_id}")
async def budget(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "budget": _a2a().budget_snapshot(run_id)}


@router.get("/a2a/status")
async def status(_: Any = Depends(require_operator)) -> dict[str, Any]:
    a2a = _a2a()
    return {
        "success": True,
        "status": {
            "agents": len(a2a.list_agents()),
            "capabilities": len(a2a.capability_index()),
            "pendingMessages": len(a2a.store.list_deliveries(status="PENDING", limit=1000)),
            "deadLetters": len(a2a.bus.dead_letters()),
        },
    }
