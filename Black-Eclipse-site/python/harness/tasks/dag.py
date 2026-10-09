"""Pure graph math for the task system: cycles, runnability, roll-ups.

Nothing here touches a store, a model or the clock. Every function takes plain
data and returns plain data, so the dependency rules, parent-state derivation and
progress math are unit-testable in isolation — and there is exactly ONE
implementation of each rule.

The edge convention everywhere is ``(dependent, prerequisite)``: the second task
must COMPLETE before the first may run. `dag` never decides whether a dependency
is REQUIRED; the caller passes only the edges that gate.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .model import FailurePolicy, TaskStatus

#: The states a prerequisite must reach for a dependent to become runnable.
DEPENDENCY_SATISFIED: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED})

#: A dependency that has terminally failed permanently blocks its dependent.
DEPENDENCY_FAILED: frozenset[TaskStatus] = frozenset(
    {TaskStatus.FAILED, TaskStatus.CANCELLED}
)


def detect_cycle(edges: Iterable[tuple[str, str]]) -> Optional[list[str]]:
    """Return a cycle (a list of node ids ending where it started) or None.

    Iterative depth-first search with an explicit color map, so a deep or
    adversarial graph can never blow the Python stack. Edges are
    ``dependent -> prerequisite``; a back-edge means a real dependency cycle.
    """
    adjacency: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for dependent, prerequisite in edges:
        nodes.add(dependent)
        nodes.add(prerequisite)
        adjacency.setdefault(dependent, []).append(prerequisite)

    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in nodes}

    for start in nodes:
        if color[start] != WHITE:
            continue
        path: list[str] = []
        on_path: dict[str, int] = {}
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, index = stack[-1]
            if index == 0:
                color[node] = GREY
                on_path[node] = len(path)
                path.append(node)
            neighbors = adjacency.get(node, [])
            if index < len(neighbors):
                stack[-1] = (node, index + 1)
                nxt = neighbors[index]
                if color.get(nxt, WHITE) == GREY:
                    return path[on_path[nxt]:] + [nxt]
                if color.get(nxt, WHITE) == WHITE:
                    stack.append((nxt, 0))
            else:
                stack.pop()
                color[node] = BLACK
                on_path.pop(node, None)
                if path and path[-1] == node:
                    path.pop()
    return None


def unmet_dependencies(dependencies: Sequence[tuple[str, TaskStatus]]) -> list[str]:
    """Given ``(prerequisite_id, status)`` for REQUIRED edges, the unmet ones."""
    return [
        prereq_id
        for prereq_id, status in dependencies
        if status not in DEPENDENCY_SATISFIED
    ]


def all_dependencies_satisfied(dependencies: Sequence[tuple[str, TaskStatus]]) -> bool:
    return all(status in DEPENDENCY_SATISFIED for _, status in dependencies)


def derive_parent_status(
    children: Sequence[tuple[TaskStatus, bool, FailurePolicy]],
) -> Optional[TaskStatus]:
    """The deterministic status of a container task from its children.

    Each child contributes ``(status, required, parent_failure_policy)``. Returns
    None when the parent has no children (a leaf owns its own status).

    Rules, in precedence order:
      1. If every required child is COMPLETED -> COMPLETED.
      2. If a required child FAILED (or CANCELLED) and the policy is FAIL_FAST
         -> FAILED.
      3. If any required child is IN_PROGRESS -> IN_PROGRESS.
      4. If any required child is TODO -> IN_PROGRESS (work remains and can
         proceed; a container is only blocked when ALL its work is blocked).
      5. If every remaining required child is BLOCKED (or WAITING) -> BLOCKED
         (or WAITING). A mix resolves to BLOCKED.
      6. Otherwise -> FAILED (only cancelled children remain).
    """
    if not children:
        return None
    required = [c for c in children if c[1]]
    pool = required or list(children)
    statuses = [c[0] for c in pool]

    def _any(state: TaskStatus) -> bool:
        return any(s == state for s in statuses)

    if all(s == TaskStatus.COMPLETED for s in statuses):
        return TaskStatus.COMPLETED
    if any(s in DEPENDENCY_FAILED for s in statuses):
        policy = children[0][2] if children else FailurePolicy.FAIL_FAST
        if policy == FailurePolicy.FAIL_FAST:
            return TaskStatus.FAILED
    if _any(TaskStatus.IN_PROGRESS) or _any(TaskStatus.TODO) or _any(TaskStatus.VERIFYING):
        return TaskStatus.IN_PROGRESS
    remaining = [s for s in statuses if s not in (TaskStatus.COMPLETED,)]
    if remaining and all(s == TaskStatus.WAITING for s in remaining):
        return TaskStatus.WAITING
    # A container whose entire remaining work is parked on a human reports the
    # same distinction its children make.
    if remaining and all(s in (TaskStatus.WAITING, TaskStatus.ASKING_USER) for s in remaining):
        return TaskStatus.ASKING_USER if _any(TaskStatus.ASKING_USER) else TaskStatus.WAITING
    if any(s in (TaskStatus.BLOCKED, TaskStatus.WAITING) for s in remaining):
        return TaskStatus.BLOCKED
    if remaining and all(s == TaskStatus.CANCELLED for s in remaining):
        return TaskStatus.FAILED
    return TaskStatus.IN_PROGRESS


def derive_parent_progress(
    children: Sequence[tuple[int, float, TaskStatus]],
) -> Optional[int]:
    """Weighted progress of a container from ``(progress, weight, status)``.

    A COMPLETED child counts as 100 regardless of a stale stored progress. The
    result is clamped to 0..100 so a bad child value can never produce an
    impossible parent number.
    """
    if not children:
        return None
    total_weight = sum(max(0.0, w) for _, w, _ in children)
    if total_weight <= 0:
        return None
    earned = 0.0
    for progress, weight, status in children:
        value = 100 if status == TaskStatus.COMPLETED else progress
        value = max(0, min(100, int(value)))
        earned += value * max(0.0, weight)
    return int(round(max(0.0, min(100.0, earned / total_weight))))


def topological_layers(
    node_ids: Sequence[str], edges: Iterable[tuple[str, str]]
) -> Optional[list[list[str]]]:
    """Kahn layering of ``dependent -> prerequisite`` edges into runnable layers.

    Layer 0 has no unmet prerequisites; each later layer depends only on earlier
    ones. Returns None if a cycle makes layering impossible.
    """
    nodes = list(dict.fromkeys(node_ids))
    node_set = set(nodes)
    pending: dict[str, set[str]] = {
        n: {p for d, p in edges if d == n and p in node_set} for n in nodes
    }
    layers: list[list[str]] = []
    placed: set[str] = set()
    remaining = set(nodes)
    while remaining:
        layer = sorted(n for n in remaining if not (pending[n] - placed))
        if not layer:
            return None  # a cycle remains
        layers.append(layer)
        placed.update(layer)
        remaining.difference_update(layer)
    return layers


__all__ = [
    "DEPENDENCY_FAILED",
    "DEPENDENCY_SATISFIED",
    "all_dependencies_satisfied",
    "derive_parent_progress",
    "derive_parent_status",
    "detect_cycle",
    "topological_layers",
    "unmet_dependencies",
]
