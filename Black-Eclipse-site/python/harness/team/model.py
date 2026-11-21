"""Bot Team Orchestration — the durable vocabulary and validated contracts.

This module defines ONLY shape and vocabulary for a *team run*: a set of
specialist bots (referenced by their runtime agent id) collaborating on one
objective through a dependency-aware task graph. It introduces no execution
plane — every field here is validated before the Task runtime, the A2A
delegation layer and the Evidence store are touched.

Field names are snake_case in Python and camelCase on the wire, exactly like
`tasks.model` and `a2a.model`.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ── Ids ────────────────────────────────────────────────────────────────────────


def new_team_run_id() -> str:
    return "teamrun_" + uuid.uuid4().hex[:16]


def new_conflict_id() -> str:
    return "cfl_" + uuid.uuid4().hex[:12]


def new_review_finding_id() -> str:
    return "rvf_" + uuid.uuid4().hex[:12]


# ── Closed vocabularies ─────────────────────────────────────────────────────────


class TeamSubtaskStatus(str, Enum):
    """The task-graph states of one subtask (maps onto the Task runtime states)."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


SUBTASK_TERMINAL: frozenset[TeamSubtaskStatus] = frozenset(
    {
        TeamSubtaskStatus.COMPLETED,
        TeamSubtaskStatus.FAILED,
        TeamSubtaskStatus.CANCELLED,
        TeamSubtaskStatus.SKIPPED,
    }
)


class TeamRunStatus(str, Enum):
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    REVIEWING = "REVIEWING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TEAM_TERMINAL: frozenset[TeamRunStatus] = frozenset(
    {
        TeamRunStatus.COMPLETED,
        TeamRunStatus.PARTIAL,
        TeamRunStatus.FAILED,
        TeamRunStatus.CANCELLED,
    }
)


class ReviewOutcome(str, Enum):
    APPROVED = "APPROVED"
    APPROVED_WITH_LIMITATIONS = "APPROVED_WITH_LIMITATIONS"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REJECTED = "REJECTED"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class Severity(str, Enum):
    BLOCKING = "BLOCKING"
    ADVISORY = "ADVISORY"


class ConflictKind(str, Enum):
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    BASIS_MISMATCH = "BASIS_MISMATCH"
    ASSUMPTION_MISMATCH = "ASSUMPTION_MISMATCH"
    STALE_DATA = "STALE_DATA"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    UNRESOLVED_UNCERTAINTY = "UNRESOLVED_UNCERTAINTY"


class ConflictStatus(str, Enum):
    RESOLVED = "RESOLVED"
    EXPLAINED = "EXPLAINED"
    UNRESOLVED = "UNRESOLVED"


class Strictness(str, Enum):
    NONE = "NONE"
    LENIENT = "LENIENT"
    STANDARD = "STANDARD"
    STRICT = "STRICT"


class OptionalFailurePolicy(str, Enum):
    """What an OPTIONAL subtask failure means for the team run."""

    ALLOW_PARTIAL = "ALLOW_PARTIAL"
    REQUIRE_ALL = "REQUIRE_ALL"


# ── Bounds ──────────────────────────────────────────────────────────────────────

MAX_MEMBERS = 12
MAX_SUBTASKS = 64
MAX_DEPENDENCIES = 16
MAX_OBJECTIVE = 4_000
MAX_SUBTASK_OBJECTIVE = 2_000
MAX_INSTRUCTION = 20_000
MAX_REPAIR_ATTEMPTS = 3
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_PER_AGENT_CONCURRENCY = 1


# ── Contracts ──────────────────────────────────────────────────────────────────


class TeamMember(BaseModel):
    """One authorised collaborating bot in a team, by its runtime agent id."""

    model_config = _CAMEL

    agent_id: str = Field(..., min_length=1, max_length=80)
    role: str = Field("specialist", max_length=40)
    capabilities: list[str] = Field(default_factory=list)
    max_concurrency: int = Field(DEFAULT_PER_AGENT_CONCURRENCY, ge=1, le=16)
    tools: Optional[list[str]] = None          # None = inherit the agent's surface
    instructions: str = Field("", max_length=MAX_INSTRUCTION)
    label: Optional[str] = Field(None, max_length=120)

    @field_validator("agent_id")
    @classmethod
    def _id_charset(cls, value: str) -> str:
        cleaned = value.strip()
        if not all(ch.isalnum() or ch in "-_." for ch in cleaned):
            raise ValueError("agentId may contain letters, digits, '-', '_' and '.'")
        return cleaned


class TeamSubtask(BaseModel):
    """One node of the team task graph."""

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=64)
    objective: str = Field(..., min_length=1, max_length=MAX_SUBTASK_OBJECTIVE)
    capability: str = Field("", max_length=80)
    assigned_agent_id: Optional[str] = Field(None, max_length=80)
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    expected_output: dict[str, Any] = Field(default_factory=dict)
    input_refs: list[str] = Field(default_factory=list)
    deadline_ms: Optional[int] = Field(None, ge=1_000, le=3_600_000)
    budget: dict[str, Any] = Field(default_factory=dict)
    review: bool = False
    priority: str = Field("NORMAL", max_length=16)
    #: When true, a COMPLETED subtask with no evidence reference is not
    #: acceptable: the team service's evidence check refuses it. Default false so
    #: existing teams are unchanged.
    evidence_required: bool = False

    @field_validator("id")
    @classmethod
    def _id_charset(cls, value: str) -> str:
        cleaned = value.strip()
        if not all(ch.isalnum() or ch in "-_." for ch in cleaned):
            raise ValueError("subtask id may contain letters, digits, '-', '_' and '.'")
        return cleaned

    @model_validator(mode="after")
    def _bounds(self) -> "TeamSubtask":
        if len(self.depends_on) > MAX_DEPENDENCIES:
            raise ValueError(f"too many dependencies (max {MAX_DEPENDENCIES})")
        if self.id in self.depends_on:
            raise ValueError("a subtask may not depend on itself")
        return self


class TeamPolicy(BaseModel):
    """Everything a team run may do, and every bound it must respect."""

    model_config = _CAMEL

    delegation_enabled: bool = True
    # Opt-in: let a team MEMBER use the `delegate` tool (split or best_of) inside
    # its own subtask. Off by default so a team's surface does not widen silently;
    # enabling it only ADDS the tool name — the delegation's own caps, narrowing
    # and permissions still apply.
    member_fanout: bool = False
    max_depth: int = Field(4, ge=1, le=8)
    max_children: int = Field(16, ge=1, le=MAX_SUBTASKS)
    max_concurrency: int = Field(DEFAULT_MAX_CONCURRENCY, ge=1, le=32)
    per_agent_concurrency: int = Field(DEFAULT_PER_AGENT_CONCURRENCY, ge=1, le=16)
    max_tasks: int = Field(MAX_SUBTASKS, ge=1, le=256)
    max_cost: float = Field(100.0, gt=0, le=100_000)
    max_runtime_ms: int = Field(3_600_000, ge=1_000, le=86_400_000)
    require_review: bool = False
    review_strictness: Strictness = Strictness.STANDARD
    optional_failure_policy: OptionalFailurePolicy = OptionalFailurePolicy.ALLOW_PARTIAL
    allowed_providers: list[str] = Field(default_factory=list)  # empty = any
    require_approval: bool = False


class TeamDefinition(BaseModel):
    """A named team: its members, its task graph and its policy."""

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=300)
    objective: str = Field("", max_length=MAX_OBJECTIVE)
    agent_id: str = Field("eclipse-orchestrator", max_length=80)  # the lead/delegator
    members: list[TeamMember] = Field(default_factory=list)
    subtasks: list[TeamSubtask] = Field(default_factory=list)
    policy: TeamPolicy = Field(default_factory=TeamPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bounds(self) -> "TeamDefinition":
        if len(self.members) > MAX_MEMBERS:
            raise ValueError(f"too many members (max {MAX_MEMBERS})")
        if len(self.subtasks) > MAX_SUBTASKS:
            raise ValueError(f"too many subtasks (max {MAX_SUBTASKS})")
        return self


class TeamRun(BaseModel):
    """The durable record of one team execution."""

    model_config = _CAMEL

    id: str
    team_id: str
    name: str
    root_run_id: str
    plan_id: Optional[str] = None
    status: TeamRunStatus = TeamRunStatus.PLANNING
    subtask_task_ids: dict[str, str] = Field(default_factory=dict)
    repair_task_ids: list[str] = Field(default_factory=list)
    member_agents: list[str] = Field(default_factory=list)
    review_required: bool = False
    attempts: int = 0
    repeat_count: int = 0
    last_review_signature: Optional[str] = None
    cost: Optional[float] = None
    error: Optional[str] = None
    definition: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    finished_at: Optional[str] = None


class TeamFinding(BaseModel):
    """One structured claim produced by a subtask, with its provenance.

    A finding is never bare prose: it carries the evidence it rests on, the
    period/unit/basis it applies to, and its own known limitations.
    """

    model_config = _CAMEL

    id: str
    subtask_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: str = ""
    claim: str = Field(..., min_length=1, max_length=2_000)
    value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=40)
    currency: Optional[str] = Field(None, max_length=8)
    period: Optional[str] = Field(None, max_length=80)
    basis: Optional[str] = Field(None, max_length=80)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TeamConflict(BaseModel):
    """A detected disagreement between findings, with its resolution status."""

    model_config = _CAMEL

    id: str
    subject: str
    kind: ConflictKind
    status: ConflictStatus
    material: bool = True
    finding_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_method: str = ""
    residual_uncertainty: str = ""
    detail: str = ""


class ReviewFinding(BaseModel):
    """One defect an independent reviewer found, with an actionable repair."""

    model_config = _CAMEL

    id: str
    subtask_id: Optional[str] = None
    criterion: str = Field(..., max_length=120)
    severity: Severity = Severity.ADVISORY
    detail: str = Field("", max_length=2_000)
    evidence_refs: list[str] = Field(default_factory=list)
    repair_instruction: str = Field("", max_length=2_000)


class ReviewReport(BaseModel):
    """The structured verdict of an independent quality review."""

    model_config = _CAMEL

    outcome: ReviewOutcome
    findings: list[ReviewFinding] = Field(default_factory=list)
    reviewer_agent_id: str = "qa-agent"
    independent: bool = True
    attempts: int = 0
    notes: list[str] = Field(default_factory=list)


class RepairAttempt(BaseModel):
    """One bounded repair task created from a review finding."""

    model_config = _CAMEL

    subtask_id: str
    attempt: int = Field(..., ge=1)
    instruction: str = Field("", max_length=2_000)
    task_id: Optional[str] = None
    status: str = "PENDING"


__all__ = [
    "ConflictKind",
    "ConflictStatus",
    "DEFAULT_MAX_CONCURRENCY",
    "DEFAULT_PER_AGENT_CONCURRENCY",
    "MAX_DEPENDENCIES",
    "MAX_MEMBERS",
    "MAX_OBJECTIVE",
    "MAX_REPAIR_ATTEMPTS",
    "MAX_SUBTASKS",
    "OptionalFailurePolicy",
    "RepairAttempt",
    "ReviewFinding",
    "ReviewOutcome",
    "ReviewReport",
    "SUBTASK_TERMINAL",
    "Severity",
    "Strictness",
    "TEAM_TERMINAL",
    "TeamConflict",
    "TeamDefinition",
    "TeamFinding",
    "TeamMember",
    "TeamPolicy",
    "TeamRun",
    "TeamRunStatus",
    "TeamSubtask",
    "TeamSubtaskStatus",
    "new_conflict_id",
    "new_review_finding_id",
    "new_team_run_id",
]
