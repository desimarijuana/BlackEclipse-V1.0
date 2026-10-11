"""Domain models for the Eclipse Execution Fabric.

The Execution Fabric is the ONE execution substrate beneath the agent runtime:

    agent / tool / automation / event
            -> ExecutionManager   (this package)
            -> DIRECT | CONCURRENT | BACKGROUND | DURABLE
            -> durable queue -> worker pool -> existing capability

It deliberately reuses the existing runtime: an `agent` job calls `service.run`,
a `tool` job calls `ToolRegistry.execute`, a DAG delegates to the existing
`orchestration` engine. Nothing here re-implements an agent loop, a tool
registry, or a second scheduler.

These models are dependency-light (dataclasses + enums), so the queue and worker
framework can be driven by tests without a model, a registry or a database — the
same discipline the orchestration layer follows.
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


def new_job_id() -> str:
    return _uid("job")


def new_attempt_id() -> str:
    return _uid("jatt")


def new_event_id() -> str:
    return _uid("jevt")


def new_worker_id() -> str:
    return _uid("wrk")


# ── Job lifecycle ────────────────────────────────────────────────────────────


class JobState(str, Enum):
    """The lifecycle state of one job. A `str` enum for easy serialization."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    DEAD_LETTER = "DEAD_LETTER"


# A job that will never run again without an explicit admin action.
TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.TIMED_OUT,
        JobState.DEAD_LETTER,
    }
)

# Terminal states that may be re-driven by an explicit retry/replay.
REPLAYABLE_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.FAILED, JobState.TIMED_OUT, JobState.DEAD_LETTER}
)

SUCCESS_JOB_STATES: frozenset[JobState] = frozenset({JobState.SUCCEEDED})


class ExecutionMode(str, Enum):
    """How much machinery a unit of work needs. Chosen by the ExecutionManager."""

    # Fast, inline, no queue: a read, a cheap calculation, a cached lookup.
    DIRECT = "DIRECT"
    # Queued and awaited: the caller blocks for the result but concurrency is
    # managed (child agents, parallel research).
    CONCURRENT = "CONCURRENT"
    # Queued, fire-and-forget: outlives the request; the caller gets a job id.
    BACKGROUND = "BACKGROUND"
    # Queued and persisted with restart survival + idempotency: ingestion,
    # scheduled work, retry-heavy, distributed.
    DURABLE = "DURABLE"


class JobPriority(str, Enum):
    """Scheduling priority. Higher `weight` runs first.

    The vocabulary is Eclipse's, not a generic one: a user request must never be
    starved by bulk ingestion.
    """

    USER_REQUEST = "USER_REQUEST"
    TRADING_ALERT = "TRADING_ALERT"
    AGENT_INTERACTIVE = "AGENT_INTERACTIVE"
    RESEARCH = "RESEARCH"
    INGESTION = "INGESTION"
    MAINTENANCE = "MAINTENANCE"

    @property
    def weight(self) -> int:
        return _PRIORITY_WEIGHTS[self]


_PRIORITY_WEIGHTS: dict[JobPriority, int] = {
    JobPriority.USER_REQUEST: 1000,
    JobPriority.TRADING_ALERT: 900,
    JobPriority.AGENT_INTERACTIVE: 750,
    JobPriority.RESEARCH: 500,
    JobPriority.INGESTION: 250,
    JobPriority.MAINTENANCE: 100,
}


def priority_weight(value: Any) -> int:
    """Resolve a priority (enum name, enum, or raw int) to its integer weight."""
    if isinstance(value, JobPriority):
        return value.weight
    if isinstance(value, bool):
        return _PRIORITY_WEIGHTS[JobPriority.RESEARCH]
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        try:
            return JobPriority(value.strip().upper()).weight
        except ValueError:
            return _PRIORITY_WEIGHTS[JobPriority.RESEARCH]
    return _PRIORITY_WEIGHTS[JobPriority.RESEARCH]


def priority_name(weight: int) -> str:
    """The nearest named priority for an integer weight (for display)."""
    best = JobPriority.MAINTENANCE
    best_delta = 10_000
    for candidate in JobPriority:
        delta = abs(candidate.weight - int(weight))
        if delta < best_delta:
            best, best_delta = candidate, delta
    return best.value


# ── Queues ───────────────────────────────────────────────────────────────────


class QueueName(str, Enum):
    """Named queues. Each maps to a resource class and a default concurrency."""

    USER = "user"
    AGENT = "agent"
    RESEARCH = "research"
    BROWSER = "browser"
    SCRAPING = "scraping"
    MARKET = "market"
    QUANT = "quant"
    PYTHON = "python"
    CODE = "code"
    PLUGIN = "plugin"
    NOTIFICATION = "notification"
    AUTOMATION = "automation"
    EVENT = "event"
    MAINTENANCE = "maintenance"
    ML = "ml"

    @classmethod
    def from_value(cls, value: Any) -> "QueueName":
        if isinstance(value, QueueName):
            return value
        text = str(value or "").strip().lower()
        for name in cls:
            if name.value == text:
                return name
        return cls.AGENT


# queue -> (resource class used for admission/rate limits, default concurrency)
QUEUE_DEFAULTS: dict[QueueName, tuple[str, int]] = {
    QueueName.USER: ("llm", 8),
    QueueName.AGENT: ("agent", 4),
    QueueName.RESEARCH: ("network", 6),
    QueueName.BROWSER: ("browser", 3),
    QueueName.SCRAPING: ("browser", 3),
    QueueName.MARKET: ("network", 10),
    QueueName.QUANT: ("code", 2),
    QueueName.PYTHON: ("code", 2),
    QueueName.CODE: ("code", 4),
    QueueName.PLUGIN: ("network", 4),
    QueueName.NOTIFICATION: ("network", 8),
    QueueName.AUTOMATION: ("agent", 2),
    QueueName.EVENT: ("agent", 4),
    QueueName.MAINTENANCE: ("database", 1),
    QueueName.ML: ("code", 1),
}


# ── Workers ──────────────────────────────────────────────────────────────────


class WorkerKind(str, Enum):
    """The domain a worker executes. Each maps onto an existing capability."""

    TOOL = "tool"
    AGENT = "agent"
    RESEARCH = "research"
    BROWSER = "browser"
    SCRAPING = "scraping"
    MARKET = "market"
    QUANT = "quant"
    PYTHON = "python"
    CODE = "code"
    PLUGIN = "plugin"
    NOTIFICATION = "notification"
    AUTOMATION = "automation"
    EVENT = "event"
    ML = "ml"


class WorkerStatus(str, Enum):
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    UNHEALTHY = "UNHEALTHY"


# ── Job ──────────────────────────────────────────────────────────────────────


@dataclass
class Job:
    """One durable unit of work. Mirrors the `FabricJob` row."""

    id: str = field(default_factory=new_job_id)
    type: str = "tool"
    queue: str = QueueName.AGENT.value
    status: str = JobState.CREATED.value
    priority: int = 500
    worker_kind: Optional[str] = None
    task_id: Optional[str] = None
    parent_job_id: Optional[str] = None
    root_job_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    input: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error: Optional[str] = None
    error_class: Optional[str] = None
    progress: float = 0.0
    attempts: int = 0
    max_attempts: int = 1
    timeout_ms: int = 120_000
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    worker_id: Optional[str] = None
    durable: bool = False
    available_at: Optional[float] = None
    created_at: float = field(default_factory=now)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cancelled_at: Optional[float] = None
    updated_at: float = field(default_factory=now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> JobState:
        try:
            return JobState(self.status)
        except ValueError:
            return JobState.CREATED

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_JOB_STATES

    def allow_dlq(self) -> bool:
        """Whether exhausted retries route to the dead-letter queue."""
        return bool(self.metadata.get("allowDlq", True))

    def duration_ms(self) -> int:
        if self.started_at is None:
            return 0
        end = self.completed_at if self.completed_at is not None else now()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """A camelCase wire view (the repo's contract style), plus `id`/`state`."""
        return {
            "id": self.id, "jobId": self.id, "type": self.type, "queue": self.queue,
            "status": self.status, "state": self.state.value,
            "priority": self.priority, "workerKind": self.worker_kind,
            "taskId": self.task_id, "parentJobId": self.parent_job_id,
            "rootJobId": self.root_job_id, "agentId": self.agent_id,
            "sessionId": self.session_id, "userId": self.user_id,
            "workspaceId": self.workspace_id, "input": self.input, "output": self.output,
            "error": self.error, "errorClass": self.error_class, "progress": self.progress,
            "attempts": self.attempts, "maxAttempts": self.max_attempts,
            "timeoutMs": self.timeout_ms, "idempotencyKey": self.idempotency_key,
            "correlationId": self.correlation_id, "traceId": self.trace_id,
            "workerId": self.worker_id, "durable": self.durable,
            "availableAt": self.available_at, "createdAt": self.created_at,
            "startedAt": self.started_at, "completedAt": self.completed_at,
            "cancelledAt": self.cancelled_at, "updatedAt": self.updated_at,
            "metadata": self.metadata, "terminal": self.terminal,
            "durationMs": self.duration_ms(),
        }


@dataclass
class JobAttempt:
    """One attempt at one job. Every attempt is recorded."""

    id: str = field(default_factory=new_attempt_id)
    job_id: str = ""
    attempt: int = 1
    worker_id: Optional[str] = None
    status: str = "RUNNING"
    error: Optional[str] = None
    error_class: Optional[str] = None
    started_at: float = field(default_factory=now)
    finished_at: Optional[float] = None
    duration_ms: int = 0


@dataclass
class WorkerInfo:
    """A registered worker's identity + live health snapshot."""

    id: str
    kind: str
    queue: str
    status: str = WorkerStatus.STARTING.value
    concurrency: int = 1
    active_jobs: int = 0
    pid: Optional[int] = None
    started_at: float = field(default_factory=now)
    last_heartbeat_at: float = field(default_factory=now)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Results ──────────────────────────────────────────────────────────────────


@dataclass
class WorkerOutcome:
    """The structured result of one worker attempt. Never only raw output."""

    status: str = "succeeded"  # succeeded | failed | cancelled | timed_out | retrying
    output: Any = None
    error: Optional[str] = None
    error_class: Optional[str] = None
    retryable: bool = False
    progress: float = 1.0
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_outcome(raw: Any) -> WorkerOutcome:
    """Coerce a worker handler's return value into a `WorkerOutcome`."""
    if isinstance(raw, WorkerOutcome):
        return raw
    if isinstance(raw, dict):
        return WorkerOutcome(
            status=str(raw.get("status") or "succeeded"),
            output=raw.get("output"),
            error=raw.get("error"),
            error_class=raw.get("errorClass") or raw.get("error_class"),
            retryable=bool(raw.get("retryable")),
            progress=float(raw.get("progress", 1.0) or 0.0),
            artifacts=list(raw.get("artifacts") or []),
            metrics=dict(raw.get("metrics") or {}),
        )
    if isinstance(raw, tuple) and len(raw) == 2:
        return WorkerOutcome(status="succeeded", output=raw[0], metrics=raw[1] or {})
    return WorkerOutcome(status="succeeded", output=raw)


__all__ = [
    "ExecutionMode",
    "Job",
    "JobAttempt",
    "JobPriority",
    "JobState",
    "QUEUE_DEFAULTS",
    "QueueName",
    "REPLAYABLE_JOB_STATES",
    "SUCCESS_JOB_STATES",
    "TERMINAL_JOB_STATES",
    "WorkerInfo",
    "WorkerKind",
    "WorkerOutcome",
    "WorkerStatus",
    "coerce_outcome",
    "new_attempt_id",
    "new_event_id",
    "new_job_id",
    "new_worker_id",
    "now",
    "priority_name",
    "priority_weight",
]
