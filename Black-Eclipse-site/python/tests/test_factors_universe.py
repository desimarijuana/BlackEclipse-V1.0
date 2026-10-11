"""Point-in-time universe membership (survivorship control)."""

from __future__ import annotations

import math

import numpy as np

from harness.factors.universe import apply_membership, membership_mask
from harness.market.universe_store import UniverseStore
from harness.persistence import AgentMemoryStore


def _store(tmp_path) -> UniverseStore:
    us = UniverseStore(AgentMemoryStore(str(tmp_path / "am.db")))
    us.record_membership("sp500", [
        {"symbol": "A", "effectiveFrom": "2020-01-01"},
        {"symbol": "B", "effectiveFrom": "2020-01-01", "effectiveTo": "2020-06-01"},
        {"symbol": "C", "effectiveFrom": "2020-06-01"},
    ], name="S&P 500")
    return us


def test_membership_mask_is_effective_dated(tmp_path):
    us = _store(tmp_path)
    dates = ["2020-03-01", "2020-07-01"]
    symbols = ["A", "B", "C"]
    mask = membership_mask(us, "sp500", symbols, dates)
    assert mask.tolist() == [[True, True, False], [True, False, True]]


def test_apply_membership_excludes_non_members(tmp_path):
    us = _store(tmp_path)
    dates = ["2020-03-01", "2020-07-01"]
    symbols = ["A", "B", "C"]
    mask = membership_mask(us, "sp500", symbols, dates)
    panel = np.ones((2, 3))
    masked = apply_membership(panel, mask)
    assert np.isfinite(masked[0, 0]) and np.isfinite(masked[0, 1]) and math.isnan(masked[0, 2])
    assert np.isfinite(masked[1, 0]) and math.isnan(masked[1, 1]) and np.isfinite(masked[1, 2])


def test_membership_mask_shape_mismatch_rejected():
    from harness.stats.base import StatsError

    try:
        apply_membership(np.ones((2, 3)), np.ones((2, 2), dtype=bool))
    except StatsError as exc:
        assert exc.code == "INVALID_INPUT"
    else:  # pragma: no cover
        raise AssertionError("expected INVALID_INPUT")
