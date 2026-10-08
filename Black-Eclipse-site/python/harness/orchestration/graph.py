"""Dependency-graph validation and analysis.

The engine NEVER executes an unvalidated graph. `validate_graph` rejects, with a
named reason, a duplicate id, a missing dependency, a self-edge, a cycle, and an
unreachable node. `evaluate_readiness` is the pure rule the scheduler asks:
can this node run now, must it wait, or must it be skipped?

Analysis here is real, not a label: `critical_path` computes a longest weighted
path over the DAG, `topological_layers` computes the exact concurrency waves, and
`ready_node_ids` / `blocked_node_ids` are derived from node status.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional

from .models import (
    ExecutionGraph,
    ExecutionNode,
    JoinPolicy,
    NodeKind,
    TaskStatus,
    TERMINAL_TASK_STATES,
)


class GraphValidationError(ValueError):
    """A graph was rejected. `errors` lists every structural defect found."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "invalid graph")


class Readiness(str, Enum):
    READY = "READY"
    WAITING = "WAITING"
    SKIPPED = "SKIPPED"


def detect_cycle(nodes: dict[str, ExecutionNode]) -> Optional[list[str]]:
    """Return one cycle (list of node ids) if the graph has one, else None."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in nodes}
    stack: list[str] = []

    def visit(node_id: str) -> Optional[list[str]]:
        color[node_id] = GREY
        stack.append(node_id)
        for dep in nodes[node_id].dependencies:
            if dep not in nodes:
                continue
            if color[dep] == GREY:
                idx = stack.index(dep)
                return stack[idx:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[node_id] = BLACK
        return None

    for nid in nodes:
        if color[nid] == WHITE:
            found = visit(nid)
            if found:
                return found
    return None


def validate_graph(graph: ExecutionGraph) -> None:
    """Raise `GraphValidationError` if the graph is structurally invalid."""
    errors: list[str] = []
    nodes = graph.nodes
    if not nodes:
        raise GraphValidationError(["graph has no nodes"])

    ids = list(nodes.keys())
    if len(ids) != len(set(ids)):
        errors.append("duplicate node ids")

    for node in nodes.values():
        if not node.id or not str(node.id).strip():
            errors.append("node with an empty id")
        if node.id in node.dependencies:
            errors.append(f"node {node.id!r} depends on itself")
        for dep in node.dependencies:
            if dep not in nodes:
                errors.append(f"node {node.id!r} depends on missing node {dep!r}")
        for target in node.dependents:
            if target not in nodes:
                errors.append(f"node {node.id!r} lists missing dependent {target!r}")
            elif node.id not in nodes[target].dependencies:
                errors.append(
                    f"edge {node.id!r}->{target!r} is not reciprocated by a dependency"
                )

    if not errors:
        cycle = detect_cycle(nodes)
        if cycle:
            errors.append(f"dependency cycle: {' -> '.join(cycle)}")

    reachable = _reachable_from_roots(nodes)
    unreachable = sorted(set(nodes) - reachable)
    if unreachable:
        errors.append(f"unreachable node(s): {', '.join(unreachable)}")

    if errors:
        raise GraphValidationError(errors)


def _reachable_from_roots(nodes: dict[str, ExecutionNode]) -> set[str]:
    roots = [nid for nid, n in nodes.items() if not n.dependencies]
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        nid = stack.pop()
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        stack.extend(nodes[nid].dependents)
    return seen


def _validate_acyclic_with_extra(
    nodes: dict[str, ExecutionNode], extra_dep: Optional[tuple[str, str]] = None,
) -> Optional[list[str]]:
    """Cycle check with one hypothetical edge added (for dynamic mutation)."""
    if extra_dep is None:
        return detect_cycle(nodes)
    from_id, to_id = extra_dep
    if from_id not in nodes or to_id not in nodes:
        return None
    original = list(nodes[to_id].dependencies)
    nodes[to_id].dependencies.append(from_id)
    try:
        return detect_cycle(nodes)
    finally:
        nodes[to_id].dependencies = original


def can_add_node(graph: ExecutionGraph, node: ExecutionNode) -> None:
    """Validate a dynamic node insertion. Raises with a named reason."""
    if node.id in graph.nodes:
        raise GraphValidationError([f"node {node.id!r} already exists"])
    for dep in node.dependencies:
        if dep not in graph.nodes:
            raise GraphValidationError([f"node {node.id!r} depends on missing node {dep!r}"])


def can_add_edge(graph: ExecutionGraph, from_id: str, to_id: str) -> None:
    """Validate a dynamic edge insertion (no missing endpoint, no cycle)."""
    if from_id not in graph.nodes:
        raise GraphValidationError([f"edge source {from_id!r} is unknown"])
    if to_id not in graph.nodes:
        raise GraphValidationError([f"edge target {to_id!r} is unknown"])
    if from_id == to_id:
        raise GraphValidationError([f"node {from_id!r} cannot depend on itself"])
    if to_id in graph.nodes[from_id].dependents:
        return  # already present — idempotent
    cycle = _validate_acyclic_with_extra(graph.nodes, (from_id, to_id))
    if cycle:
        raise GraphValidationError([f"edge {from_id!r}->{to_id!r} creates a cycle"])


def topological_order(nodes: dict[str, ExecutionNode]) -> list[str]:
    """Deterministic Kahn topological order. Raises on a cycle."""
    indegree = {nid: len(n.dependencies) for nid, n in nodes.items()}
    ready = sorted(nid for nid, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for dependent in sorted(nodes[nid].dependents):
            if dependent not in indegree:
                continue
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
        ready.sort()
    if len(order) != len(nodes):
        raise GraphValidationError(["graph has a cycle"])
    return order


def topological_layers(nodes: dict[str, ExecutionNode]) -> list[list[str]]:
    """The concurrency waves: layer 0 has no dependencies, layer N depends only
    on earlier layers. This is the maximum parallelism the DAG permits."""
    remaining = {nid: set(n.dependencies) for nid, n in nodes.items()}
    layers: list[list[str]] = []
    while remaining:
        ready = sorted(nid for nid, deps in remaining.items() if not deps)
        if not ready:
            raise GraphValidationError(["graph has a cycle"])
        layers.append(ready)
        for nid in ready:
            remaining.pop(nid)
        for deps in remaining.values():
            deps.difference_update(ready)
    return layers


def evaluate_readiness(node: ExecutionNode, graph: ExecutionGraph) -> Readiness:
    """The pure scheduling rule for one node.

    A node with no dependencies is READY. With a join policy, the rule is the
    policy; without one, the default is strict ALL (every dependency COMPLETED).
    A node whose dependencies can no longer satisfy it is SKIPPED — a failed
    dependency NEVER unlocks a task.
    """
    if not node.dependencies:
        return Readiness.READY
    deps = [graph.nodes.get(d) for d in node.dependencies]
    if any(dep is None for dep in deps):
        return Readiness.SKIPPED
    terminal = [d for d in deps if d.status in TERMINAL_TASK_STATES]
    completed = [d for d in deps if d.status is TaskStatus.COMPLETED]
    all_terminal = len(terminal) == len(deps)
    join = node.join
    policy = join.policy if join is not None else JoinPolicy.ALL

    if policy is JoinPolicy.ALL:
        if all_terminal:
            if len(completed) == len(deps):
                return Readiness.READY
            if join is not None and join.allow_partial:
                return Readiness.READY
            return Readiness.SKIPPED
        return Readiness.WAITING
    if policy is JoinPolicy.ANY:
        return Readiness.READY if terminal else Readiness.WAITING
    if policy is JoinPolicy.FIRST_SUCCESS:
        if completed:
            return Readiness.READY
        return Readiness.SKIPPED if all_terminal else Readiness.WAITING
    if policy in (JoinPolicy.QUORUM, JoinPolicy.THRESHOLD):
        threshold = max(1, (join.threshold if join is not None else 1))
        if len(completed) >= threshold:
            return Readiness.READY
        return Readiness.SKIPPED if all_terminal else Readiness.WAITING
    return Readiness.WAITING


def ready_node_ids(graph: ExecutionGraph) -> list[str]:
    """Nodes eligible to start right now (PENDING + readiness READY)."""
    return [
        nid for nid, node in graph.nodes.items()
        if node.status is TaskStatus.PENDING and evaluate_readiness(node, graph) is Readiness.READY
    ]


def blocked_node_ids(graph: ExecutionGraph) -> list[str]:
    """Non-terminal nodes whose dependencies are not all complete or running."""
    out: list[str] = []
    for nid, node in graph.nodes.items():
        if node.status in TERMINAL_TASK_STATES or node.status in (TaskStatus.RUNNING, TaskStatus.READY):
            continue
        if any(
            graph.nodes[d].status not in TERMINAL_TASK_STATES
            for d in node.dependencies if d in graph.nodes
        ):
            out.append(nid)
    return out


def parallelizable_node_ids(graph: ExecutionGraph) -> list[str]:
    """Independent nodes (no dependencies between them) that could overlap."""
    return [nid for nid, n in graph.nodes.items() if not n.dependencies]


def critical_path(
    graph: ExecutionGraph, duration_ms: Callable[[ExecutionNode], int] | None = None,
) -> tuple[list[str], int]:
    """Longest weighted path through the DAG (the true critical path).

    The weight of a node is its measured duration when available, otherwise its
    declared estimate, otherwise 1 (unit cost) so the topology still drives the
    result. Returns (path node ids, total weight).
    """
    order = topological_order(graph.nodes)
    best: dict[str, tuple[int, Optional[str]]] = {}
    for nid in order:
        node = graph.nodes[nid]
        weight = _node_weight(node) if duration_ms is None else max(0, int(duration_ms(node)))
        best_pred: Optional[str] = None
        best_score = -1
        for dep in node.dependencies:
            if dep not in best:
                continue
            score, _ = best[dep]
            if score > best_score:
                best_score = score
                best_pred = dep
        total = weight + (best_score if best_pred is not None else 0)
        best[nid] = (total, best_pred)
    if not best:
        return [], 0
    end = max(best, key=lambda nid: best[nid][0])
    path: list[str] = []
    cursor: Optional[str] = end
    while cursor is not None:
        path.append(cursor)
        cursor = best[cursor][1]
    path.reverse()
    return path, best[end][0]


def critical_path_ms(graph: ExecutionGraph) -> int:
    """Critical path length using measured/estimated node durations."""
    path, total = critical_path(graph, lambda n: _node_weight(n))
    return total


def _node_weight(node: ExecutionNode) -> int:
    measured = node.to_dict().get("durationMs") or 0
    if node.status is TaskStatus.COMPLETED and measured:
        return int(measured)
    if node.started_at is not None and node.completed_at is not None:
        return int(node.duration_ms())
    estimate = node.metadata.get("estimatedMs")
    if estimate:
        try:
            return max(1, int(estimate))
        except (TypeError, ValueError):
            return 1
    return 1


def graph_summary(graph: ExecutionGraph) -> dict[str, Any]:
    """A bounded, UI-ready summary of the graph and its progress."""
    nodes = list(graph.nodes.values())
    by_status: dict[str, int] = {}
    for node in nodes:
        by_status[node.status.value] = by_status.get(node.status.value, 0) + 1
    try:
        layers = topological_layers(graph.nodes)
    except GraphValidationError:
        layers = []
    path, total = critical_path(graph, _node_weight)
    return {
        "executionId": graph.id,
        "status": graph.status.value,
        "failurePolicy": graph.failure_policy.value,
        "total": len(nodes),
        "byStatus": by_status,
        "ready": ready_node_ids(graph),
        "blocked": blocked_node_ids(graph),
        "layers": layers,
        "criticalPath": path,
        "criticalPathMs": total,
    }


def is_terminal_node_kind(kind: NodeKind) -> bool:
    """NOOP/JOIN nodes run in-engine, not through the runner's heavy paths."""
    return kind in (NodeKind.NOOP, NodeKind.JOIN)


__all__ = [
    "GraphValidationError",
    "Readiness",
    "blocked_node_ids",
    "can_add_edge",
    "can_add_node",
    "critical_path",
    "critical_path_ms",
    "detect_cycle",
    "evaluate_readiness",
    "graph_summary",
    "is_terminal_node_kind",
    "parallelizable_node_ids",
    "ready_node_ids",
    "topological_layers",
    "topological_order",
    "validate_graph",
]
