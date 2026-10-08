"""Eclipse Execution Fabric — the common execution substrate.

    agent / tool / automation / event / JDdS
                -> ExecutionManager
                -> DIRECT | CONCURRENT | BACKGROUND | DURABLE
                -> durable queue (SQLite, the ONE agent-memory connection)
                -> worker pool -> existing capability

It deliberately reuses the existing runtime (orchestration DAG engine, tool
registry, agent graph, automation engine, event system, plugins, browser, quant,
sandbox) and adds routing, durability, idempotency, priority, retries, DLQ,
cancellation, distributed locks and observability around it.
"""

from __future__ import annotations

from .bootstrap import (
    install_fabric_layer,
    recover_fabric,
    start_fabric,
    stop_fabric,
)
from .config import FabricConfig
from .locks import DistributedLockManager, LockNotAcquired
from .manager import ExecutionManager
from .metrics import FabricMetrics
from .models import (
    ExecutionMode,
    Job,
    JobAttempt,
    JobPriority,
    JobState,
    QueueName,
    WorkerInfo,
    WorkerKind,
    WorkerOutcome,
    WorkerStatus,
)
from .policies import DEFAULT_POLICIES, ExecutionPolicy, PolicyRegistry
from .state import (
    InvalidJobTransition,
    JobStateMachine,
    can_transition,
    is_job_terminal,
    is_replayable,
)
from .store import FabricStore
from .workers import (
    BaseWorker,
    FunctionWorker,
    WorkerContext,
    WorkerManager,
    WorkerRegistry,
)

__all__ = [
    "BaseWorker",
    "DEFAULT_POLICIES",
    "DistributedLockManager",
    "ExecutionManager",
    "ExecutionMode",
    "ExecutionPolicy",
    "FabricConfig",
    "FabricMetrics",
    "FabricStore",
    "FunctionWorker",
    "InvalidJobTransition",
    "Job",
    "JobAttempt",
    "JobPriority",
    "JobState",
    "JobStateMachine",
    "LockNotAcquired",
    "PolicyRegistry",
    "QueueName",
    "WorkerContext",
    "WorkerInfo",
    "WorkerKind",
    "WorkerManager",
    "WorkerOutcome",
    "WorkerRegistry",
    "WorkerStatus",
    "can_transition",
    "install_fabric_layer",
    "is_job_terminal",
    "is_replayable",
    "recover_fabric",
    "start_fabric",
    "stop_fabric",
]
