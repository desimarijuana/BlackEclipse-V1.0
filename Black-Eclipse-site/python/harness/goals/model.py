"""C4 contracts: Goal, Plan, Step, Evidence, Claim, Verdict.

These are plain dataclasses on purpose. The task runtime keeps owning durable
plan execution; this package adds the GOAL-scoped view and the evidence that
proves a step/answer. IDs are opaque strings so a task plan and a goal plan can
share the same identity when C4.3 binds them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


GOAL_STATUSES = frozenset({"active", "completed", "failed", "blocked", "cancelled"})
STEP_STATUSES = frozenset({
    "pending", "running", "verified", "failed", "skipped", "blocked", "cancelled",
})
CLAIM_STATUSES = frozenset({"supported", "unsupported", "unverified", "superseded"})
HANDLE_KINDS = frozenset({
    "file", "run", "tool_output", "artifact", "citation", "record", "computation",
})


@dataclass
class Goal:
    id: str
    objective: str
    acceptance: tuple[str, ...] = ()
    plan_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str = "active"
    budget: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "objective": self.objective,
            "acceptance": list(self.acceptance), "planId": self.plan_id,
            "taskId": self.task_id, "status": self.status,
            "budget": dict(self.budget), "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class PlanStep:
    id: str
    plan_id: str
    index: int
    title: str
    objective: str
    acceptance: tuple[str, ...] = ()
    status: str = "pending"
    run_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "planId": self.plan_id, "index": self.index,
            "title": self.title, "objective": self.objective,
            "acceptance": list(self.acceptance), "status": self.status,
            "runId": self.run_id, "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class Plan:
    id: str
    goal_id: str
    iteration: int = 1
    status: str = "active"
    steps: list[PlanStep] = field(default_factory=list)
    created_at: str = ""

    @property
    def current_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status in ("running", "pending"):
                return step
        return None

    @property
    def complete(self) -> bool:
        return bool(self.steps) and all(
            step.status in ("verified", "skipped") for step in self.steps
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "goalId": self.goal_id, "iteration": self.iteration,
            "status": self.status, "steps": [s.to_dict() for s in self.steps],
            "createdAt": self.created_at,
        }


@dataclass
class EvidenceHandle:
    kind: str
    ref: str
    source: str = ""
    digest: Optional[str] = None
    at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "ref": self.ref, "source": self.source,
            "digest": self.digest, "at": self.at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceHandle":
        return cls(
            kind=str(data.get("kind") or ""),
            ref=str(data.get("ref") or ""),
            source=str(data.get("source") or ""),
            digest=data.get("digest"),
            at=str(data.get("at") or ""),
        )

    @property
    def valid(self) -> bool:
        return self.kind in HANDLE_KINDS and bool(self.ref.strip())


@dataclass
class Claim:
    id: str
    run_id: str
    text: str
    status: str = "unverified"
    verifier: str = ""
    step_id: Optional[str] = None
    handles: list[EvidenceHandle] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "runId": self.run_id, "stepId": self.step_id,
            "text": self.text, "status": self.status, "verifier": self.verifier,
            "handles": [h.to_dict() for h in self.handles],
            "createdAt": self.created_at,
        }


@dataclass
class Verdict:
    verifier: str
    ok: bool
    reason: str = ""
    missing: tuple[str, ...] = ()
    repaired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier": self.verifier, "ok": self.ok, "reason": self.reason,
            "missing": list(self.missing), "repaired": self.repaired,
        }


__all__ = [
    "CLAIM_STATUSES",
    "GOAL_STATUSES",
    "HANDLE_KINDS",
    "STEP_STATUSES",
    "Claim",
    "EvidenceHandle",
    "Goal",
    "Plan",
    "PlanStep",
    "Verdict",
]
