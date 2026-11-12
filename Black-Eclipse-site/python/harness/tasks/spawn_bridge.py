"""Route A2A/team task execution through the spawn primitive (C5.6).

The task runtime continues to own the PLAN (task rows, dependencies, leases).
When a task is an A2A/team delegation, the execution attempt is a Fabric `agent`
job created by `spawn_child`, and its `ChildOutcome` is mapped back to the task
outcome. Non-delegation tasks keep the existing executor byte-for-byte.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Callable

from .scheduler import TaskRunOutcome


def _is_delegation(task: Any) -> bool:
    metadata = getattr(task, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("a2a") or metadata.get("team"))


def wrap_task_executor(service: Any, base: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap the task executor; only A2A/team tasks go through spawn."""

    async def executor(task: Any, context: Any, run_id: str) -> TaskRunOutcome:
        if not _is_delegation(task):
            return await base(task, context, run_id)

        from ..spawn import SpawnBudget, SpawnSpec, spawn_child  # noqa: PLC0415
        from .context import render_task_query  # noqa: PLC0415

        fabric = getattr(service, "fabric", None)
        if fabric is None:
            # No Fabric in THIS service: the old executor is the honest fallback
            # (a process-global manager from another service must not be used).
            return await base(task, context, run_id)

        query = render_task_query(context)[:4_000] if context is not None else str(
            getattr(task, "objective", "") or getattr(task, "title", "") or ""
        )
        spec = SpawnSpec(
            objective=query,
            agent=str(getattr(task, "assigned_agent_id", "") or "eclipse-agent"),
            budget=SpawnBudget(tokens=120_000, steps=24, timeout_s=900),
        )
        ctx = SimpleNamespace(
            run_id=run_id,
            memory_store=getattr(service, "store", None),
            user_id=getattr(service, "user_id", None),
            workspace_id=None,
            session_id=getattr(service, "session_id", None),
            emitter=None,
        )
        try:
            outcome = await spawn_child(spec, ctx, parent_run_id=run_id, fabric=fabric)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a spawn failure is data
            return TaskRunOutcome(
                status="failed", run_id=run_id, error_class="SPAWN_FAILED",
                error=str(exc)[:2_000],
            )

        if outcome.status == "completed":
            return TaskRunOutcome(
                status="completed",
                output=outcome.output,
                run_id=outcome.run_id or run_id,
                evidence={"claims": outcome.claims[:24]},
                metrics={"tokens": outcome.tokens_used, "spawned": True},
            )
        return TaskRunOutcome(
            status="failed",
            output=outcome.output,
            run_id=outcome.run_id or run_id,
            error=outcome.error or f"spawn {outcome.status}",
            error_class=outcome.error_class or "SPAWN_FAILED",
            evidence={"claims": outcome.claims[:24]},
            metrics={"tokens": outcome.tokens_used, "spawned": True},
        )

    return executor


__all__ = ["wrap_task_executor"]
