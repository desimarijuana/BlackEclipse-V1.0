"""Retry classification and backoff.

Transient failures are retried; deterministic ones are not. The classifier is a
pure function of the error code so it is testable without a runner. A policy may
add codes to retry or to never-retry, but the safety default is to NOT retry an
authorization, validation, or argument error — retrying those only repeats a side
effect or burns budget.
"""

from __future__ import annotations

import random
from typing import Optional

from .models import NodeError, RetryPolicy

# Codes that are safe to retry by default: transient infrastructure conditions.
DEFAULT_RETRYABLE: frozenset[str] = frozenset(
    {
        "TASK_TIMEOUT",
        "TOOL_TIMEOUT",
        "PROVIDER_TIMEOUT",
        "PROVIDER_ERROR",
        "PROVIDER_UNAVAILABLE",
        "NETWORK_ERROR",
        "RATE_LIMITED",
        "DATABASE_BUSY",
        "DATABASE_UNAVAILABLE",
        "TEMPORARY_FAILURE",
        "WORKER_LOST",
        "LEASE_EXPIRED",
    }
)

# Codes that must NEVER be retried unless a policy explicitly says otherwise:
# retrying them repeats a deterministic failure or a refused effect.
DEFAULT_NON_RETRYABLE: frozenset[str] = frozenset(
    {
        "INVALID_INPUT",
        "INVALID_ARGUMENTS",
        "TOOL_VALIDATION_FAILED",
        "TOOL_NOT_FOUND",
        "TOOL_FORBIDDEN",
        "PERMISSION_DENIED",
        "AUTH_ERROR",
        "PROVIDER_NOT_CONFIGURED",
        "SECURITY_BLOCKED",
        "CANCELLED",
        "DETERMINISTIC_ERROR",
    }
)


def is_retryable(code: str, policy: Optional[RetryPolicy] = None) -> bool:
    """Whether an error code is retryable under `policy` (defaults when None)."""
    normalized = (code or "NODE_ERROR").upper()
    if policy is not None:
        if normalized in {c.upper() for c in policy.non_retryable_errors}:
            return False
        if normalized in {c.upper() for c in policy.retryable_errors}:
            return True
    if normalized in DEFAULT_NON_RETRYABLE:
        return False
    if normalized in DEFAULT_RETRYABLE:
        return True
    return False


def should_retry(policy: RetryPolicy, error: Optional[NodeError], attempts_done: int) -> bool:
    """Whether another attempt is allowed. `attempts_done` counts finished tries."""
    if attempts_done >= max(1, policy.max_attempts):
        return False
    if error is None:
        return False
    if error.retryable:
        return True
    return is_retryable(error.code, policy)


def backoff_ms(policy: RetryPolicy, attempt: int, *, rng: Optional[random.Random] = None) -> int:
    """Exponential backoff for the `attempt`-th retry (1-based), with jitter."""
    base = max(0, policy.backoff_ms)
    if base == 0:
        return 0
    factor = max(1.0, policy.multiplier) ** max(0, attempt - 1)
    value = min(policy.max_backoff_ms, int(base * factor))
    if policy.jitter > 0:
        rand = (rng or random).random()
        value = int(value * (1 - policy.jitter) + rand * value * policy.jitter)
    return max(0, value)


__all__ = [
    "DEFAULT_NON_RETRYABLE",
    "DEFAULT_RETRYABLE",
    "backoff_ms",
    "is_retryable",
    "should_retry",
]
