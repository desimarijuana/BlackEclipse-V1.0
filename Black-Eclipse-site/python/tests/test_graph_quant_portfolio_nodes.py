"""Portfolio backtest node: several strategies on one book, one engine.

The point of these tests is the adapter, not the engine: the series map is
adapted once, the preset route covers every symbol, and a portfolio that cannot
be executed (missing symbol, double-claimed symbol, bad spec) fails by name.
"""

from __future__ import annotations

import json

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.quant import fixtures as F

REGISTRY = build_default_registry()


def _run(inputs: dict, config: dict | None = None) -> dict:
    definition = REGISTRY.get("quant.portfolio_backtest")
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="quant.portfolio_backtest",
        run_id="run",
        mode=ExecutionMode.BACKTEST,
        inputs=inputs,
        config=config or {},
    ))


def _map(*symbols: str, n: int = 240) -> dict:
    return {symbol: {"symbol": symbol, "interval": "1d", "rows": F.bull_market(symbol, n=n)}
            for symbol in symbols}


def test_preset_runs_one_strategy_per_symbol_and_is_deterministic():
    config = {"preset": "ema_cross", "fast": 5, "slow": 20, "includeSeries": True}
    first = _run({"series": _map("AAA", "BBB")}, config)
    second = _run({"series": _map("AAA", "BBB")}, config)
    assert first["result"]["status"] == "OK"
    assert isinstance(first["metrics"], dict)
    assert isinstance(first["trades"], list)
    assert first["result"]["equityCurve"]
    assert first["metrics"] == second["metrics"]
    assert [t.get("netPnl") for t in first["trades"]] == [t.get("netPnl") for t in second["trades"]]


def test_explicit_strategies_json_is_supported():
    spec = {
        "strategy": {"id": "aaa_cross", "name": "AAA cross", "version": "1.0.0"},
        "universe": {"symbols": ["AAA"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}},
            ]}},
            "exit": {"stop_loss": {"type": "percent", "value": 5}},
        },
        "position_sizing": {"type": "percent_equity", "value": 50},
    }
    result = _run(
        {"series": _map("AAA")},
        {"strategiesJson": json.dumps([spec])},
    )
    assert result["result"]["status"] == "OK"


def test_a_strategy_for_an_absent_symbol_is_an_explicit_failure():
    spec = {
        "strategy": {"id": "bbb_cross", "name": "BBB cross", "version": "1.0.0"},
        "universe": {"symbols": ["BBB"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
        ],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}},
        ]}}},
        "position_sizing": {"type": "percent_equity", "value": 50},
    }
    with pytest.raises(ValueError, match="not in the series map"):
        _run({"series": _map("AAA")}, {"strategiesJson": json.dumps([spec])})


def test_two_strategies_claiming_one_symbol_is_rejected_by_the_engine():
    def spec(strategy_id: str) -> dict:
        return {
            "strategy": {"id": strategy_id, "name": strategy_id, "version": "1.0.0"},
            "universe": {"symbols": ["AAA"]},
            "indicators": [
                {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
            ],
            "rules": {"entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}},
            ]}}},
            "position_sizing": {"type": "percent_equity", "value": 50},
        }

    with pytest.raises(ValueError, match="portfolio backtest failed"):
        _run(
            {"series": _map("AAA")},
            {"strategiesJson": json.dumps([spec("first"), spec("second")])},
        )


def test_a_single_payload_is_rejected_instead_of_becoming_a_symbol():
    payload = {"symbol": "AAA", "rows": F.bull_market("AAA", n=60)}
    with pytest.raises(ValueError, match="expects a map of"):
        _run({"series": payload})


def test_an_empty_or_invalid_strategies_json_is_explicit():
    with pytest.raises(ValueError, match="non-empty JSON array"):
        _run({"series": _map("ACE")}, {"strategiesJson": "[]"})
    with pytest.raises(ValueError, match="strategiesJson"):
        _run({"series": _map("ACE")}, {"strategiesJson": "{not json"})
