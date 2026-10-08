"""Execution policies — tools/tasks declare HOW they must run.

A policy is the decision input to the ExecutionManager's routing. It is not
hardcoded per tool: `PolicyRegistry` holds defaults per job type, and a caller
(agent tool metadata, automation, JDdS ingestion) may override any field.

    browser.scrape -> DURABLE, queue=browser, timeout=5m, concurrency=browser
    get_price      -> DIRECT

The `ExecutionPolicy` names the execution mode, resource class, priority, retry
and durability so the manager can route without a chain of `if name == ...`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional

from .config import FabricConfig
from .models import (
    ExecutionMode,
    JobPriority,
    QueueName,
    WorkerKind,
    priority_weight,
)


@dataclass(frozen=True)
class ExecutionPolicy:
    mode: ExecutionMode = ExecutionMode.CONCURRENT
    queue: str = QueueName.AGENT.value
    worker_kind: Optional[str] = None
    priority: int = JobPriority.RESEARCH.weight
    timeout_ms: int = 120_000
    max_attempts: int = 1
    backoff_ms: int = 500
    multiplier: float = 2.0
    jitter: float = 0.1
    resources: dict[str, int] = field(default_factory=dict)
    idempotent: bool = False
    durable: bool = False
    allow_dlq: bool = True
    sandbox: bool = False

    def merged(self, **overrides: Any) -> "ExecutionPolicy":
        clean = {k: v for k, v in overrides.items() if v is not None and k in self.__dataclass_fields__}
        if "priority" in clean:
            clean["priority"] = priority_weight(clean["priority"])
        if "mode" in clean and not isinstance(clean["mode"], ExecutionMode):
            clean["mode"] = ExecutionMode(str(clean["mode"]).upper())
        if "queue" in clean and not isinstance(clean["queue"], str):
            clean["queue"] = QueueName.from_value(clean["queue"]).value
        return replace(self, **clean)

    def to_dict(self) -> dict[str, Any]:
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}
        data["mode"] = self.mode.value
        return data


# Default policy per job type. Fast/synchronous work is DIRECT; long, isolated or
# retry-heavy work is queued.
DEFAULT_POLICIES: dict[str, ExecutionPolicy] = {
    "tool": ExecutionPolicy(mode=ExecutionMode.DIRECT, queue=QueueName.USER.value,
                            worker_kind=WorkerKind.TOOL.value, priority=JobPriority.USER_REQUEST.weight,
                            timeout_ms=30_000),
    "agent": ExecutionPolicy(mode=ExecutionMode.CONCURRENT, queue=QueueName.AGENT.value,
                             worker_kind=WorkerKind.AGENT.value, priority=JobPriority.AGENT_INTERACTIVE.weight,
                             timeout_ms=900_000, max_attempts=2, backoff_ms=1000),
    "research": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.RESEARCH.value,
                                worker_kind=WorkerKind.RESEARCH.value, priority=JobPriority.RESEARCH.weight,
                                timeout_ms=900_000, max_attempts=2, backoff_ms=1000),
    "browser": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.BROWSER.value,
                               worker_kind=WorkerKind.BROWSER.value, priority=JobPriority.RESEARCH.weight,
                               timeout_ms=300_000, max_attempts=2, resources={"browser": 1}),
    "scraping": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.SCRAPING.value,
                                worker_kind=WorkerKind.SCRAPING.value, priority=JobPriority.INGESTION.weight,
                                timeout_ms=300_000, max_attempts=3, resources={"browser": 1}),
    "market": ExecutionPolicy(mode=ExecutionMode.DURABLE, queue=QueueName.MARKET.value,
                              worker_kind=WorkerKind.MARKET.value, priority=JobPriority.INGESTION.weight,
                              timeout_ms=120_000, max_attempts=4, backoff_ms=2000,
                              idempotent=True, durable=True, resources={"network": 1}),
    "quant": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.QUANT.value,
                             worker_kind=WorkerKind.QUANT.value, priority=JobPriority.RESEARCH.weight,
                             timeout_ms=1_800_000, max_attempts=1, resources={"code": 1}),
    "python": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.PYTHON.value,
                              worker_kind=WorkerKind.PYTHON.value, priority=JobPriority.RESEARCH.weight,
                              timeout_ms=600_000, max_attempts=2, resources={"code": 1}, sandbox=True),
    "code": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.CODE.value,
                            worker_kind=WorkerKind.CODE.value, priority=JobPriority.AGENT_INTERACTIVE.weight,
                            timeout_ms=600_000, max_attempts=2, resources={"code": 1}, sandbox=True),
    "plugin": ExecutionPolicy(mode=ExecutionMode.DURABLE, queue=QueueName.PLUGIN.value,
                              worker_kind=WorkerKind.PLUGIN.value, priority=JobPriority.RESEARCH.weight,
                              timeout_ms=120_000, max_attempts=3, idempotent=True, durable=True),
    "notification": ExecutionPolicy(mode=ExecutionMode.DURABLE, queue=QueueName.NOTIFICATION.value,
                                    worker_kind=WorkerKind.NOTIFICATION.value, priority=JobPriority.AGENT_INTERACTIVE.weight,
                                    timeout_ms=60_000, max_attempts=4, backoff_ms=500,
                                    idempotent=True, durable=True),
    "automation": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.AUTOMATION.value,
                                  worker_kind=WorkerKind.AUTOMATION.value, priority=JobPriority.MAINTENANCE.weight,
                                  timeout_ms=900_000, max_attempts=1),
    "event": ExecutionPolicy(mode=ExecutionMode.BACKGROUND, queue=QueueName.EVENT.value,
                             worker_kind=WorkerKind.EVENT.value, priority=JobPriority.AGENT_INTERACTIVE.weight,
                             timeout_ms=300_000, max_attempts=2),
}


class PolicyRegistry:
    """Resolve a policy for a job type, with env-config defaults applied."""

    def __init__(self, config: Optional[FabricConfig] = None) -> None:
        self._config = config or FabricConfig()
        self._policies: dict[str, ExecutionPolicy] = dict(DEFAULT_POLICIES)

    @property
    def config(self) -> FabricConfig:
        return self._config

    def register(self, job_type: str, policy: ExecutionPolicy) -> None:
        self._policies[str(job_type).strip().lower()] = policy

    def policy_for(self, job_type: str) -> ExecutionPolicy:
        return self._policies.get(str(job_type).strip().lower(), DEFAULT_POLICIES["tool"])

    def resolve(self, job_type: str, **overrides: Any) -> ExecutionPolicy:
        """The effective policy: the default, with env defaults, then overrides."""
        base = self.policy_for(job_type)
        config = self._config
        defaults: dict[str, Any] = {
            "timeout_ms": config.job_timeout_ms
            if base.timeout_ms == DEFAULT_POLICIES["tool"].timeout_ms else base.timeout_ms,
            "max_attempts": base.max_attempts,
        }
        merged = base.merged(**defaults).merged(**overrides)
        return merged


__all__ = ["DEFAULT_POLICIES", "ExecutionPolicy", "PolicyRegistry"]
