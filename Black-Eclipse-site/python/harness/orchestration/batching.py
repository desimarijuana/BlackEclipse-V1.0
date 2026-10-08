"""Provider/tool batching: coalesce compatible nodes into one call.

A node opts in by declaring `batch` in its input:

    {"tool": "get_quote", "args": {"symbol": "AAPL"},
     "batch": {"key": "quotes", "maxSize": 100,
               "argField": "symbols", "itemField": "symbol"}}

The scheduler groups all currently-READY nodes that share the same batch key and
whose other arguments (everything except `itemField`) are identical, up to
`maxSize`. One call is then made with `args[argField] = [each member's item]`, and
the returned list is fanned back out to the members in order. This is what turns
"10,000 symbols" into "batches of 100, concurrency 10" instead of 10,000 requests.

The helpers here are pure; the engine owns the actual dispatch so retries,
timeouts, leases and resource accounting stay in one place.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .models import ExecutionNode, NodeKind, NodeOutcome

DEFAULT_MAX_BATCH = 64
_TOOL_BATCHABLE = (NodeKind.TOOL, NodeKind.FUNCTION)


def batch_spec(node: ExecutionNode) -> Optional[dict[str, Any]]:
    """Normalize a node's `batch` declaration, or None when it is not batching."""
    if node.kind not in _TOOL_BATCHABLE:
        return None
    raw = (node.input or {}).get("batch")
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "")
    if not key:
        return None
    try:
        max_size = int(raw.get("maxSize") or raw.get("max_size") or DEFAULT_MAX_BATCH)
    except (TypeError, ValueError):
        max_size = DEFAULT_MAX_BATCH
    return {
        "key": key,
        "maxSize": max(2, max_size),
        "argField": str(raw.get("argField") or raw.get("arg_field") or "items"),
        "itemField": str(raw.get("itemField") or raw.get("item_field") or "item"),
    }


def _base_args(node: ExecutionNode, item_field: str) -> dict[str, Any]:
    args = dict((node.input or {}).get("args") or {})
    args.pop(item_field, None)
    return args


def _item_value(node: ExecutionNode, item_field: str) -> Any:
    return ((node.input or {}).get("args") or {}).get(item_field)


def _group_key(node: ExecutionNode, spec: dict[str, Any]) -> str:
    base = _base_args(node, spec["itemField"])
    target = (node.input or {}).get("tool") or (node.input or {}).get("function")
    return "|".join([
        node.kind.value, str(target), spec["key"], spec["argField"], spec["itemField"],
        json.dumps(base, sort_keys=True, default=str),
    ])


def plan_batches(ready: list[ExecutionNode]) -> tuple[list[list[ExecutionNode]], list[ExecutionNode]]:
    """Split ready nodes into batch groups (>=2) and singles, preserving order."""
    groups: dict[str, list[ExecutionNode]] = {}
    order: list[str] = []
    singles: list[ExecutionNode] = []
    for node in ready:
        spec = batch_spec(node)
        if spec is None:
            singles.append(node)
            continue
        key = _group_key(node, spec)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(node)
    batches: list[list[ExecutionNode]] = []
    for key in order:
        members = groups[key]
        if len(members) < 2:
            singles.extend(members)
            continue
        cap = min(batch_spec(m)["maxSize"] for m in members)  # type: ignore[index]
        for i in range(0, len(members), cap):
            chunk = members[i:i + cap]
            if len(chunk) >= 2:
                batches.append(chunk)
            else:
                singles.extend(chunk)
    return batches, singles


def merged_requirements(members: list[ExecutionNode]) -> dict[str, int]:
    """One running unit's resource draw: the max per class across members."""
    merged: dict[str, int] = {}
    for member in members:
        for key, weight in member.resources.effective().items():
            merged[key] = max(merged.get(key, 0), weight)
    merged.setdefault("global", 1)
    return merged


def build_synthetic_node(members: list[ExecutionNode]) -> ExecutionNode:
    """A single node representing the whole batch call."""
    spec = batch_spec(members[0]) or {"argField": "items", "itemField": "item"}
    combined_args = _base_args(members[0], spec["itemField"])
    combined_args[spec["argField"]] = [_item_value(m, spec["itemField"]) for m in members]
    first = members[0]
    synthetic = ExecutionNode(
        id=f"batch_{spec['key']}",
        execution_id=first.execution_id,
        kind=first.kind,
        input=dict(first.input or {}),
        priority=first.priority,
        retry=first.retry,
        timeout_ms=max(m.timeout_ms for m in members),
        metadata=dict(first.metadata or {}),
    )
    synthetic.input["args"] = combined_args
    synthetic.input.pop("batch", None)
    synthetic.dedup_key = None
    return synthetic


def distribute(members: list[ExecutionNode], outcome: NodeOutcome) -> list[NodeOutcome]:
    """Fan a batch result back out; a misaligned result fails every member."""
    from .models import NodeError

    if outcome.error is not None:
        return [NodeOutcome(error=outcome.error) for _ in members]
    spec = batch_spec(members[0]) or {"itemField": "item"}
    items = _extract_items(outcome.output, members, spec["itemField"])
    if items is None:
        return [NodeOutcome(error=NodeError(
            "BATCH_RESULT_MISMATCH",
            f"batched call returned a result that did not align with {len(members)} inputs",
            retryable=False,
        )) for _ in members]
    return [NodeOutcome(output=item) for item in items]


def _extract_items(output: Any, members: list[ExecutionNode], item_field: str) -> Optional[list[Any]]:
    count = len(members)
    if isinstance(output, list):
        return output if len(output) == count else None
    if isinstance(output, dict):
        for key in ("results", "items", "outputs"):
            value = output.get(key)
            if isinstance(value, list) and len(value) == count:
                return value
        # A dict keyed by the item value is also a valid aligned shape.
        values = [_item_value(m, item_field) for m in members]
        if all(v in output for v in values):
            return [output[v] for v in values]
    return None


async def run_batch(engine: Any, ex: Any, members: list[ExecutionNode], reqs: dict[str, int]) -> bool:
    """Execute one coalesced batch: a single call, fanned back to each member.

    The engine owns retries/timeouts (via `_execute_attempts`), leases, resources
    and settling, so batching does not duplicate any of that policy.
    """
    import asyncio

    from .events import TASK_STARTED
    from .models import TaskStatus, now

    graph = ex.graph
    synthetic = build_synthetic_node(members)
    try:
        for member in members:
            engine._set_task_status(member, TaskStatus.RUNNING)  # noqa: SLF001
            member.started_at = member.started_at or now()
            member.worker_id = engine._worker_id()  # noqa: SLF001
            lease = engine.store.acquire_lease(  # noqa: SLF001
                graph.id, member.id, member.worker_id, engine.config.lease_ttl_ms
            )
            member.metadata["_leaseId"] = lease
            engine.store.save_node(member)  # noqa: SLF001
            engine._emit(graph.id, TASK_STARTED, {  # noqa: SLF001
                "nodeId": member.id, "kind": member.kind.value, "batched": True,
            }, node_id=member.id)
        outcome = await engine._execute_attempts(ex, synthetic)  # noqa: SLF001
        outcomes = distribute(members, outcome)
        for member, member_outcome in zip(members, outcomes):
            if member_outcome.error is None:
                member.attempt_count = synthetic.attempt_count
            engine._settle_node(ex, member, member_outcome)  # noqa: SLF001
        return True
    except asyncio.CancelledError:
        for member in members:
            if not member.terminal:
                engine._settle_node(  # noqa: SLF001
                    ex, member, NodeOutcome(error=_cancelled()),
                )
        raise
    finally:
        engine._resources.release(reqs)  # noqa: SLF001
        for member in members:
            lease = (member.metadata or {}).pop("_leaseId", None)
            if lease:
                engine.store.release_lease(lease)  # noqa: SLF001
            ex.running.pop(member.id, None)


def _cancelled():
    from .models import NodeError

    return NodeError("CANCELLED", "batch cancelled")


__all__ = [
    "DEFAULT_MAX_BATCH",
    "batch_spec",
    "build_synthetic_node",
    "distribute",
    "merged_requirements",
    "plan_batches",
    "run_batch",
]
