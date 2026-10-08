"""Shared helpers for the Execution Fabric tests (offline, deterministic)."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Optional

from harness.fabric import ExecutionManager, FabricConfig, FabricStore, FunctionWorker
from harness.persistence import AgentMemoryStore


def make_store(tmp_path: Any) -> AgentMemoryStore:
    return AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))


def make_config(**overrides: Any) -> FabricConfig:
    base: dict[str, Any] = dict(
        poll_seconds=0.02, lease_seconds=5, max_attempts=3, job_timeout_ms=5000,
        shutdown_timeout_s=5, dlq_limit=500, lock_ttl_ms=2000, max_jobs_per_tick=16,
    )
    base.update(overrides)
    return FabricConfig(**base)


def make_manager(store: AgentMemoryStore, **overrides: Any) -> ExecutionManager:
    return ExecutionManager(FabricStore(store), config=make_config(**overrides))


def function_worker(kind: str, queues: list[str], handler: Callable, *, concurrency: int = 1) -> FunctionWorker:
    return FunctionWorker(kind, queues, handler, concurrency=concurrency)


async def wait_terminal(manager: ExecutionManager, job_id: str, *, timeout: float = 6.0) -> Optional[dict[str, Any]]:
    steps = max(1, int(timeout / 0.02))
    for _ in range(steps):
        job = manager.get(job_id)
        if job and job.get("terminal"):
            return job
        await asyncio.sleep(0.02)
    return manager.get(job_id)
