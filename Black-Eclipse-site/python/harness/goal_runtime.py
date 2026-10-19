"""Durable-by-default goal runtime (round 4, W8.2).

The chat path no longer leaves "is this a durable task?" to the model's
discretion. Before a chat run executes, a deterministic intake (`tasks/goal.py`)
decides: a long-horizon, multi-deliverable or resumable request is turned into a
durable goal task and THIS run becomes its first attempt; a single short result
stays a single turn. After the run, the task-type verifier settles the durable
task — verified completion, or a bounded repair attempt re-queued for the
scheduler (the product loop continues beyond the chat turn).

One runtime, no second loop: the run itself is unchanged (`service.run` /
`run_background`), the task is created and settled through the EXISTING
`TaskManager`/verifier, and a task-dispatched run (source `task-scheduler`) is
never wrapped again — that would recurse.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .tasks.goal import intake_goal
from .tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    CriterionState,
    TaskStatus,
)
from .tasks.verification import verify_task

log = logging.getLogger("harness.goal_runtime")

#: Run-result blobs the verifier may read as evidence (mirrors the task
#: executor's set — the same evidence, whichever path ran the work).
_EVIDENCE_KEYS: tuple[str, ...] = (
    "codeVerification", "research", "documents", "images", "vision", "capability",
)


def is_chat_run(request: Any) -> bool:
    """Whether this request is an ordinary chat turn (not a task dispatch)."""
    ctx = getattr(getattr(request, "input", None), "context", None) or {}
    if str(ctx.get("source") or "") == "task-scheduler":
        return False
    return not ctx.get("taskId")


def maybe_start_goal(service: Any, request: Any) -> Optional[dict[str, Any]]:
    """Create the durable goal task for a durable chat request, or return None.

    The run itself becomes the task's first attempt (`start_task(run_id=…)`), so
    nothing executes twice. Returns `{"taskId", "planId", "taskType",
    "durableReason"}` and records `goalTaskId` on the request context so the
    settlement step knows what to close.
    """
    manager = getattr(service, "tasks", None)
    if manager is None or not is_chat_run(request):
        return None
    query = str(getattr(getattr(request, "input", None), "query", "") or "").strip()
    if not query:
        return None
    context = getattr(getattr(request, "input", None), "context", None)
    if isinstance(context, dict) and context.get("goalTaskId"):
        return None
    try:
        intake = intake_goal(query)
        if not intake.durable:
            return None
        plan = manager.create_plan(CreatePlanInput(
            name=intake.title, objective=intake.contract.objective,
            description=intake.contract.objective, metadata={"source": "chat-goal"},
        ))
        task = manager.create_task(CreateTaskInput(
            title=intake.title, plan_id=plan.id,
            objective=intake.contract.objective,
            description=intake.contract.objective,
            task_type=intake.task_type, goal_contract=intake.contract,
        ))
        manager.start_plan(plan.id)
        manager.start_task(task.id, run_id=str(getattr(request, "runId", "") or "") or None)
        if isinstance(context, dict):
            context["goalTaskId"] = task.id
        return {
            "taskId": task.id, "planId": plan.id,
            "taskType": intake.task_type.value,
            "durableReason": intake.durable_reason,
        }
    except Exception:  # noqa: BLE001 - goal tracking must never block the run
        log.warning("goal task creation failed", exc_info=True)
        return None


def _dumped(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return dict(result)
    return {}


def settle_goal(service: Any, request: Any, result: Any) -> Optional[dict[str, Any]]:
    """Settle the durable goal task after the chat run finished.

    Verified completion only when the task-type verifier passes; otherwise the
    task is re-queued (TODO) with the missing evidence named, so the EXISTING
    scheduler continues the product loop with a bounded repair attempt.
    """
    manager = getattr(service, "tasks", None)
    if manager is None:
        return None
    context = getattr(getattr(request, "input", None), "context", None) or {}
    task_id = context.get("goalTaskId") if isinstance(context, dict) else None
    if not task_id:
        return None
    try:
        task = manager.get_task(str(task_id))
    except Exception:  # noqa: BLE001 - a vanished task is reported, never invented
        return None
    if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
        return {"ok": True, "taskId": task.id, "settled": task.status.value}

    dumped = _dumped(result)
    run_status = str(dumped.get("status") or "failed")
    try:
        from .tasks.bootstrap import _extract_artifacts  # noqa: PLC0415

        artifacts = _extract_artifacts(dumped, service)
    except Exception:  # noqa: BLE001
        artifacts = []
    evidence = {k: dumped.get(k) for k in _EVIDENCE_KEYS if dumped.get(k)}
    metrics = {
        "toolCalls": dumped.get("toolCalls", 0),
        "totalTokens": dumped.get("totalTokens", 0),
        "modelSteps": dumped.get("modelSteps", 0),
    }

    if task.status == TaskStatus.IN_PROGRESS:
        try:
            manager.begin_verification(task.id)
        except Exception:  # noqa: BLE001 - a status race is not fatal
            pass

    def _requeue(reason: str, error_class: str) -> dict[str, Any]:
        try:
            manager.retry_task(task.id)
            manager._store.update_task_fields(  # noqa: SLF001 - the manager is the writer
                task.id, {"error": reason[:2000], "errorClass": error_class},
            )
            return {"ok": False, "taskId": task.id, "requeued": True,
                    "reason": reason, "errorClass": error_class}
        except Exception as exc:  # noqa: BLE001 - an unqueueable task stays inspectable
            return {"ok": False, "taskId": task.id, "requeued": False, "reason": str(exc)}

    if run_status != "completed":
        error = dumped.get("error")
        message = (error.get("message") if isinstance(error, dict) else None) or "the run did not complete"
        return _requeue(str(message), "RUN_FAILED")

    verification = verify_task(
        task, status="completed", evidence=evidence,
        artifacts=artifacts, metrics=metrics,
    )
    if verification is not None and not verification.ok:
        return _requeue(verification.summary(), "VERIFICATION_FAILED")

    # Verified: satisfy the contract's criteria with the run as evidence, then
    # complete through the SAME structural contract the scheduler uses.
    try:
        for criterion in manager.list_criteria(task.id):
            if criterion.state == CriterionState.PENDING:
                manager.set_criterion(
                    criterion.id, CriterionState.PASSED,
                    evidence=f"run:{getattr(request, 'runId', '') or ''}",
                )
        manager.complete_task(
            task.id, output_reference=str(getattr(request, "runId", "") or "") or None,
        )
        return {"ok": True, "taskId": task.id, "settled": "COMPLETED",
                "verification": verification.to_dict() if verification else None}
    except Exception as exc:  # noqa: BLE001 - a refused completion re-queues for repair
        return _requeue(str(exc), "COMPLETION_REJECTED")


def wrap_service_for_goals(service: Any) -> bool:
    """Wrap `service.run` / `run_background` with the goal lifecycle. Idempotent.

    A no-op when the service has no task manager or the methods are not async.
    The wrapper never changes the run: it decides before, settles after, and a
    failure in either step is logged and swallowed — a chat turn must never
    break over goal bookkeeping.
    """
    if getattr(service, "_goal_runtime_wrapped", False):
        return False
    tasks = getattr(service, "tasks", None)
    if tasks is None:
        return False
    wrapped_any = False
    for method_name in ("run", "run_background"):
        original = getattr(service, method_name, None)
        if original is None or not callable(original):
            continue

        def _make(original=original):  # noqa: ANN001 - closure over the bound method
            async def _run_with_goal(request: Any) -> Any:
                started = None
                try:
                    started = maybe_start_goal(service, request)
                except Exception:  # noqa: BLE001
                    log.warning("goal intake failed", exc_info=True)
                try:
                    result = await original(request)
                except BaseException:
                    if started is not None:
                        try:
                            settle_goal(service, request, {"status": "failed"})
                        except Exception:  # noqa: BLE001
                            log.warning("goal settlement failed", exc_info=True)
                    raise
                if started is not None:
                    try:
                        settle_goal(service, request, result)
                    except Exception:  # noqa: BLE001
                        log.warning("goal settlement failed", exc_info=True)
                return result

            return _run_with_goal

        try:
            setattr(service, method_name, _make())
            wrapped_any = True
        except Exception:  # noqa: BLE001 - an unwrappable service stays unchanged
            log.warning("could not wrap %s for goals", method_name, exc_info=True)
    if wrapped_any:
        try:
            service._goal_runtime_wrapped = True  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
    return wrapped_any


__all__ = [
    "is_chat_run",
    "maybe_start_goal",
    "settle_goal",
    "wrap_service_for_goals",
]
