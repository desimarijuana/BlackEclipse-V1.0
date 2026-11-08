"""Typed decisions (System One-shaped): state in, calibrated typed answers out.

Not a chat abstraction. See `docs/decision-models.md`.
"""

from __future__ import annotations

from .contracts import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    DecisionResult,
    NoulAnswer,
    NoulQuestion,
    Question,
    RuleSpec,
    ScoreAnswer,
    ScoreQuestion,
    questions_hash,
    state_hash,
)
from .policy import DecisionPolicy
from .providers import DecisionProvider, DecisionUnavailable, DecisionUnsupported, RuleProvider
from .registry import DecisionRegistry
from .service import DecisionService

__all__ = [
    "Answer",
    "ChoiceAnswer",
    "ChoiceQuestion",
    "DecisionPolicy",
    "DecisionProvider",
    "DecisionRegistry",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionResult",
    "DecisionService",
    "DecisionUnavailable",
    "DecisionUnsupported",
    "NoulAnswer",
    "NoulQuestion",
    "Question",
    "RuleProvider",
    "RuleSpec",
    "ScoreAnswer",
    "ScoreQuestion",
    "questions_hash",
    "state_hash",
]
