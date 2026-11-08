"""Typed decision contracts (System One style).

A decision request is a `state` plus a set of named, TYPED questions. A decision
answer is a typed value plus (where the question type supports it) calibrated
probabilities and a confidence score. This is deliberately NOT a chat contract:
there are no messages, no tool calls and no free-form text anywhere in the
response.

The vocabulary is CLOSED. Adding a question type is adding a model to the
`Question`/`Answer` unions and a case to every provider adapter — the same
"closed vocabulary + adapter" pattern as `ml.models` and `quant.verdict`.

Provider-neutral by construction: nothing here names TypeSafe, Jev, or any SDK.
A TypeSafe adapter, an LLM-structured adapter and the deterministic rule adapter
all translate to and from these shapes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..model_runtime.types import Usage

# ── Question types (the closed vocabulary) ───────────────────────────────────

QUESTION_TYPES: tuple[str, ...] = ("choice", "score", "noul")

# A question id is stable: calibration is tracked per template, so an id that
# changes shape must be a new id, never silent drift.
QUESTION_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class _Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(min_length=1, max_length=4_000)
    # An Eclipse-local extension. Provider adapters DROP it before the wire (the
    # TypeSafe/LLM APIs have no such field); the deterministic rule provider is
    # the only consumer. Keeping it here means the request shape never forks.
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleSpec(BaseModel):
    """A closed, deterministic predicate used by the rule provider.

    This is NOT a model judgment: it is a declared comparison against one fact
    in the request state. It exists so workflows have an honest zero-model path.
    """

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1, max_length=200)
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "exists"]
    value: Any = None


class ChoiceQuestion(_Question):
    """Pick one option from a defined set."""

    type: Literal["choice"] = "choice"
    criteria: dict[str, str] = Field(min_length=2, max_length=255)
    rule: Optional[RuleSpec] = None

    @field_validator("criteria")
    @classmethod
    def _criteria_are_described(cls, value: dict[str, str]) -> dict[str, str]:
        for key, description in value.items():
            if not key or len(key) > 128:
                raise ValueError("each choice option needs a non-empty key (<=128 chars)")
            if not description or len(description) > 1_000:
                raise ValueError(f"choice option {key!r} needs a description")
        return value


class ScoreQuestion(_Question):
    """Rate the state against ordered, descriptive levels."""

    type: Literal["score"] = "score"
    criteria: list[str] = Field(min_length=2, max_length=20)
    rule: Optional[RuleSpec] = None

    @field_validator("criteria")
    @classmethod
    def _levels_are_described(cls, value: list[str]) -> list[str]:
        if any(not level or len(level) > 1_000 for level in value):
            raise ValueError("each score level needs a description")
        return value


class NoulQuestion(_Question):
    """A yes/no question answered with a probability in [0, 1]."""

    type: Literal["noul"] = "noul"
    rule: Optional[RuleSpec] = None


Question = Annotated[
    Union[ChoiceQuestion, ScoreQuestion, NoulQuestion],
    Field(discriminator="type"),
]


# ── Answers ─────────────────────────────────────────────────────────────────


def _check_probabilities(value: dict[str, float]) -> dict[str, float]:
    for key, probability in value.items():
        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError(f"probability for {key!r} is outside [0, 1]")
    return value


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("probabilities")
    @classmethod
    def _valid_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        return _check_probabilities(value)


class ScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["score"] = "score"
    score: float
    legend: dict[str, str] = Field(default_factory=dict)
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("probabilities")
    @classmethod
    def _valid_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        return _check_probabilities(value)


class NoulAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["noul"] = "noul"
    noul: float = Field(ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


Answer = Annotated[
    Union[ChoiceAnswer, ScoreAnswer, NoulAnswer],
    Field(discriminator="type"),
]


# ── Requests / responses ────────────────────────────────────────────────────


class DecisionRequest(BaseModel):
    """One System One-shaped request: state in, typed answers out."""

    model_config = ConfigDict(extra="forbid")

    state: Union[str, dict[str, Any]]
    questions: dict[str, Question] = Field(min_length=1, max_length=64)
    model: Optional[str] = None
    timeout_ms: int = Field(default=15_000, ge=100, le=120_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("questions")
    @classmethod
    def _question_ids_are_stable(
        cls, value: dict[str, Question]
    ) -> dict[str, Question]:
        import re

        for question_id in value:
            if not re.match(QUESTION_ID_PATTERN, question_id):
                raise ValueError(
                    f"question id {question_id!r} must match {QUESTION_ID_PATTERN}"
                )
        return value

    @model_validator(mode="after")
    def _state_is_not_empty(self) -> "DecisionRequest":
        if isinstance(self.state, str) and not self.state.strip():
            raise ValueError("state must not be empty")
        if isinstance(self.state, dict) and not self.state:
            raise ValueError("state must not be empty")
        return self


class DecisionResponse(BaseModel):
    """A provider's raw, validated answer set. Never text."""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, Answer]
    provider: str
    model: str = ""
    usage: Usage = Field(default_factory=Usage)
    question_hash: str = ""
    latency_ms: int = 0


class DecisionResult(BaseModel):
    """The service envelope: the answers PLUS the policy outcome and audit id.

    `status` is the only thing a caller should branch on:
      * `answered`    — every answer cleared the policy thresholds;
      * `review`      — an answer is inside the abstain band; use it as a hint,
                        not as a decision;
      * `unavailable` — no provider/answer; NOTHING is inferred.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "review", "unavailable"]
    answers: dict[str, Answer] = Field(default_factory=dict)
    provider: str = ""
    model: str = ""
    usage: Usage = Field(default_factory=Usage)
    question_hash: str = ""
    record_id: Optional[str] = None
    policy: dict[str, dict[str, Any]] = Field(default_factory=dict)
    reason: Optional[str] = None
    latency_ms: int = 0


# ── Canonical hashing ───────────────────────────────────────────────────────


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def questions_hash(questions: dict[str, Question]) -> str:
    """A stable fingerprint of the question TEMPLATE (id + wording + criteria)."""
    payload = {
        key: question.model_dump(mode="json", exclude_none=True)
        for key, question in sorted(questions.items())
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:32]


def state_hash(state: Union[str, dict[str, Any]]) -> str:
    """A stable fingerprint of the evaluated state (content, not identity)."""
    return hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest()[:32]


__all__ = [
    "Answer",
    "ChoiceAnswer",
    "ChoiceQuestion",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionResult",
    "NoulAnswer",
    "NoulQuestion",
    "QUESTION_TYPES",
    "Question",
    "RuleSpec",
    "ScoreAnswer",
    "ScoreQuestion",
    "questions_hash",
    "state_hash",
]
