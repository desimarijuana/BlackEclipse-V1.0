"""GTJA191 tranche 11: the rank-inside-correlation family — a self-correction.

Earlier documentation in this repository claimed the panel evaluator "refuses" a
cross-sectional rank nested inside a rolling correlation. **That was wrong**, and
this tranche exists because a smoke test disproved it:

    correlation(rank(volume), rank(vwap), 5)

evaluates correctly in the panel path — `rank(...)` yields a T x N array of per-date
cross-sectional ranks, and `correlation(...)` then runs column-wise over time. What
would be wrong is running the same expression through the *per-series* engine,
where `rank` is a time-series percentile; every alpha here is `requiresPanel`, and
the strict-bench test parses them with the panel allowance only.

The tests therefore pin three things: the nesting actually evaluates, a rank series
that is constant over the window yields NaN rather than a fabricated correlation,
and each alpha's declared inputs are honest.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191

NEW = (16, 32, 36, 55, 62, 74, 83, 90, 99, 101, 105, 119, 130, 141, 176, 179)
VWAP_USERS = (36, 74, 90, 101, 119, 130, 179)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _panel(rows=120, cols=24, seed=127):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i:03d}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.012, rows))
        open_ = close * (1 + rng.normal(0, 0.003, rows))
        high = close * (1 + abs(rng.normal(0, 0.006, rows)))
        low = close * (1 - abs(rng.normal(0, 0.006, rows)))
        volume = rng.integers(1_000_000, 5_000_000, rows).astype(float)
        vwap = close * (1 + rng.normal(0, 0.002, rows))
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "open": float(open_[i]),
             "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i]),
             "vwap": float(vwap[i])}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap"])


# -- the correction ---------------------------------------------------------


def test_rank_inside_correlation_evaluates_in_the_panel_path():
    value = P.evaluate("correlation(rank(volume), rank(vwap), 5)", _panel())
    finite = value[-1]
    finite = finite[np.isfinite(finite)]
    assert finite.size > 0
    assert (finite >= -1.0 - 1e-9).all() and (finite <= 1.0 + 1e-9).all()


def test_a_constant_rank_series_yields_nan_not_a_fabricated_correlation():
    # Two names whose ranks never change: the correlation is undefined, and the
    # kernel must say so rather than return 0.
    rows = 10
    timestamps = [f"d{i:02d}" for i in range(rows)]
    rows_by_symbol = {
        "AAA": [{"timestamp": timestamps[i], "a": 1.0, "b": 1.0} for i in range(rows)],
        "BBB": [{"timestamp": timestamps[i], "a": 2.0, "b": 2.0} for i in range(rows)],
    }
    built = P.build_panel(rows_by_symbol, ["a", "b"])
    value = P.evaluate("correlation(rank(a), rank(b), 4)", built)[-1]
    assert np.isnan(value).all()


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    numbers = [f["alphaNumber"] for f in gtja191.GTJA191_FACTORS]
    assert len(numbers) == len(set(numbers)), "duplicate alpha number"
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 167
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_every_new_alpha_is_flagged_panel_and_declares_its_inputs():
    for number in NEW:
        factor = _by_number()[number]
        assert factor["requiresPanel"] is True, number
    for number in VWAP_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("vwap",), number


@pytest.mark.parametrize("number", NEW)
def test_each_alpha_evaluates_on_a_wide_enough_panel(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any(), number


def test_alpha16_and_83_are_the_published_duplicate_pair():
    a, b = _by_number()[16], _by_number()[83]
    assert a["expression"] == b["expression"]
    assert a["alphaNumber"] != b["alphaNumber"]


def test_alpha101_is_boolean():
    value = P.evaluate(_by_number()[101]["expression"], _panel(rows=160, cols=24))[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert set(np.unique(finite)) <= {0.0, -1.0}


def test_alpha32_is_a_sum_of_ranks_so_it_is_bounded():
    value = P.evaluate(_by_number()[32]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert (finite >= -3.0 - 1e-9).all() and (finite <= 0.0 + 1e-9).all()
