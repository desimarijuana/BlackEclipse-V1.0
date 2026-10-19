"""Bounded configuration for the Recursive Self-Improvement Loop (RSL).

The loop is DARK by default. `HARNESS_RSL_MODE=off` makes every RSL entry point
a no-op; observation mode is an explicit operator opt-in. Every numeric value is
clamped so an environment typo can never remove a budget ceiling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

MODES: tuple[str, ...] = ("off", "observe", "propose", "verify")
DEFAULT_MODE = "off"

_MODE_ENV = "HARNESS_RSL_MODE"


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


@dataclass(frozen=True)
class RSLConfig:
    """The bounded RSL settings for one process.

    `mode` is one of `off`/`observe`/`propose`/`verify`. R1 only implements the
    deterministic observation pass; `propose` and `verify` are accepted so the
    later phases can broaden behaviour without a config migration.
    """

    mode: str = DEFAULT_MODE
    max_candidates: int = 5
    max_experiments_per_day: int = 3
    trials: int = 3
    k: int = 1
    tick_seconds: int = 300
    lease_seconds: int = 1800
    max_wall_seconds: int = 1800
    max_cost_usd: float = 5.0

    @property
    def is_off(self) -> bool:
        return self.mode == "off"

    @property
    def observes(self) -> bool:
        """True for every non-off mode (the observation pass always runs first)."""
        return self.mode in ("observe", "propose", "verify")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "RSLConfig":
        env: Mapping[str, str] = os.environ if environ is None else environ
        raw_mode = str(env.get(_MODE_ENV, DEFAULT_MODE)).strip().lower()
        mode = raw_mode if raw_mode in MODES else DEFAULT_MODE
        return cls(
            mode=mode,
            max_candidates=_env_int(env, "HARNESS_RSL_MAX_CANDIDATES", 5, 1, 50),
            max_experiments_per_day=_env_int(
                env, "HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY", 3, 0, 50,
            ),
            trials=_env_int(env, "HARNESS_RSL_TRIALS", 3, 1, 10),
            k=_env_int(env, "HARNESS_RSL_K", 1, 1, 8),
            tick_seconds=_env_int(env, "HARNESS_RSL_TICK_SECONDS", 300, 10, 3600),
            lease_seconds=_env_int(env, "HARNESS_RSL_LEASE_SECONDS", 1800, 60, 86400),
            max_wall_seconds=_env_int(
                env, "HARNESS_RSL_MAX_WALL_SECONDS", 1800, 30, 7200,
            ),
            max_cost_usd=_env_float(env, "HARNESS_RSL_MAX_COST_USD", 5.0, 0.0, 1000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """A bounded, non-secret diagnostic view."""
        return {
            "mode": self.mode,
            "maxCandidates": self.max_candidates,
            "maxExperimentsPerDay": self.max_experiments_per_day,
            "trials": self.trials,
            "k": self.k,
            "tickSeconds": self.tick_seconds,
            "leaseSeconds": self.lease_seconds,
            "maxWallSeconds": self.max_wall_seconds,
            "maxCostUsd": self.max_cost_usd,
        }


__all__ = ["DEFAULT_MODE", "MODES", "RSLConfig"]
