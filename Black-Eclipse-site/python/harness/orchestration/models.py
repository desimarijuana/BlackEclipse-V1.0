"""Domain models for the parallel-execution / DAG orchestration layer.

This is the internal vocabulary of the engine. It is deliberately dependency-light
(dataclasses + enums, no pydantic) so the scheduler can be driven by tests without
a model, a registry, or a database. The wire contracts (tool inputs, HTTP bodies)
validate separately at their own seams, exactly as the rest of the harness does.

An EXECUTION is a DAG of NODES. A node is a unit of work with declared
dependencies, a priority, a retry policy, a timeout, and resource requirements.
Independent nodes run concurrently; the scheduler is the only thing that decides
what becomes READY and when.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


def now() -> float:
    return time.time()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class TaskStatus(str, Enum):
    """The lifecycle state of one node. A `str` enum for easy serialization."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"
    PAUSED = "PAUSED"


# A node that will never run again. Used by the scheduler to decide completion.
TERMINAL_TASK_STATES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.BLOCKED,
        TaskStatus.SKIPPED,
        TaskStatus.TIMED_OUT,
    }
)
# A terminal state that counts as a usable input for a dependent.
SUCCESS_TASK_STATES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED})


class ExecutionStatus(str, Enum):
    """The lifecycle state of a whole execution."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    # Reached its end with some nodes failed and no policy that turns that into a
    # hard failure. Never silently reported as COMPLETED.
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


TERMINAL_EXECUTION_STATES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.PARTIAL_SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)


class Priority(str, Enum):
    """Scheduling priority. Higher `weight` runs first."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    BACKGROUND = "BACKGROUND"

    @property
    def weight(self) -> int:
        return {
            Priority.CRITICAL: 1000,
            Priority.HIGH: 750,
            Priority.NORMAL: 500,
            Priority.LOW: 250,
            Priority.BACKGROUND: 0,
        }[self]


class NodeKind(str, Enum):
    """What a node does. Each maps to a runner strategy."""

    AGENT = "agent"
    TOOL = "tool"
    AGGREGATE = "aggregate"
    FUNCTION = "function"
    JOIN = "join"
    NOOP = "noop"


class JoinPolicy(str, Enum):
    """When a node with multiple dependencies may run."""

    ALL = "ALL"
    ANY = "ANY"
    FIRST_SUCCESS = "FIRST_SUCCESS"
    QUORUM = "QUORUM"
    THRESHOLD = "THRESHOLD"


class FailurePolicy(str, Enum):
    """What an execution does when a node fails."""

    FAIL_FAST = "FAIL_FAST"
    CONTINUE = "CONTINUE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    RETRY_FAILED = "RETRY_FAILED"
    REQUIRE_QUORUM = "REQUIRE_QUORUM"


@dataclass
class RetryPolicy:
    """A bounded retry policy. Never unbounded."""

    max_attempts: int = 1
    backoff_ms: int = 0
    multiplier: float = 2.0
    max_backoff_ms: int = 60_000
    jitter: float = 0.0  # fraction of the computed backoff, 0..1
    # Error codes that ARE retryable even though the default classifier would not
    # say so (an explicit operator override). Empty = use the classifier only.
    retryable_errors: tuple[str, ...] = ()
    # Error codes that are NEVER retried, even if the classifier would allow it.
    non_retryable_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["retryableErrors"] = list(self.retryable_errors)
        data["nonRetryableErrors"] = list(self.non_retryable_errors)
        return data

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "RetryPolicy":
        if not data:
            return cls()
        return cls(
            max_attempts=max(1, int(data.get("max_attempts") or data.get("maxAttempts") or 1)),
            backoff_ms=max(0, int(data.get("backoff_ms") or data.get("backoffMs") or 0)),
            multiplier=max(1.0, float(data.get("multiplier") or 2.0)),
            max_backoff_ms=max(0, int(data.get("max_backoff_ms") or data.get("maxBackoffMs") or 60_000)),
            jitter=min(1.0, max(0.0, float(data.get("jitter") or 0.0))),
            retryable_errors=tuple(data.get("retryable_errors") or data.get("retryableErrors") or ()),
            non_retryable_errors=tuple(data.get("non_retryable_errors") or data.get("nonRetryableErrors") or ()),
        )


@dataclass
class ResourceRequirements:
    """Named resource weights a node consumes while running.

    `global` is always consumed (weight 1) by the engine; the remaining keys are
    per-class limits (llm, browser, code, database, network, provider:<name>).
    """

    resources: dict[str, int] = field(default_factory=dict)
    weight: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"resources": dict(self.resources), "weight": self.weight}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "ResourceRequirements":
        if not data:
            return cls()
        return cls(
            resources={str(k): max(1, int(v)) for k, v in (data.get("resources") or {}).items()},
            weight=max(1, int(data.get("weight") or 1)),
        )

    def effective(self) -> dict[str, int]:
        reqs = {"global": max(1, int(self.weight))}
        for key, value in self.resources.items():
            reqs[key] = reqs.get(key, 0) + max(1, int(value))
        return reqs


@dataclass
class JoinConfig:
    """How a node combines its dependencies before it may run."""

    policy: JoinPolicy = JoinPolicy.ALL
    # For QUORUM/THRESHOLD: the number of COMPLETED dependencies required.
    threshold: int = 1
    # ADVANCED: a node may run once every dependency is TERMINAL even when some
    # failed, receiving the failures as structured data. Default False keeps the
    # strict rule (a failed required dependency cascades to SKIPPED).
    allow_partial: bool = False
    # For FIRST_SUCCESS/ANY/QUORUM: cancel remaining non-terminal dependencies
    # that no other live node needs, once the join condition is satisfied.
    cancel_losers: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "threshold": self.threshold,
            "allowPartial": self.allow_partial,
            "cancelLosers": self.cancel_losers,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> Optional["JoinConfig"]:
        if not data:
            return None
        try:
            policy = JoinPolicy(str(data.get("policy") or "ALL").upper())
        except ValueError:
            policy = JoinPolicy.ALL
        return cls(
            policy=policy,
            threshold=max(1, int(data.get("threshold") or 1)),
            allow_partial=bool(data.get("allowPartial") or data.get("allow_partial")),
            cancel_losers=bool(data.get("cancelLosers", data.get("cancel_losers", True))),
        )


@dataclass
class NodeError:
    """A structured node failure. `code` is stable and testable."""

    code: str
    message: str
    retryable: bool = False
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> Optional["NodeError"]:
        if not data:
            return None
        return cls(
            code=str(data.get("code") or "NODE_ERROR"),
            message=str(data.get("message") or ""),
            retryable=bool(data.get("retryable")),
            detail=data.get("detail"),
        )


@dataclass
class NodeOutcome:
    """The structured result of one node attempt."""

    output: Any = None
    error: Optional[NodeError] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {"output": self.output, "error": self.error.to_dict() if self.error else None}


@dataclass
class ExecutionNode:
    """One unit of work in an execution graph."""

    id: str
    kind: NodeKind
    execution_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    input: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error: Optional[NodeError] = None
    priority: Priority = Priority.NORMAL
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_ms: int = 120_000
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    join: Optional[JoinConfig] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # A stable fingerprint. Two nodes in the same execution with the same key share
    # one execution; None disables deduplication for this node.
    dedup_key: Optional[str] = None
    cacheable: bool = False
    cache_ttl_ms: int = 0
    attempt_count: int = 0
    worker_id: Optional[str] = None
    created_at: float = field(default_factory=now)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATES

    def duration_ms(self) -> int:
        if self.started_at is None:
            return 0
        end = self.completed_at if self.completed_at is not None else now()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "executionId": self.execution_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "input": self.input,
            "output": self.output,
            "error": self.error.to_dict() if self.error else None,
            "priority": self.priority.value,
            "retry": self.retry.to_dict(),
            "timeoutMs": self.timeout_ms,
            "resources": self.resources.to_dict(),
            "join": self.join.to_dict() if self.join else None,
            "metadata": self.metadata,
            "dedupKey": self.dedup_key,
            "cacheable": self.cacheable,
            "cacheTtlMs": self.cache_ttl_ms,
            "attemptCount": self.attempt_count,
            "workerId": self.worker_id,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "durationMs": self.duration_ms(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionNode":
        return cls(
            id=str(data["id"]),
            kind=NodeKind(str(data.get("kind") or "noop").lower()),
            execution_id=str(data.get("executionId") or data.get("execution_id") or ""),
            status=TaskStatus(str(data.get("status") or "PENDING")),
            dependencies=list(data.get("dependencies") or []),
            dependents=list(data.get("dependents") or []),
            input=dict(data.get("input") or {}),
            output=data.get("output"),
            error=NodeError.from_dict(data.get("error")),
            priority=Priority(str(data.get("priority") or "NORMAL")),
            retry=RetryPolicy.from_dict(data.get("retry")),
            timeout_ms=int(data.get("timeoutMs") or data.get("timeout_ms") or 120_000),
            resources=ResourceRequirements.from_dict(data.get("resources")),
            join=JoinConfig.from_dict(data.get("join")),
            metadata=dict(data.get("metadata") or {}),
            dedup_key=data.get("dedupKey") or data.get("dedup_key"),
            cacheable=bool(data.get("cacheable")),
            cache_ttl_ms=int(data.get("cacheTtlMs") or data.get("cache_ttl_ms") or 0),
            attempt_count=int(data.get("attemptCount") or 0),
            worker_id=data.get("workerId"),
            created_at=float(data.get("createdAt") or now()),
            started_at=data.get("startedAt"),
            completed_at=data.get("completedAt"),
        )


@dataclass
class ExecutionGraph:
    """A whole execution: a validated DAG of nodes plus its lifecycle."""

    id: str
    root_task_id: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    failure_policy: FailurePolicy = FailurePolicy.CONTINUE
    quorum: int = 0  # for REQUIRE_QUORUM
    max_concurrency: int = 0  # 0 = use the process-wide limit
    nodes: dict[str, ExecutionNode] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=now)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    updated_at: float = field(default_factory=now)

    def node(self, node_id: str) -> Optional[ExecutionNode]:
        return self.nodes.get(node_id)

    def add_node(self, node: ExecutionNode) -> ExecutionNode:
        node.execution_id = self.id
        self.nodes[node.id] = node
        self.updated_at = now()
        return node

    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            raise KeyError("both endpoints must exist to add an edge")
        if from_id not in self.nodes[to_id].dependencies:
            self.nodes[to_id].dependencies.append(from_id)
        if to_id not in self.nodes[from_id].dependents:
            self.nodes[from_id].dependents.append(to_id)
        self.updated_at = now()

    def edges(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for node in self.nodes.values():
            for dep in node.dependencies:
                out.append((dep, node.id))
        return out

    def roots(self) -> list[str]:
        return [n.id for n in self.nodes.values() if not n.dependencies]

    def leaves(self) -> list[str]:
        return [n.id for n in self.nodes.values() if not n.dependents]

    def to_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.id,
            "rootTaskId": self.root_task_id,
            "status": self.status.value,
            "failurePolicy": self.failure_policy.value,
            "quorum": self.quorum,
            "maxConcurrency": self.max_concurrency,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"from": a, "to": b} for a, b in self.edges()],
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionGraph":
        graph = cls(
            id=str(data["executionId"]),
            root_task_id=str(data.get("rootTaskId") or ""),
            status=ExecutionStatus(str(data.get("status") or "PENDING")),
            failure_policy=FailurePolicy(str(data.get("failurePolicy") or "CONTINUE")),
            quorum=int(data.get("quorum") or 0),
            max_concurrency=int(data.get("maxConcurrency") or 0),
            metadata=dict(data.get("metadata") or {}),
            created_at=float(data.get("createdAt") or now()),
            started_at=data.get("startedAt"),
            completed_at=data.get("completedAt"),
            updated_at=float(data.get("updatedAt") or now()),
        )
        for raw in data.get("nodes") or []:
            node = ExecutionNode.from_dict(raw)
            graph.nodes[node.id] = node
        return graph


@dataclass
class NodeAttempt:
    """One attempt at one node. Every attempt is recorded."""

    id: str
    execution_id: str
    node_id: str
    attempt: int
    status: str = "RUNNING"
    error: Optional[NodeError] = None
    started_at: float = field(default_factory=now)
    finished_at: Optional[float] = None

    @property
    def duration_ms(self) -> int:
        end = self.finished_at if self.finished_at is not None else now()
        return int((end - self.started_at) * 1000)


@dataclass
class ExecutionResult:
    """The structured result of an execution. Never only raw output."""

    execution_id: str
    status: ExecutionStatus
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    skipped_tasks: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, dict[str, Any]] = field(default_factory=dict)
    coverage: float = 1.0
    nodes: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    critical_path_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "status": self.status.value,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "totalTasks": self.total_tasks,
            "successfulTasks": self.successful_tasks,
            "failedTasks": self.failed_tasks,
            "cancelledTasks": self.cancelled_tasks,
            "skippedTasks": self.skipped_tasks,
            "outputs": self.outputs,
            "errors": self.errors,
            "coverage": self.coverage,
            "nodes": self.nodes,
            "timeline": self.timeline,
            "criticalPath": self.critical_path,
            "criticalPathMs": self.critical_path_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_graph(cls, graph: ExecutionGraph, *, timeline: Optional[list[dict[str, Any]]] = None,
                   critical_path: Optional[list[str]] = None, critical_path_ms: int = 0) -> "ExecutionResult":
        nodes = list(graph.nodes.values())
        completed = [n for n in nodes if n.status is TaskStatus.COMPLETED]
        failed = [n for n in nodes if n.status in (TaskStatus.FAILED, TaskStatus.TIMED_OUT)]
        cancelled = [n for n in nodes if n.status is TaskStatus.CANCELLED]
        skipped = [n for n in nodes if n.status in (TaskStatus.SKIPPED, TaskStatus.BLOCKED)]
        outputs = {n.id: n.output for n in completed}
        errors = {n.id: n.error.to_dict() for n in nodes if n.error is not None}
        total = len(nodes)
        coverage = (len(completed) / total) if total else 1.0
        return cls(
            execution_id=graph.id,
            status=graph.status,
            started_at=graph.started_at,
            completed_at=graph.completed_at,
            total_tasks=total,
            successful_tasks=len(completed),
            failed_tasks=len(failed),
            cancelled_tasks=len(cancelled),
            skipped_tasks=len(skipped),
            outputs=outputs,
            errors=errors,
            coverage=round(coverage, 4),
            nodes=[n.to_dict() for n in nodes],
            timeline=timeline or [],
            critical_path=critical_path or [],
            critical_path_ms=critical_path_ms,
            metadata=dict(graph.metadata),
        )


def new_execution_id() -> str:
    return _uid("exec")


def new_node_id(prefix: str = "node") -> str:
    return _uid(prefix)


def new_attempt_id() -> str:
    return _uid("att")


def new_lease_id() -> str:
    return _uid("lease")


__all__ = [
    "ExecutionGraph",
    "ExecutionNode",
    "ExecutionResult",
    "ExecutionStatus",
    "FailurePolicy",
    "JoinConfig",
    "JoinPolicy",
    "NodeAttempt",
    "NodeError",
    "NodeKind",
    "NodeOutcome",
    "Priority",
    "ResourceRequirements",
    "RetryPolicy",
    "SUCCESS_TASK_STATES",
    "TERMINAL_EXECUTION_STATES",
    "TERMINAL_TASK_STATES",
    "TaskStatus",
    "new_attempt_id",
    "new_execution_id",
    "new_lease_id",
    "new_node_id",
    "now",
]
