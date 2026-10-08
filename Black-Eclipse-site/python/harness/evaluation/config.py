"""Configuration for the Eclipse Agent Evaluation system.

All evaluation artifacts (trajectories, reports, mined candidates) live under
``<repo>/.black-eclipse/evaluation/`` — derived data, never the user's folders and
never ``jdds.db``. Durability rows (runs, trials, scores, baselines, regressions)
live in the shared ``agent-memory.db`` connection via :class:`EvaluationStore`.

Precedence: explicit overrides > environment variable > built-in default. This
mirrors ``harness.search.config`` / ``harness.event_system.config`` so a reader
who knows one subsystem knows this one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

# The normalized trajectory / report / grader schema versions. Bump a version
# when a shape changes so historical records keep their original meaning.
TRAJECTORY_FORMAT_VERSION = "1"
TASK_SCHEMA_VERSION = 1
GRADER_API_VERSION = 1

_TRUTHY = ("1", "true", "yes", "on", "enable", "enabled")


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _int(name: str, default: int, *, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def evaluation_root() -> str:
    """``<repo>/.black-eclipse/evaluation`` — created on demand."""
    from ..eclipse_memory.config import repo_root  # noqa: PLC0415

    path = os.path.join(repo_root(), ".black-eclipse", "evaluation")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class EvaluationConfig:
    """Runtime knobs for evaluation. Every field has an env override."""

    enabled: bool = True
    # Trials per task. Agent execution is stochastic; one success proves nothing.
    trials: int = 1
    # Independent (task, trial) executions in flight at once.
    max_concurrency: int = 4
    # A per-trial wall clock budget (seconds) before the trial is classified
    # `timeout`. 0 disables the guard.
    trial_timeout_seconds: float = 300.0
    # Token/step ceilings applied to every trial unless a task narrows them.
    max_turns: int = 40
    max_tool_calls: int = 200
    # Default regeneration / report location.
    artifact_root: str = ""
    # Allow trials to perform external side effects. OFF by default: an
    # evaluation must never touch a real network/service/account unless asked.
    allow_external_side_effects: bool = False
    # A cap on how many mined production failures are kept before dedup pruning.
    mining_max_candidates: int = 500

    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "EvaluationConfig":
        config = cls(
            enabled=_flag("HARNESS_EVAL_ENABLED", True),
            trials=_int("HARNESS_EVAL_TRIALS", 1, low=1, high=100),
            max_concurrency=_int("HARNESS_EVAL_CONCURRENCY", 4, low=1, high=64),
            trial_timeout_seconds=float(
                os.environ.get("HARNESS_EVAL_TRIAL_TIMEOUT", "300") or "300"
            ),
            max_turns=_int("HARNESS_EVAL_MAX_TURNS", 40, low=1, high=10000),
            max_tool_calls=_int("HARNESS_EVAL_MAX_TOOL_CALLS", 200, low=1, high=100000),
            allow_external_side_effects=_flag("HARNESS_EVAL_ALLOW_SIDE_EFFECTS", False),
            mining_max_candidates=_int(
                "HARNESS_EVAL_MINING_MAX", 500, low=1, high=100000
            ),
        )
        config.artifact_root = config.artifact_root or evaluation_root()
        if overrides:
            for key, value in overrides.items():
                if value is not None and hasattr(config, key):
                    setattr(config, key, value)
        return config


def trajectory_dir() -> str:
    path = os.path.join(evaluation_root(), "trajectories")
    os.makedirs(path, exist_ok=True)
    return path


def report_dir() -> str:
    path = os.path.join(evaluation_root(), "reports")
    os.makedirs(path, exist_ok=True)
    return path


__all__ = [
    "GRADER_API_VERSION",
    "TASK_SCHEMA_VERSION",
    "TRAJECTORY_FORMAT_VERSION",
    "EvaluationConfig",
    "evaluation_root",
    "report_dir",
    "trajectory_dir",
]
