"""Task / Plan contracts — the durable vocabulary of the execution backbone.

This module defines ONLY shape and vocabulary: the closed sets of states,
reasons, priorities, dependency kinds and event types, plus the pydantic
contracts used to validate EXTERNAL input (tool arguments, API bodies). The
runtime never trusts an LLM-generated task definition, so every field a caller
may supply passes through one of these models before it is persisted.

The persisted form is a set of SQLite rows (see `store.py`); a `Task`/`Plan`
model is the validated view of one row. State is NEVER stored on the model and
written back blindly: every status change goes through `state.py`.

Field names are snake_case in Python and camelCase on the wire (the TS front
door), exactly like `jobs.model` and `schemas.ModelSettings`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ── Closed vocabularies ───────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    """The exact primary task states. No module invents another string."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFYING = "VERIFYING"
    ASKING_USER = "ASKING_USER"
    BLOCKED = "BLOCKED"
    WAITING = "WAITING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


#: States from which no ordinary transition moves without an explicit operation
#: (`reopen_task` / `retry_task`).
TASK_TERMINAL: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)


class PlanStatus(str, Enum):
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


#: Higher rank = scheduled first. The scheduler sorts runnable tasks by this then
#: by creation order (deterministic tie-break).
PRIORITY_RANK: dict[str, int] = {
    TaskPriority.LOW.value: 0,
    TaskPriority.NORMAL.value: 1,
    TaskPriority.HIGH.value: 2,
    TaskPriority.URGENT.value: 3,
    TaskPriority.CRITICAL.value: 4,
}


class DependencyKind(str, Enum):
    """How one task relates to a prerequisite it points at.

    ``BLOCKS`` and ``REQUIRES`` are REQUIRED edges: the dependent cannot run
    until the prerequisite is COMPLETED. ``OPTIONAL`` edges are recorded for
    ordering/visibility but never gate the dependent.
    """

    BLOCKS = "BLOCKS"
    REQUIRES = "REQUIRES"
    OPTIONAL = "OPTIONAL"


REQUIRED_DEPENDENCY_KINDS: frozenset[DependencyKind] = frozenset(
    {DependencyKind.BLOCKS, DependencyKind.REQUIRES}
)


class WaitingReason(str, Enum):
    """Why a task is WAITING for an external event."""

    USER_INPUT = "USER_INPUT"
    APPROVAL = "APPROVAL"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"
    TOOL = "TOOL"
    SCHEDULE = "SCHEDULE"
    AGENT = "AGENT"


class BlockedReason(str, Enum):
    """Why a task cannot continue because a prerequisite is unavailable."""

    DEPENDENCY = "DEPENDENCY"
    RESOURCE = "RESOURCE"
    PERMISSION = "PERMISSION"
    PARENT = "PARENT"
    #: The task-type verifier (round 4, W8.4/W8.5) cannot pass with the evidence
    #: the work produced — the run(s) finished but the goal contract's proof is
    #: missing. Non-terminal and inspectable: the missing evidence is named.
    VERIFICATION = "VERIFICATION"


class TaskType(str, Enum):
    """The task-type key a completion verifier is registered under (W8.4/W14).

    An explicit, closed vocabulary — never inferred from prose at verification
    time. `general` is the honest fallback for work that fits no other class.
    `data` (W14) is the quantitative class: its verifier demands a reproducible
    calculation (a recorded formula/analysis with its inputs), never a number
    in prose.
    """

    CODE = "code"
    RESEARCH = "research"
    DOCUMENT = "document"
    WORKFLOW = "workflow"
    FINANCE = "finance"
    DATA = "data"
    GENERAL = "general"


class CriterionState(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    REFUSED = "REFUSED"


class FailurePolicy(str, Enum):
    """How a parent reacts when a REQUIRED child fails."""

    FAIL_FAST = "FAIL_FAST"
    CONTINUE = "CONTINUE"


class TaskEventType(str, Enum):
    """The immutable task event vocabulary (§17)."""

    TASK_CREATED = "TASK_CREATED"
    TASK_UPDATED = "TASK_UPDATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_VERIFYING = "TASK_VERIFYING"
    TASK_ASKING_USER = "TASK_ASKING_USER"
    TASK_WAITING = "TASK_WAITING"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_UNBLOCKED = "TASK_UNBLOCKED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_DELEGATED = "TASK_DELEGATED"
    TASK_RETRIED = "TASK_RETRIED"
    TASK_FAILED = "TASK_FAILED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_CANCEL_REQUESTED = "TASK_CANCEL_REQUESTED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_DECOMPOSED = "TASK_DECOMPOSED"
    TASK_DEPENDENCY_ADDED = "TASK_DEPENDENCY_ADDED"
    TASK_DEPENDENCY_REMOVED = "TASK_DEPENDENCY_REMOVED"
    TASK_DEPENDENCY_COMPLETED = "TASK_DEPENDENCY_COMPLETED"
    TASK_CHECKPOINT_CREATED = "TASK_CHECKPOINT_CREATED"
    TASK_CRITERION_UPDATED = "TASK_CRITERION_UPDATED"
    TASK_PROGRESS_UPDATED = "TASK_PROGRESS_UPDATED"
    TASK_RECOVERED = "TASK_RECOVERED"
    TASK_ESCALATED = "TASK_ESCALATED"
    TASK_ARTIFACT_ADDED = "TASK_ARTIFACT_ADDED"
    TASK_COMPLETION_REJECTED = "TASK_COMPLETION_REJECTED"
    TASK_COMPLETION_OVERRIDDEN = "TASK_COMPLETION_OVERRIDDEN"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_STATUS_CHANGED = "PLAN_STATUS_CHANGED"
    PLAN_REVISED = "PLAN_REVISED"


# Error class names used by the retry policy. A model/provider boundary failure
# is retryable; a validation or permission error is not.
RETRYABLE_ERRORS: frozenset[str] = frozenset(
    {
        "TOOL_TIMEOUT",
        "TIMEOUT",
        "RATE_LIMITED",
        "PROVIDER_ERROR",
        "NETWORK_ERROR",
        "INFRASTRUCTURE_ERROR",
        "RUNTIME_UNAVAILABLE",
        # A dead worker's lease expiring is the canonical retryable condition: the
        # work did not fail, its owner did.
        "LEASE_EXPIRED",
    }
)
NON_RETRYABLE_ERRORS: frozenset[str] = frozenset(
    {
        "TOOL_VALIDATION_FAILED",
        "VALIDATION_ERROR",
        "SECURITY_ERROR",
        "PERMISSION_DENIED",
        "TOOL_FORBIDDEN",
        "INVALID_INPUT",
        "NOT_FOUND",
        "DEPENDENCY_UNSATISFIED",
    }
)


# ── Bounds (keep a plan a PLAN, not an unbounded program) ─────────────────────

MAX_TITLE = 300
MAX_DESCRIPTION = 8_000
MAX_OBJECTIVE = 4_000
MAX_CRITERIA_PER_TASK = 50
MAX_DEPENDENCIES_PER_TASK = 100
MAX_CHILDREN_PER_TASK = 100
MAX_MAX_RETRIES = 10
DEFAULT_MAX_RETRIES = 2
DEFAULT_LEASE_SECONDS = 600
DEFAULT_BACKOFF_MS = 1_000
MAX_BACKOFF_MS = 300_000
MAX_DELIVERABLES = 12
MAX_GOAL_CONSTRAINTS = 12
MAX_GOAL_ACCEPTANCE = 20
MAX_GOAL_LINE = 500


# ── Contracts ─────────────────────────────────────────────────────────────────


class TaskBudget(BaseModel):
    """Contract-level caps for one task (round 4, W8.6).

    Enforced AFTER the run against the run's own recorded metrics; exceeding a
    cap is a BLOCKED outcome with the violated cap named — never a silent
    truncation and never a retry that burns more of the same budget. Only the
    measurable caps are declared here; an unenforceable cap (e.g. model cost,
    which the runtime does not price) is not invented.
    """

    model_config = _CAMEL

    max_duration_ms: Optional[int] = Field(None, ge=0)
    max_tool_calls: Optional[int] = Field(None, ge=0)
    max_tokens: Optional[int] = Field(None, ge=0)
    max_model_steps: Optional[int] = Field(None, ge=0)
    #: A cap on how many tasks for this goal may run at once. Enforced through
    #: the scheduler's EXISTING per-agent concurrency cap (the goal task carries
    #: `metadata.maxConcurrency`), not by a second limiter.
    max_parallel_workers: Optional[int] = Field(None, ge=1)


class GoalContract(BaseModel):
    """A goal as DATA on the durable task (round 4, W8.1).

    The deterministic intake (`goal.py::intake_goal`) turns a request into this
    contract, which travels with the task — not with a prompt. `deliverables`
    and `acceptance` are what the task-type verifier checks before the task may
    complete; `constraints` and `budgets` bound the work.
    """

    model_config = _CAMEL

    objective: str = Field("", max_length=MAX_OBJECTIVE)
    deliverables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    budgets: Optional[TaskBudget] = None
    # ── W4 autonomy (all additive/defaulted: an old contract still validates) ──
    #: Named deterministic gates that must pass before a goal may complete.
    verification: list[str] = Field(default_factory=list)
    #: Out-of-scope paths/actions the work must not touch.
    boundaries: list[str] = Field(default_factory=list)
    #: Conditions the advisory judge must honour (never overrides a gate).
    stop_when: list[str] = Field(default_factory=list)

    @field_validator("objective")
    @classmethod
    def _strip_objective(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "deliverables", "constraints", "acceptance",
        "verification", "boundaries", "stop_when", mode="before",
    )
    @classmethod
    def _strip_lines(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return value

    @model_validator(mode="after")
    def _bounded(self) -> "GoalContract":
        if len(self.deliverables) > MAX_DELIVERABLES:
            raise ValueError(f"too many deliverables (max {MAX_DELIVERABLES})")
        if len(self.constraints) > MAX_GOAL_CONSTRAINTS:
            raise ValueError(f"too many constraints (max {MAX_GOAL_CONSTRAINTS})")
        if len(self.acceptance) > MAX_GOAL_ACCEPTANCE:
            raise ValueError(f"too many acceptance tests (max {MAX_GOAL_ACCEPTANCE})")
        for name in ("verification", "boundaries", "stop_when"):
            if len(getattr(self, name)) > 24:
                raise ValueError(f"too many {name} lines (max 24)")
        return self


class GoalGate(BaseModel):
    """One deterministic gate on a goal (W4).

    A gate names a CLOSED `code/commands.py` command class rather than a shell
    string, so `build_argv` pins an absolute executable and validates every
    argument. `workspace_id` is required to execute; a goal may carry gates only
    when a workspace is bound.
    """

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=120)
    check: str = Field(..., min_length=1, max_length=40)
    args: dict[str, Any] = Field(default_factory=dict)
    workspace_id: Optional[str] = Field(None, max_length=200)
    timeout_seconds: int = Field(600, ge=10, le=3600)
    retries: int = Field(0, ge=0, le=5)

    @field_validator("check")
    @classmethod
    def _known_check(cls, value: str) -> str:
        allowed = (
            "unit_test", "python_test", "typecheck", "lint", "build", "format_check",
        )
        text = str(value or "").strip().lower()
        if text not in allowed:
            raise ValueError(f"unknown gate check {value!r}; expected one of {allowed}")
        return text


class TaskAcceptanceCriterion(BaseModel):
    """One verifiable condition a task must satisfy before it may complete."""

    model_config = _CAMEL

    id: str
    task_id: str
    text: str = Field(..., min_length=1, max_length=1_000)
    state: CriterionState = CriterionState.PENDING
    evidence: Optional[str] = Field(None, max_length=2_000)
    required: bool = True
    ordinal: int = 0
    created_at: str
    updated_at: str


class TaskDependency(BaseModel):
    """A directed edge: ``task_id`` cannot run until ``depends_on_task_id`` does."""

    model_config = _CAMEL

    id: str
    task_id: str            # the dependent
    depends_on_task_id: str  # the prerequisite
    kind: DependencyKind = DependencyKind.REQUIRES
    created_at: str


class TaskArtifact(BaseModel):
    """A reference from a task to a real artifact. NEVER the bytes itself."""

    model_config = _CAMEL

    id: str
    task_id: str
    execution_id: Optional[str] = None
    kind: str = Field(default="file", max_length=40)
    uri: str = Field(..., max_length=2_000)   # a path, digest, asset id or URL
    digest: Optional[str] = Field(None, max_length=128)
    size_bytes: Optional[int] = None
    label: Optional[str] = Field(None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TaskExecution(BaseModel):
    """One attempt to execute a task. A task may have many, chronologically."""

    model_config = _CAMEL

    id: str
    task_id: str
    attempt: int
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    error: Optional[str] = Field(None, max_length=2_000)
    error_class: Optional[str] = Field(None, max_length=60)
    metrics: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: Optional[str] = None


class TaskCheckpoint(BaseModel):
    """A durable resume boundary for a long-running task."""

    model_config = _CAMEL

    id: str
    task_id: str
    execution_id: Optional[str] = None
    seq: int
    label: str = Field(default="checkpoint", max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TaskEvent(BaseModel):
    """An immutable record of one thing that happened to a task or plan."""

    model_config = _CAMEL

    id: str
    plan_id: Optional[str] = None
    task_id: Optional[str] = None
    type: str
    seq: int
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Plan(BaseModel):
    """A durable, named intent containing an arbitrary task hierarchy."""

    model_config = _CAMEL

    id: str
    name: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    objective: str = Field("", max_length=MAX_OBJECTIVE)
    root_task_id: Optional[str] = None
    status: PlanStatus = PlanStatus.PLANNING
    priority: TaskPriority = TaskPriority.NORMAL
    agent_id: str = "eclipse-agent"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class Task(BaseModel):
    """The durable view of one task. Validated from a store row."""

    model_config = _CAMEL

    id: str
    plan_id: Optional[str] = None
    parent_task_id: Optional[str] = None

    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    objective: str = Field("", max_length=MAX_OBJECTIVE)

    # Round 4 (W8): the task-type key that selects the completion verifier, and
    # the goal contract it verifies against. Both optional — a task created
    # without them keeps the pre-W8 completion contract exactly as it was.
    task_type: Optional[TaskType] = None
    goal_contract: Optional[GoalContract] = None

    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.NORMAL
    progress: int = Field(0, ge=0, le=100)

    assigned_agent_id: Optional[str] = None
    assigned_run_id: Optional[str] = None
    delegated_by: Optional[str] = None
    delegation_id: Optional[str] = None

    retry_count: int = Field(0, ge=0)
    max_retries: int = Field(DEFAULT_MAX_RETRIES, ge=0, le=MAX_MAX_RETRIES)
    backoff_ms: int = Field(DEFAULT_BACKOFF_MS, ge=0, le=MAX_BACKOFF_MS)
    available_at: Optional[str] = None   # backoff gate for a retry

    claimed_by: Optional[str] = None
    claim_token: Optional[str] = None
    claimed_at: Optional[str] = None
    lease_expires_at: Optional[str] = None

    required: bool = True                     # does the parent require this child?
    failure_policy: FailurePolicy = FailurePolicy.FAIL_FAST
    weight: float = Field(1.0, gt=0)

    waiting_reason: Optional[WaitingReason] = None
    blocked_reason: Optional[BlockedReason] = None
    blocked_by: list[str] = Field(default_factory=list)

    output_reference: Optional[str] = Field(None, max_length=2_000)
    error: Optional[str] = Field(None, max_length=2_000)
    error_class: Optional[str] = Field(None, max_length=60)

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    deadline: Optional[str] = None


# ── Input contracts (tool arguments) ──────────────────────────────────────────


class AcceptanceCriterionInput(BaseModel):
    model_config = _CAMEL

    text: str = Field(..., min_length=1, max_length=1_000)
    required: bool = True


class DependencyInput(BaseModel):
    model_config = _CAMEL

    task_id: str
    depends_on_task_id: str
    kind: DependencyKind = DependencyKind.REQUIRES


class CreateTaskInput(BaseModel):
    """Validated input for `create_task`. Every reference is checked by the manager."""

    model_config = _CAMEL

    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    objective: str = Field("", max_length=MAX_OBJECTIVE)
    plan_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    assigned_agent_id: Optional[str] = None
    acceptance_criteria: list[AcceptanceCriterionInput] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)   # task ids this needs first
    required: bool = True
    failure_policy: FailurePolicy = FailurePolicy.FAIL_FAST
    weight: float = Field(1.0, gt=0)
    max_retries: int = Field(DEFAULT_MAX_RETRIES, ge=0, le=MAX_MAX_RETRIES)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Round 4 (W8): a goal contract creates acceptance criteria from its
    # `acceptance` lines (deduped against `acceptance_criteria`) and selects the
    # completion verifier through `task_type`.
    task_type: Optional[TaskType] = None
    goal_contract: Optional[GoalContract] = None

    @field_validator("title", "description", "objective")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _need_a_home(self) -> "CreateTaskInput":
        if not self.plan_id and not self.parent_task_id:
            raise ValueError("a task requires a planId or a parentTaskId")
        if len(self.acceptance_criteria) > MAX_CRITERIA_PER_TASK:
            raise ValueError(f"too many acceptance criteria (max {MAX_CRITERIA_PER_TASK})")
        if len(self.dependencies) > MAX_DEPENDENCIES_PER_TASK:
            raise ValueError(f"too many dependencies (max {MAX_DEPENDENCIES_PER_TASK})")
        return self


class CreatePlanInput(BaseModel):
    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    objective: str = Field("", max_length=MAX_OBJECTIVE)
    priority: TaskPriority = TaskPriority.NORMAL
    agent_id: str = "eclipse-agent"
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AcceptanceCriterionInput",
    "BlockedReason",
    "CreatePlanInput",
    "CreateTaskInput",
    "CriterionState",
    "DEFAULT_BACKOFF_MS",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DependencyInput",
    "DependencyKind",
    "ExecutionStatus",
    "FailurePolicy",
    "GoalContract",
    "GoalGate",
    "MAX_BACKOFF_MS",
    "MAX_CHILDREN_PER_TASK",
    "MAX_CRITERIA_PER_TASK",
    "MAX_DELIVERABLES",
    "MAX_DEPENDENCIES_PER_TASK",
    "MAX_DESCRIPTION",
    "MAX_GOAL_ACCEPTANCE",
    "MAX_GOAL_CONSTRAINTS",
    "MAX_GOAL_LINE",
    "MAX_MAX_RETRIES",
    "MAX_OBJECTIVE",
    "MAX_TITLE",
    "NON_RETRYABLE_ERRORS",
    "PRIORITY_RANK",
    "Plan",
    "PlanStatus",
    "REQUIRED_DEPENDENCY_KINDS",
    "RETRYABLE_ERRORS",
    "Task",
    "TaskAcceptanceCriterion",
    "TaskArtifact",
    "TaskBudget",
    "TaskCheckpoint",
    "TaskDependency",
    "TaskEvent",
    "TaskEventType",
    "TaskExecution",
    "TaskPriority",
    "TaskStatus",
    "TaskType",
    "TASK_TERMINAL",
    "WaitingReason",
]
