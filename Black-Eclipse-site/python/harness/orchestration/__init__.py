"""Eclipse parallel execution & DAG orchestration.

A dependency-aware execution layer ON TOP of the existing runtime. It does NOT
replace `execute_run`, the tool registry, the event bus or the persistence layer:
an `agent` node calls `execute_run`, a `tool` node calls `ToolRegistry.execute`,
and every execution/node/attempt/event/lease row lands on the ONE agent-memory
connection.

Capabilities:
  * a real DAG with validation (cycles, missing deps, unreachable nodes, …);
  * automatic parallelism — independent nodes run concurrently by construction;
  * a scheduler with priorities, critical-path ordering, resource-aware
    concurrency, retries/backoff, timeouts, cancellation and failure policies;
  * join policies (ALL/ANY/FIRST_SUCCESS/QUORUM/THRESHOLD) and the primitives
    `parallel_execute`, `task_fork`, `task_join`, `task_race`, `task_quorum`,
    `task_map`, `task_reduce`, `dependency_graph`;
  * task deduplication and TTL caching;
  * persistence and crash recovery.
"""

from __future__ import annotations

from .engine import (
    EngineConfig,
    OrchestrationEngine,
    compute_dedup_key,
)
from .graph import (
    GraphValidationError,
    Readiness,
    critical_path,
    evaluate_readiness,
    graph_summary,
    topological_layers,
    validate_graph,
)
from .models import (
    ExecutionGraph,
    ExecutionNode,
    ExecutionResult,
    ExecutionStatus,
    FailurePolicy,
    JoinConfig,
    JoinPolicy,
    NodeError,
    NodeKind,
    NodeOutcome,
    Priority,
    ResourceRequirements,
    RetryPolicy,
    TaskStatus,
)
from .primitives import (
    build_task_graph,
    dependency_graph,
    parallel_execute,
    task_batch,
    task_fork,
    task_join,
    task_map,
    task_quorum,
    task_race,
    task_reduce,
)
from .resources import RateLimiter, ResourceManager
from .runner import DefaultNodeRunner, NodeRunner, RuntimeContext
from .state import (
    InvalidTransition,
    TaskStateMachine,
    can_transition_task,
    is_task_terminal,
)
from .store import OrchestrationStore
from .tools import engine_for, forget_engine, register_orchestration_tools

__all__ = [
    "DefaultNodeRunner",
    "EngineConfig",
    "ExecutionGraph",
    "ExecutionNode",
    "ExecutionResult",
    "ExecutionStatus",
    "FailurePolicy",
    "GraphValidationError",
    "InvalidTransition",
    "JoinConfig",
    "JoinPolicy",
    "NodeError",
    "NodeKind",
    "NodeOutcome",
    "NodeRunner",
    "OrchestrationEngine",
    "OrchestrationStore",
    "Priority",
    "RateLimiter",
    "Readiness",
    "ResourceManager",
    "ResourceRequirements",
    "RetryPolicy",
    "RuntimeContext",
    "TaskStateMachine",
    "TaskStatus",
    "build_task_graph",
    "can_transition_task",
    "compute_dedup_key",
    "critical_path",
    "dependency_graph",
    "engine_for",
    "evaluate_readiness",
    "forget_engine",
    "graph_summary",
    "is_task_terminal",
    "parallel_execute",
    "register_orchestration_tools",
    "task_batch",
    "task_fork",
    "task_join",
    "task_map",
    "task_quorum",
    "task_race",
    "task_reduce",
    "topological_layers",
    "validate_graph",
]
