"""Deterministic hyperparameter search — grid or seeded random, no Optuna needed.

A search is N training runs of ONE family over a declared space, all validated on
the caller's exact split spec. It reuses the arena's ranking, so the same honest
rules apply: an unmeasured metric is excluded rather than treated as zero, and a
margin inside the fold noise is reported as no clear winner.

The one thing a search must SAY out loud: the winner was selected on the same
folds it is scored on, so its reported score is optimistic. Every result carries
that warning; a confirmation run on a fresh period is the honest next step.
"""

from __future__ import annotations

import itertools
from typing import Any, Optional

from .models import MLError

MAX_TRIALS = 24

# Small, documented defaults per native family. Optional families accept their
# library's own parameter names, so a caller passes an explicit grid for them.
DEFAULT_SPACES: dict[str, dict[str, list[Any]]] = {
    "logistic": {"l2": [1e-4, 1e-3, 1e-2], "learningRate": [0.1, 0.5]},
    "ridge": {"alpha": [0.01, 0.1, 1.0, 10.0]},
    "random_forest": {"nEstimators": [100, 200], "maxDepth": [4, 6, 8]},
    "kmeans": {"nClusters": [2, 3, 4, 5, 6]},
    "mad_z": {"contamination": [0.01, 0.05, 0.1]},
}


def expand_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of a grid, in sorted key order (deterministic)."""
    if not grid:
        return [{}]
    keys = sorted(grid)
    values = []
    for key in keys:
        column = list(grid[key])
        if not column:
            raise MLError("INVALID_INPUT", f"grid parameter {key!r} has no values", 422)
        values.append(column)
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def sample_configs(grid: dict[str, list[Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Seeded, duplicate-free sample of a grid (deterministic for a given seed)."""
    import numpy as np  # noqa: PLC0415

    universe = expand_grid(grid)
    if len(universe) <= n:
        return universe
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(universe), size=max(1, n), replace=False)
    return [universe[int(i)] for i in sorted(picked)]


def plan_trials(
    family: str,
    *,
    grid: Optional[dict[str, list[Any]]] = None,
    n_trials: Optional[int] = None,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], bool]:
    """The trial configs to run, plus whether they were sampled from a larger grid."""
    space = dict(grid) if grid else dict(DEFAULT_SPACES.get(family, {}))
    if not space:
        return [{}], False
    universe = expand_grid(space)
    if n_trials is None or n_trials >= len(universe):
        return universe[:MAX_TRIALS], False
    return sample_configs(space, max(1, int(n_trials)), seed), True


__all__ = ["DEFAULT_SPACES", "MAX_TRIALS", "expand_grid", "plan_trials", "sample_configs"]
