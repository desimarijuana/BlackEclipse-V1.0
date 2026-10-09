"""The adaptive recovery controller — bounded, deterministic, inspectable.

The controller is the decision core of the recovery engine. Given one normalized
failure plus the small amount of recovery state known so far (how many attempts,
how many for THIS signature, delegations used, whether the signature has
recurred), it returns a single `RecoveryDecision`: what to do next, why, and the
delay to honour.

It performs no I/O and calls no model, so a decision is reproducible and can be
recorded verbatim as evidence. It is deliberately NOT a second execution loop:

  * it never runs a tool, a graph node or a model;
  * it never mutates task state — the caller (an existing subsystem) owns that;
  * every limit comes from `RecoveryBudget`, so a decision can never promise an
    unbounded number of retries (spec §9.4).
"""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from .policy import (
    CandidateStrategy,
    RecoveryBudget,
    RecoveryStrategy,
    select_strategies,
)
from .taxonomy import NormalizedFailure


class RecoveryAction(str, enum.Enum):
    RECOVER = "recover"
    SUSPEND = "suspend"
    STOP = "stop"


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    strategy: Optional[RecoveryStrategy]
    reason: str
    backoff_ms: int = 0
    exhausted: bool = False
    requires_approval: bool = False
    candidates: list[CandidateStrategy] = field(default_factory=list)

    @property
    def should_recover(self) -> bool:
        return self.action == RecoveryAction.RECOVER

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "strategy": self.strategy.value if self.strategy else None,
            "reason": self.reason,
            "backoffMs": self.backoff_ms,
            "exhausted": self.exhausted,
            "requiresApproval": self.requires_approval,
            "candidates": [c.to_dict() for c in self.candidates],
        }


_BACKOFF_BASE_MS = 500
_BACKOFF_MAX_MS = 30_000


class RecoveryController:
    """Turns a failure + recovery state into one bounded decision."""

    def __init__(
        self,
        *,
        budget: Optional[RecoveryBudget] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.budget = budget or RecoveryBudget()
        self._rng = rng or random.Random()

    def backoff_ms(self, attempt: int) -> int:
        """Exponential backoff with jitter for the `attempt`-th retry (1-based)."""
        factor = 2 ** max(0, int(attempt) - 1)
        value = min(_BACKOFF_MAX_MS, _BACKOFF_BASE_MS * factor)
        jitter = 0.85 + self._rng.random() * 0.15
        return max(0, int(value * jitter))

    def decide(
        self,
        failure: NormalizedFailure,
        *,
        attempts: int = 0,
        signature_attempts: int = 0,
        delegations: int = 0,
        recurrent: bool = False,
        allow_provider_substitution: bool = True,
    ) -> RecoveryDecision:
        """The one decision for this failure under the configured budget."""
        reason = self.budget.attempt_exceeded(attempts)
        if reason is not None:
            return self._stop(failure, f"recovery budget exhausted ({reason})", exhausted=True)
        reason = self.budget.signature_exceeded(signature_attempts)
        if reason is not None:
            return self._stop(
                failure, f"recovery budget exhausted for this failure ({reason})", exhausted=True
            )

        candidates = select_strategies(
            failure,
            recurrent=recurrent,
            allow_provider_substitution=allow_provider_substitution,
        )
        if not candidates:
            return self._stop(failure, "no permitted recovery strategy", exhausted=False)

        chosen = candidates[0]
        if delegations >= max(0, self.budget.max_delegations):
            # Never choose a delegation we cannot fund; fall through to any other.
            chosen = next(
                (c for c in candidates if c.strategy != RecoveryStrategy.DELEGATE_INVESTIGATION),
                chosen,
            )

        if chosen.strategy == RecoveryStrategy.STOP_AND_REPORT:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                strategy=chosen.strategy,
                reason=chosen.reason,
                candidates=candidates,
            )
        if chosen.strategy == RecoveryStrategy.SUSPEND:
            return RecoveryDecision(
                action=RecoveryAction.SUSPEND,
                strategy=chosen.strategy,
                reason=chosen.reason,
                requires_approval=True,
                candidates=candidates,
            )

        backoff = 0
        if chosen.strategy in (RecoveryStrategy.RETRY, RecoveryStrategy.RATE_LIMIT_BACKOFF):
            backoff = self.backoff_ms(attempts + 1)

        return RecoveryDecision(
            action=RecoveryAction.RECOVER,
            strategy=chosen.strategy,
            reason=chosen.reason,
            backoff_ms=backoff,
            requires_approval=chosen.requires_approval,
            candidates=candidates,
        )

    def _stop(self, failure: NormalizedFailure, reason: str, *, exhausted: bool) -> RecoveryDecision:
        return RecoveryDecision(
            action=RecoveryAction.STOP,
            strategy=RecoveryStrategy.STOP_AND_REPORT,
            reason=reason,
            exhausted=exhausted,
            candidates=[],
        )


__all__ = ["RecoveryAction", "RecoveryController", "RecoveryDecision"]
