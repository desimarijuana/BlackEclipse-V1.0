"""Bounded configuration for the Recursive Self-Improvement Loop (RSL).

The loop is DARK by default. `HARNESS_RSL_MODE=off` makes every RSL entry point
a no-op; observation mode is an explicit operator opt-in. Every numeric value is
clamped so an environment typo can never remove a budget ceiling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

MODES: tuple[str, ...] = ("off", "observe", "propose", "verify", "auto")
STRATEGIES: tuple[str, ...] = ("rsl", "hillclimb")
DEFAULT_MODE = "off"
DEFAULT_STRATEGY = "rsl"

_MODE_ENV = "HARNESS_RSL_MODE"
_STRATEGY_ENV = "HARNESS_RSL_STRATEGY"


def _env_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _env_float(
    environ: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    return max(minimum, min(maximum, value))


def _env_bool(environ: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RSLConfig:
    """The bounded RSL settings for one process.

    `mode` is one of `off`/`observe`/`propose`/`verify`/`auto`. `auto` runs the
    bounded propose and verify phases in one tick; it still never lands a change.
    The deterministic observation pass runs in every non-off mode.
    """

    mode: str = DEFAULT_MODE
    strategy: str = DEFAULT_STRATEGY
    max_candidates: int = 5
    max_experiments_per_day: int = 3
    trials: int = 3
    k: int = 1
    generations: int = 1
    objective: str = 'single'
    tick_seconds: int = 300
    lease_seconds: int = 1800
    max_wall_seconds: int = 1800
    max_cost_usd: float = 5.0
    lesson_retire: bool = False
    lesson_transfer: bool = False
    model_proposer: bool = False
    code_benchmark: bool = False
    canary: bool = False
    canary_split: str = 'held_out'
    canary_tolerance: float = 0.05

    @property
    def is_off(self) -> bool:
        return self.mode == "off"

    @property
    def observes(self) -> bool:
        """True for every non-off mode (the observation pass always runs first)."""
        return self.mode in ("observe", "propose", "verify", "auto")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "RSLConfig":
        env: Mapping[str, str] = os.environ if environ is None else environ
        raw_mode = str(env.get(_MODE_ENV, DEFAULT_MODE)).strip().lower()
        mode = raw_mode if raw_mode in MODES else DEFAULT_MODE
        raw_objective = str(env.get("HARNESS_RSL_OBJECTIVE", "single")).strip().lower()
        objective = raw_objective if raw_objective in ("single", "pareto") else "single"
        raw_strategy = str(env.get(_STRATEGY_ENV, DEFAULT_STRATEGY)).strip().lower()
        strategy = raw_strategy if raw_strategy in STRATEGIES else DEFAULT_STRATEGY
        return cls(
            mode=mode,
            strategy=strategy,
            objective=objective,
            max_candidates=_env_int(env, "HARNESS_RSL_MAX_CANDIDATES", 5, 1, 50),
            max_experiments_per_day=_env_int(
                env, "HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY", 3, 0, 50,
            ),
            trials=_env_int(env, "HARNESS_RSL_TRIALS", 3, 1, 10),
            k=_env_int(env, "HARNESS_RSL_K", 1, 1, 8),
            generations=_env_int(env, "HARNESS_RSL_GENERATIONS", 1, 1, 3),
            tick_seconds=_env_int(env, "HARNESS_RSL_TICK_SECONDS", 300, 10, 3600),
            lease_seconds=_env_int(env, "HARNESS_RSL_LEASE_SECONDS", 1800, 60, 86400),
            max_wall_seconds=_env_int(
                env, "HARNESS_RSL_MAX_WALL_SECONDS", 1800, 30, 7200,
            ),
            max_cost_usd=_env_float(env, "HARNESS_RSL_MAX_COST_USD", 5.0, 0.0, 1000.0),
            lesson_retire=_env_bool(env, "HARNESS_RSL_LESSON_RETIRE", False),
            lesson_transfer=_env_bool(env, "HARNESS_RSL_LESSON_TRANSFER", False),
            model_proposer=_env_bool(env, "HARNESS_RSL_MODEL_PROPOSER", False),
            code_benchmark=_env_bool(env, "HARNESS_RSL_CODE_BENCHMARK", False),
            canary=_env_bool(env, "HARNESS_RSL_CANARY", False),
            canary_split=str(env.get("HARNESS_RSL_CANARY_SPLIT", "held_out")),
            canary_tolerance=_env_float(
                env, "HARNESS_RSL_CANARY_TOLERANCE", 0.05, 0.0, 1.0,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """A bounded, non-secret diagnostic view."""
        return {
            "mode": self.mode,
            "strategy": self.strategy,
            "maxCandidates": self.max_candidates,
            "maxExperimentsPerDay": self.max_experiments_per_day,
            "trials": self.trials,
            "k": self.k,
            "objective": self.objective,
            "generations": self.generations,
            "tickSeconds": self.tick_seconds,
            "leaseSeconds": self.lease_seconds,
            "maxWallSeconds": self.max_wall_seconds,
            "maxCostUsd": self.max_cost_usd,
            "lessonRetire": self.lesson_retire,
            "lessonTransfer": self.lesson_transfer,
            "modelProposer": self.model_proposer,
            "codeBenchmark": self.code_benchmark,
            "canary": self.canary,
            "canarySplit": self.canary_split,
            "canaryTolerance": self.canary_tolerance,
        }


__all__ = [
    "DEFAULT_MODE",
    "DEFAULT_STRATEGY",
    "MODES",
    "RSLConfig",
    "STRATEGIES",
]
