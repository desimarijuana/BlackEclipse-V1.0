"""Extended indicator library: stochastic, ADX, Donchian, Keltner, OBV, MFI, %R, CCI."""

from __future__ import annotations

import numpy as np
import pytest

from harness.quant import indicators as ind


def _out(out, suffix):
    key = next(k for k in out if k.endswith(suffix))
    return out[key]


def _ohlcv(o, h, l, c, v):
    return {
        "open": np.array(o, float), "high": np.array(h, float),
        "low": np.array(l, float), "close": np.array(c, float),
        "volume": np.array(v, float),
    }


RAMP = _ohlcv([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 1, 1, 1, 1])


def test_donchian_bounds():
    out = ind.compute_one(ind.IndicatorSpec("donchian", {"period": 3}), RAMP)
    upper = out["donchian_3_upper"]
    lower = out["donchian_3_lower"]
    assert np.isnan(upper[1]) and np.isnan(lower[1])
    assert upper[2] == 3 and lower[2] == 1
    assert upper[4] == 5 and lower[4] == 3
    assert out["donchian_3_middle"][4] == 4


def test_williams_r_and_stochastic_on_ramp():
    wr = ind.compute_one(ind.IndicatorSpec("williams_r", {"period": 3}), RAMP)["williams_r_3"]
    assert wr[4] == 0.0  # close is the period high
    st = ind.compute_one(ind.IndicatorSpec("stochastic", {"period": 3}), RAMP)
    assert _out(st, "_k")[2] == 100.0
    assert _out(st, "_d")[4] == 100.0


def test_obv_cumulative():
    out = ind.compute_one(ind.IndicatorSpec("obv", {}), RAMP)["obv"]
    assert out[0] == 0 and out[4] == 4  # strictly rising closes, unit volume
    down = _ohlcv([5, 4, 3], [5, 4, 3], [5, 4, 3], [5, 4, 3], [2, 2, 2])
    out2 = ind.compute_one(ind.IndicatorSpec("obv", {}), down)["obv"]
    assert out2[1] == -2 and out2[2] == -4


def test_mfi_bounded():
    out = ind.compute_one(ind.IndicatorSpec("mfi", {"period": 3}), RAMP)["mfi_3"]
    valid = out[~np.isnan(out)]
    assert np.all((valid >= 0) & (valid <= 100))
    assert out[3] == 100.0  # all money flow positive


def test_adx_and_di_bounded():
    rng = np.random.default_rng(0)
    close = np.cumsum(rng.normal(0, 1, 200)) + 100
    high = close + 1.0
    low = close - 1.0
    data = _ohlcv(close, high, low, close, np.ones(200))
    out = ind.compute_one(ind.IndicatorSpec("adx", {"period": 14}), data)
    adx_line = out["adx_14"]
    valid = adx_line[~np.isnan(adx_line)]
    assert len(valid) > 0 and np.all((valid >= 0) & (valid <= 100))
    assert np.all(out["adx_14_plus_di"][~np.isnan(out["adx_14_plus_di"])] >= 0)


def test_keltner_and_cci_shapes():
    rng = np.random.default_rng(1)
    close = np.cumsum(rng.normal(0, 1, 120)) + 50
    high, low = close + 0.8, close - 0.8
    data = _ohlcv(close, high, low, close, np.ones(120))
    kelt = ind.compute_one(ind.IndicatorSpec("keltner", {"period": 20}), data)
    assert _out(kelt, "_upper")[-1] >= _out(kelt, "_middle")[-1] >= _out(kelt, "_lower")[-1]
    cci_line = ind.compute_one(ind.IndicatorSpec("cci", {"period": 20}), data)["cci_20"]
    assert np.isfinite(cci_line[-1])


def test_catalog_and_defaults():
    spec = ind.resolve_spec(ind.IndicatorSpec("stochastic", {"period": 14}))
    assert spec.params["d_period"] == 3
    kelt = ind.resolve_spec(ind.IndicatorSpec("keltner", {"period": 20}))
    assert kelt.params["mult"] == 2.0 and kelt.params["atr_period"] == 10
    assert ind.output_keys(ind.IndicatorSpec("adx", {"period": 14})) == [
        "adx_14", "adx_14_plus_di", "adx_14_minus_di"]
    with pytest.raises(ind.IndicatorError):
        ind.resolve_spec(ind.IndicatorSpec("nope", {}))


def test_nodes_registry_has_extended_indicators():
    from harness.quant.nodes import REGISTRY

    for t in ("stochastic", "adx", "donchian", "keltner", "obv", "mfi", "williams_r", "cci"):
        assert f"indicator.{t}" in REGISTRY.types()
