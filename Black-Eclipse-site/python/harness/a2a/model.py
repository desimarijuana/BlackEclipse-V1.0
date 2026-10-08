"""The Agent-to-Agent (A2A) domain vocabulary.

Shape and contract only: the closed sets of agent statuses, message types,
delivery states, delegation states and priorities, plus the validated contracts
used to carry them (`AgentDefinition`, `AgentEnvelope`, `Finding`, `A2AResult`,
`Conflict`, `DelegationRecord`, `AgentBudget`).

Field names are snake_case in Python and camelCase on the wire (the TS front
door), exactly like `tasks/model.py`, `jobs/model.py` and `schemas.ModelSettings`.
A2A NEVER trusts an LLM-supplied envelope: every field a caller may supply passes
through one of these models before it is persisted.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def new_agent_id() -> str:
    return _uid("agt")


def new_envelope_id() -> str:
    return _uid("msg")


def new_delegation_id() -> str:
    return _uid("dlg")


def new_finding_id() -> str:
    return _uid("fnd")


def new_conflict_id() -> str:
    return _uid("cfl")


# ── Closed vocabularies ───────────────────────────────────────────────────────


class AgentStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"


class MessageType(str, Enum):
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESPONSE = "TASK_RESPONSE"
    FINDING = "FINDING"
    EVIDENCE = "EVIDENCE"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    DELEGATION = "DELEGATION"
    STATUS = "STATUS"
    FAILURE = "FAILURE"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_RESPONSE = "APPROVAL_RESPONSE"
    REVIEW_REQUEST = "REVIEW_REQUEST"
    REVIEW_RESPONSE = "REVIEW_RESPONSE"
    CANCEL = "CANCEL"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    DEAD_LETTER = "DEAD_LETTER"


class DelegationStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MessagePriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


PRIORITY_RANK: dict[str, int] = {
    MessagePriority.LOW.value: 0,
    MessagePriority.NORMAL.value: 1,
    MessagePriority.HIGH.value: 2,
    MessagePriority.URGENT.value: 3,
}


class SupervisorVerdict(str, Enum):
    PASS = "PASS"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class BudgetKind(str, Enum):
    AGENTS = "agents"
    DEPTH = "depth"
    TASKS = "tasks"
    TOKENS = "tokens"
    COST = "cost"
    RUNTIME = "runtime"
    TOOL_CALLS = "toolCalls"


# ── Bounds ────────────────────────────────────────────────────────────────────

MAX_INSTRUCTION_CHARS = 20_000
MAX_PAYLOAD_CHARS = 100_000
MAX_ENVELOPE_TTL_S = 86_400
DEFAULT_ENVELOPE_TTL_S = 3_600
MAX_OBJECTIVE_CHARS = 4_000
MAX_AGENTS_PER_RUN = 32
MAX_DEPTH = 4
MAX_TASKS_PER_RUN = 128
MAX_TOKENS_PER_RUN = 2_000_000
MAX_COST_PER_RUN = 100.0
MAX_RUNTIME_MS = 3_600_000
MAX_TOOL_CALLS_PER_RUN = 2_000


# ── Budgets ───────────────────────────────────────────────────────────────────


class AgentBudget(BaseModel):
    """A hard resource envelope for one root run. Child budgets only ever narrow."""

    model_config = _CAMEL

    max_agents: int = Field(MAX_AGENTS_PER_RUN, ge=0)
    max_depth: int = Field(MAX_DEPTH, ge=0)
    max_tasks: int = Field(MAX_TASKS_PER_RUN, ge=0)
    max_tokens: int = Field(MAX_TOKENS_PER_RUN, ge=0)
    max_cost: float = Field(MAX_COST_PER_RUN, ge=0)
    max_runtime_ms: int = Field(MAX_RUNTIME_MS, ge=0)
    max_tool_calls: int = Field(MAX_TOOL_CALLS_PER_RUN, ge=0)

    # Consumption counters (mutated only by BudgetTracker).
    agents_spawned: int = Field(0, ge=0)
    tasks_created: int = Field(0, ge=0)
    depth: int = Field(0, ge=0)
    tokens_used: int = Field(0, ge=0)
    cost_used: float = Field(0.0, ge=0)
    runtime_ms: int = Field(0, ge=0)
    tool_calls: int = Field(0, ge=0)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    def sub_budget(self, *, depth_delta: int = 1, task_fraction: float = 0.5,
                   token_fraction: float = 0.5, cost_fraction: float = 0.5,
                   runtime_fraction: float = 0.5, tool_fraction: float = 0.5) -> "AgentBudget":
        """A child budget that can only NARROW — never a superset of the parent."""
        return AgentBudget(
            max_agents=max(0, self.remaining("agents")),
            max_depth=max(0, self.max_depth - max(1, depth_delta)),
            max_tasks=max(1, int(self.remaining("tasks") * task_fraction)),
            max_tokens=max(1, int(self.remaining("tokens") * token_fraction)),
            max_cost=max(0.0, self.remaining("cost") * cost_fraction),
            max_runtime_ms=max(1, int(self.remaining("runtime") * runtime_fraction)),
            max_tool_calls=max(1, int(self.remaining("toolCalls") * tool_fraction)),
            depth=self.depth + max(1, depth_delta),
        )

    def remaining(self, kind: str) -> float:
        table = {
            "agents": (self.max_agents, self.agents_spawned),
            "depth": (self.max_depth, self.depth),
            "tasks": (self.max_tasks, self.tasks_created),
            "tokens": (self.max_tokens, self.tokens_used),
            "cost": (self.max_cost, self.cost_used),
            "runtime": (self.max_runtime_ms, self.runtime_ms),
            "toolCalls": (self.max_tool_calls, self.tool_calls),
        }
        limit, used = table.get(kind, (0, 0))
        return max(0, float(limit) - float(used))

    def exhausted(self, kind: str) -> bool:
        return self.remaining(kind) <= 0


# ── Agent definition / registry ────────────────────────────────────────────────


class AgentCapability(BaseModel):
    """A machine-readable thing an agent can do, with its required tool surface."""

    model_config = _CAMEL

    name: str
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class AgentDefinition(BaseModel):
    """A versioned agent profile. Behaviour is DATA, never hardcoded in code."""

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1_000)
    role: str = Field("specialist", max_length=40)
    version: str = Field("1.0.0", max_length=20)

    system_instructions: str = Field("", max_length=MAX_INSTRUCTION_CHARS)

    capabilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: Optional[list[str]] = None

    model_policy: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)

    max_concurrency: int = Field(1, ge=1, le=32)
    timeout_ms: int = Field(120_000, ge=1_000, le=3_600_000)

    can_delegate: bool = False
    allowed_delegates: list[str] = Field(default_factory=list)

    status: AgentStatus = AgentStatus.ACTIVE
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("agent id may contain letters, digits, -, _, .")
        return cleaned

    def capability_objects(self) -> list[AgentCapability]:
        return [AgentCapability(name=c) for c in self.capabilities]

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "role": self.role, "version": self.version, "capabilities": self.capabilities,
            "skills": self.skills, "tools": self.tools, "modelPolicy": self.model_policy,
            "permissions": self.permissions, "memoryPolicy": self.memory_policy,
            "evidencePolicy": self.evidence_policy, "maxConcurrency": self.max_concurrency,
            "timeoutMs": self.timeout_ms, "canDelegate": self.can_delegate,
            "allowedDelegates": self.allowed_delegates, "status": self.status.value,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
        }


# ── Protocol ───────────────────────────────────────────────────────────────────


class AgentEnvelope(BaseModel):
    """The ONE message envelope. All A2A communication is one of these."""

    model_config = _CAMEL

    id: str = Field(default_factory=new_envelope_id)
    type: MessageType

    run_id: str = ""
    task_id: Optional[str] = None

    sender_agent_id: str
    recipient_agent_id: Optional[str] = None  # None = broadcast

    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None

    timestamp: float = Field(default_factory=time.time)
    priority: MessagePriority = MessagePriority.NORMAL

    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    permissions: dict[str, Any] = Field(default_factory=dict)

    ttl: int = Field(DEFAULT_ENVELOPE_TTL_S, ge=1, le=MAX_ENVELOPE_TTL_S)
    idempotency_key: Optional[str] = None

    def is_expired(self, *, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        return (current - self.timestamp) > self.ttl

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type.value, "runId": self.run_id,
            "taskId": self.task_id, "senderAgentId": self.sender_agent_id,
            "recipientAgentId": self.recipient_agent_id,
            "correlationId": self.correlation_id, "replyTo": self.reply_to,
            "timestamp": self.timestamp, "priority": self.priority.value,
            "payload": self.payload, "evidenceRefs": self.evidence_refs,
            "permissions": self.permissions, "ttl": self.ttl,
            "idempotencyKey": self.idempotency_key,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "AgentEnvelope":
        return cls(
            id=row["id"], type=MessageType(row["type"]), run_id=row.get("runId") or "",
            task_id=row.get("taskId"), sender_agent_id=row.get("senderAgentId") or "",
            recipient_agent_id=row.get("recipientAgentId"),
            correlation_id=row.get("correlationId"), reply_to=row.get("replyTo"),
            timestamp=float(row.get("timestamp") or time.time()),
            priority=MessagePriority(row.get("priority") or "NORMAL"),
            payload=dict(row.get("payload") or {}),
            evidence_refs=list(row.get("evidenceRefs") or []),
            permissions=dict(row.get("permissions") or {}),
            ttl=int(row.get("ttl") or DEFAULT_ENVELOPE_TTL_S),
            idempotency_key=row.get("idempotencyKey"),
        )


# ── Results / findings / conflicts ──────────────────────────────────────────────


class Finding(BaseModel):
    """A structured, evidence-anchored claim. Never free prose."""

    model_config = _CAMEL

    id: str = Field(default_factory=new_finding_id)
    claim: str = Field(..., min_length=1, max_length=2_000)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    implications: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ConflictCandidate(BaseModel):
    model_config = _CAMEL

    agent_id: str
    task_id: Optional[str] = None
    value: Any = None
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    basis: str = ""


class Conflict(BaseModel):
    model_config = _CAMEL

    id: str = Field(default_factory=new_conflict_id)
    subject: str
    candidates: list[ConflictCandidate] = Field(default_factory=list)
    status: str = "UNRESOLVED"     # UNRESOLVED | EXPLAINED | RESOLVED
    material: bool = True
    reason: str = ""


class A2AResult(BaseModel):
    """The structured result every agent returns. Never only prose."""

    model_config = _CAMEL

    task_id: Optional[str] = None
    agent_id: str = ""
    status: str = "COMPLETED"

    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    metrics: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id, "agentId": self.agent_id, "status": self.status,
            "summary": self.summary, "findings": [f.model_dump(by_alias=True) for f in self.findings],
            "evidenceRefs": self.evidence_refs, "outputs": self.outputs,
            "conflicts": [c.model_dump(by_alias=True) for c in self.conflicts],
            "gaps": self.gaps, "confidence": self.confidence, "metrics": self.metrics,
            "nextActions": self.next_actions,
        }


class MergedResult(BaseModel):
    """The normalized, deduplicated, evidence-linked synthesis of many results."""

    model_config = _CAMEL

    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    coverage: float = 0.0
    sources: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    dropped_duplicates: int = 0


class DelegationRecord(BaseModel):
    model_config = _CAMEL

    id: str = Field(default_factory=new_delegation_id)
    parent_agent_id: str
    child_agent_id: str
    parent_run_id: str
    parent_task_id: Optional[str] = None
    child_task_id: Optional[str] = None
    child_run_id: Optional[str] = None
    objective: str = Field("", max_length=MAX_OBJECTIVE_CHARS)
    status: DelegationStatus = DelegationStatus.CREATED
    budget: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class SupervisorCheck(BaseModel):
    model_config = _CAMEL

    name: str
    passed: bool
    detail: str = ""


class SupervisorReport(BaseModel):
    model_config = _CAMEL

    verdict: SupervisorVerdict
    checks: list[SupervisorCheck] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    rework_task_ids: list[str] = Field(default_factory=list)


__all__ = [
    "AgentBudget",
    "AgentCapability",
    "AgentDefinition",
    "AgentEnvelope",
    "AgentStatus",
    "ApprovalStatus",
    "A2AResult",
    "BudgetKind",
    "Conflict",
    "ConflictCandidate",
    "DelegationRecord",
    "DelegationStatus",
    "DeliveryStatus",
    "DEFAULT_ENVELOPE_TTL_S",
    "Finding",
    "MAX_AGENTS_PER_RUN",
    "MAX_COST_PER_RUN",
    "MAX_DEPTH",
    "MAX_ENVELOPE_TTL_S",
    "MAX_INSTRUCTION_CHARS",
    "MAX_OBJECTIVE_CHARS",
    "MAX_PAYLOAD_CHARS",
    "MAX_RUNTIME_MS",
    "MAX_TASKS_PER_RUN",
    "MAX_TOKENS_PER_RUN",
    "MAX_TOOL_CALLS_PER_RUN",
    "MergedResult",
    "MessagePriority",
    "MessageType",
    "PRIORITY_RANK",
    "SupervisorCheck",
    "SupervisorReport",
    "SupervisorVerdict",
    "new_agent_id",
    "new_conflict_id",
    "new_delegation_id",
    "new_envelope_id",
    "new_finding_id",
]
