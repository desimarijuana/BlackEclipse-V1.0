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
from .hillclimb import HillClimbConfig, run_hillclimb
from .lesson_feedback import (
    LessonOutcomeStore,
    LessonStats,
    rank_lessons,
    retire_unhelpful,
)
from .models import HarnessSnapshot, Observation
from .proposer_model import model_settings_from_env, propose_variants
from .replay import ReplaySuite, build_replay_suite, replay_gate
from .security import (
    RSL_DENY_GLOBS,
    RSLTargetError,
    assert_landable_target,
)
from .state import HarnessStateStore
from .utility import UtilityWeights, acceptance, utility

__all__ = [
    "DEFAULT_MODE",
    "HarnessSnapshot",
    "HarnessStateStore",
    "HillClimbConfig",
    "LessonOutcomeStore",
    "LessonStats",
    "MODES",
    "Observation",
    "RSLConfig",
    "RSL_DENY_GLOBS",
    "RSLTargetError",
    "ReplaySuite",
    "UtilityWeights",
    "acceptance",
    "assert_landable_target",
    "build_replay_suite",
    "model_settings_from_env",
    "propose_variants",
    "rank_lessons",
    "replay_gate",
    "retire_unhelpful",
    "run_hillclimb",
    "utility",
]
