"""Bounded retry with backoff for transient source failures (Phase 6).

A transient failure (timeout, 5xx, 429, socket error) should not end a leg's
search when an independent retry could succeed. A *permanent* failure (blocked
host, unsupported content type, invalid request) must NOT be retried — retrying a
403 or an anti-bot block just wastes the budget and hides the real cause.

Retries are bounded and use a small deterministic exponential backoff with no
jitter, so the behavior is reproducible in tests. The number of retries is
recorded on the outcome so the receipt can show it.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from .sources import SourceOutcome, outcome_diagnostics

# Categories for which a retry could plausibly help.
_RETRYABLE_CATEGORIES = {"timeout", "transport_error"}
_RETRYABLE_DEFAULT = False

DEFAULT_MAX_RETRIES = 2
DEFAULT_BASE_DELAY_S = 0.4
DEFAULT_MAX_DELAY_S = 3.0


def is_retryable(outcome: SourceOutcome) -> bool:
    """True when this outcome represents a transient, retryable failure."""
    if outcome.status == "OK":
        return False
    if outcome.status == "ERROR":
        return True
    for diagnostic in outcome_diagnostics(outcome):
        if diagnostic.get("retryable"):
            return True
        if diagnostic.get("category") in _RETRYABLE_CATEGORIES:
            return True
    # An UNAVAILABLE with no diagnostic and no error is a genuine absence, not a
    # transport failure — do not retry it.
    return bool(outcome.error) and "timed out" in str(outcome.error).lower()


async def retrieve_with_retry(
    attempt: Callable[[], Awaitable[SourceOutcome]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
) -> SourceOutcome:
    """Run `attempt`, retrying only transient failures with bounded backoff."""
    _sleep = sleep or asyncio.sleep
    outcome = await attempt()
    retries = 0
    while retries < max(0, max_retries) and is_retryable(outcome):
        delay = min(max_delay_s, base_delay_s * (2 ** retries))
        await _sleep(delay)
        retries += 1
        outcome = await attempt()
    if retries:
        outcome.retries = outcome.retries + retries
        outcome.warnings = [
            *outcome.warnings,
            f"retried {retries} time(s) after a transient failure",
        ]
    return outcome


__all__ = ["is_retryable", "retrieve_with_retry", "DEFAULT_MAX_RETRIES"]
