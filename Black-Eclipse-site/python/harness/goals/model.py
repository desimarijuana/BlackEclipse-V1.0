"""C4 contracts: Goal, Plan, Step, Evidence, Claim, Verdict.

These are plain dataclasses on purpose. The task runtime keeps owning durable
plan execution; this package adds the GOAL-scoped view and the evidence that
proves a step/answer. IDs are opaque strings so a task plan and a goal plan can
share the same identity when C4.3 binds them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


GOAL_STATUSES = frozenset({
    "active", "paused", "completed", "failed", "blocked", "cancelled",
})
STEP_STATUSES = frozenset({
    "pending", "running", "verified", "failed", "skipped", "blocked", "cancelled",
})
CLAIM_STATUSES = frozenset({"supported", "unsupported", "unverified", "superseded"})
GOAL_VERDICTS = frozenset({"done", "continue", "blocked", "wait"})
LOOP_KINDS = frozenset({"loop", "heartbeat"})
LOOP_MODES = frozenset({"fixed", "self_paced"})
LOOP_STATUSES = frozenset({"active", "paused", "cancelled", "completed"})
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
    # ── W4 autonomy ──────────────────────────────────────────────────────────
    contract: Optional[dict[str, Any]] = None
    gates: list[dict[str, Any]] = field(default_factory=list)
    max_turns: int = 20
    used_turns: int = 0
    last_verdict: Optional[dict[str, Any]] = None
    session_id: Optional[str] = None
    next_run_at: Optional[str] = None
    no_progress: int = 0
    current_run_id: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    model_base_url: Optional[str] = None
    workspace_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "objective": self.objective,
            "acceptance": list(self.acceptance), "planId": self.plan_id,
            "taskId": self.task_id, "status": self.status,
            "budget": dict(self.budget), "contract": self.contract,
            "gates": list(self.gates), "maxTurns": self.max_turns,
            "usedTurns": self.used_turns, "lastVerdict": self.last_verdict,
            "sessionId": self.session_id, "nextRunAt": self.next_run_at,
            "noProgress": self.no_progress,
            "currentRunId": self.current_run_id,
            "modelProvider": self.model_provider, "modelName": self.model_name,
            "workspaceId": self.workspace_id,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
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


@dataclass
class GoalVerdict:
    """One evaluated goal turn (W4). Persisted for audit and resumed runs."""

    goal_id: str
    verdict: str
    reason: str = ""
    id: str = ""
    run_id: Optional[str] = None
    turn: int = 1
    evidence: list[str] = field(default_factory=list)
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "goalId": self.goal_id, "runId": self.run_id,
            "turn": self.turn, "verdict": self.verdict, "reason": self.reason,
            "evidence": list(self.evidence),
            "gateResults": list(self.gate_results),
            "usage": dict(self.usage), "createdAt": self.created_at,
        }


@dataclass
class Loop:
    """A session-scoped loop or heartbeat (W4)."""

    id: str
    session_id: str
    kind: str
    prompt: str
    mode: str = "fixed"
    interval_seconds: int = 300
    next_tick_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    max_ticks: int = 50
    used_ticks: int = 0
    no_change_count: int = 0
    last_digest: Optional[str] = None
    last_run_id: Optional[str] = None
    status: str = "active"
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    model_base_url: Optional[str] = None
    workspace_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "sessionId": self.session_id, "kind": self.kind,
            "prompt": self.prompt, "mode": self.mode,
            "intervalSeconds": self.interval_seconds,
            "nextTickAt": self.next_tick_at, "lastTickAt": self.last_tick_at,
            "maxTicks": self.max_ticks,
            "usedTicks": self.used_ticks, "noChangeCount": self.no_change_count,
            "lastDigest": self.last_digest, "lastRunId": self.last_run_id,
            "status": self.status,
            "modelProvider": self.model_provider, "modelName": self.model_name,
            "workspaceId": self.workspace_id,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
        }


__all__ = [
    "CLAIM_STATUSES",
    "GOAL_STATUSES",
    "GOAL_VERDICTS",
    "HANDLE_KINDS",
    "LOOP_KINDS",
    "LOOP_MODES",
    "LOOP_STATUSES",
    "STEP_STATUSES",
    "Claim",
    "EvidenceHandle",
    "Goal",
    "GoalVerdict",
    "Loop",
    "Plan",
    "PlanStep",
    "Verdict",
]
