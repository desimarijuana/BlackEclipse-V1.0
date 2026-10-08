"""Node execution — the ONE seam between the scheduler and real work.

A node kind maps to exactly one runner strategy, and every strategy reaches the
EXISTING runtime: an `agent` node calls `execute_run` (the one execution plane),
a `tool` node calls `ToolRegistry.execute` (the one tool seam), a `function` node
calls a callable the engine itself registered (used by map/reduce), and an
`aggregate`/`join` node combines structured dependency outputs.

The runner never decides policy: retries, timeouts, cancellation, dedup and
resource admission are the engine's job. The runner returns a `NodeOutcome`.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .aggregate import aggregate
from .models import ExecutionGraph, ExecutionNode, NodeError, NodeKind, NodeOutcome
from .retry import is_retryable


@dataclass
class RuntimeContext:
    """Everything a node runner needs, assembled from the invoking run.

    `tool_context` is the live `ToolContext` when the engine was started from
    inside an agent run; the API/scheduled path leaves it None and the runner
    builds a minimal one from the fields here.
    """

    registry: Any = None
    data_bridge: Any = None
    store: Any = None
    bus: Any = None
    model_settings: Any = None
    allowed: Optional[set[str]] = None
    actor: Any = None
    base_request: Any = None
    run_id: str = ""
    user_id: Optional[str] = None
    callback_base_url: str = ""
    callback_token: Optional[str] = None
    tool_context: Any = None
    memory_service: Any = None
    skill_registry: Any = None
    approvals: Any = None
    memory_router: Any = None
    mcp_manager: Any = None
    retrieval_cache: Any = None
    code_store: Any = None
    evidence_store: Any = None
    # Callables addressable by a `function` node. Only the engine registers these;
    # a model can never name an arbitrary callable.
    callables: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def extend(self, **updates: Any) -> "RuntimeContext":
        from dataclasses import replace

        return replace(self, **updates)


def narrow_allowed(parent: Optional[set[str]], requested: Optional[list[str]]) -> Optional[set[str]]:
    """A child's tool set is a subset of its parent's — never a superset."""
    if requested is None:
        return set(parent) if parent is not None else None
    wanted = {str(t) for t in requested}
    if parent is None:
        return wanted
    return {t for t in wanted if t in parent}


class NodeRunner(ABC):
    """Base for node runners. An implementation returns a `NodeOutcome`."""

    @abstractmethod
    async def run(self, node: ExecutionNode, context: RuntimeContext,
                  graph: Optional[ExecutionGraph] = None) -> NodeOutcome:
        """Execute one node and return its structured outcome."""


class DefaultNodeRunner(NodeRunner):
    def __init__(self, context: RuntimeContext) -> None:
        self.context = context

    async def run(self, node: ExecutionNode, context: RuntimeContext,
                  graph: Optional[ExecutionGraph] = None) -> NodeOutcome:
        if node.kind is NodeKind.NOOP:
            return NodeOutcome(output=(node.input or {}).get("value"))
        if node.kind is NodeKind.FUNCTION:
            return await self._function(node)
        if node.kind is NodeKind.TOOL:
            return await self._tool(node, context)
        if node.kind is NodeKind.AGENT:
            return await self._agent(node, context, graph)
        if node.kind in (NodeKind.AGGREGATE, NodeKind.JOIN):
            if graph is None:
                return NodeOutcome(error=NodeError("GRAPH_UNAVAILABLE", "no graph for aggregation"))
            return NodeOutcome(output=aggregate(graph, node))
        return NodeOutcome(error=NodeError(
            "UNSUPPORTED_NODE_KIND", f"node kind {node.kind.value!r} has no runner", retryable=False,
        ))

    # ── function ──────────────────────────────────────────────────────────────

    async def _function(self, node: ExecutionNode) -> NodeOutcome:
        name = str((node.input or {}).get("function") or "")
        callable_ = self.context.callables.get(name)
        if callable_ is None:
            return NodeOutcome(error=NodeError(
                "FUNCTION_NOT_FOUND", f"no registered callable named {name!r}", retryable=False,
            ))
        args = (node.input or {}).get("args") or {}
        try:
            result = callable_(args, node)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # noqa: BLE001 - a function failure is data
            code = getattr(exc, "code", "FUNCTION_ERROR")
            return NodeOutcome(error=NodeError(str(code), str(exc), retryable=is_retryable(str(code))))
        if isinstance(result, NodeOutcome):
            return result
        return NodeOutcome(output=result)

    # ── tool ──────────────────────────────────────────────────────────────────

    async def _tool(self, node: ExecutionNode, context: RuntimeContext) -> NodeOutcome:
        from ..tools import ToolContext

        spec = node.input or {}
        name = str(spec.get("tool") or spec.get("name") or "")
        if not name:
            return NodeOutcome(error=NodeError("INVALID_INPUT", "tool node has no tool name"))
        args = spec.get("args") or {}
        tool_ctx = context.tool_context
        if tool_ctx is None:
            tool_ctx = ToolContext(
                run_id=context.run_id or node.execution_id,
                log=lambda *a, **k: None,
                allowed=context.allowed,
                memory_store=context.store,
                bus=context.bus,
                data_bridge=context.data_bridge,
                tool_registry=context.registry,
                model_settings=context.model_settings,
            )
        result = await context.registry.execute(
            name, f"{node.id}_call", args, tool_ctx, allowed=context.allowed,
        )
        if result.ok:
            return NodeOutcome(output=result.data if result.data is not None else result.text)
        err = result.error
        code = str(getattr(err, "code", None) or "TOOL_ERROR")
        message = str(getattr(err, "message", None) or result.text or code)
        return NodeOutcome(error=NodeError(code, message, retryable=is_retryable(code)))

    # ── agent ─────────────────────────────────────────────────────────────────

    async def _agent(self, node: ExecutionNode, context: RuntimeContext,
                     graph: Optional[ExecutionGraph]) -> NodeOutcome:
        from ..graph import execute_run
        from ..schemas import AgentConfig, RunInput, RunRequest

        base = context.base_request
        spec = node.input or {}
        model_settings = context.model_settings or (base.modelSettings if base else None)
        if model_settings is None:
            return NodeOutcome(error=NodeError(
                "PROVIDER_NOT_CONFIGURED", "agent node has no model settings", retryable=False,
            ))

        query = str(
            spec.get("query") or spec.get("instruction")
            or (base.input.query if base else "task")
        )
        child_run_id = str(spec.get("runId") or f"{context.run_id or node.execution_id}_{node.id}")
        requested = spec.get("tools") if isinstance(spec.get("tools"), list) else None
        allowed = narrow_allowed(context.allowed, requested)

        agent: Optional[AgentConfig] = None
        if spec.get("systemPrompt"):
            agent = AgentConfig(
                id=str(spec.get("agentId") or "orchestration-node"),
                name=str(spec.get("name") or "Orchestration node"),
                systemPrompt=str(spec["systemPrompt"]),
                tools=sorted(allowed) if allowed is not None else None,
                maxSteps=int(spec.get("maxSteps") or 6),
            )

        child_context = dict(spec.get("context") or {})
        child_context["_orchestration"] = {
            "executionId": node.execution_id, "nodeId": node.id,
        }
        child = RunRequest(
            runId=child_run_id,
            input=RunInput(
                query=query[:4000],
                ticker=spec.get("ticker"),
                market=spec.get("market"),
                context=child_context,
            ),
            agentId=(None if agent is not None else (spec.get("agentId") or (base.agentId if base else None))),
            agent=agent,
            modelSettings=model_settings,
            userId=context.user_id or (base.userId if base else None),
            parentRunId=context.run_id or (base.parentRunId if base else None),
            sessionId=(base.sessionId if base else None),
            profileId=(base.profileId if base else None),
            projectId=(base.projectId if base else None),
            callbackBaseUrl=context.callback_base_url or (base.callbackBaseUrl if base else "http://127.0.0.1"),
            callbackToken=context.callback_token,
            workspaceId=spec.get("workspaceId"),
        )
        try:
            result = await execute_run(
                child, context.registry, context.data_bridge, context.store, context.bus,
                retrieval_cache=context.retrieval_cache,
                memory_service=context.memory_service,
                skill_registry=context.skill_registry,
                approvals=context.approvals,
                memory_router=context.memory_router,
                mcp_manager=context.mcp_manager,
                code_store=context.code_store,
                evidence_store=context.evidence_store,
            )
        except Exception as exc:  # noqa: BLE001 - a child crash is a node failure
            return NodeOutcome(error=NodeError("AGENT_ERROR", f"{type(exc).__name__}: {exc}",
                                                retryable=True))
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        status = dumped.get("status")
        if status == "completed":
            return NodeOutcome(output=dumped.get("output"))
        error = dumped.get("error") or {}
        code = str(error.get("code") or ("CANCELLED" if status == "cancelled" else "AGENT_FAILED"))
        return NodeOutcome(error=NodeError(
            code, str(error.get("message") or f"agent node ended {status}"),
            retryable=is_retryable(code),
        ))


__all__ = ["DefaultNodeRunner", "NodeRunner", "RuntimeContext", "narrow_allowed"]
