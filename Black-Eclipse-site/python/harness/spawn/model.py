"""C5 contracts: one spawn request, one child outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


MAX_DEPTH = 2
MAX_CHILDREN = 8
MAX_TOKENS = 120_000
MAX_STEPS = 24
MAX_TIMEOUT_S = 900
MAX_CHILD_OBJECTIVE = 4_000


@dataclass
class SpawnBudget:
    tokens: int = MAX_TOKENS
    steps: int = MAX_STEPS
    timeout_s: int = MAX_TIMEOUT_S

    def clamped(self) -> "SpawnBudget":
        return SpawnBudget(
            tokens=max(1, min(int(self.tokens), MAX_TOKENS)),
            steps=max(1, min(int(self.steps), MAX_STEPS)),
            timeout_s=max(30, min(int(self.timeout_s), MAX_TIMEOUT_S)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"tokens": self.tokens, "steps": self.steps, "timeoutS": self.timeout_s}


@dataclass
class SpawnSpec:
    objective: str
    agent: str = "eclipse-agent"
    budget: SpawnBudget = field(default_factory=SpawnBudget)
    board: str = "shared"  # shared | isolated
    background: bool = False
    model: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective[:MAX_CHILD_OBJECTIVE],
            "agent": self.agent,
            "budget": self.budget.to_dict(),
            "board": self.board,
            "background": self.background,
            "model": self.model,
        }


@dataclass
class ChildOutcome:
    status: str
    run_id: str = ""
    job_id: str = ""
    output: str = ""
    claims: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    steps_used: int = 0
    error: str = ""
    error_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "runId": self.run_id, "jobId": self.job_id,
            "output": self.output[:12_000], "claims": self.claims[:32],
            "artifacts": self.artifacts[:16], "verdicts": self.verdicts[:16],
            "tokensUsed": self.tokens_used, "stepsUsed": self.steps_used,
            "error": self.error[:2_000], "errorClass": self.error_class,
        }


__all__ = [
    "MAX_CHILDREN",
    "MAX_DEPTH",
    "MAX_STEPS",
    "MAX_TIMEOUT_S",
    "MAX_TOKENS",
    "ChildOutcome",
    "SpawnBudget",
    "SpawnSpec",
]
