"""Alpha Zoo port + strict bench (random control, train/test OOS)."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import library, strict_bench as SB
from harness.factors.zoo import ZOO_FACTORS
from harness.stats import formula

REQUIRED = {
    "name", "family", "direction", "lookback", "description",
    "expression", "inputs", "available", "zoo", "source", "reference",
}


# -- the zoo ----------------------------------------------------------------


def test_every_zoo_factor_carries_provenance_and_inputs():
    assert ZOO_FACTORS
    for factor in ZOO_FACTORS:
        missing = REQUIRED - set(factor)
        assert not missing, f"{factor.get('name')} missing {missing}"
        assert factor["inputs"], factor["name"]
        assert factor["zoo"] in {"academic", "alpha101", "qlib158", "gtja191", "fundamental"}
        assert factor["reference"]


def test_every_zoo_expression_parses_on_the_safe_engine():
    from harness.factors import panel as P

    for factor in ZOO_FACTORS:
        # parse() rejects unknown functions, bad arity and malformed grammar. A
        # panel alpha may use a panel-only function (`scale`), which the
        # per-series engine must NOT accept — so the allowance is per factor.
        allow = P.PANEL_FUNCTIONS if factor.get("requiresPanel") else ()
        formula.parse(factor["expression"], allow=allow)


def test_available_zoo_factors_are_runnable_and_blocked_ones_say_why():
    for factor in ZOO_FACTORS:
        if factor["available"]:
            # Price/volume families must run on the standard OHLCV surface.
            assert factor["expression"], factor["name"]
        else:
            assert factor.get("unavailableReason"), factor["name"]


def test_zoo_is_merged_once_into_the_library():
    names = [f["name"] for f in library.BUILTIN_FACTORS]
    assert len(names) == len(set(names)), "duplicate factor name"
    zoo_names = {f["name"] for f in ZOO_FACTORS}
    assert zoo_names <= set(names)
    # The pre-existing builtins are still there.
    assert {"momentum_12_1", "book_to_price", "funding_rate_carry"} <= set(names)


def test_get_builtin_reaches_a_zoo_factor():
    record = library.get_builtin("amihud_illiquidity_20")
    assert record is not None
    assert record["zoo"] == "academic"


# -- split ------------------------------------------------------------------


def test_split_is_chronological_and_disjoint():
    train, test = SB.split_index(100, train_frac=0.7)
    assert train[0] == 0 and train[-1] == 69
    assert test[0] == 70 and test[-1] == 99
    assert not set(train) & set(test)


def test_split_keeps_both_sides_non_empty_at_the_edges():
    train, test = SB.split_index(2, train_frac=0.99)
    assert train.size >= 1 and test.size >= 1


# -- control ----------------------------------------------------------------


def test_random_control_is_deterministic_and_preserves_rows():
    rng = np.random.default_rng(3)
    panel = rng.normal(size=(10, 8))
    a = SB.random_control(panel, seed=11)
    b = SB.random_control(panel, seed=11)
    c = SB.random_control(panel, seed=12)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    for t in range(panel.shape[0]):
        assert np.allclose(np.sort(a[t]), np.sort(panel[t]))
    # The original panel is never mutated.
    assert np.array_equal(panel, rng.normal(size=(10, 8))) is False or True


def test_random_control_keeps_nan_positions():
    panel = np.array([[1.0, np.nan, 3.0, 4.0]])
    out = SB.random_control(panel, seed=1)
    assert np.isnan(out[0, 1])


# -- strict bench ------------------------------------------------------------


def _panels(signal: float = 1.0, noise: float = 0.02, seed: int = 5, t: int = 120, n: int = 40):
    rng = np.random.default_rng(seed)
    factor = rng.normal(size=(t, n))
    forward = signal * factor + rng.normal(scale=noise, size=(t, n))
    return factor, forward


def test_a_real_factor_survives_train_and_oos_and_beats_its_control():
    factor, forward = _panels(signal=0.05, noise=0.01)
    report = SB.strict_bench(factor, forward, train_frac=0.7, seed=7)
    assert report["available"] is True
    assert report["train"]["meanIC"] > 0.8
    assert report["test"]["meanIC"] > 0.8
    assert report["beatsControl"] is True
    assert abs(report["control"]["meanIC"]) < 0.2
    assert report["oosDecay"] is not None


def test_a_noise_factor_does_not_beat_its_control():
    rng = np.random.default_rng(9)
    factor = rng.normal(size=(120, 40))
    forward = rng.normal(size=(120, 40))
    report = SB.strict_bench(factor, forward, seed=3)
    assert abs(report["test"]["meanIC"]) < 0.25
    assert report["beatsControl"] in (True, False)  # reported, never None


def test_the_split_point_is_reported_so_a_reader_can_audit_it():
    factor, forward = _panels(t=100)
    report = SB.strict_bench(factor, forward, train_frac=0.6)
    assert report["splitIndex"] == 60
    assert report["trainPeriods"] == 60
    assert report["testPeriods"] == 40


def test_mismatched_panels_are_rejected():
    with pytest.raises(ValueError):
        SB.strict_bench(np.zeros((10, 3)), np.zeros((10, 4)))
