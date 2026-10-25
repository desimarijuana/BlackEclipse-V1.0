"""Configuration for the Execution Fabric, resolved from the environment.

Every operationally-sensitive knob has a safe desktop default and an env
override, so nothing production-sensitive is hardcoded and `npm run dev` keeps
working with zero setup. Configuration is validated on construction.

Environment (all optional):

  HARNESS_FABRIC_ENABLED                1|0            (default 1)
  HARNESS_FABRIC_POLL_SECONDS           float          (default 0.5)
  HARNESS_FABRIC_LEASE_SECONDS          int            (default 120)
  HARNESS_FABRIC_MAX_ATTEMPTS           int            (default 3)
  HARNESS_FABRIC_JOB_TIMEOUT_MS         int            (default 120000)
  HARNESS_FABRIC_SHUTDOWN_TIMEOUT_S     int            (default 20)
  HARNESS_FABRIC_DLQ_LIMIT              int            (default 1000)
  HARNESS_FABRIC_LOCK_TTL_MS            int            (default 30000)
  HARNESS_FABRIC_MAX_JOBS_PER_TICK      int            (default 16)
  HARNESS_FABRIC_<QUEUE>_CONCURRENCY    int            per-queue worker count
  HARNESS_FABRIC_RATE_<KEY>             rps,burst      token bucket per key
  HARNESS_FABRIC_WORKERS                csv            worker kinds/queues this
                                                       process runs; unset = all,
                                                       `none` = producer-only
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import QUEUE_DEFAULTS, QueueName


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(minimum, int(float(raw)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(minimum, float(raw))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "enabled")


def _workers_env() -> Optional[frozenset[str]]:
    raw = os.environ.get("HARNESS_FABRIC_WORKERS")
    if raw is None or not raw.strip():
        return None
    names = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(names)


@dataclass
class FabricConfig:
    enabled: bool = True
    poll_seconds: float = 0.5
    lease_seconds: int = 120
    max_attempts: int = 3
    job_timeout_ms: int = 120_000
    shutdown_timeout_s: int = 20
    dlq_limit: int = 1000
    lock_ttl_ms: int = 30_000
    max_jobs_per_tick: int = 16
    # queue -> worker concurrency (number of concurrent slots)
    queue_concurrency: dict[str, int] = field(default_factory=dict)
    # provider/tool key -> (requests_per_second, burst)
    rate_limits: dict[str, tuple[float, float]] = field(default_factory=dict)
    # Worker kinds/queues this process may run. None = every worker (the
    # single-process default); an empty set = producer-only (another process
    # owns the consumer loops).
    workers: Optional[frozenset[str]] = None

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0:
            self.poll_seconds = 0.5
        if self.lease_seconds < 5:
            self.lease_seconds = 5
        if self.max_attempts < 1:
            self.max_attempts = 1
        if self.job_timeout_ms < 100:
            self.job_timeout_ms = 100
        if self.shutdown_timeout_s < 1:
            self.shutdown_timeout_s = 1

    def runs_worker(self, kind: str, queues: Any) -> bool:
        """Whether THIS process may run a worker (multi-process split)."""
        if self.workers is None:
            return True
        if "none" in self.workers:
            return False
        names = {str(kind).strip().lower()}
        names.update(str(queue).strip().lower() for queue in queues)
        return bool(self.workers & names)

    def concurrency_for(self, queue: Any) -> int:
        name = QueueName.from_value(queue).value
        if name in self.queue_concurrency:
            return max(1, int(self.queue_concurrency[name]))
        _, default = QUEUE_DEFAULTS[QueueName.from_value(queue)]
        return max(1, default)

    @classmethod
    def from_env(cls) -> "FabricConfig":
        queue_concurrency: dict[str, int] = {}
        for queue in QueueName:
            env_name = f"HARNESS_FABRIC_{queue.value.upper()}_CONCURRENCY"
            if os.environ.get(env_name) is not None:
                queue_concurrency[queue.value] = max(1, _int_env(env_name, 1, minimum=1))
        rate_limits: dict[str, tuple[float, float]] = {}
        prefix = "HARNESS_FABRIC_RATE_"
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            name = key[len(prefix):].strip().lower()
            parts = [p for p in value.split(",") if p.strip()]
            if not name or not parts:
                continue
            try:
                rps = max(0.0, float(parts[0]))
                burst = float(parts[1]) if len(parts) > 1 else max(1.0, rps)
            except (TypeError, ValueError):
                continue
            rate_limits[name] = (rps, burst)
        return cls(
            enabled=_bool_env("HARNESS_FABRIC_ENABLED", True),
            poll_seconds=_float_env("HARNESS_FABRIC_POLL_SECONDS", 0.5, minimum=0.05),
            lease_seconds=_int_env("HARNESS_FABRIC_LEASE_SECONDS", 120, minimum=5),
            max_attempts=_int_env("HARNESS_FABRIC_MAX_ATTEMPTS", 3, minimum=1),
            job_timeout_ms=_int_env("HARNESS_FABRIC_JOB_TIMEOUT_MS", 120_000, minimum=100),
            shutdown_timeout_s=_int_env("HARNESS_FABRIC_SHUTDOWN_TIMEOUT_S", 20, minimum=1),
            dlq_limit=_int_env("HARNESS_FABRIC_DLQ_LIMIT", 1000, minimum=1),
            lock_ttl_ms=_int_env("HARNESS_FABRIC_LOCK_TTL_MS", 30_000, minimum=1000),
            max_jobs_per_tick=_int_env("HARNESS_FABRIC_MAX_JOBS_PER_TICK", 16, minimum=1),
            queue_concurrency=queue_concurrency,
            rate_limits=rate_limits,
            workers=_workers_env(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "pollSeconds": self.poll_seconds,
            "leaseSeconds": self.lease_seconds,
            "maxAttempts": self.max_attempts,
            "jobTimeoutMs": self.job_timeout_ms,
            "shutdownTimeoutSeconds": self.shutdown_timeout_s,
            "dlqLimit": self.dlq_limit,
            "lockTtlMs": self.lock_ttl_ms,
            "maxJobsPerTick": self.max_jobs_per_tick,
            "queueConcurrency": dict(self.queue_concurrency),
            "rateLimits": {k: list(v) for k, v in self.rate_limits.items()},
            "workers": sorted(self.workers) if self.workers is not None else None,
        }


__all__ = ["FabricConfig"]
