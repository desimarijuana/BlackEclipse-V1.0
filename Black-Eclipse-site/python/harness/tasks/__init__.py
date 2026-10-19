"""The Task / Plan runtime — Eclipse's durable execution backbone.

A Plan contains an arbitrary hierarchy of Tasks. Tasks carry dependencies,
acceptance criteria, priorities, agent assignments, retries and leases. The
scheduler discovers runnable tasks, claims them atomically under a lease, and
dispatches each one through the EXISTING runtime (`service.run`) — so a task run
is a normal run with its own trace, events and verification.

Package layout:
  * `model.py`     — the closed vocabularies + validated contracts.
  * `state.py`     — the task and plan state machines (closed transition tables).
  * `store.py`     — the durable tables on the ONE agent-memory connection.
  * `dag.py`       — cycle detection, runnable predicate, parent/progress roll-up.
  * `manager.py`   — the ONE writer of task/plan state (CRUD, deps, verification).
  * `context.py`   — the execution context envelope built from durable state.
  * `scheduler.py` — claim / lease / heartbeat / retry / recovery / dispatch.
  * `tools.py`     — the curated LLM-facing tool surface.
  * `bootstrap.py` — boot wiring onto `AgenticService`.
"""

from .bootstrap import build_task_executor, install_task_layer
from .context import TaskContext, build_task_context, render_task_query
from .goal import GoalIntake, budget_violations, intake_goal
from .manager import TaskError, TaskManager
from .model import (
    AcceptanceCriterionInput,
    BlockedReason,
    CreatePlanInput,
    CreateTaskInput,
    CriterionState,
    DependencyInput,
    DependencyKind,
    ExecutionStatus,
    FailurePolicy,
    GoalContract,
    Plan,
    PlanStatus,
    Task,
    TaskAcceptanceCriterion,
    TaskArtifact,
    TaskBudget,
    TaskCheckpoint,
    TaskDependency,
    TaskEvent,
    TaskEventType,
    TaskExecution,
    TaskPriority,
    TaskStatus,
    TaskType,
    WaitingReason,
)
from .scheduler import TaskRunOutcome, TaskScheduler
from .state import (
    InvalidPlanTransition,
    InvalidTaskTransition,
    TaskOperation,
    can_transition_plan,
    can_transition_task,
)
from .store import TaskStore
from .tools import TASK_TOOLS, register_task_tools
from .verification import TaskVerification, register_verifier, verify_task

__all__ = [
    "AcceptanceCriterionInput",
    "BlockedReason",
    "CreatePlanInput",
    "CreateTaskInput",
    "CriterionState",
    "DependencyInput",
    "DependencyKind",
    "ExecutionStatus",
    "FailurePolicy",
    "GoalContract",
    "GoalIntake",
    "InvalidPlanTransition",
    "InvalidTaskTransition",
    "Plan",
    "PlanStatus",
    "TASK_TOOLS",
    "Task",
    "TaskAcceptanceCriterion",
    "TaskArtifact",
    "TaskBudget",
    "TaskCheckpoint",
    "TaskContext",
    "TaskDependency",
    "TaskError",
    "TaskEvent",
    "TaskEventType",
    "TaskExecution",
    "TaskManager",
    "TaskOperation",
    "TaskPriority",
    "TaskRunOutcome",
    "TaskScheduler",
    "TaskStatus",
    "TaskStore",
    "TaskType",
    "TaskVerification",
    "WaitingReason",
    "budget_violations",
    "build_task_context",
    "build_task_executor",
    "can_transition_plan",
    "can_transition_task",
    "install_task_layer",
    "intake_goal",
    "register_task_tools",
    "register_verifier",
    "render_task_query",
    "verify_task",
]
