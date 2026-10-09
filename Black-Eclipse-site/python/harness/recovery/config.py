"""Configuration for the recovery engine — flags and bounds, one place."""

from __future__ import annotations

import os

from .policy import RecoveryBudget

_TRUTHY = ("1", "true", "yes", "on")
_FALSEY = ("0", "false", "no", "off")


def recovery_enabled() -> bool:
    """Whether the recovery engine is active. Default ON; `0`/`false` disables.

    Unlike the experimental replan path (default OFF), failure intelligence is a
    core runtime behavior: recording an incident changes no run outcome, so it is
    safe on by default. An operator can still turn it off with one variable.
    """
    value = os.environ.get("HARNESS_RECOVERY_ENABLED")
    if value is None:
        return True
    return value.strip().lower() not in _FALSEY


def budget_from_env() -> RecoveryBudget:
    """The recovery budget, overridable per environment (spec §9.4)."""
    defaults = RecoveryBudget()

    def _int(name: str, fallback: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return fallback
        try:
            return max(0, int(raw))
        except ValueError:
            return fallback

    return RecoveryBudget(
        max_attempts=_int("HARNESS_RECOVERY_MAX_ATTEMPTS", defaults.max_attempts),
        max_per_signature=_int("HARNESS_RECOVERY_MAX_PER_SIGNATURE", defaults.max_per_signature),
        max_delegations=_int("HARNESS_RECOVERY_MAX_DELEGATIONS", defaults.max_delegations),
        max_total_ms=_int("HARNESS_RECOVERY_MAX_TOTAL_MS", defaults.max_total_ms),
    )


__all__ = ["budget_from_env", "recovery_enabled"]
