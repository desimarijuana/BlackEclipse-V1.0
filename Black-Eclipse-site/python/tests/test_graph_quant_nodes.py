"""Quant backtest node: reuses the tested engine, deterministic presets, honest
failures, and StrategySpec JSON support."""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.quant import fixtures as F

REGISTRY = build_default_registry()


def _exec(config: dict, series: dict | None = None, node_type: str = "quant.backtest"):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    payload = series if series is not None else {
        "symbol": "TESTUSDT", "interval": "1d",
        "rows": F.bull_market("TESTUSDT", n=180),
    }
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.BACKTEST,
        inputs={"series": payload}, config=config,
    ))


def test_ema_cross_backtest_is_wellformed_and_deterministic():
    config = {
        "preset": "ema_cross", "fast": 5, "slow": 20,
        "atrPeriod": 14, "atrMult": 2, "reward": 2, "sizePct": 90,
    }
    first = _exec(config)
    second = _exec(config)
    assert first["result"]["status"] == "OK"
    assert "trade_count" in first["metrics"]
    assert isinstance(first["trades"], list)
    assert first["metrics"] == second["metrics"]
    assert [t["netPnl"] for t in first["trades"]] == [t["netPnl"] for t in second["trades"]]
    assert "equityCurve" not in first["result"]  # includeSeries defaults off


def test_rsi_reversion_preset_runs():
    result = _exec({"preset": "rsi_reversion", "rsiPeriod": 14, "oversold": 30, "overbought": 55})
    assert result["result"]["status"] == "OK"
    assert result["metrics"]["trade_count"] >= 0


def test_include_series_adds_the_curves():
    result = _exec({"preset": "ema_cross", "includeSeries": True, "maxBars": 60})
    assert result["result"]["equityCurve"]
    assert result["result"]["drawdownCurve"]


def test_full_strategy_json_is_supported():
    spec = {
        "strategy": {"id": "custom_ema", "name": "Custom EMA", "version": "1.0.0"},
        "universe": {"symbols": ["IGNORED"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
            {"id": "atr", "type": "atr", "params": {"period": 14}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}},
            ]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2}, "take_profit": {"type": "risk_reward", "value": 2}},
        },
        "position_sizing": {"type": "percent_equity", "value": 90},
    }
    result = _exec({"strategyJson": json.dumps(spec)})
    assert result["result"]["status"] == "OK"


def test_walkforward_produces_oos_windows():
    series = {
        "symbol": "TESTUSDT", "interval": "1d",
        "rows": F.bull_market("TESTUSDT", n=300),
    }
    result = _exec(
        {
            "preset": "ema_cross", "trainBars": 120, "testBars": 40, "stepBars": 40,
            "method": "grid", "maxEvaluations": 9, "objective": "sharpe",
        },
        series,
        "quant.walkforward",
    )
    assert result["result"]["status"] == "OK"
    assert result["windows"]
    assert "sharpe" in result["metrics"]
    assert result["result"]["outOfSampleAggregate"]


def test_walkforward_insufficient_history_is_honest():
    result = _exec(
        {"preset": "ema_cross", "trainBars": 500, "testBars": 40},
        None,
        "quant.walkforward",
    )
    assert result["result"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["windows"] == []


def test_empty_series_and_bad_strategy_are_explicit():
    with pytest.raises(ValueError, match="OHLCV series"):
        _exec({}, {"symbol": "X", "interval": "1d", "rows": []})
    with pytest.raises(ValueError, match="strategyJson"):
        _exec({"strategyJson": "{not json"})
    with pytest.raises(ValueError, match="invalid strategy"):
        _exec({"strategyJson": json.dumps({"strategy": {"id": "x"}})})
