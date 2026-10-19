"""The Recursive Self-Improvement Loop (RSL) — native, dark by default.

RSL is a *conductor* over machinery that already exists: post-run review,
mistake capture, the one recurrence ledger, the evolution candidate store, the
evaluator, worktrees, promotion and self-host landing. It adds no second
runtime, database, queue, evaluator or memory system.

R0–R1 implement the observation closure only:

    observe → diagnose → (inert candidate)

The loop is OFF unless `HARNESS_RSL_MODE` is set. Observations are deterministic
and model-free; they never activate a change.
"""

from .config import DEFAULT_MODE, MODES, RSLConfig
from .models import HarnessSnapshot, Observation
from .security import (
    RSL_DENY_GLOBS,
    RSLTargetError,
    assert_landable_target,
)

__all__ = [
    "DEFAULT_MODE",
    "HarnessSnapshot",
    "MODES",
    "Observation",
    "RSLConfig",
    "RSL_DENY_GLOBS",
    "RSLTargetError",
    "assert_landable_target",
]
