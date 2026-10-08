"""Tests for the quant strategy/experiment store (temp DB + artifact files)."""

from __future__ import annotations

import os

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.errors import ExperimentNotFound, StrategyNotFound
from harness.quant.store import QuantStore


@pytest.fixture()
def store(tmp_path) -> QuantStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStore(ams, artifact_root=str(tmp_path / "art"))


def _spec(version="1.0.0"):
    return S.parse_strategy({
        "strategy": {"id": "ema", "name": "EMA", "version": version},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_f", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_s", "type": "ema", "params": {"period": 20}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_above", "right": {"ref": "ema_s"}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    })


def test_strategy_crud_and_versions(store):
    store.save_strategy(_spec("1.0.0"))
    store.save_strategy(_spec("1.1.0"))
    assert len(store.list_versions("ema")) == 2
    assert store.get_strategy("ema")["version"] == "1.1.0"
    assert store.get_strategy("ema", "1.0.0")["version"] == "1.0.0"
    store.archive_strategy("ema", True)
    assert store.list_strategies() == []
    assert len(store.list_strategies(include_archived=True)) == 1
    with pytest.raises(StrategyNotFound):
        store.get_strategy("nope")


def test_experiment_roundtrip_and_artifact(store):
    spec = _spec()
    store.save_strategy(spec)
    rows = F.bull_market("TESTUSDT", n=200)
    ds = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})
    res = E.run_backtest(spec, ds, E.BacktestConfig(initial_capital=100_000))
    exp_id = store.save_experiment(res, strategy_id="ema", strategy_version="1.0.0", kind="backtest")
    got = store.get_experiment(exp_id)
    assert got["strategyId"] == "ema"
    assert got["hasArtifact"]
    artifact = store.read_artifact(exp_id)
    assert len(artifact["equityCurve"]) == 200
    assert "metricDefinitions" in artifact
    assert len(store.list_experiments(strategy_id="ema")) == 1
    store.delete_experiment(exp_id)
    with pytest.raises(ExperimentNotFound):
        store.get_experiment(exp_id)


def test_compare_experiments(store):
    spec = _spec()
    store.save_strategy(spec)
    rows = F.bull_market("TESTUSDT", n=200)
    ds = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})
    ids = []
    for cap in (100_000, 50_000):
        res = E.run_backtest(spec, ds, E.BacktestConfig(initial_capital=cap))
        ids.append(store.save_experiment(res, strategy_id="ema", strategy_version="1.0.0", kind="backtest"))
    comp = store.compare_experiments(ids)
    assert len(comp["experiments"]) == 2
    assert "sharpe" in comp["metrics"]
