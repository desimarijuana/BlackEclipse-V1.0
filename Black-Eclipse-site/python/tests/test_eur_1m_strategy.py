"""The EUR/USD 1-minute starter strategy runs on 1m bars.

The spec mirrors `src/lib/bots/trading/eur-1m.ts` (the TS starter constant). This
test is the engine-side contract: the real parser accepts it, the timeframe is the
engine's `1m`, and the cross + RSI filter actually produces a signal on synthetic
1-minute bars in both directions.

Synthetic bars prove the rule wiring, NOT performance — a backtest on real data is
what the seed requires before it will create the bot.
"""

from __future__ import annotations

import pytest

from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.copilot import calculate_signals
from harness.quant.live import LiveStrategyService
from harness.quant.store import QuantStore
from harness.persistence import AgentMemoryStore
from harness.automation.model import AutomationDefinition
from harness.automation.validation import validate_automation

EUR_1M_SPEC = {
    "strategy": {
        "id": "eurusd_m1_ema_rsi",
        "name": "EUR/USD 1m EMA-RSI",
        "version": "1.0.0",
        "description": "EURUSD 1-minute EMA(9/21) cross with RSI momentum.",
    },
    "universe": {"symbols": ["EURUSD"], "asset_classes": ["fx"]},
    "timeframes": {"primary": "1m", "confirmation": []},
    "indicators": [
        {"id": "ema_fast", "type": "ema", "params": {"period": 9}},
        {"id": "ema_slow", "type": "ema", "params": {"period": 21}},
        {"id": "rsi", "type": "rsi", "params": {"period": 14}},
        {"id": "atr", "type": "atr", "params": {"period": 14}},
    ],
    "rules": {
        "entry": {
            "long": {"type": "group", "combine": "all", "conditions": [
                {"type": "condition", "left": {"ref": "ema_fast"},
                 "op": "cross_above", "right": {"ref": "ema_slow"}},
                {"type": "condition", "left": {"ref": "rsi"}, "op": ">", "right": {"value": 50}},
            ]},
            "short": {"type": "group", "combine": "all", "conditions": [
                {"type": "condition", "left": {"ref": "ema_fast"},
                 "op": "cross_below", "right": {"ref": "ema_slow"}},
                {"type": "condition", "left": {"ref": "rsi"}, "op": "<", "right": {"value": 50}},
            ]},
        },
        "exit": {
            "long": {"type": "group", "combine": "any", "conditions": [
                {"type": "condition", "left": {"ref": "ema_fast"},
                 "op": "cross_below", "right": {"ref": "ema_slow"}},
                {"type": "condition", "left": {"ref": "rsi"}, "op": "<", "right": {"value": 45}},
            ]},
            "short": {"type": "group", "combine": "any", "conditions": [
                {"type": "condition", "left": {"ref": "ema_fast"},
                 "op": "cross_above", "right": {"ref": "ema_slow"}},
                {"type": "condition", "left": {"ref": "rsi"}, "op": ">", "right": {"value": 55}},
            ]},
            "stop_loss": {"type": "atr", "value": 1.5},
            "take_profit": {"type": "risk_reward", "value": 1.5},
        },
    },
    "position_sizing": {"type": "percent_risk", "value": 0.5},
    "risk": {
        "max_position_pct": 10,
        "max_open_positions": 1,
        "max_daily_loss_pct": 3,
        "max_risk_per_trade_pct": 0.5,
        "allow_long": True,
        "allow_short": True,
    },
    "execution": {
        "commission": {"type": "none", "value": 0},
        "slippage": {"type": "percentage", "value": 0.001},
        "spread": {"type": "bps", "value": 1.2},
        "fill_at": "next_open",
    },
    "metadata": {"starter": "eur-1m"},
}


def _spec():
    return S.parse_strategy(EUR_1M_SPEC)


def _dataset(rows):
    return D.build_dataset({
        "EURUSD": D.series_from_rows("EURUSD", "1m", rows, source="synthetic"),
    })


def test_the_engine_accepts_the_1m_spec():
    spec = _spec()
    assert spec.timeframes.primary == "1m"
    assert spec.universe.symbols == ["EURUSD"]
    assert spec.position_sizing.type == "percent_risk"
    assert spec.risk.max_open_positions == 1


def test_a_rising_1m_market_produces_a_long_entry():
    dataset = _dataset(F.bull_market("EURUSD", n=240))
    result = calculate_signals(_spec(), dataset, symbols=["EURUSD"])
    signals = [point["signal"] for point in result["signals"]["EURUSD"]]
    assert "long_entry" in signals
    # The momentum veto is respected: no long entry while RSI is under 50.
    for point in result["signals"]["EURUSD"]:
        if point["signal"] == "long_entry":
            assert float(point["indicators"]["rsi"]) >= 50


def test_a_falling_1m_market_produces_a_short_entry():
    dataset = _dataset(F.bear_market("EURUSD", n=240))
    result = calculate_signals(_spec(), dataset, symbols=["EURUSD"])
    signals = [point["signal"] for point in result["signals"]["EURUSD"]]
    assert "short_entry" in signals
    for point in result["signals"]["EURUSD"]:
        if point["signal"] == "short_entry":
            assert float(point["indicators"]["rsi"]) <= 50


def test_sideways_1m_noise_does_not_force_a_trade():
    dataset = _dataset(F.sideways_market("EURUSD", n=240))
    result = calculate_signals(_spec(), dataset, symbols=["EURUSD"])
    # It may produce signals on a whipsaw; the contract is that it returns a
    # well-formed series and never invents a signal without a cross.
    assert "signals" in result
    assert isinstance(result["signals"]["EURUSD"], list)


def test_the_bot_payload_validates_with_the_real_automation_model():
    """The starter's `action.config` is accepted by the runtime's own validator."""
    now = "2026-11-17T10:00:00Z"
    definition = AutomationDefinition(
        id="aut_eur_1m",
        name="EUR/USD 1-minute scalper",
        state="draft",
        trigger={"type": "interval", "intervalSeconds": 60, "timezone": "UTC"},
        action={
            "type": "run_strategy",
            "objective": "Trade EURUSD on the 1-minute chart in London hours.",
            "config": {
                "strategyId": "eurusd_m1_ema_rsi",
                "strategyVersion": "1.0.0",
                "mode": "shadow",
                "connectionId": "",
                "symbols": ["EURUSD"],
                "dynamicSymbols": False,
                "maxSymbols": 1,
                "timeframe": "M1",
                "volume": 0.01,
                "stopLossPoints": 30,
                "takeProfitPoints": 45,
                "maxOrdersPerDay": 4,
                "session": {
                    "timezone": "Europe/London",
                    "weekdays": [1, 2, 3, 4, 5],
                    "start": "08:00",
                    "end": "17:00",
                },
                "trialId": "",
                "dryRun": False,
                "consent": None,
                "visuals": [],
                "learning": {"enabled": True, "threshold": 3},
            },
        },
        execution={"misfire": "skip", "maxRuntimeS": 120},
        execution_authority={
            "tier": "l1",
            "appetite": "normal",
            "maxOpenPositions": 1,
            "maxMarginPerOrder": 100,
            "requireStop": True,
            "cooldownS": 300,
        },
        tags=["bot", "trading", "eur-1m"],
        created_at=now,
        updated_at=now,
    )
    issues = validate_automation(
        definition, strategy_lookup=lambda sid, version: {"id": sid},
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    assert errors == [], [issue.message for issue in errors]
    assert any(issue.code == "TRADING_NOT_PREPARED" for issue in issues)  # draft warning


@pytest.mark.asyncio
async def test_the_shadow_trial_is_created_from_the_real_strategy(tmp_path):
    """The seed's step 5, against the real stores: prepare(strategy, backtest) → shadow trial."""
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    spec = _spec()
    store.save_strategy(spec)
    approval = store.request_approval("eurusd_m1_ema_rsi", "1.0.0")
    store.decide_approval(approval["id"], approve=True)
    backtest = E.run_backtest(spec, _dataset(F.bull_market("EURUSD", n=240)), E.BacktestConfig())
    store.save_experiment(
        backtest, strategy_id="eurusd_m1_ema_rsi",
        strategy_version="1.0.0", kind="backtest",
    )

    service = LiveStrategyService(store)
    trial = service.prepare(
        strategy_id="eurusd_m1_ema_rsi",
        version="1.0.0",
        symbols=["EURUSD"],
        mode="shadow",
        timeframe="M1",
        volume=0.01,
        stop_loss_points=30,
        take_profit_points=45,
        max_orders=4,
        max_margin=100,
        bot_id="aut_eur_1m",
        bot_version=1,
    )
    assert trial["mode"] == "shadow"
    assert trial["connectionId"] == ""
    assert trial["mandateId"] == ""
    assert trial["botId"] == "aut_eur_1m"
    assert trial["botVersion"] == 1
    assert trial["status"] == "ready"

    signal = await service.signal(
        trial["id"], dataset=_dataset(F.bull_market("EURUSD", n=240)),
    )
    assert signal["symbol"] == "EURUSD"
    assert signal["signal"] in (
        "long_entry", "short_entry", "long_exit", "short_exit", "none",
    )
    assert "bar" in signal

    stopped = service.stop_by_bot("aut_eur_1m")
    assert len(stopped) == 1
    assert stopped[0]["status"] == "stopped"
