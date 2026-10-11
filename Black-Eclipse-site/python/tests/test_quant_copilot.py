"""AI Strategy Copilot support: signals, research plan, report, config helpers."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.copilot import (
    build_report,
    build_research_plan,
    calculate_signals,
    describe_rules,
    with_position_sizing,
    with_stops_and_targets,
)
from harness.quant.data import build_dataset, series_from_rows
from harness.quant.engine import BacktestConfig, run_backtest
from harness.quant.store import QuantStore
from harness.quant.tools import QUANT_TOOLS, register_quant_tools
from harness.tools import ToolRegistry


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "ema_x", "name": "EMA X", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_f", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_s", "type": "ema", "params": {"period": 20}},
                       {"id": "atr", "type": "atr", "params": {"period": 14}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_above", "right": {"ref": "ema_s"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2}}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    })


def _dataset(n=260):
    rows = F.bull_market("TESTUSDT", n=n)
    return build_dataset({"TESTUSDT": series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


def test_calculate_signals_no_orders():
    result = calculate_signals(_spec(), _dataset())
    assert result["strategyId"] == "ema_x"
    assert result["signalCounts"].get("long_entry", 0) > 0
    # Signals carry reasons and (bounded) indicator snapshots; no portfolio is touched.
    points = result["signals"]["TESTUSDT"]
    assert all(p["signal"].startswith("long") for p in points)
    assert "ema_f" in points[0]["indicators"]


def test_calculate_signals_missing_symbol_reports_gap():
    result = calculate_signals(_spec(), _dataset(), symbols=["NOPE"])
    assert any(w["code"] == "MISSING_DATA" for w in result["warnings"])


def test_research_plan_is_explicit_and_grounded():
    plan = build_research_plan(_spec(), start="2023-01-01", end="2024-01-01")
    assert plan["strategyId"] == "ema_x"
    assert plan["parameterSearch"]["space"]  # inferred from indicator params
    assert plan["periods"]["holdout"]
    assert plan["potentialBiases"]
    assert plan["acceptanceCriteria"]
    assert plan["notFinancialAdvice"] is True


def test_report_is_grounded_in_experiment(tmp_path):
    store = QuantStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "a"))
    spec = _spec()
    store.save_strategy(spec)
    res = run_backtest(spec, _dataset(), BacktestConfig(initial_capital=100_000))
    exp_id = store.save_experiment(res, strategy_id="ema_x", strategy_version="1.0.0",
                                   kind="backtest")
    report = build_report(store.get_experiment(exp_id), store.read_artifact(exp_id))
    assert exp_id in report
    assert "## Performance metrics" in report
    assert "not investment advice" in report


def test_describe_rules_is_plain_language():
    rules = describe_rules(_spec())
    assert "ema_f" in rules["entry"]["long"]
    assert rules["exit"]["stopLoss"]["type"] == "atr"


def test_config_helpers_validate():
    spec, issues = with_position_sizing(_spec(), {"type": "percent_equity", "value": 150})
    assert spec.position_sizing.value == 150
    assert any(i["code"] == "SIZING_OVER_100" for i in issues)  # warning, not silent

    spec2, issues2 = with_stops_and_targets(_spec(), {"take_profit": {"type": "risk_reward", "value": 3}})
    assert spec2.rules.exit.take_profit.value == 3
    assert not [i for i in issues2 if i["severity"] == "error"]


def test_copilot_tools_registered():
    registry = ToolRegistry()
    register_quant_tools(registry)
    assert set(registry.names()) == set(QUANT_TOOLS)
    for name in ("calculate_signals", "create_research_plan", "generate_strategy_report",
                 "analyze_trade_log", "compare_strategies", "run_parameter_sweep"):
        assert name in QUANT_TOOLS
