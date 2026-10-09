"""TaskManager — the ONE writer of task/plan state.

Every mutation a caller can make goes through here, and every status change is
validated by `state.py` first. The manager owns:
  * plan + task creation with validated references;
  * the dependency graph (with cycle rejection before a row is written);
  * acceptance criteria and completion VERIFICATION (a task is not complete just
    because an agent said so);
  * cancellation with child cascade;
  * deterministic parent state + progress roll-up;
  * the immutable event history (persisted in `HarnessTaskEvent`, published on the
    process bus when one is supplied).

The manager is UI- and model-agnostic: it never runs a task. Dispatch is the
scheduler's job; execution is the runtime's job.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..persistence import now_iso
from . import dag
from .model import (
    BlockedReason,
    CreatePlanInput,
    CreateTaskInput,
    CriterionState,
    DependencyKind,
    MAX_CHILDREN_PER_TASK,
    Plan,
    PlanStatus,
    REQUIRED_DEPENDENCY_KINDS,
    Task,
    TaskAcceptanceCriterion,
    TaskArtifact,
    TaskCheckpoint,
    TaskDependency,
    TaskEvent,
    TaskEventType,
    TaskExecution,
    TaskPriority,
    TaskStatus,
    WaitingReason,
)
from .state import (
    InvalidPlanTransition,
    InvalidTaskTransition,
    TaskOperation,
    can_transition_plan,
    can_transition_task,
    require_plan_transition,
)
from .store import TaskStore, new_id

# Structured refusal codes. Stable and testable.
TASK_NOT_FOUND = "TASK_NOT_FOUND"
PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
INVALID_PARENT = "INVALID_PARENT"
INVALID_PLAN = "INVALID_PLAN"
DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
TOO_MANY_CHILDREN = "TOO_MANY_CHILDREN"
INVALID_TRANSITION = "INVALID_TRANSITION"
COMPLETION_REJECTED = "COMPLETION_REJECTED"
INVALID_STATUS = "INVALID_STATUS"
CROSS_PLAN_DEPENDENCY = "CROSS_PLAN_DEPENDENCY"
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"

Publisher = Callable[[str, dict[str, Any]], None]

_TERMINAL = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


class TaskError(ValueError):
    """A structured task refusal. `code` is stable; `message` is plain."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TaskManager:
    def __init__(self, store: TaskStore, *, publisher: Optional[Publisher] = None) -> None:
        self._store = store
        self._publisher = publisher

    # ── Events ───────────────────────────────────────────────────────────────
    def _emit(
        self, event_type: str, *, task: Optional[Task] = None,
        plan_id: Optional[str] = None, data: Optional[dict[str, Any]] = None,
    ) -> TaskEvent:
        payload = dict(data or {})
        if task is not None:
            plan_id = plan_id or task.plan_id
            payload.setdefault("taskId", task.id)
            payload.setdefault("status", task.status.value)
            payload.setdefault("title", task.title)
        if plan_id:
            payload.setdefault("planId", plan_id)
        event = self._store.append_event(
            event_type=event_type, plan_id=plan_id,
            task_id=task.id if task is not None else None, data=payload,
        )
        if self._publisher is not None:
            try:
                self._publisher(event_type, {"event": event.model_dump(by_alias=True)})
            except Exception:  # noqa: BLE001 - a live listener must never break a write
                pass
        return event

    # ── Plans ────────────────────────────────────────────────────────────────
    def create_plan(self, payload: CreatePlanInput | dict[str, Any]) -> Plan:
        data = payload if isinstance(payload, CreatePlanInput) else CreatePlanInput(**payload)
        moment = now_iso()
        plan = Plan(
            id=new_id("plan"), name=data.name, description=data.description,
            objective=data.objective, status=PlanStatus.PLANNING, priority=data.priority,
            agent_id=data.agent_id, metadata=data.metadata,
            created_at=moment, updated_at=moment,
        )
        self._store.save_plan(plan)
        self._emit(TaskEventType.PLAN_CREATED.value, plan_id=plan.id,
                   data={"name": plan.name, "status": plan.status.value})
        return plan

    def get_plan(self, plan_id: str) -> Plan:
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise TaskError(PLAN_NOT_FOUND, f"no plan {plan_id!r}")
        return plan

    def list_plans(self, *, limit: int = 100, status: Optional[str] = None) -> list[Plan]:
        return self._store.list_plans(limit=limit, status=status)

    def set_plan_status(
        self, plan_id: str, status: PlanStatus | str, *, operation: Optional[str] = None
    ) -> Plan:
        plan = self.get_plan(plan_id)
        target = PlanStatus(status) if not isinstance(status, PlanStatus) else status
        if target == plan.status:
            return plan
        try:
            require_plan_transition(plan.status, target, operation=operation)
        except InvalidPlanTransition as exc:
            raise TaskError(INVALID_TRANSITION, str(exc)) from exc
        updated = self._store.update_plan_fields(plan_id, {"status": target.value})
        assert updated is not None
        self._emit(TaskEventType.PLAN_STATUS_CHANGED.value, plan_id=plan_id,
                   data={"status": target.value, "from": plan.status.value})
        return updated

    def start_plan(self, plan_id: str) -> Plan:
        """Move a plan to RUNNING (from PLANNING/READY/BLOCKED)."""
        plan = self.get_plan(plan_id)
        if plan.status == PlanStatus.RUNNING:
            return plan
        if plan.status == PlanStatus.PLANNING:
            plan = self.set_plan_status(plan_id, PlanStatus.READY)
        return self.set_plan_status(plan_id, PlanStatus.RUNNING)

    # ── Tasks ────────────────────────────────────────────────────────────────
    def create_task(
        self, payload: CreateTaskInput | dict[str, Any], *, actor_id: Optional[str] = None
    ) -> Task:
        data = payload if isinstance(payload, CreateTaskInput) else CreateTaskInput(**payload)
        plan_id = data.plan_id
        parent: Optional[Task] = None
        if data.parent_task_id:
            parent = self._store.get_task(data.parent_task_id)
            if parent is None:
                raise TaskError(INVALID_PARENT,
                                f"parent task {data.parent_task_id!r} does not exist")
            if plan_id is None:
                plan_id = parent.plan_id
            elif parent.plan_id != plan_id:
                raise TaskError(INVALID_PARENT, "parent task belongs to a different plan")
        if plan_id is not None and self._store.get_plan(plan_id) is None:
            raise TaskError(INVALID_PLAN, f"plan {plan_id!r} does not exist")
        if parent is not None and self._store.count_children(parent.id) >= MAX_CHILDREN_PER_TASK:
            raise TaskError(TOO_MANY_CHILDREN,
                            f"a task may have at most {MAX_CHILDREN_PER_TASK} subtasks")

        moment = now_iso()
        task = Task(
            id=new_id("task"), plan_id=plan_id, parent_task_id=data.parent_task_id,
            title=data.title, description=data.description, objective=data.objective,
            status=TaskStatus.TODO, priority=data.priority,
            assigned_agent_id=data.assigned_agent_id, required=data.required,
            failure_policy=data.failure_policy, weight=data.weight,
            max_retries=data.max_retries, metadata=data.metadata,
            created_at=moment, updated_at=moment,
        )
        # Validate dependencies BEFORE writing the task so a cycle never persists.
        deps: list[str] = []
        for dep_id in data.dependencies:
            prereq = self._store.get_task(dep_id)
            if prereq is None:
                raise TaskError(DEPENDENCY_NOT_FOUND, f"dependency {dep_id!r} does not exist")
            if plan_id is not None and prereq.plan_id not in (None, plan_id):
                raise TaskError(CROSS_PLAN_DEPENDENCY, "a dependency may not cross plans")
            deps.append(dep_id)
        self._check_no_cycle(task.id, deps, plan_id)

        self._store.insert_task(task)
        for ordinal, criterion in enumerate(data.acceptance_criteria):
            self._store.add_criterion(
                task_id=task.id, text=criterion.text, required=criterion.required,
                ordinal=ordinal,
            )
        for dep_id in deps:
            self._store.add_dependency(
                task_id=task.id, depends_on_task_id=dep_id, kind=DependencyKind.REQUIRES
            )
        task = self._reconcile_dependency_block(task, emit=False)
        if plan_id is not None:
            plan = self._store.get_plan(plan_id)
            if plan is not None and plan.root_task_id is None:
                self._store.update_plan_fields(plan_id, {"rootTaskId": task.id})
        self._emit(TaskEventType.TASK_CREATED.value, task=task,
                   data={"priority": task.priority.value, "parentTaskId": task.parent_task_id})
        if task.status == TaskStatus.BLOCKED:
            self._emit(TaskEventType.TASK_BLOCKED.value, task=task,
                       data={"blockedReason": BlockedReason.DEPENDENCY.value,
                             "blockedBy": task.blocked_by})
        self.recompute_ancestors(task.id)
        self.bump_plan_revision(plan_id, reason="task_created")
        return self.get_task(task.id)

    def add_subtask(
        self, parent_task_id: str, payload: CreateTaskInput | dict[str, Any],
        *, actor_id: Optional[str] = None,
    ) -> Task:
        if isinstance(payload, CreateTaskInput):
            data = payload.model_dump(by_alias=False)
        else:
            data = dict(payload)
        data.pop("parent_task_id", None)
        data["parent_task_id"] = parent_task_id
        return self.create_task(data, actor_id=actor_id)

    def decompose_task(
        self, task_id: str, subtasks: list[CreateTaskInput | dict[str, Any]],
        *, actor_id: Optional[str] = None,
    ) -> list[Task]:
        parent = self.get_task(task_id)
        created = [self.add_subtask(task_id, sub, actor_id=actor_id) for sub in subtasks]
        self._emit(TaskEventType.TASK_DECOMPOSED.value, task=parent,
                   data={"childIds": [t.id for t in created], "count": len(created)})
        self.recompute_ancestors(task_id)
        return created

    def get_task(self, task_id: str) -> Task:
        task = self._store.get_task(task_id)
        if task is None:
            raise TaskError(TASK_NOT_FOUND, f"no task {task_id!r}")
        return task

    def list_tasks(
        self, *, plan_id: Optional[str] = None, parent_task_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 500,
    ) -> list[Task]:
        return self._store.list_tasks(
            plan_id=plan_id, parent_task_id=parent_task_id, status=status, limit=limit
        )

    def update_task(
        self, task_id: str, fields: dict[str, Any], *, actor_id: Optional[str] = None
    ) -> Task:
        """Update non-status fields. A `status` key is routed through the machine."""
        task = self.get_task(task_id)
        status = fields.pop("status", None)
        updated = task
        if fields:
            updated = self._store.update_task_fields(task_id, fields) or task
            self._emit(TaskEventType.TASK_UPDATED.value, task=updated,
                       data={"fields": sorted(fields.keys())})
        if status is not None:
            target = TaskStatus(status) if not isinstance(status, TaskStatus) else status
            updated = self._transition(updated, target)
            self._emit_for_status(updated, previous=task.status)
            self._after_terminal(updated, completed=target == TaskStatus.COMPLETED)
        return self.get_task(task_id)

    # ── State transitions ────────────────────────────────────────────────────
    def _transition(
        self, task: Task, target: TaskStatus, *, operation: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Task:
        if target == task.status:
            return task
        if not can_transition_task(task.status, target, operation=operation):
            raise TaskError(INVALID_TRANSITION,
                            f"cannot move task from {task.status.value} to {target.value}")
        moment = now_iso()
        fields: dict[str, Any] = {"status": target}
        if extra:
            fields.update(extra)
        if target == TaskStatus.IN_PROGRESS and task.started_at is None:
            fields.setdefault("startedAt", moment)
        if target in _TERMINAL:
            fields.setdefault("completedAt", moment)
        if target != TaskStatus.IN_PROGRESS:
            fields.setdefault("claimedBy", None)
            fields.setdefault("claimToken", None)
            fields.setdefault("claimedAt", None)
            fields.setdefault("leaseExpiresAt", None)
        if target == TaskStatus.COMPLETED:
            fields.setdefault("progress", 100)
        if target not in (TaskStatus.WAITING, TaskStatus.ASKING_USER):
            fields.setdefault("waitingReason", None)
        if target != TaskStatus.BLOCKED:
            fields.setdefault("blockedReason", None)
            fields.setdefault("blockedBy", [])
        if target in (TaskStatus.TODO, TaskStatus.IN_PROGRESS):
            fields.setdefault("error", None)
            fields.setdefault("errorClass", None)
        self._store.update_task_fields(task.id, fields)
        return self.get_task(task.id)

    def _emit_for_status(self, task: Task, *, previous: TaskStatus) -> None:
        event_type = {
            TaskStatus.IN_PROGRESS: TaskEventType.TASK_STARTED,
            TaskStatus.VERIFYING: TaskEventType.TASK_VERIFYING,
            TaskStatus.ASKING_USER: TaskEventType.TASK_ASKING_USER,
            TaskStatus.WAITING: TaskEventType.TASK_WAITING,
            TaskStatus.BLOCKED: TaskEventType.TASK_BLOCKED,
            TaskStatus.FAILED: TaskEventType.TASK_FAILED,
            TaskStatus.COMPLETED: TaskEventType.TASK_COMPLETED,
            TaskStatus.CANCELLED: TaskEventType.TASK_CANCELLED,
        }.get(task.status)
        if event_type is not None:
            self._emit(event_type.value, task=task, data={"from": previous.value})

    def start_task(
        self, task_id: str, *, actor_id: Optional[str] = None, run_id: Optional[str] = None
    ) -> Task:
        task = self.get_task(task_id)
        extra = {"assignedRunId": run_id} if run_id else None
        updated = self._transition(task, TaskStatus.IN_PROGRESS, extra=extra)
        self._emit_for_status(updated, previous=task.status)
        return updated

    def begin_verification(
        self, task_id: str, *, actor_id: Optional[str] = None
    ) -> Task:
        """Move a running task into the authoritative VERIFYING state.

        Entered after the run completes and before the completion contract is
        evaluated, so an interrupted verification is recoverable as VERIFYING
        rather than looking like an ordinary run.
        """
        task = self.get_task(task_id)
        updated = self._transition(task, TaskStatus.VERIFYING)
        self._emit_for_status(updated, previous=task.status)
        return updated

    def wait_task(
        self, task_id: str, *, reason: WaitingReason | str = WaitingReason.EXTERNAL_EVENT,
        actor_id: Optional[str] = None,
    ) -> Task:
        task = self.get_task(task_id)
        value = WaitingReason(reason) if not isinstance(reason, WaitingReason) else reason
        # A question or an approval parks the task in ASKING_USER (a HUMAN wait);
        # every other external event stays WAITING. The reason is still recorded.
        target = (
            TaskStatus.ASKING_USER
            if value in (WaitingReason.USER_INPUT, WaitingReason.APPROVAL)
            else TaskStatus.WAITING
        )
        updated = self._transition(task, target, extra={"waitingReason": value})
        self._emit_for_status(updated, previous=task.status)
        return updated

    def block_task(
        self, task_id: str, *, reason: BlockedReason | str = BlockedReason.DEPENDENCY,
        blocked_by: Optional[list[str]] = None, actor_id: Optional[str] = None,
    ) -> Task:
        task = self.get_task(task_id)
        value = BlockedReason(reason) if not isinstance(reason, BlockedReason) else reason
        updated = self._transition(
            task, TaskStatus.BLOCKED,
            extra={"blockedReason": value, "blockedBy": blocked_by or []},
        )
        self._emit_for_status(updated, previous=task.status)
        return updated

    def unblock_task(self, task_id: str, *, actor_id: Optional[str] = None) -> Task:
        task = self.get_task(task_id)
        updated = self._transition(task, TaskStatus.TODO)
        self._emit(TaskEventType.TASK_UNBLOCKED.value, task=updated,
                   data={"from": TaskStatus.BLOCKED.value})
        return updated

    def resume_task(self, task_id: str, *, actor_id: Optional[str] = None) -> Task:
        task = self.get_task(task_id)
        return self._transition(task, TaskStatus.TODO)

    def fail_task(
        self, task_id: str, *, error: str = "", error_class: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Task:
        task = self.get_task(task_id)
        if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.TODO,
                               TaskStatus.WAITING, TaskStatus.ASKING_USER,
                               TaskStatus.VERIFYING, TaskStatus.BLOCKED):
            raise TaskError(INVALID_TRANSITION, f"cannot fail a task in {task.status.value}")
        updated = self._transition(task, TaskStatus.FAILED,
                                   extra={"error": error[:2000], "errorClass": error_class})
        self._emit_for_status(updated, previous=task.status)
        self._after_terminal(updated, completed=False)
        return updated

    def escalate_task(
        self, task_id: str, *, target: TaskStatus | str, error: str = "",
        error_class: Optional[str] = None, actor_id: Optional[str] = None,
    ) -> Task:
        """Escalate a task that exhausted its retry budget.

        ``target`` is ``BLOCKED`` (a resource/prerequisite that will not resolve
        by retrying) or ``ASKING_USER`` (only a human can unblock it). Both stay
        NON-terminal and inspectable rather than being silently failed. The
        default scheduler policy is still FAILED; escalation is opt-in per task.
        """
        task = self.get_task(task_id)
        want = TaskStatus(target) if not isinstance(target, TaskStatus) else target
        if want is TaskStatus.ASKING_USER:
            value = WaitingReason.USER_INPUT
            updated = self._transition(
                task, TaskStatus.ASKING_USER,
                extra={"waitingReason": value, "error": error[:2000], "errorClass": error_class},
            )
        elif want is TaskStatus.BLOCKED:
            updated = self._transition(
                task, TaskStatus.BLOCKED,
                extra={"blockedReason": BlockedReason.RESOURCE,
                       "error": error[:2000], "errorClass": error_class},
            )
        else:
            raise TaskError(VALIDATION_ERROR, f"cannot escalate to {want.value}")
        self._emit_for_status(updated, previous=task.status)
        self._emit(TaskEventType.TASK_ESCALATED.value, task=updated,
                   data={"target": want.value, "errorClass": error_class})
        return updated

    def retry_task(self, task_id: str, *, actor_id: Optional[str] = None) -> Task:
        task = self.get_task(task_id)
        self._transition(task, TaskStatus.TODO, operation=TaskOperation.RETRY.value)
        self._store.update_task_fields(task_id, {"retryCount": task.retry_count + 1,
                                                 "availableAt": None})
        updated = self.get_task(task_id)
        self._emit(TaskEventType.TASK_RETRIED.value, task=updated,
                   data={"retryCount": updated.retry_count})
        return updated

    def reopen_task(self, task_id: str, *, actor_id: Optional[str] = None) -> Task:
        task = self.get_task(task_id)
        updated = self._transition(task, TaskStatus.TODO, operation=TaskOperation.REOPEN.value)
        self._emit(TaskEventType.TASK_UPDATED.value, task=updated,
                   data={"reopened": True, "from": task.status.value})
        return updated

    def complete_task(
        self, task_id: str, *, output_reference: Optional[str] = None,
        force: bool = False, actor_id: Optional[str] = None,
    ) -> Task:
        """Complete a task ONLY when its completion contract passes.

        Verification checks required dependencies, required child tasks, required
        acceptance criteria and a required output reference. `force=True` records
        an explicit override event instead of silently ignoring a failed check — it
        is the caller's auditable decision, never the default.
        """
        task = self.get_task(task_id)
        if task.status == TaskStatus.COMPLETED:
            return task
        failures = self.verify_completion(task)
        if failures and not force:
            self._emit(TaskEventType.TASK_COMPLETION_REJECTED.value, task=task,
                       data={"reasons": failures})
            raise TaskError(COMPLETION_REJECTED, "; ".join(failures))
        extra: dict[str, Any] = {}
        if output_reference is not None:
            extra["outputReference"] = output_reference
        if task.status == TaskStatus.TODO:
            task = self._transition(task, TaskStatus.IN_PROGRESS)
        updated = self._transition(task, TaskStatus.COMPLETED, extra=extra)
        if failures and force:
            self._emit(TaskEventType.TASK_COMPLETION_OVERRIDDEN.value, task=updated,
                       data={"reasons": failures, "actorId": actor_id})
        self._emit_for_status(updated, previous=task.status)
        self._after_terminal(updated, completed=True)
        return updated

    def cancel_task(
        self, task_id: str, *, reason: str = "", cascade: bool = True,
        actor_id: Optional[str] = None,
    ) -> list[Task]:
        """Cancel a task and (by default) every non-terminal descendant.

        Returns the whole cancelled set, deepest first. Orphaned running children
        are never left behind.
        """
        task = self.get_task(task_id)
        self._emit(TaskEventType.TASK_CANCEL_REQUESTED.value, task=task,
                   data={"reason": reason, "cascade": cascade})
        cancelled: list[Task] = []
        targets: list[Task] = [task]
        if cascade:
            targets.extend(self._descendants(task_id))
        for target in sorted(targets, key=lambda t: -self._depth(t.id)):
            current = self._store.get_task(target.id)
            if current is None or current.status in _TERMINAL:
                continue
            updated = self._transition(current, TaskStatus.CANCELLED,
                                       extra={"error": reason[:2000] or None})
            cancelled.append(updated)
            self._emit_for_status(updated, previous=current.status)
        self.recompute_ancestors(task_id)
        return cancelled

    def cancel_plan(
        self, plan_id: str, *, reason: str = "", actor_id: Optional[str] = None
    ) -> Plan:
        """Cancel a whole plan and every non-terminal task inside it.

        Cancels deepest-first (a parent after its children), then forces the plan
        to CANCELLED. Already-terminal plans are returned unchanged. This is the
        operator's stop switch for a running plan; it does not reverse external
        side effects already performed (a compensating action is a separate,
        explicit operation).
        """
        plan = self.get_plan(plan_id)
        if plan.status in (PlanStatus.COMPLETED, PlanStatus.FAILED, PlanStatus.CANCELLED):
            return plan
        tasks = self._store.list_tasks(plan_id=plan_id, limit=5000)
        for task in sorted(tasks, key=lambda t: -self._depth(t.id)):
            current = self._store.get_task(task.id)
            if current is None or current.status in _TERMINAL:
                continue
            try:
                self.cancel_task(task.id, reason=reason, cascade=False, actor_id=actor_id)
            except TaskError:
                pass
        updated = self._store.get_plan(plan_id)
        if updated is not None and updated.status not in (
            PlanStatus.COMPLETED, PlanStatus.FAILED, PlanStatus.CANCELLED
        ):
            updated = self.set_plan_status(plan_id, PlanStatus.CANCELLED)
        return updated if updated is not None else plan

    def bump_plan_revision(self, plan_id: Optional[str], *, reason: str) -> None:
        """Record a structural change to a plan (a new revision).

        A plan's shape can change mid-flight (a new step, a new edge, a
        decomposition). Each structural change increments a monotonic revision in
        the plan's metadata and emits PLAN_REVISED, so a plan change is auditable
        and a stale view can be detected. Completed work is never removed by this.
        """
        if not plan_id:
            return
        plan = self._store.get_plan(plan_id)
        if plan is None:
            return
        metadata = dict(plan.metadata or {})
        revision = int(metadata.get("revision") or 1) + 1
        metadata["revision"] = revision
        metadata["revisionReason"] = reason
        self._store.update_plan_fields(plan_id, {"metadata": metadata})
        self._emit(TaskEventType.PLAN_REVISED.value, plan_id=plan_id,
                   data={"revision": revision, "reason": reason})

    # ── Dependencies ─────────────────────────────────────────────────────────
    def add_dependency(
        self, task_id: str, depends_on_task_id: str,
        kind: DependencyKind | str = DependencyKind.REQUIRES,
        *, actor_id: Optional[str] = None,
    ) -> TaskDependency:
        task = self.get_task(task_id)
        prereq = self.get_task(depends_on_task_id)
        if task.id == prereq.id:
            raise TaskError(DEPENDENCY_CYCLE, "a task cannot depend on itself")
        if task.plan_id and prereq.plan_id and task.plan_id != prereq.plan_id:
            raise TaskError(CROSS_PLAN_DEPENDENCY, "a dependency may not cross plans")
        k = DependencyKind(kind) if not isinstance(kind, DependencyKind) else kind
        deps = [d.depends_on_task_id for d in self._store.list_dependencies(task_id)]
        deps.append(prereq.id)
        self._check_no_cycle(task.id, deps, task.plan_id)
        dep = self._store.add_dependency(task_id=task_id, depends_on_task_id=prereq.id, kind=k)
        self._emit(TaskEventType.TASK_DEPENDENCY_ADDED.value, task=task,
                   data={"dependsOnTaskId": prereq.id, "kind": k.value})
        self._reconcile_dependency_block(self.get_task(task_id))
        self.bump_plan_revision(task.plan_id, reason="dependency_added")
        return dep

    def remove_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        task = self.get_task(task_id)
        removed = self._store.remove_dependency(
            task_id=task_id, depends_on_task_id=depends_on_task_id
        )
        if removed:
            self._emit(TaskEventType.TASK_DEPENDENCY_REMOVED.value, task=task,
                       data={"dependsOnTaskId": depends_on_task_id})
            self._reconcile_dependency_block(self.get_task(task_id))
            self.bump_plan_revision(task.plan_id, reason="dependency_removed")
        return removed

    def get_dependencies(self, task_id: str) -> list[TaskDependency]:
        return self._store.list_dependencies(task_id)

    def get_dependents(self, task_id: str) -> list[TaskDependency]:
        return self._store.list_dependents(task_id)

    def dependency_states(self, task: Task) -> list[tuple[str, TaskStatus]]:
        """REQUIRED ``(prerequisite_id, status)`` pairs for a task."""
        out: list[tuple[str, TaskStatus]] = []
        for dep in self._store.list_dependencies(task.id):
            if dep.kind not in REQUIRED_DEPENDENCY_KINDS:
                continue
            prereq = self._store.get_task(dep.depends_on_task_id)
            out.append((dep.depends_on_task_id,
                        prereq.status if prereq else TaskStatus.FAILED))
        return out

    def is_runnable(self, task: Task, *, now: Optional[str] = None) -> bool:
        """The deterministic runnable predicate (§11), pure given the task row."""
        if task.status != TaskStatus.TODO:
            return False
        if task.claim_token is not None:
            return False
        if task.available_at is not None and now is not None and task.available_at > now:
            return False
        if self._store.count_children(task.id) > 0:
            return False  # a container is derived, never dispatched directly
        if dag.unmet_dependencies(self.dependency_states(task)):
            return False
        if task.parent_task_id:
            parent = self._store.get_task(task.parent_task_id)
            if parent is None or parent.status in _TERMINAL:
                return False
        return True

    def runnable_tasks(
        self, *, plan_id: Optional[str] = None, limit: int = 200, now: Optional[str] = None
    ) -> list[Task]:
        """All runnable tasks, highest priority first (deterministic tie-break)."""
        moment = now or now_iso()
        candidates = self._store.list_tasks(
            plan_id=plan_id, status=TaskStatus.TODO.value, limit=2000
        )
        ready = [t for t in candidates if self.is_runnable(t, now=moment)]
        ready.sort(key=lambda t: (-_priority_rank(t.priority), t.created_at, t.id))
        return ready[:limit]

    def _reconcile_dependency_block(self, task: Task, *, emit: bool = True) -> Task:
        unmet = dag.unmet_dependencies(self.dependency_states(task))
        if unmet and task.status == TaskStatus.TODO:
            updated = self._transition(
                task, TaskStatus.BLOCKED,
                extra={"blockedReason": BlockedReason.DEPENDENCY, "blockedBy": unmet},
            )
            if emit:
                self._emit_for_status(updated, previous=task.status)
            return updated
        if (not unmet and task.status == TaskStatus.BLOCKED
                and task.blocked_reason == BlockedReason.DEPENDENCY):
            updated = self._transition(task, TaskStatus.TODO)
            if emit:
                self._emit(TaskEventType.TASK_UNBLOCKED.value, task=updated,
                           data={"from": TaskStatus.BLOCKED.value})
            return updated
        return task

    def _notify_dependents(self, task: Task, *, completed: bool) -> None:
        """Unblock every dependent of a task that has just COMPLETED.

        A dependent is re-reconciled only after ALL of its required prerequisites
        are COMPLETED, so a diamond (A,B -> D) unblocks exactly once, when the
        last prerequisite lands.
        """
        if not completed:
            return
        for dep in self._store.list_dependents(task.id):
            self._emit(TaskEventType.TASK_DEPENDENCY_COMPLETED.value,
                       task=self._store.get_task(dep.task_id),
                       data={"prerequisite": task.id})
        for dep in self._store.list_dependents(task.id):
            dependent = self._store.get_task(dep.task_id)
            if dependent is not None:
                self._reconcile_dependency_block(dependent)

    def _after_terminal(self, task: Task, *, completed: bool) -> None:
        """Unblock dependents when a prerequisite completes, then roll up."""
        self._notify_dependents(task, completed=completed)
        self.recompute_ancestors(task.id)

    # ── Acceptance criteria ──────────────────────────────────────────────────
    def add_criterion(
        self, task_id: str, text: str, *, required: bool = True
    ) -> TaskAcceptanceCriterion:
        task = self.get_task(task_id)
        existing = self._store.list_criteria(task_id)
        criterion = self._store.add_criterion(
            task_id=task.id, text=text, required=required, ordinal=len(existing)
        )
        self._emit(TaskEventType.TASK_CRITERION_UPDATED.value, task=task,
                   data={"criterionId": criterion.id, "state": criterion.state.value})
        return criterion

    def set_criterion(
        self, criterion_id: str, state: CriterionState | str, *, evidence: Optional[str] = None
    ) -> TaskAcceptanceCriterion:
        value = CriterionState(state) if not isinstance(state, CriterionState) else state
        criterion = self._store.update_criterion_state(
            criterion_id, state=value, evidence=evidence
        )
        if criterion is None:
            raise TaskError(TASK_NOT_FOUND, f"no criterion {criterion_id!r}")
        task = self._store.get_task(criterion.task_id)
        self._emit(TaskEventType.TASK_CRITERION_UPDATED.value, task=task,
                   data={"criterionId": criterion.id, "state": value.value})
        return criterion

    def list_criteria(self, task_id: str) -> list[TaskAcceptanceCriterion]:
        return self._store.list_criteria(task_id)

    def verify_completion(self, task: Task) -> list[str]:
        """The completion contract. Returns human-readable failures (empty = pass)."""
        failures: list[str] = []
        for prereq_id, status in self.dependency_states(task):
            if status != TaskStatus.COMPLETED:
                failures.append(f"dependency {prereq_id} is {status.value}, not COMPLETED")
        for child in self._store.list_children(task.id):
            if not child.required:
                continue
            if child.status != TaskStatus.COMPLETED:
                failures.append(
                    f"required subtask {child.id} is {child.status.value}, not COMPLETED"
                )
        for criterion in self._store.list_criteria(task.id):
            if criterion.required and criterion.state != CriterionState.PASSED:
                failures.append(f"acceptance criterion not passed: {criterion.text}")
        metadata = task.metadata or {}
        if metadata.get("requireOutputReference") and not task.output_reference:
            failures.append("no output reference was recorded")
        required_artifacts = metadata.get("requiredArtifacts") or []
        if required_artifacts:
            present = {(a.label or a.kind) for a in self._store.list_artifacts(task.id)}
            for needed in required_artifacts:
                if needed not in present:
                    failures.append(f"required artifact missing: {needed}")
        return failures

    # ── Roll-ups ─────────────────────────────────────────────────────────────
    def recompute_ancestors(self, task_id: str) -> None:
        current = self._store.get_task(task_id)
        seen: set[str] = set()
        while current is not None and current.parent_task_id:
            parent_id = current.parent_task_id
            if parent_id in seen:
                break
            seen.add(parent_id)
            parent = self._store.get_task(parent_id)
            if parent is None:
                break
            self.recompute_container(parent)
            current = self._store.get_task(parent_id)
        origin = self._store.get_task(task_id)
        if origin is not None and origin.plan_id:
            self.recompute_plan(origin.plan_id)

    def recompute_plan(self, plan_id: str) -> Optional[Plan]:
        """Derive a plan's terminal status from its tasks (§9).

        A plan is COMPLETED only when every task is COMPLETED, FAILED when any
        task failed, CANCELLED when every task was cancelled, BLOCKED when all
        remaining work is blocked, otherwise RUNNING. Only a legal transition is
        applied (a PLANNING plan stays PLANNING until `start_plan`).
        """
        plan = self._store.get_plan(plan_id)
        if plan is None:
            return None
        tasks = self._store.list_tasks(plan_id=plan_id, limit=2000)
        if not tasks:
            return plan
        statuses = [t.status for t in tasks]

        def _all(state: TaskStatus) -> bool:
            return all(s == state for s in statuses)

        if _all(TaskStatus.COMPLETED):
            target = PlanStatus.COMPLETED
        elif any(s == TaskStatus.FAILED for s in statuses):
            target = PlanStatus.FAILED
        elif _all(TaskStatus.CANCELLED):
            target = PlanStatus.CANCELLED
        elif any(s in (TaskStatus.IN_PROGRESS, TaskStatus.WAITING) for s in statuses):
            target = PlanStatus.RUNNING
        elif any(s == TaskStatus.BLOCKED for s in statuses):
            target = PlanStatus.BLOCKED
        else:
            target = PlanStatus.RUNNING
        if target == plan.status or not can_transition_plan(plan.status, target):
            return plan
        updated = self._store.update_plan_fields(plan_id, {"status": target.value})
        self._emit(TaskEventType.PLAN_STATUS_CHANGED.value, plan_id=plan_id,
                   data={"status": target.value, "from": plan.status.value})
        return updated

    def recompute_container(self, parent: Task) -> Task:
        """Derive a container's status + progress from its children (deterministic)."""
        children = self._store.list_children(parent.id)
        if not children:
            return parent
        # A container with children is live: move TODO -> IN_PROGRESS once so the
        # derived COMPLETED/FAILED edges below are all legal.
        if parent.status == TaskStatus.TODO:
            self._store.update_task_fields(parent.id, {
                "status": TaskStatus.IN_PROGRESS.value,
                "startedAt": parent.started_at or now_iso(),
            })
            parent = self._store.get_task(parent.id) or parent
        new_status = dag.derive_parent_status(
            [(c.status, c.required, parent.failure_policy) for c in children]
        )
        new_progress = dag.derive_parent_progress(
            [(c.progress, c.weight, c.status) for c in children]
        )
        fields: dict[str, Any] = {}
        if new_progress is not None and new_progress != parent.progress:
            fields["progress"] = new_progress
        if (new_status is not None and new_status != parent.status
                and can_transition_task(parent.status, new_status)):
            fields["status"] = new_status
            if new_status in _TERMINAL:
                fields["completedAt"] = now_iso()
            if new_status == TaskStatus.COMPLETED:
                fields["progress"] = 100
        if not fields:
            return parent
        self._store.update_task_fields(parent.id, fields)
        updated = self._store.get_task(parent.id) or parent
        if "status" in fields:
            self._emit_for_status(updated, previous=parent.status)
            # A container that auto-completes must unblock ITS dependents too
            # (ancestors are handled by the walking caller, not here).
            if updated.status == TaskStatus.COMPLETED:
                self._notify_dependents(updated, completed=True)
        elif "progress" in fields:
            self._emit(TaskEventType.TASK_PROGRESS_UPDATED.value, task=updated,
                       data={"progress": updated.progress})
        return updated

    def progress_of(self, task_id: str) -> int:
        return self.get_task(task_id).progress

    # ── Artifacts / checkpoints ──────────────────────────────────────────────
    def attach_artifact(
        self, task_id: str, *, uri: str, kind: str = "file", digest: Optional[str] = None,
        size_bytes: Optional[int] = None, label: Optional[str] = None,
        execution_id: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
    ) -> TaskArtifact:
        task = self.get_task(task_id)
        artifact = self._store.add_artifact(
            task_id=task.id, uri=uri, kind=kind, digest=digest, size_bytes=size_bytes,
            label=label, execution_id=execution_id, metadata=metadata,
        )
        self._emit(TaskEventType.TASK_ARTIFACT_ADDED.value, task=task,
                   data={"artifactId": artifact.id, "uri": uri, "kind": kind})
        return artifact

    def list_artifacts(self, task_id: str) -> list[TaskArtifact]:
        return self._store.list_artifacts(task_id)

    def save_checkpoint(
        self, task_id: str, *, label: str = "checkpoint",
        payload: Optional[dict[str, Any]] = None, execution_id: Optional[str] = None,
    ) -> TaskCheckpoint:
        task = self.get_task(task_id)
        checkpoint = self._store.save_checkpoint(
            task_id=task.id, label=label, payload=payload, execution_id=execution_id
        )
        self._emit(TaskEventType.TASK_CHECKPOINT_CREATED.value, task=task,
                   data={"checkpointId": checkpoint.id, "label": label})
        return checkpoint

    def list_checkpoints(self, task_id: str) -> list[TaskCheckpoint]:
        return self._store.list_checkpoints(task_id)

    def prune(self, *, retention_days: int = 90) -> dict[str, int]:
        """Apply the retention policy to aged execution/trace rows."""
        return self._store.prune(retention_days=retention_days)

    def latest_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        return self._store.latest_checkpoint(task_id)

    def restore_checkpoint(
        self, task_id: str, *, resume: bool = True, actor_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Restore a task from its latest durable checkpoint.

        A checkpoint carries the resume metadata a task needs (the output
        reference, progress and the run it belongs to). Restoring applies that
        metadata, and — unless the task is already terminal — moves a stuck
        ``IN_PROGRESS``/``VERIFYING`` task back to ``TODO`` so the scheduler
        re-dispatches it. A terminal task is NOT reopened by a restore; the
        checkpoint is simply returned. Raises when there is no checkpoint, so a
        caller never believes it restored when it did not.
        """
        task = self.get_task(task_id)
        checkpoint = self._store.latest_checkpoint(task_id)
        if checkpoint is None:
            raise TaskError(NOT_FOUND, f"no checkpoint exists for task {task_id!r}")
        payload = checkpoint.payload or {}
        applied: dict[str, Any] = {}
        if payload.get("outputReference"):
            applied["outputReference"] = payload["outputReference"]
        if payload.get("progress") is not None:
            applied["progress"] = max(0, min(100, int(payload["progress"])))
        if applied:
            self._store.update_task_fields(task.id, applied)
        resumed = False
        current = self.get_task(task_id)
        if resume and current.status in (
            TaskStatus.IN_PROGRESS, TaskStatus.VERIFYING, TaskStatus.WAITING,
            TaskStatus.ASKING_USER, TaskStatus.BLOCKED,
        ):
            operation = (
                TaskOperation.RECOVER.value
                if current.status in (TaskStatus.IN_PROGRESS, TaskStatus.VERIFYING)
                else None
            )
            self._transition(current, TaskStatus.TODO, operation=operation)
            resumed = True
        updated = self.get_task(task_id)
        self._emit(TaskEventType.TASK_RECOVERED.value, task=updated,
                   data={"checkpointId": checkpoint.id, "resumed": resumed,
                         "from": current.status.value})
        return {
            "checkpoint": checkpoint.model_dump(by_alias=True),
            "task": updated.model_dump(by_alias=True),
            "resumed": resumed,
        }

    def list_executions(self, task_id: str) -> list[TaskExecution]:
        return self._store.list_executions(task_id)

    # ── Views ────────────────────────────────────────────────────────────────
    def task_view(self, task_id: str, *, include_children: bool = True) -> dict[str, Any]:
        task = self.get_task(task_id)
        view: dict[str, Any] = task.model_dump(by_alias=True)
        view["criteria"] = [c.model_dump(by_alias=True) for c in self._store.list_criteria(task.id)]
        view["dependencies"] = [
            d.model_dump(by_alias=True) for d in self._store.list_dependencies(task.id)
        ]
        view["dependents"] = [
            d.model_dump(by_alias=True) for d in self._store.list_dependents(task.id)
        ]
        view["artifacts"] = [a.model_dump(by_alias=True) for a in self._store.list_artifacts(task.id)]
        checkpoints = self._store.list_checkpoints(task.id)
        view["checkpoints"] = [c.model_dump(by_alias=True) for c in checkpoints]
        view["latestCheckpoint"] = (
            self._store.latest_checkpoint(task.id).model_dump(by_alias=True)
            if checkpoints else None
        )
        executions = self._store.list_executions(task.id)
        view["executions"] = [e.model_dump(by_alias=True) for e in executions]
        view["executionCount"] = len(executions)
        view["events"] = [e.model_dump(by_alias=True) for e in self._store.list_task_events(task.id)]
        view["completionFailures"] = self.verify_completion(task)
        view["runnable"] = self.is_runnable(task)
        if include_children:
            view["children"] = [
                self.task_view(c.id, include_children=True)
                for c in self._store.list_children(task.id)
            ]
        return view

    def task_tree(self, root_task_id: str) -> dict[str, Any]:
        return self.task_view(root_task_id, include_children=True)

    def plan_view(self, plan_id: str) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        tasks = self._store.list_tasks(plan_id=plan_id, limit=2000)
        ids = {t.id for t in tasks}
        by_parent: dict[Optional[str], list[Task]] = {}
        for task in tasks:
            by_parent.setdefault(task.parent_task_id, []).append(task)
        roots = [t for t in tasks if t.parent_task_id is None or t.parent_task_id not in ids]
        ordered_roots = sorted(roots, key=lambda t: (t.id != plan.root_task_id, t.created_at))
        return {
            "plan": plan.model_dump(by_alias=True),
            "stats": self.plan_stats(plan_id),
            "tasks": [self._subtree_view(t, by_parent) for t in ordered_roots],
        }

    def _subtree_view(
        self, task: Task, by_parent: dict[Optional[str], list[Task]]
    ) -> dict[str, Any]:
        view = task.model_dump(by_alias=True)
        view["criteria"] = [c.model_dump(by_alias=True) for c in self._store.list_criteria(task.id)]
        view["dependencies"] = [
            d.model_dump(by_alias=True) for d in self._store.list_dependencies(task.id)
        ]
        view["children"] = [self._subtree_view(c, by_parent) for c in by_parent.get(task.id, [])]
        return view

    def plan_stats(self, plan_id: str) -> dict[str, Any]:
        tasks = self._store.list_tasks(plan_id=plan_id, limit=2000)
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        plan = self._store.get_plan(plan_id)
        root = self._store.get_task(plan.root_task_id) if plan and plan.root_task_id else None
        return {
            "total": len(tasks),
            "byStatus": counts,
            "runnable": len(self.runnable_tasks(plan_id=plan_id)),
            "progress": root.progress if root is not None else (
                int(sum(t.progress for t in tasks) / len(tasks)) if tasks else 0
            ),
        }

    # ── Internals ────────────────────────────────────────────────────────────
    def _descendants(self, task_id: str) -> list[Task]:
        out: list[Task] = []
        frontier = self._store.list_children(task_id)
        while frontier:
            out.extend(frontier)
            nxt: list[Task] = []
            for child in frontier:
                nxt.extend(self._store.list_children(child.id))
            frontier = nxt
        return out

    def _depth(self, task_id: str) -> int:
        depth = 0
        current = self._store.get_task(task_id)
        seen: set[str] = set()
        while current is not None and current.parent_task_id:
            if current.parent_task_id in seen:
                break
            seen.add(current.parent_task_id)
            depth += 1
            current = self._store.get_task(current.parent_task_id)
        return depth

    def _check_no_cycle(
        self, task_id: str, dependencies: list[str], plan_id: Optional[str]
    ) -> None:
        """Reject a dependency that would create a cycle.

        Edges are ``(dependent, prerequisite)``. `task_id` depends on each entry in
        `dependencies`; combined with the existing plan graph, a cycle must not form.
        """
        edges: set[tuple[str, str]] = set()
        if plan_id:
            for dep in self._store.list_plan_edges(plan_id):
                edges.add((dep.task_id, dep.depends_on_task_id))
        for prereq in dependencies:
            edges.add((task_id, prereq))
        cycle = dag.detect_cycle(edges)
        if cycle is not None:
            raise TaskError(DEPENDENCY_CYCLE,
                            "that would create a dependency loop: " + " -> ".join(cycle))


def _priority_rank(priority: TaskPriority) -> int:
    from .model import PRIORITY_RANK

    return PRIORITY_RANK.get(priority.value, 1)


__all__ = [
    "COMPLETION_REJECTED",
    "CROSS_PLAN_DEPENDENCY",
    "DEPENDENCY_CYCLE",
    "DEPENDENCY_NOT_FOUND",
    "INVALID_PARENT",
    "INVALID_PLAN",
    "INVALID_STATUS",
    "INVALID_TRANSITION",
    "PLAN_NOT_FOUND",
    "TASK_NOT_FOUND",
    "TOO_MANY_CHILDREN",
    "TaskError",
    "TaskManager",
]
