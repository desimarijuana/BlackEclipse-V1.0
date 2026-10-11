"""Factor registry + persistence + service integration."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import service as S
from harness.factors.models import FactorDefinition
from harness.factors.store import FactorStore, build_version_string
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path) -> FactorStore:
    fs = FactorStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_factor_store(fs)
    yield fs
    S.set_factor_store(None)


def test_build_version_string():
    assert build_version_string(None) == "0.0.1"
    assert build_version_string("1.0.0", "minor") == "1.1.0"
    assert build_version_string("1.2.3", "major") == "2.0.0"


def test_validate_expression():
    ok = S.validate_expression("pct_change(close, 21)")
    assert ok["valid"] and ok["variables"] == ["close"]
    bad = S.validate_expression("no_such_fn(close)")
    assert bad["valid"] is False
    empty = S.validate_expression("")
    assert empty["valid"] is False


def test_validate_expression_with_sample_preview():
    result = S.validate_expression("pct_change(close, 1)", sample={"close": [1.0, 2.0, 4.0]})
    assert result["valid"]
    assert result["coverage"] is not None
    assert result["preview"][-1] == pytest.approx(1.0)


def test_save_and_version_immutability(store):
    defn = FactorDefinition(name="My Momentum", expression="pct_change(close, 21)", family="momentum",
                            direction="positive")
    first = S.save_factor(defn, bump="minor")
    assert first["factor"]["latestVersion"] == "1.0.0"
    assert first["version"]["version"] == "1.0.0"
    second = S.save_factor(FactorDefinition(name="My Momentum", expression="pct_change(close, 63)",
                                            family="momentum"), bump="minor")
    factor_id = first["factor"]["id"]
    assert second["factor"]["latestVersion"] == "1.1.0"
    versions = store.list_versions(factor_id)
    assert [v["version"] for v in versions] == ["1.0.0", "1.1.0"]
    # original expression is unchanged
    assert store.get_version(factor_id, "1.0.0")["expression"] == "pct_change(close, 21)"


def test_install_builtins_registers_available_factors(store):
    S.install_builtins()
    names = {f["name"] for f in S.list_factors()}
    assert "momentum_12_1" in names
    assert "low_volatility_3m" in names
    # unavailable (fundamental) factors are registered only after explicit creation
    assert "earnings_yield" not in names
    spec = S.get_builtin_spec("momentum_1m")
    assert spec["available"] is True


def test_build_factor_panel_and_evaluate(store):
    rng = np.random.default_rng(3)
    n = 300
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + rng.normal(0, 0.01)))
    # two symbols whose forward returns correlate with the factor's rank
    series = {
        "AAA": {"close": prices},
        "BBB": {"close": [p * (1 + 0.001 * (i % 5)) for i, p in enumerate(prices)]},
        "CCC": {"close": [p * (1 - 0.001 * (i % 5)) for i, p in enumerate(prices)]},
    }
    panel, warnings = S.build_factor_panel("pct_change(close, 21)", series, list(series))
    assert panel.shape == (n, 3)
    ev = S.evaluate("pct_change(close, 21)", series, list(series), horizons=[1, 5], min_obs=3)
    assert ev["observations"] > 0
    assert ev["ic"]["summary"]["available"] is True
    assert len(ev["decay"]["curve"]) == 2


def test_quantile_portfolio_service(store):
    rng = np.random.default_rng(11)
    series = {}
    for i, sym in enumerate(["A", "B", "C", "D", "E", "F"]):
        base = 100.0
        px = [base]
        for _ in range(250):
            px.append(px[-1] * (1 + rng.normal(0.0002 * i, 0.01)))
        series[sym] = {"close": px}
    out = S.quantile_portfolio("pct_change(close, 21)", series, list(series), quantiles=3,
                               long_short=True, rebalance=5, cost_bps=10.0)
    assert "longShortMetrics" in out
    assert out["turnover"]["average"] >= 0
    assert len(out["finalWeights"]) >= 0
