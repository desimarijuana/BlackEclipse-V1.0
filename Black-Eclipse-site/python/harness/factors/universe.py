"""Point-in-time universe membership for factor research (survivorship control).

A factor cross-section is only valid if it is computed over the instruments that
were ACTUALLY members of the universe on each date. This module turns the
effective-dated membership history (`UniverseStore.members_as_of`, SCD-2) into a
`(T, N)` boolean mask aligned to the factor panel, so a name that joined late or
was delisted is excluded from the cross-sections it did not belong to.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from ..stats.base import INVALID_INPUT, StatsError


def _members_by_date(universe_store: Any, universe_id: str, dates: Sequence[str]) -> dict[str, set[str]]:
    cache: dict[str, set[str]] = {}
    for d in dates:
        key = str(d)
        if key not in cache:
            rows = universe_store.members_as_of(universe_id, key)
            cache[key] = {str(m["symbol"]).upper() for m in rows}
    return cache


def membership_mask(universe_store: Any, universe_id: str, symbols: Sequence[str],
                    dates: Sequence[str]) -> np.ndarray:
    """A ``(T, N)`` bool mask: True where symbol ``j`` was a member on date ``t``."""
    if universe_store is None:
        raise StatsError("DEPENDENCY_MISSING", "the universe store is unavailable in this runtime", 503)
    syms = [str(s).upper() for s in symbols]
    by_date = _members_by_date(universe_store, str(universe_id), list(dates))
    mask = np.zeros((len(dates), len(syms)), dtype=bool)
    for t, d in enumerate(dates):
        members = by_date[str(d)]
        for j, s in enumerate(syms):
            mask[t, j] = s in members
    return mask


def apply_membership(panel: np.ndarray, membership: Optional[np.ndarray]) -> np.ndarray:
    """Return the panel with non-member cells set to NaN (never silently kept)."""
    if membership is None:
        return panel
    m = np.asarray(membership, dtype=bool)
    if m.shape != panel.shape:
        raise StatsError(INVALID_INPUT, "membership mask must match the panel shape")
    return np.where(m, panel, np.nan)


__all__ = ["membership_mask", "apply_membership"]
