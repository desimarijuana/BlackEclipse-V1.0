"""The recovery strategy vocabulary, budgets and pure selection policy.

This module answers ONE question deterministically: *given a normalized failure,
which recovery strategies are permitted, and in what order?* It never executes
anything, never calls a model, and never reads the clock — so the policy is
inspectable and unit-testable in isolation (spec §9.2: "Select the best permitted
strategy using explicit, inspectable policy").

Safety rules encoded here:

  * A deterministic failure is never retried unchanged. `RETRY` is dropped for
    every non-retryable kind.
  * A provider substitution is never offered to fix an authentication or
    authorization denial — swapping providers cannot grant a credential, and
    doing so would be the "disable safety to pass" anti-pattern (spec §9.1).
  * When a signature has recurred, plain retry is demoted: the engine must change
    strategy rather than repeat.
  * Every candidate names whether it needs operator approval, so the controller
    can route a gated action through the existing approval system rather than
    performing it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional

from .taxonomy import FailureKind, NormalizedFailure, Retryability


class RecoveryStrategy(str, enum.Enum):
    """The bounded set of recovery strategies (spec §9.1)."""

    RETRY = "retry"
    RATE_LIMIT_BACKOFF = "rate_limit_backoff"
    REPAIR_INPUT = "repair_input"
    FIX_DEPENDENCY = "fix_dependency"
    SUBSTITUTE_TOOL = "substitute_tool"
    SUBSTITUTE_PROVIDER = "substitute_provider"
    ALTERNATIVE_IMPLEMENTATION = "alternative_implementation"
    REPLAN = "replan"
    RE_EXECUTE_NODE = "re_execute_node"
    RESTORE_CHECKPOINT = "restore_checkpoint"
    DELEGATE_INVESTIGATION = "delegate_investigation"
    ROLLBACK = "rollback"
    COMPENSATE = "compensate"
    SUSPEND = "suspend"
    STOP_AND_REPORT = "stop_and_report"


@dataclass(frozen=True)
class RecoveryBudget:
    """The hard bounds on recovery in one task (spec §9.4). Never crossed."""

    max_attempts: int = 4
    max_per_signature: int = 2
    max_delegations: int = 2
    max_total_ms: int = 600_000

    def attempt_exceeded(self, attempts: int) -> Optional[str]:
        if attempts >= max(0, int(self.max_attempts)):
            return "attempts"
        return None

    def signature_exceeded(self, signature_attempts: int) -> Optional[str]:
        if signature_attempts >= max(0, int(self.max_per_signature)):
            return "signature"
        return None

    def delegation_exceeded(self, delegations: int) -> Optional[str]:
        if delegations >= max(0, int(self.max_delegations)):
            return "delegations"
        return None


@dataclass(frozen=True)
class CandidateStrategy:
    """A permitted recovery strategy with its rationale and gating."""

    strategy: RecoveryStrategy
    reason: str
    priority: int = 50
    requires_approval: bool = False
    reversible: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "reason": self.reason,
            "priority": self.priority,
            "requiresApproval": self.requires_approval,
            "reversible": self.reversible,
        }


# Kinds for which substituting the tool or provider is a legitimate fix.
_SUBSTITUTABLE = frozenset(
    {
        FailureKind.PROVIDER_OUTAGE,
        FailureKind.NETWORK,
        FailureKind.RATE_LIMIT,
        FailureKind.CAPABILITY,
        FailureKind.DATA_QUALITY,
        FailureKind.BROWSER,
    }
)

# Kinds where a credential or permission is genuinely missing. No substitution,
# no silent retry — only an authorized path (request consent) may proceed.
_AUTH_KINDS = frozenset(
    {FailureKind.AUTHENTICATION, FailureKind.AUTHORIZATION, FailureKind.POLICY_DENIED}
)


def _base_candidates(failure: NormalizedFailure) -> list[CandidateStrategy]:
    kind = failure.kind
    out: list[CandidateStrategy] = []

    if kind == FailureKind.RATE_LIMIT:
        out.append(CandidateStrategy(
            RecoveryStrategy.RATE_LIMIT_BACKOFF,
            "rate limited; wait for the server-directed delay then retry",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_PROVIDER,
            "a compatible provider may not be rate limited",
            priority=30,
        ))
    elif kind == FailureKind.TIMEOUT or kind == FailureKind.NETWORK:
        out.append(CandidateStrategy(
            RecoveryStrategy.RETRY,
            "transient transport failure; retry with backoff",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_PROVIDER
            if failure.source == "provider"
            else RecoveryStrategy.SUBSTITUTE_TOOL,
            "a fallback endpoint or tool may reach the same result",
            priority=30,
        ))
    elif kind == FailureKind.PROVIDER_OUTAGE:
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_PROVIDER,
            "move to a healthy, capability-compatible provider",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.RETRY,
            "provider outage may be transient",
            priority=20,
        ))
    elif kind == FailureKind.RESOURCE_EXHAUSTION:
        out.append(CandidateStrategy(
            RecoveryStrategy.REPAIR_INPUT,
            "shrink the request (tighter context / smaller input) before re-running",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.REPLAN,
            "decompose the step so it fits the resource budget",
            priority=20,
        ))
    elif kind == FailureKind.SYNTAX or kind == FailureKind.ASSERTION:
        out.append(CandidateStrategy(
            RecoveryStrategy.REPAIR_INPUT,
            "correct the invalid input/source the error points at",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.RE_EXECUTE_NODE,
            "re-run the corrected step",
            priority=20,
        ))
    elif kind == FailureKind.DEPENDENCY:
        out.append(CandidateStrategy(
            RecoveryStrategy.FIX_DEPENDENCY,
            "install or align the missing/incompatible dependency",
            priority=10,
            requires_approval=True,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION,
            "implement the objective without the unavailable dependency",
            priority=30,
        ))
    elif kind == FailureKind.CAPABILITY:
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_TOOL,
            "an equivalent, already-registered capability may fit",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.ALTERNATIVE_IMPLEMENTATION,
            "complete the objective through a different legitimate route",
            priority=30,
        ))
    elif kind in _AUTH_KINDS:
        out.append(CandidateStrategy(
            RecoveryStrategy.SUSPEND,
            "a credential or permission is required; request authorized consent",
            priority=10,
            requires_approval=True,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.STOP_AND_REPORT,
            "report the authorization gap honestly rather than bypass it",
            priority=20,
        ))
    elif kind == FailureKind.BROWSER:
        out.append(CandidateStrategy(
            RecoveryStrategy.RE_EXECUTE_NODE,
            "re-observe the page and retry with a fresh locator",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_TOOL,
            "read the source/API when the browser interaction cannot be resolved",
            priority=20,
        ))
    elif kind in (FailureKind.PLUGIN, FailureKind.WORKFLOW):
        out.append(CandidateStrategy(
            RecoveryStrategy.RE_EXECUTE_NODE,
            "re-run the failed node after reconciling its state",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.RESTORE_CHECKPOINT,
            "resume from the last durable checkpoint",
            priority=20,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.STOP_AND_REPORT,
            "report the unrecoverable node state",
            priority=40,
        ))
    elif kind == FailureKind.DATA_QUALITY:
        out.append(CandidateStrategy(
            RecoveryStrategy.SUBSTITUTE_TOOL,
            "use an alternative source with adequate freshness/provenance",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.DELEGATE_INVESTIGATION,
            "investigate the data conflict before re-answering",
            priority=20,
        ))
    elif kind == FailureKind.INVALID_REQUEST:
        out.append(CandidateStrategy(
            RecoveryStrategy.REPAIR_INPUT,
            "fix the request to match the API contract",
            priority=10,
        ))
    elif kind == FailureKind.PLANNING:
        out.append(CandidateStrategy(
            RecoveryStrategy.REPLAN,
            "revise the plan; the current decomposition is invalid",
            priority=10,
        ))
    elif kind == FailureKind.NO_PROGRESS:
        out.append(CandidateStrategy(
            RecoveryStrategy.REPLAN,
            "the current strategy is making no progress; change approach",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.DELEGATE_INVESTIGATION,
            "delegate a focused investigation of the stall",
            priority=20,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.STOP_AND_REPORT,
            "stop repeating an ineffective action",
            priority=30,
        ))
    elif kind == FailureKind.RUNTIME:
        out.append(CandidateStrategy(
            RecoveryStrategy.RETRY,
            "a runtime error may be transient; retry with backoff",
            priority=10,
        ))
        out.append(CandidateStrategy(
            RecoveryStrategy.REPLAN,
            "if retry does not help, revise the approach",
            priority=30,
        ))

    # Universal safety net: there is always a truthful terminal option.
    out.append(CandidateStrategy(
        RecoveryStrategy.STOP_AND_REPORT,
        "report the outcome honestly when no permitted recovery applies",
        priority=100,
    ))
    return out


def reject_reason(failure: NormalizedFailure, strategy: RecoveryStrategy) -> Optional[str]:
    """Why `strategy` is forbidden for this failure, or None if permitted."""
    if strategy == RecoveryStrategy.RETRY:
        if failure.retryability == Retryability.NON_RETRYABLE:
            return "non-retryable failure; retrying unchanged repeats the failure"
        if failure.kind in _AUTH_KINDS:
            return "authorization failures must not be retried unchanged"
    if strategy == RecoveryStrategy.RATE_LIMIT_BACKOFF and failure.kind != FailureKind.RATE_LIMIT:
        # A backoff is only honest when the server said to wait.
        return "no rate-limit signal"
    if strategy == RecoveryStrategy.SUBSTITUTE_PROVIDER:
        if failure.kind in _AUTH_KINDS:
            return "provider substitution cannot grant a missing credential"
        if failure.kind not in _SUBSTITUTABLE:
            return "provider substitution is not a fix for this failure"
    if strategy == RecoveryStrategy.SUBSTITUTE_TOOL and failure.kind in _AUTH_KINDS:
        return "tool substitution cannot grant a missing credential"
    if strategy == RecoveryStrategy.SUSPEND and failure.kind not in _AUTH_KINDS:
        # Suspension is reserved for a genuine consent gate, not ordinary faults.
        return "suspension is reserved for authorization gaps"
    return None


def select_strategies(
    failure: NormalizedFailure,
    *,
    recurrent: bool = False,
    allow_provider_substitution: bool = True,
) -> list[CandidateStrategy]:
    """The permitted strategies, ordered by priority (pure, deterministic).

    `recurrent` (the same signature has repeated) demotes `RETRY` to the end so a
    changing strategy is preferred over a repeat. `allow_provider_substitution`
    lets a caller with no provider fallback configured drop that candidate.
    """
    candidates = _base_candidates(failure)
    kept: list[CandidateStrategy] = []
    seen: set[RecoveryStrategy] = set()
    for candidate in candidates:
        if candidate.strategy in seen:
            continue
        if reject_reason(failure, candidate.strategy) is not None:
            continue
        if (
            candidate.strategy == RecoveryStrategy.SUBSTITUTE_PROVIDER
            and not allow_provider_substitution
        ):
            continue
        seen.add(candidate.strategy)
        kept.append(candidate)

    if recurrent:
        # Sort retry last (but keep it if it is the only option).
        order = {RecoveryStrategy.RETRY: 1}
        kept.sort(key=lambda c: (order.get(c.strategy, 0), c.priority))
    else:
        kept.sort(key=lambda c: c.priority)
    return kept


__all__ = [
    "CandidateStrategy",
    "RecoveryBudget",
    "RecoveryStrategy",
    "reject_reason",
    "select_strategies",
]
