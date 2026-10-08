"""First-class execution primitives built on the orchestration engine.

`parallel_execute`, `task_fork`, `task_join`, `task_race`, `task_quorum`,
`task_map` and `task_reduce` are thin, honest constructors over the SAME engine.
They never loop-and-await sequentially: they build a DAG and hand it to the
scheduler, which runs independent nodes concurrently.

A task spec is a plain mapping (the tool layer validates its JSON schema, the
engine validates the graph):
  { id?, kind?, tool?|function?|query?, args?, input?, priority?, timeoutMs?,
    retry?, resources?, dependsOn?, join?, dedupKey?, cacheable?, cacheTtlMs?,
    terminal? }
"""

from __future__ import annotations

from typing import Any, Optional

from .engine import OrchestrationEngine, compute_dedup_key
from .models import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionResult,
    FailurePolicy,
    JoinConfig,
    JoinPolicy,
    NodeKind,
    Priority,
    ResourceRequirements,
    RetryPolicy,
    new_execution_id,
    new_node_id,
)
from .runner import RuntimeContext


def _kind(value: Any) -> NodeKind:
    try:
        return NodeKind(str(value or "tool").lower())
    except ValueError:
        return NodeKind.TOOL


def _priority(value: Any) -> Priority:
    try:
        return Priority(str(value or "NORMAL").upper())
    except ValueError:
        return Priority.NORMAL


def _join(value: Any) -> Optional[JoinConfig]:
    if value is None:
        return None
    if isinstance(value, JoinConfig):
        return value
    return JoinConfig.from_dict(value)


def node_from_spec(spec: dict[str, Any], execution_id: str, *, default_timeout_ms: int = 120_000) -> ExecutionNode:
    kind = _kind(spec.get("kind"))
    raw_input = spec.get("input")
    if not isinstance(raw_input, dict):
        if kind is NodeKind.AGENT:
            raw_input = {"query": spec.get("query") or spec.get("instruction") or "",
                         **({"ticker": spec["ticker"]} if spec.get("ticker") else {}),
                         **({"context": spec["context"]} if spec.get("context") else {})}
        elif kind is NodeKind.FUNCTION:
            raw_input = {"function": spec.get("function"), "args": spec.get("args") or {}}
        elif kind is NodeKind.TOOL:
            raw_input = {"tool": spec.get("tool") or spec.get("name"), "args": spec.get("args") or {}}
        else:
            raw_input = {"value": spec.get("value")}
    retry = spec.get("retry")
    resources = spec.get("resources")
    node = ExecutionNode(
        id=str(spec.get("id") or new_node_id()),
        execution_id=execution_id,
        kind=kind,
        input=dict(raw_input),
        priority=_priority(spec.get("priority")),
        retry=retry if isinstance(retry, RetryPolicy) else RetryPolicy.from_dict(retry),
        timeout_ms=int(spec.get("timeoutMs") or spec.get("timeout_ms") or default_timeout_ms),
        resources=(resources if isinstance(resources, ResourceRequirements)
                   else ResourceRequirements.from_dict(resources)),
        join=_join(spec.get("join")),
        metadata=dict(spec.get("metadata") or {}),
        cacheable=bool(spec.get("cacheable")),
        cache_ttl_ms=int(spec.get("cacheTtlMs") or spec.get("cache_ttl_ms") or 0),
    )
    rate_key = spec.get("rateKey") or spec.get("rate_key")
    if rate_key:
        node.input["rateKey"] = str(rate_key)
    if isinstance(spec.get("batch"), dict) and "batch" not in node.input:
        node.input["batch"] = spec["batch"]
    if spec.get("shared"):
        node.input["shared"] = True
    if spec.get("dedupScope") or spec.get("dedup_scope"):
        node.input["dedupScope"] = str(spec.get("dedupScope") or spec.get("dedup_scope"))
    dedup_key = spec.get("dedupKey") or spec.get("dedup_key")
    if dedup_key:
        node.dedup_key = str(dedup_key)
    elif spec.get("dedup") is not False and kind in (NodeKind.TOOL, NodeKind.FUNCTION):
        node.dedup_key = compute_dedup_key(node)
    return node


def build_task_graph(
    tasks: list[dict[str, Any]],
    *,
    execution_id: Optional[str] = None,
    root_task_id: str = "",
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    quorum: int = 0,
    max_concurrency: int = 0,
    aggregate: bool = False,
    aggregate_mode: str = "list",
    aggregate_id: str = "aggregate",
    metadata: Optional[dict[str, Any]] = None,
) -> ExecutionGraph:
    """Build (but do not run) a graph of independent/declared-dependency tasks."""
    graph = ExecutionGraph(
        id=execution_id or new_execution_id(),
        root_task_id=root_task_id,
        failure_policy=failure_policy if isinstance(failure_policy, FailurePolicy)
        else FailurePolicy(str(failure_policy).upper()),
        quorum=max(0, int(quorum)),
        max_concurrency=max(0, int(max_concurrency)),
        metadata=dict(metadata or {}),
    )
    ids: dict[int, str] = {}
    for index, spec in enumerate(tasks):
        node = node_from_spec(spec, graph.id)
        graph.nodes[node.id] = node
        ids[index] = node.id
    # Resolve dependencies by node id or by positional index.
    for index, spec in enumerate(tasks):
        node = graph.nodes[ids[index]]
        for dep in spec.get("dependsOn") or spec.get("depends_on") or []:
            dep_id = ids.get(dep, dep) if isinstance(dep, int) else dep
            if dep_id not in graph.nodes:
                raise ValueError(f"task {index} depends on unknown node {dep_id!r}")
            if dep_id not in node.dependencies:
                node.dependencies.append(dep_id)
    for node in graph.nodes.values():
        for dep in node.dependencies:
            graph.nodes[dep].dependents.append(node.id)
    if aggregate and len(tasks) > 1:
        agg = ExecutionNode(
            id=aggregate_id,
            execution_id=graph.id,
            kind=NodeKind.AGGREGATE,
            input={"mode": aggregate_mode},
            join=JoinConfig(policy=JoinPolicy.ALL, allow_partial=True, cancel_losers=False),
            metadata={"aggregate": True},
        )
        graph.nodes[agg.id] = agg
        for index in ids.values():
            agg.dependencies.append(index)
            graph.nodes[index].dependents.append(agg.id)
    return graph


async def parallel_execute(
    engine: OrchestrationEngine,
    tasks: list[dict[str, Any]],
    *,
    concurrency: int = 0,
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    quorum: int = 0,
    aggregate: bool = False,
    aggregate_mode: str = "list",
    metadata: Optional[dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
    execution_id: Optional[str] = None,
) -> ExecutionResult:
    """Run independent tasks concurrently. The core parallel primitive."""
    if not tasks:
        raise ValueError("parallel_execute requires at least one task")
    graph = build_task_graph(
        tasks, execution_id=execution_id, failure_policy=failure_policy, quorum=quorum,
        max_concurrency=concurrency, aggregate=aggregate, aggregate_mode=aggregate_mode,
        metadata=metadata,
    )
    return await engine.run_graph(graph, timeout_ms=timeout_ms)


async def task_fork(
    engine: OrchestrationEngine,
    children: list[dict[str, Any]],
    *,
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    concurrency: int = 0,
    timeout_ms: Optional[int] = None,
) -> tuple[str, ExecutionResult]:
    """Fork one execution into multiple child tasks. Returns (fork id, result)."""
    result = await parallel_execute(
        engine, children, concurrency=concurrency, failure_policy=failure_policy,
        timeout_ms=timeout_ms, metadata={"primitive": "task_fork"},
    )
    return result.execution_id, result


async def task_join(
    engine: OrchestrationEngine,
    children: list[dict[str, Any]],
    *,
    policy: JoinPolicy | str = JoinPolicy.ALL,
    threshold: int = 1,
    aggregate_mode: str = "list",
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Run children and join them under a policy. Returns the joined result."""
    if not children:
        raise ValueError("task_join requires at least one child")
    graph = build_task_graph(
        children, metadata={"primitive": "task_join"},
        aggregate=False,
    )
    # Validate the policy against the child count.
    if isinstance(policy, JoinPolicy):
        join_policy = policy
    else:
        try:
            join_policy = JoinPolicy(str(policy).upper())
        except ValueError:
            join_policy = JoinPolicy.ALL
    if not graph.nodes:
        raise ValueError("task_join produced no nodes")
    join_node = ExecutionNode(
        id="join",
        execution_id=graph.id,
        kind=NodeKind.JOIN,
        input={"mode": aggregate_mode},
        join=JoinConfig(policy=join_policy, threshold=max(1, int(threshold)),
                        allow_partial=True, cancel_losers=True),
        metadata={"primitive": "task_join", "policy": join_policy.value},
    )
    graph.nodes[join_node.id] = join_node
    for child_id in list(graph.nodes):
        if child_id == join_node.id:
            continue
        child = graph.nodes[child_id]
        if child.dependents and any(graph.nodes[d].kind is NodeKind.JOIN for d in child.dependents):
            continue
        join_node.dependencies.append(child_id)
        child.dependents.append(join_node.id)
    return await engine.run_graph(graph, timeout_ms=timeout_ms)


async def task_race(
    engine: OrchestrationEngine,
    racers: list[dict[str, Any]],
    *,
    aggregate_mode: str = "list",
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Run producers concurrently; the first VALID result wins and losers cancel."""
    return await task_join(
        engine, racers, policy=JoinPolicy.FIRST_SUCCESS,
        aggregate_mode=aggregate_mode, timeout_ms=timeout_ms,
    )


async def task_quorum(
    engine: OrchestrationEngine,
    candidates: list[dict[str, Any]],
    *,
    quorum: int,
    aggregate_mode: str = "list",
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Run candidates concurrently; continue once `quorum` valid results exist."""
    return await task_join(
        engine, candidates, policy=JoinPolicy.QUORUM, threshold=max(1, int(quorum)),
        aggregate_mode=aggregate_mode, timeout_ms=timeout_ms,
    )


async def task_map(
    engine: OrchestrationEngine,
    items: list[Any],
    *,
    template: dict[str, Any],
    concurrency: int = 0,
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    reduce: Optional[dict[str, Any]] = None,
    reduce_mode: str = "list",
    batch_size: int = 0,
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Map a template over items concurrently, then optionally reduce.

    `batch_size` groups items so one node receives a batch in `args['items']` —
    for a tool/provider with a native batch call this is far cheaper than N
    single-item requests, while concurrency still bounds the number of batches.
    """
    groups: list[list[Any]] = _chunk(items, int(batch_size))
    tasks: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        spec = dict(template)
        spec["id"] = f"map_{index}"
        if len(group) == 1:
            tasks.append(_bind_item(spec, group[0]))
        else:
            bound = dict(spec)
            args = dict(bound.get("args") or {})
            args["items"] = list(group)
            args.setdefault("item", list(group))
            bound["args"] = args
            tasks.append(bound)
    graph = build_task_graph(
        tasks, failure_policy=failure_policy, max_concurrency=concurrency,
        aggregate=reduce is not None or bool(reduce_mode),
        aggregate_mode=reduce_mode,
        metadata={"primitive": "task_map", "count": len(items), "batches": len(groups)},
    )
    return await engine.run_graph(graph, timeout_ms=timeout_ms)


def _chunk(items: list[Any], batch_size: int) -> list[list[Any]]:
    if batch_size and batch_size > 1:
        return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    return [[item] for item in items]


async def task_batch(
    engine: OrchestrationEngine,
    items: list[Any],
    *,
    template: dict[str, Any],
    batch_key: str,
    max_size: int = 64,
    arg_field: str = "items",
    item_field: str = "item",
    concurrency: int = 0,
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Batch many items into one call per group via the scheduler's coalescer.

    Each item becomes a node declaring a `batch` block; the scheduler groups the
    ready nodes sharing `batch_key` (up to `max_size`) into one tool/function call
    whose `args[arg_field]` is the list of `item_field` values.
    """
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        spec = dict(template)
        spec["id"] = f"batch_{index}"
        args = dict(spec.get("args") or {})
        if isinstance(item, dict):
            args.update(item)
        else:
            args[item_field] = item
        spec["args"] = args
        spec["batch"] = {"key": batch_key, "maxSize": max_size,
                         "argField": arg_field, "itemField": item_field}
        tasks.append(spec)
    return await parallel_execute(
        engine, tasks, concurrency=concurrency, failure_policy=failure_policy,
        timeout_ms=timeout_ms, metadata={"primitive": "task_batch", "count": len(items)},
    )


async def task_reduce(
    engine: OrchestrationEngine,
    items: list[Any],
    *,
    template: dict[str, Any],
    reduce: dict[str, Any],
    concurrency: int = 0,
    failure_policy: FailurePolicy | str = FailurePolicy.CONTINUE,
    timeout_ms: Optional[int] = None,
) -> ExecutionResult:
    """Map then reduce in one DAG. `reduce` is a WITH-DEPS function node spec."""
    tasks = []
    for index, item in enumerate(items):
        spec = _bind_item(dict({**template, "id": f"map_{index}"}), item)
        tasks.append(spec)
    graph = build_task_graph(tasks, failure_policy=failure_policy, max_concurrency=concurrency,
                             metadata={"primitive": "task_reduce", "count": len(items)})
    reducer = ExecutionNode(
        id=str(reduce.get("id") or "reduce"),
        execution_id=graph.id,
        kind=NodeKind.FUNCTION if reduce.get("function") else NodeKind.AGGREGATE,
        input=({"function": reduce.get("function"), "args": reduce.get("args") or {}}
               if reduce.get("function") else {"mode": reduce.get("mode") or "list"}),
    )
    graph.nodes[reducer.id] = reducer
    for child_id in list(graph.nodes):
        if child_id == reducer.id:
            continue
        reducer.dependencies.append(child_id)
        graph.nodes[child_id].dependents.append(reducer.id)
    return await engine.run_graph(graph, timeout_ms=timeout_ms)


def _bind_item(spec: dict[str, Any], item: Any) -> dict[str, Any]:
    bound = dict(spec)
    if isinstance(item, dict):
        for key, value in item.items():
            if key not in bound:
                bound[key] = value
        args = dict(bound.get("args") or {})
        args.setdefault("item", item)
        bound["args"] = args
    else:
        args = dict(bound.get("args") or {})
        args.setdefault("item", item)
        bound["args"] = args
    return bound


def dependency_graph(engine: OrchestrationEngine, execution_id: str) -> dict[str, Any]:
    """Inspect an execution's graph, readiness, waves and critical path."""
    from .graph import graph_summary

    graph = engine.build_graph(execution_id)
    summary = graph_summary(graph)
    summary["nodes"] = [n.to_dict() for n in graph.nodes.values()]
    summary["edges"] = [{"from": a, "to": b} for a, b in graph.edges()]
    return summary


__all__ = [
    "build_task_graph",
    "dependency_graph",
    "node_from_spec",
    "parallel_execute",
    "task_batch",
    "task_fork",
    "task_join",
    "task_map",
    "task_quorum",
    "task_race",
    "task_reduce",
]
