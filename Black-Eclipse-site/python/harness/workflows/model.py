"""Workflow + workflow-step contracts (Harness closeout Phase 5).

A `Workflow` is a bounded, versioned plan of `WorkflowStep`s. A step is one of a
closed set of kinds; each carries inputs/outputs, a retry policy, a timeout, and
— critically — a DECLARED tool scope. The scope is enforced at the existing
`ToolRegistry.execute(allowed=...)` seam: a step can never call a tool outside
the intersection of the agent's allowlist and the step's declared tools.

Pydantic validates every field (the runtime never trusts a stored definition).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The closed set of step kinds. Each maps to a compile strategy in compile.py.
STEP_KINDS = ("agent", "skill", "conditional", "parallel", "approval", "retrieval")
StepKind = Literal["agent", "skill", "conditional", "parallel", "approval", "retrieval"]

# Bounds keep a workflow a PLAN, not an unbounded program.
MAX_STEPS = 32
MAX_PARALLEL_FANOUT = 8
MAX_STEP_TIMEOUT_MS = 600_000
MIN_STEP_TIMEOUT_MS = 1_000
MAX_RETRIES = 5

# An id is a simple token; the compiler uses it as an identifier and key.
_ID_RE = r"^[A-Za-z0-9_.:-]{1,64}$"


class WorkflowValidationError(ValueError):
    """A workflow definition was rejected. `reason` names the exact defect."""

    def __init__(self, reason: str, *, step_id: Optional[str] = None) -> None:
        self.reason = reason
        self.step_id = step_id
        prefix = f"step {step_id!r}: " if step_id else ""
        super().__init__(f"{prefix}{reason}")


class RetryPolicy(BaseModel):
    """A bounded retry policy for one step. Never unbounded."""

    model_config = ConfigDict(populate_by_name=True)

    max_attempts: int = Field(default=1, ge=1, le=MAX_RETRIES)  # noqa: N815
    backoff_ms: int = Field(default=0, ge=0, le=60_000)  # noqa: N815


class WorkflowStep(BaseModel):
    """One bounded step in a workflow plan."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=_ID_RE)
    kind: StepKind
    # The instruction/objective for this step (rendered into the run's input).
    instruction: str = Field(default="", max_length=8_000)
    # The tools this step DECLARES it may use. A step's EFFECTIVE scope is the
    # intersection of this and the resolved agent's allowlist. None = inherit the
    # agent's full allowlist (still bounded by it).
    tools: Optional[list[str]] = None
    # Step dependencies (ids). Used for ordering and cycle detection.
    depends_on: list[str] = Field(default_factory=list)  # noqa: N815
    # `parallel`/`conditional` children.
    branches: list[str] = Field(default_factory=list)
    # `conditional` predicate: a simple, declared comparison over prior-step
    # output. Never arbitrary code.
    condition: Optional[dict[str, Any]] = None
    # For an `approval` step: the MCP server/tool/effect being gated.
    approval: Optional[dict[str, Any]] = None
    # For a `skill` step: the skill id + input.
    skill_id: Optional[str] = None  # noqa: N815
    skill_input: Optional[dict[str, Any]] = None  # noqa: N815
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_ms: int = Field(default=120_000, ge=MIN_STEP_TIMEOUT_MS, le=MAX_STEP_TIMEOUT_MS)  # noqa: N815
    # A step with `terminal=True` is a valid end of the plan.
    terminal: bool = False

    @field_validator("instruction")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class Workflow(BaseModel):
    """A versioned, bounded plan compiled onto the existing execution graph."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(pattern=_ID_RE)
    version: str = Field(default="1.0.0", max_length=32)
    name: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2_000)
    # The agent whose allowlist bounds every step. A step's tools are intersected
    # with this agent's allowlist — a step can only NARROW, never widen.
    agent_id: str = Field(default="eclipse-agent")  # noqa: N815
    steps: list[WorkflowStep] = Field(default_factory=list, max_length=MAX_STEPS)

    def step(self, step_id: str) -> Optional[WorkflowStep]:
        return next((s for s in self.steps if s.id == step_id), None)


__all__ = [
    "Workflow",
    "WorkflowStep",
    "RetryPolicy",
    "StepKind",
    "STEP_KINDS",
    "WorkflowValidationError",
    "MAX_STEPS",
    "MAX_PARALLEL_FANOUT",
]
