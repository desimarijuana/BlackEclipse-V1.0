"""Shared fixtures for the bot-team orchestration tests (offline, deterministic).

The TeamService, A2AService, TaskManager and TaskScheduler under test are the REAL
implementations; only the injected executor (the model backend) is a test double —
exactly the seam the production code injects `service.run` into.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

from harness.a2a.service import A2AService
from harness.events import EventBus
from harness.persistence import AgentMemoryStore
from harness.tasks.scheduler import TaskRunOutcome, TaskScheduler
from harness.team.service import TeamService
from harness.tools import ToolRegistry


def make_host(tmp_path: Any, *, store: Optional[AgentMemoryStore] = None) -> Any:
    memory = store or AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    host = SimpleNamespace(
        store=memory, bus=EventBus(), registry=ToolRegistry(),
        tasks=None, task_scheduler=None, evidence_store=None, a2a=None, team=None,
    )
    a2a = A2AService(host)
    host.a2a = a2a
    host.team = TeamService(host, a2a=a2a)
    return host


def make_scheduler(host: Any, executor: Any, *, max_in_flight: int = 8) -> TaskScheduler:
    return TaskScheduler(host.tasks, executor=executor, max_in_flight=max_in_flight)


def completing_executor(trace: Optional[list] = None):
    async def executor(task, context, run_id):
        if trace is not None:
            trace.append(("start", task.id))
            await asyncio.sleep(0.02)
            trace.append(("end", task.id))
        return TaskRunOutcome(status="completed", output=f"done:{task.title}", run_id=run_id)
    return executor


async def drain(scheduler: TaskScheduler, host: Any, rounds: int = 80) -> None:
    manager = host.tasks
    for _ in range(rounds):
        await scheduler.tick()
        await scheduler.wait_idle()
        if not manager.runnable_tasks():
            break
