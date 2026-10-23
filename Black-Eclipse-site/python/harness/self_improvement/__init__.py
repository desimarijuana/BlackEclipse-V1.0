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

from .archive import ArchiveConfig, StateArchive
from .autonomy import (
    AutonomyKillSwitch,
    autonomy_status,
    classify_ops_risk,
    classify_snapshot_risk,
    decide as autonomy_decide,
)
from .cmp import CMPConfig, descendant_lift, metaproductivity
from .config import DEFAULT_MODE, MODES, RSLConfig
from .hillclimb import HillClimbConfig, run_hillclimb
from .lesson_feedback import (
    LessonOutcomeStore,
    LessonStats,
    rank_lessons,
    retire_unhelpful,
)
from .models import HarnessSnapshot, Observation
from .operators import (
    OPERATORS,
    classify_ops,
    classify_snapshot,
    jaccard_novelty,
    op_signature,
    tokens_for_ops,
)
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
    "ArchiveConfig",
    "AutonomyKillSwitch",
    "CMPConfig",
    "DEFAULT_MODE",
    "HarnessSnapshot",
    "HarnessStateStore",
    "HillClimbConfig",
    "LessonOutcomeStore",
    "LessonStats",
    "MODES",
    "OPERATORS",
    "Observation",
    "RSLConfig",
    "RSL_DENY_GLOBS",
    "RSLTargetError",
    "ReplaySuite",
    "StateArchive",
    "UtilityWeights",
    "acceptance",
    "assert_landable_target",
    "autonomy_decide",
    "autonomy_status",
    "build_replay_suite",
    "classify_ops",
    "classify_ops_risk",
    "classify_snapshot_risk",
    "classify_snapshot",
    "descendant_lift",
    "jaccard_novelty",
    "metaproductivity",
    "model_settings_from_env",
    "op_signature",
    "propose_variants",
    "rank_lessons",
    "replay_gate",
    "retire_unhelpful",
    "run_hillclimb",
    "tokens_for_ops",
    "utility",
]
