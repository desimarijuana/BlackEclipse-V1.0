"""Boot wiring for the W4 autonomy loop (goals, gates, judge, loops).

One idempotent install: construct the goal/loop runtimes over the ONE
agent-memory store, subscribe to terminal task events so a finished turn is
evaluated, and register the loop heartbeat on the EXISTING automation tick.
Every step is best-effort: autonomy must never block boot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .goal_runtime import GoalError, GoalRuntime, loop_mode
from .loop_runtime import LoopRuntime
from .store import GoalStore

log = logging.getLogger("harness.goals.bootstrap")

_TERMINAL_EVENTS = frozenset({
    "task.completed", "task.failed", "task.blocked", "task.cancelled",
})
_EVALUATE_EVENTS = frozenset({"task.completed", "task.failed", "task.blocked"})


class AutonomyService:
    """The thin facade shared by the router and the automation tick."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.store = GoalStore(service.store)
        self.goals = GoalRuntime(service, self.store)
        self.loops = LoopRuntime(service, self.store)
        self._evaluating: set[str] = set()

    # ── Goals ────────────────────────────────────────────────────────────────
    def create_goal(self, objective: str, **kwargs: Any) -> Any:
        return self.goals.create(objective, **kwargs)

    def get_goal(self, goal_id: str) -> Any:
        return self.goals.get(goal_id)

    def list_goals(self, *, session_id: Optional[str] = None,
                   status: Optional[str] = None) -> list[Any]:
        return self.goals.list(session_id=session_id, status=status)

    def pause_goal(self, goal_id: str, reason: str = "operator") -> Any:
        return self.goals.pause(goal_id, reason)

    def resume_goal(self, goal_id: str) -> Any:
        return self.goals.resume(goal_id)

    def cancel_goal(self, goal_id: str) -> Any:
        return self.goals.cancel(goal_id)

    def verdicts(self, goal_id: str) -> list[dict[str, Any]]:
        return self.goals.verdicts(goal_id)

    # ── Loops ────────────────────────────────────────────────────────────────
    def create_loop(self, session_id: str, **kwargs: Any) -> Any:
        return self.loops.create(session_id, **kwargs)

    def list_loops(self, *, session_id: Optional[str] = None,
                   status: Optional[str] = None) -> list[Any]:
        return self.loops.list(session_id=session_id, status=status)

    def pause_loop(self, loop_id: str, reason: str = "operator") -> Any:
        return self.loops.pause(loop_id, reason)

    def resume_loop(self, loop_id: str) -> Any:
        return self.loops.resume(loop_id)

    def cancel_loop(self, loop_id: str) -> Any:
        return self.loops.cancel(loop_id)

    # ── Event bridge + heartbeat ─────────────────────────────────────────────
    def on_task_event(self, event: dict[str, Any]) -> None:
        """Synchronous bus listener: schedule evaluation off the writer."""
        event_type = str(event.get("type") or "")
        if event_type not in _TERMINAL_EVENTS:
            return
        task_id = str(event.get("taskId") or "")
        if not task_id:
            return
        if event_type not in _EVALUATE_EVENTS:
            return
        try:
            asyncio.get_running_loop().create_task(self.handle_task_event(task_id))
        except RuntimeError:
            # A synchronous test/boot caller can await `handle_task_event`.
            log.debug("no running loop; task %s will be evaluated on demand", task_id)

    async def handle_task_event(self, task_id: str) -> Optional[dict[str, Any]]:
        if loop_mode() == "off":
            return None
        if task_id in self._evaluating:
            return None
        goal = self.store.goal_for_task(task_id)
        if goal is None:
            return None
        self._evaluating.add(task_id)
        try:
            manager = getattr(self.service, "tasks", None)
            task = manager.get_task(task_id) if manager is not None else None
            # The scheduler records the run on the task's COMPLETION
            # (`outputReference`), not always on `assignedRunId`; and an
            # execution row is the last resort. Resolve all three so an
            # event-driven evaluation still has the run's evidence.
            run_id = str(getattr(task, "assigned_run_id", "") or "") or None
            if not run_id and task is not None:
                candidate = str(getattr(task, "output_reference", "") or "")
                if candidate.startswith("run_"):
                    run_id = candidate
            if not run_id and manager is not None:
                for execution in reversed(manager.list_executions(task_id)):
                    if execution.run_id:
                        run_id = str(execution.run_id)
                        break
            run = {}
            if run_id:
                try:
                    run = self.service.store.get_run(run_id) or {}
                except Exception:  # noqa: BLE001 - a missing run is still evaluable
                    run = {}
            summary = {
                "status": str((run or {}).get("status") or
                              (task.status.value if task is not None else "failed")),
                "output": (run or {}).get("output") or "",
                "totalTokens": int((run or {}).get("totalTokens") or 0),
                "toolCalls": int((run or {}).get("toolCalls") or 0),
                "modelSteps": int((run or {}).get("modelSteps") or 0),
                "taskId": task_id,
                "codeVerification": (run or {}).get("codeVerification"),
                "research": (run or {}).get("research"),
                "documents": (run or {}).get("documents"),
                "images": (run or {}).get("images"),
            }
            return await self.goals.evaluate(goal.id, run_id, summary)
        except GoalError as exc:
            log.warning("goal evaluation refused for task %s: %s", task_id, exc)
            return None
        except Exception:  # noqa: BLE001 - evaluation must never break a task write
            log.warning("goal evaluation failed for task %s", task_id, exc_info=True)
            return None
        finally:
            self._evaluating.discard(task_id)

    async def tick(self, now: Any) -> dict[str, int]:
        report = await self.loops.tick(now)
        # A `wait` verdict parks a goal with a wake time; the same heartbeat is
        # the only wakeup path. It is independent of loops.
        if loop_mode() != "off":
            try:
                from ..persistence import now_iso  # noqa: PLC0415

                report["wokenGoals"] = len(self.goals.wake_due(now_iso()))
            except Exception:  # noqa: BLE001 - a wake failure must not break the tick
                log.warning("goal wake tick failed", exc_info=True)
        return report

    def health(self) -> dict[str, Any]:
        goals = self.store.list_goals(limit=500)
        loops = self.store.list_loops(limit=500)
        by_status: dict[str, int] = {}
        for goal in goals:
            by_status[goal.status] = by_status.get(goal.status, 0) + 1
        active_loops = [loop for loop in loops if loop.status == "active"]
        return {
            "mode": loop_mode(),
            "goals": {"total": len(goals), "byStatus": by_status},
            "loops": {
                "total": len(loops), "active": len(active_loops),
                "kinds": {
                    kind: sum(1 for loop in loops if loop.kind == kind)
                    for kind in ("loop", "heartbeat")
                },
            },
        }


def install_autonomy_layer(service: Any) -> bool:
    """Install W4 on the service. Idempotent and best-effort."""
    if getattr(service, "autonomy", None) is not None:
        return False
    try:
        layer = AutonomyService(service)
        service.autonomy = layer
        bus = getattr(service, "bus", None)
        if bus is not None:
            bus.subscribe(layer.on_task_event)
        try:
            engine = service.automation_engine()
            engine.add_tick_hook(layer.tick)
        except Exception:  # noqa: BLE001 - the engine may not exist in a test host
            log.debug("automation engine unavailable; loop tick not attached")
        return True
    except Exception:  # noqa: BLE001 - autonomy must never block boot
        log.warning("autonomy layer unavailable", exc_info=True)
        service.autonomy = None
        return False


__all__ = ["AutonomyService", "install_autonomy_layer"]
