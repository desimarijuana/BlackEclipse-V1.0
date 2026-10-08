"""The model-facing orchestration tools, on the ONE tool registry.

These handlers are the agent surface for parallel execution. Each builds (or
reuses) an `OrchestrationEngine` from the invoking `ToolContext`, so a tool node
runs through the SAME `ToolRegistry` and an agent node through the SAME
`execute_run` — no second execution path, no second registry.

The engine is cached per parent run so an execution started by one tool call can
be inspected or cancelled by the next (`execution_status`, `execution_cancel`).
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .engine import OrchestrationEngine, EngineConfig
from .models import FailurePolicy, JoinPolicy, ExecutionResult
from .primitives import (
    dependency_graph as _dependency_graph,
    parallel_execute as _parallel_execute,
    task_batch as _task_batch,
    task_fork as _task_fork,
    task_join as _task_join,
    task_map as _task_map,
    task_quorum as _task_quorum,
    task_race as _task_race,
    task_reduce as _task_reduce,
)
from .runner import RuntimeContext
from .store import OrchestrationStore

# Tool names.
TOOL_NAMES = (
    "parallel_execute",
    "task_fork",
    "task_join",
    "task_race",
    "task_quorum",
    "task_map",
    "task_batch",
    "task_reduce",
    "dependency_graph",
    "execution_status",
    "execution_cancel",
)

_ENGINES: dict[tuple, OrchestrationEngine] = {}
_MAX_CACHED_ENGINES = 64


def _reduce_list(args: dict[str, Any], node: Any) -> Any:
    items = args.get("items") or []
    return {"items": items, "count": len(items)}


def _reduce_merge(args: dict[str, Any], node: Any) -> Any:
    merged: dict[str, Any] = {}
    for item in args.get("items") or []:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _reduce_text(args: dict[str, Any], node: Any) -> Any:
    return {"text": "\n".join(str(i) for i in (args.get("items") or []) if i is not None)}


def engine_for(ctx: ToolContext) -> OrchestrationEngine:
    """Return the engine bound to this run + store (created once, then reused)."""
    store = getattr(ctx, "memory_store", None)
    if store is None:
        raise RuntimeError("orchestration requires the harness memory store")
    key = (ctx.run_id or "anonymous", id(store))
    engine = _ENGINES.get(key)
    if engine is not None:
        return engine
    runtime = RuntimeContext(
        registry=getattr(ctx, "tool_registry", None),
        data_bridge=getattr(ctx, "data_bridge", None),
        store=store,
        bus=getattr(ctx, "bus", None),
        model_settings=getattr(ctx, "model_settings", None),
        allowed=getattr(ctx, "allowed", None),
        tool_context=ctx,
        run_id=ctx.run_id,
        user_id=getattr(ctx, "user_id", None),
        callback_base_url=__import__("os").environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        memory_service=getattr(ctx, "memory_service", None),
        skill_registry=getattr(ctx, "skill_registry", None),
        approvals=getattr(ctx, "approvals", None),
        memory_router=getattr(ctx, "memory_router", None),
        mcp_manager=getattr(ctx, "mcp_manager", None),
        retrieval_cache=getattr(ctx, "retrieval_cache", None),
        code_store=getattr(ctx, "code_store", None),
        evidence_store=getattr(ctx, "evidence_store", None),
    )
    engine = OrchestrationEngine(OrchestrationStore(store), runtime, config=EngineConfig.from_env())
    engine.register_callable("reduce_list", _reduce_list)
    engine.register_callable("reduce_merge", _reduce_merge)
    engine.register_callable("reduce_text", _reduce_text)
    if len(_ENGINES) >= _MAX_CACHED_ENGINES:
        _ENGINES.pop(next(iter(_ENGINES)), None)
    _ENGINES[key] = engine
    return engine


def forget_engine(run_id: str) -> None:
    for key in [k for k in _ENGINES if isinstance(k, tuple) and k[0] == run_id]:
        _ENGINES.pop(key, None)


# ── formatting ──────────────────────────────────────────────────────────────


def format_result(result: ExecutionResult) -> str:
    lines = [
        f"Ran {result.total_tasks} task(s): {result.successful_tasks} ok, "
        f"{result.failed_tasks} failed, {result.skipped_tasks} skipped, "
        f"{result.cancelled_tasks} cancelled (coverage {result.coverage:.0%})."
    ]
    for node in result.nodes:
        mark = {
            "COMPLETED": "ok", "FAILED": "failed", "TIMED_OUT": "timeout",
            "CANCELLED": "cancelled", "SKIPPED": "skipped", "BLOCKED": "blocked",
        }.get(node["status"], node["status"].lower())
        line = f"- {node['id']}: {mark}"
        if node.get("error"):
            line += f" ({node['error'].get('code')})"
        lines.append(line)
    if result.critical_path:
        lines.append(f"Critical path: {' -> '.join(result.critical_path)}")
    return "\n".join(lines)


def _refusal(code: str, message: str) -> tuple[str, Any]:
    return f"REFUSED ({code}): {message}", {"status": "refused", "code": code, "reason": message}


# ── handlers ─────────────────────────────────────────────────────────────────


async def parallel_execute_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    tasks = args.get("tasks") or []
    if not isinstance(tasks, list) or not tasks:
        return _refusal("INVALID_INPUT", "parallel_execute needs a non-empty tasks array")
    result = await _parallel_execute(
        engine, tasks,
        concurrency=int(args.get("concurrency") or 0),
        failure_policy=args.get("failurePolicy") or FailurePolicy.CONTINUE,
        aggregate=bool(args.get("aggregate")),
        aggregate_mode=str(args.get("aggregateMode") or "list"),
        metadata={"primitive": "parallel_execute", "runId": ctx.run_id},
    )
    return format_result(result), result.to_dict()


async def task_fork_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    children = args.get("tasks") or args.get("children") or []
    if not isinstance(children, list) or not children:
        return _refusal("INVALID_INPUT", "task_fork needs a non-empty tasks array")
    fork_id, result = await _task_fork(
        engine, children,
        concurrency=int(args.get("concurrency") or 0),
        failure_policy=args.get("failurePolicy") or FailurePolicy.CONTINUE,
    )
    data = result.to_dict()
    data["forkId"] = fork_id
    return f"Forked {fork_id}: {result.successful_tasks}/{result.total_tasks} completed.", data


async def task_join_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    children = args.get("tasks") or args.get("children") or []
    if not isinstance(children, list) or not children:
        return _refusal("INVALID_INPUT", "task_join needs a non-empty tasks array")
    result = await _task_join(
        engine, children,
        policy=args.get("policy") or JoinPolicy.ALL,
        threshold=int(args.get("threshold") or 1),
        aggregate_mode=str(args.get("aggregateMode") or "list"),
    )
    return format_result(result), result.to_dict()


async def task_race_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    racers = args.get("tasks") or args.get("racers") or []
    if not isinstance(racers, list) or not racers:
        return _refusal("INVALID_INPUT", "task_race needs a non-empty tasks array")
    result = await _task_race(engine, racers, aggregate_mode=str(args.get("aggregateMode") or "list"))
    return format_result(result), result.to_dict()


async def task_quorum_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    candidates = args.get("tasks") or args.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return _refusal("INVALID_INPUT", "task_quorum needs a non-empty tasks array")
    quorum = int(args.get("quorum") or 0)
    if quorum < 1:
        return _refusal("INVALID_INPUT", "task_quorum needs a positive quorum")
    result = await _task_quorum(
        engine, candidates, quorum=quorum, aggregate_mode=str(args.get("aggregateMode") or "list"),
    )
    return format_result(result), result.to_dict()


async def task_map_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    items = args.get("items") or []
    template = args.get("template") or {}
    if not isinstance(items, list) or not items:
        return _refusal("INVALID_INPUT", "task_map needs a non-empty items array")
    if not isinstance(template, dict) or not template:
        return _refusal("INVALID_INPUT", "task_map needs a template task")
    result = await _task_map(
        engine, items, template=template,
        concurrency=int(args.get("concurrency") or 0),
        failure_policy=args.get("failurePolicy") or FailurePolicy.CONTINUE,
        reduce=args.get("reduce"),
        reduce_mode=str(args.get("reduceMode") or "list"),
        batch_size=int(args.get("batchSize") or 0),
    )
    return format_result(result), result.to_dict()


async def task_batch_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    items = args.get("items") or []
    template = args.get("template") or {}
    batch_key = str(args.get("batchKey") or args.get("batch_key") or "batch")
    if not isinstance(items, list) or not items:
        return _refusal("INVALID_INPUT", "task_batch needs a non-empty items array")
    if not isinstance(template, dict) or not template:
        return _refusal("INVALID_INPUT", "task_batch needs a template task")
    result = await _task_batch(
        engine, items, template=template, batch_key=batch_key,
        max_size=int(args.get("maxSize") or args.get("max_size") or 64),
        arg_field=str(args.get("argField") or args.get("arg_field") or "items"),
        item_field=str(args.get("itemField") or args.get("item_field") or "item"),
        concurrency=int(args.get("concurrency") or 0),
        failure_policy=args.get("failurePolicy") or FailurePolicy.CONTINUE,
    )
    return format_result(result), result.to_dict()


async def task_reduce_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    items = args.get("items") or []
    template = args.get("template") or {}
    reduce = args.get("reduce") or {}
    if not isinstance(items, list) or not items:
        return _refusal("INVALID_INPUT", "task_reduce needs a non-empty items array")
    if not isinstance(template, dict) or not isinstance(reduce, dict) or not reduce:
        return _refusal("INVALID_INPUT", "task_reduce needs a template and a reduce spec")
    result = await _task_reduce(
        engine, items, template=template, reduce=reduce,
        concurrency=int(args.get("concurrency") or 0),
        failure_policy=args.get("failurePolicy") or FailurePolicy.CONTINUE,
    )
    return format_result(result), result.to_dict()


def dependency_graph_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    execution_id = str(args.get("executionId") or args.get("execution_id") or "")
    if not execution_id:
        return _refusal("INVALID_INPUT", "dependency_graph needs an executionId")
    summary = _dependency_graph(engine, execution_id)
    return (f"Execution {execution_id}: {summary['status']} "
            f"({summary['byStatus']}).", summary)


def execution_status_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    execution_id = str(args.get("executionId") or args.get("execution_id") or "")
    status = engine.get_status(execution_id) if execution_id else None
    if status is None:
        return _refusal("NOT_FOUND", f"no execution {execution_id!r}")
    return (f"{execution_id}: {status['status']} "
            f"({status.get('nodeCounts')}).", status)


async def execution_cancel_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    engine = engine_for(ctx)
    execution_id = str(args.get("executionId") or args.get("execution_id") or "")
    if not execution_id:
        return _refusal("INVALID_INPUT", "execution_cancel needs an executionId")
    cancelled = await engine.cancel(execution_id)
    return (f"Cancelled {execution_id}." if cancelled else f"{execution_id} was not running.",
            {"executionId": execution_id, "cancelled": cancelled})


# ── schemas ────────────────────────────────────────────────────────────────

_TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "kind": {"type": "string", "enum": ["agent", "tool", "function", "aggregate", "join", "noop"]},
        "tool": {"type": "string", "description": "A tool name for a `tool` node."},
        "function": {"type": "string", "description": "A registered reducer for a `function` node."},
        "query": {"type": "string", "description": "The task for an `agent` node."},
        "args": {"type": "object"},
        "input": {"type": "object"},
        "priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "NORMAL", "LOW", "BACKGROUND"]},
        "timeoutMs": {"type": "integer"},
        "retry": {"type": "object"},
        "resources": {"type": "object"},
        "dependsOn": {"type": "array", "items": {"type": "string"}},
        "join": {"type": "object"},
        "dedupKey": {"type": "string"},
        "cacheable": {"type": "boolean"},
        "cacheTtlMs": {"type": "integer"},
        "rateKey": {"type": "string", "description": "Rate-limit bucket this task consumes."},
    },
    "required": [],
}


def _tasks_schema() -> dict[str, Any]:
    return {"type": "array", "items": _TASK_SCHEMA}


def register_orchestration_tools(registry: ToolRegistry) -> None:
    defs = [
        ToolDefinition(
            name="parallel_execute",
            description=(
                "Run independent tasks concurrently and return their structured results. "
                "Tasks with no dependencies overlap; `dependsOn` orders them. Supports "
                "concurrency limits, priority, retries, timeouts and failure policies."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "tasks": _tasks_schema(),
                    "concurrency": {"type": "integer"},
                    "failurePolicy": {"type": "string",
                                      "enum": ["FAIL_FAST", "CONTINUE", "PARTIAL_SUCCESS",
                                               "RETRY_FAILED", "REQUIRE_QUORUM"]},
                    "aggregate": {"type": "boolean"},
                    "aggregateMode": {"type": "string", "enum": ["list", "merge", "concat", "claims"]},
                },
                "required": ["tasks"],
                "additionalProperties": False,
            },
            handler=parallel_execute_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_fork",
            description="Fork one execution into multiple concurrent child tasks; returns a fork id.",
            input_schema={"type": "object", "properties": {
                "tasks": _tasks_schema(), "concurrency": {"type": "integer"},
                "failurePolicy": {"type": "string"},
            }, "required": ["tasks"], "additionalProperties": False},
            handler=task_fork_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_join",
            description="Run children concurrently and join them under ALL/ANY/FIRST_SUCCESS/QUORUM/THRESHOLD.",
            input_schema={"type": "object", "properties": {
                "tasks": _tasks_schema(),
                "policy": {"type": "string",
                           "enum": ["ALL", "ANY", "FIRST_SUCCESS", "QUORUM", "THRESHOLD"]},
                "threshold": {"type": "integer"},
                "aggregateMode": {"type": "string", "enum": ["list", "merge", "concat", "claims"]},
            }, "required": ["tasks"], "additionalProperties": False},
            handler=task_join_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_race",
            description="Run producers concurrently; the first valid result wins and the rest are cancelled.",
            input_schema={"type": "object", "properties": {
                "tasks": _tasks_schema(),
                "aggregateMode": {"type": "string", "enum": ["list", "merge", "concat", "claims"]},
            }, "required": ["tasks"], "additionalProperties": False},
            handler=task_race_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_quorum",
            description="Run candidates concurrently; continue once `quorum` valid results exist.",
            input_schema={"type": "object", "properties": {
                "tasks": _tasks_schema(), "quorum": {"type": "integer"},
                "aggregateMode": {"type": "string", "enum": ["list", "merge", "concat", "claims"]},
            }, "required": ["tasks", "quorum"], "additionalProperties": False},
            handler=task_quorum_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_map",
            description="Map a task template over many items concurrently, then aggregate the results.",
            input_schema={"type": "object", "properties": {
                "items": {"type": "array"},
                "template": _TASK_SCHEMA,
                "concurrency": {"type": "integer"},
                "failurePolicy": {"type": "string"},
                "reduce": {"type": "object"},
                "reduceMode": {"type": "string", "enum": ["list", "merge", "concat", "claims"]},
                "batchSize": {"type": "integer",
                              "description": "Group items so one node receives a batch in args.items."},
            }, "required": ["items", "template"], "additionalProperties": False},
            handler=task_map_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_batch",
            description=(
                "Batch many items into one call per group: ready nodes sharing a batch "
                "key are coalesced (up to maxSize) and the tool receives args[argField] "
                "as the list of itemField values."
            ),
            input_schema={"type": "object", "properties": {
                "items": {"type": "array"},
                "template": _TASK_SCHEMA,
                "batchKey": {"type": "string"},
                "maxSize": {"type": "integer"},
                "argField": {"type": "string"},
                "itemField": {"type": "string"},
                "concurrency": {"type": "integer"},
                "failurePolicy": {"type": "string"},
            }, "required": ["items", "template", "batchKey"], "additionalProperties": False},
            handler=task_batch_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="task_reduce",
            description="Map a template over items concurrently, then reduce with a function/aggregate node.",
            input_schema={"type": "object", "properties": {
                "items": {"type": "array"},
                "template": _TASK_SCHEMA,
                "reduce": {"type": "object"},
                "concurrency": {"type": "integer"},
                "failurePolicy": {"type": "string"},
            }, "required": ["items", "template", "reduce"], "additionalProperties": False},
            handler=task_reduce_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="dependency_graph",
            description="Inspect an execution's DAG: nodes, edges, readiness, waves, critical path.",
            input_schema={"type": "object", "properties": {
                "executionId": {"type": "string"},
            }, "required": ["executionId"], "additionalProperties": False},
            handler=dependency_graph_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="execution_status",
            description="Get the live status of an orchestration execution.",
            input_schema={"type": "object", "properties": {
                "executionId": {"type": "string"},
            }, "required": ["executionId"], "additionalProperties": False},
            handler=execution_status_handler, permission="read", risk="low",
        ),
        ToolDefinition(
            name="execution_cancel",
            description="Cancel a running orchestration execution and all of its tasks.",
            input_schema={"type": "object", "properties": {
                "executionId": {"type": "string"},
            }, "required": ["executionId"], "additionalProperties": False},
            handler=execution_cancel_handler, permission="read", risk="low",
        ),
    ]
    for definition in defs:
        registry.register(definition)


__all__ = ["TOOL_NAMES", "engine_for", "forget_engine", "format_result", "register_orchestration_tools"]
