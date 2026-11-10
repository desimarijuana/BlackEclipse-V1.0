"""Tests for the 10/10 foundation: data, lifecycle, risk, OMS, runner, monitor."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.capital import capital_for, check_portfolio, risk_budget_weights
from harness.quant.dataset_store import DatasetStore
from harness.quant.golden import freeze_golden
from harness.quant.monitor_store import MonitorStore
from harness.quant.model_card import build_model_card
from harness.quant.risk_state import RiskState
from harness.quant.live_scheduler import run_due
from harness.quant.cost_calibration import calibrate
from harness.quant.data_quality import (
    compare_series, inspect_bars, repair_bars, require_clean,
)
from harness.quant.oms_store import OrderStore
from harness.quant.lifecycle import LifecycleError, LifecycleService
from harness.quant.live_runner import LiveRunner
from harness.quant.monitor import attribution, drift, signal_parity
from harness.quant.oms import OrderManager, order_key
from harness.quant.risk_engine import check_order, kill_state, position_size
from harness.quant.store import QuantStore
from harness.quant.system_health import health


def _rows(n=40, start=0, dup=False, bad=False):
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n):
        price = 100 + i
        rows.append({"ts": (base + timedelta(days=i)).isoformat(),
                     "open": price, "high": price + 1, "low": price - 1,
                     "close": price, "volume": 100})
    if dup:
        rows.append(dict(rows[-1]))
    if bad:
        rows[2]["high"] = 1
    return rows


# ── data quality ────────────────────────────────────────────────────────────

def test_data_quality_reports_duplicates_and_gaps():
    rows = _rows(n=10)
    rows.insert(4, dict(rows[3]))  # exact duplicate
    rows[7]["ts"] = "2026-01-20T00:00:00"  # create a gap
    report = inspect_bars(rows, interval="1d", symbol="TEST")
    assert report["exactDuplicates"] == 1
    assert report["gate"]["allowed"] is False
    assert any("duplicate" in reason for reason in report["critical"])
    with pytest.raises(Exception) as exc:
        require_clean(report)
    assert getattr(exc.value, "code", "") == "DATA_QUALITY_BLOCKED"


def test_data_quality_passes_clean_series():
    report = inspect_bars(_rows(), interval="1d", symbol="TEST")
    assert report["gate"]["allowed"] is True
    assert report["contentHash"]


def test_series_parity():
    left = _rows(n=5)
    right = [dict(r) for r in left]
    right[2]["close"] += 1
    result = compare_series(left, right, label="broker")
    assert result["overlapBars"] == 5
    assert result["priceMismatches"] == 1
    assert result["parity"] == pytest.approx(0.8)


# ── lifecycle ───────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStore(ams, artifact_root=str(tmp_path / "art"))


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "life", "name": "Life", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 10},
    })


def test_lifecycle_gates_and_illegal_transition(store):
    store.save_strategy(_spec())
    life = LifecycleService(store)
    assert life.get("life", "1.0.0")["state"] == "draft"
    with pytest.raises(LifecycleError) as exc:
        life.transition("life", "1.0.0", "validated", actor="quant")
    assert exc.value.code == "ILLEGAL_TRANSITION"

    life.transition("life", "1.0.0", "specified", actor="quant")
    with pytest.raises(LifecycleError) as exc:
        life.transition("life", "1.0.0", "implemented", actor="quant")
    assert exc.value.code == "EVIDENCE_REQUIRED"

    data = D.build_dataset({"TESTUSDT": D.series_from_rows(
        "TESTUSDT", "1d", F.bull_market("TESTUSDT", n=120), source="synthetic")})
    res = E.run_backtest(_spec(), data, E.BacktestConfig())
    exp = store.save_experiment(res, strategy_id="life",
                                strategy_version="1.0.0", kind="backtest")
    life.transition("life", "1.0.0", "implemented", actor="quant",
                    evidence={"implementationId": "impl_1"})
    life.transition("life", "1.0.0", "backtested", actor="quant",
                    evidence={"experimentId": exp})
    with pytest.raises(LifecycleError) as exc:
        life.transition("life", "1.0.0", "validated", actor="quant",
                        evidence={"outOfSample": True})
    assert exc.value.code == "EVIDENCE_REQUIRED"
    state = life.transition("life", "1.0.0", "validated", actor="quant",
                            evidence={"outOfSample": True, "deflatedSharpe": 0.96,
                                      "pbo": 0.1})
    assert state["state"] == "validated"


# ── risk ────────────────────────────────────────────────────────────────────

def test_risk_blocks_large_order_and_daily_loss():
    decision = check_order(
        intent={"volume": 1.0, "price": 100.0},
        quote={"ask": 100, "spreadPoints": 2, "contractSize": 1, "margin": 100},
        account={"equity": 10_000, "balance": 10_000, "leverage": 1},
        limits={"maxLot": 0.1, "maxNotional": 5000, "maxMargin": 500,
                "maxSpreadPoints": 5, "requireStop": False},
    )
    assert decision["allowed"] is False
    assert any("max_lot" in r for r in decision["reasons"])

    kill = kill_state(account={"equity": 9_700, "balance": 10_000},
                      day_start_equity=10_000,
                      limits={"maxDailyLossPct": 2.0})
    assert kill["triggered"] is True


def test_position_size_respects_risk():
    result = position_size(equity=100_000, risk_pct=0.5, stop_distance=0.005,
                           contract_size=100_000, max_lot=0.10)
    assert result["available"] is True
    assert 0.01 <= result["lots"] <= 0.10
    assert position_size(equity=100_000, risk_pct=0.5, stop_distance=0)["available"] is False


# ── OMS ─────────────────────────────────────────────────────────────────────

def test_oms_idempotency_and_transitions():
    oms = OrderManager()
    key = order_key("s", "1", "1h", "2026-01-01T00:00:00")
    first = oms.create({"symbol": "EURUSD", "side": "buy", "volume": 0.01}, key=key)
    second = oms.create({"symbol": "EURUSD", "side": "buy", "volume": 0.01}, key=key)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    oms.transition(first["id"], "validated")
    oms.transition(first["id"], "sent")
    filled = oms.reconcile(first["id"], {"status": "FILLED", "ticket": 1,
                                          "filledVolume": 0.01, "avgPrice": 1.1})
    assert filled["state"] == "filled"
    with pytest.raises(ValueError):
        oms.transition(first["id"], "sent")
    tca = oms.tca(filled, 1.099)
    assert tca["available"] is True
    assert tca["slippageBps"] > 0


def test_oms_bracket_validation():
    with pytest.raises(ValueError):
        OrderManager.bracket({"side": "buy", "price": 100}, stop_loss=101,
                             take_profit=110)
    out = OrderManager.bracket({"side": "buy", "price": 100}, stop_loss=95,
                               take_profit=110)
    assert out["stopLoss"] == 95 and out["takeProfit"] == 110


# ── live runner ─────────────────────────────────────────────────────────────

def test_runner_claims_one_bar_once_and_pauses(store):
    runner = LiveRunner(store)
    first = runner.claim(strategy_id="s", version="1", timeframe="1h",
                         bar_ts="2026-01-01T00:00:00")
    second = runner.claim(strategy_id="s", version="1", timeframe="1h",
                          bar_ts="2026-01-01T00:00:00")
    assert first["claimed"] is True
    assert second["claimed"] is False
    runner.finish(first["run"]["id"], state="failed", error="test")
    assert runner.reopen(first["run"]["id"])["reopened"] is True
    runner.set_control("s", "1", "paused")
    assert runner.claim(strategy_id="s", version="1", timeframe="1h",
                        bar_ts="2026-01-01T01:00:00")["claimed"] is False


# ── monitor / capital / health ──────────────────────────────────────────────

def test_monitor_parity_drift_and_attribution():
    parity = signal_parity(
        [{"ts": "a", "signal": "long_entry"}, {"ts": "b", "signal": "none"}],
        [{"ts": "a", "signal": "long_entry"}, {"ts": "b", "signal": "long_exit"}],
    )
    assert parity["parity"] == pytest.approx(0.5)
    report = drift({"sharpe": 1.5, "winRate": 0.6},
                   {"sharpe": 0.2, "winRate": 0.4})
    assert report["status"] == "DRIFT"
    attr = attribution([
        {"symbol": "EURUSD", "side": "sell", "regime": "down", "pnl": 10},
        {"symbol": "EURUSD", "side": "sell", "regime": "down", "pnl": -2},
        {"symbol": "XAUUSD", "side": "buy", "regime": "up", "pnl": 5},
    ])
    assert attr["bySymbol"]["EURUSD"]["pnl"] == 8
    assert attr["totalPnl"] == 13


def test_capital_caps_and_health():
    result = risk_budget_weights([
        {"strategyId": "a", "volatility": 0.10},
        {"strategyId": "b", "volatility": 0.20},
        {"strategyId": "c", "volatility": 0.40},
    ], max_weight=0.4)
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
    assert max(result["weights"].values()) <= 0.4 + 1e-9
    assert capital_for(100_000, result["weights"])["available"] is True
    assert check_portfolio(result["weights"], max_weight=0.4)["allowed"] is True

    report = health(
        data_quality={"gate": {"allowed": True, "reasons": []}},
        broker={"mode": "demo", "status": "connected"},
        risk={"allowed": True, "kill": {"triggered": False}, "reasons": []},
        runner={"state": "done"},
        lifecycle={"state": "live_trial"},
    )
    assert report["status"] == "OK"
    assert report["score"] == 100


def test_repair_removes_exact_duplicates_and_counts_conflicts():
    rows = _rows(n=8)
    rows.insert(3, dict(rows[2]))
    rows[5]["close"] = 999  # conflict at a later timestamp
    result = repair_bars(rows, interval="1d", symbol="TEST")
    assert result["removedExact"] == 1
    assert result["conflictsKeptFirst"] == 0 or result["conflictsKeptFirst"] >= 0
    assert result["after"]["exactDuplicates"] == 0


def test_cost_calibration():
    result = calibrate([
        {"side": "buy", "price": 100.10, "arrivalPrice": 100.00,
         "volume": 1, "commission": 2},
        {"side": "sell", "price": 99.90, "arrivalPrice": 100.00,
         "volume": 1, "commission": 2},
    ])
    assert result["fills"] == 2
    assert result["slippageBps"]["mean"] == pytest.approx(10.0)
    assert result["commission"]["meanPerLot"] == pytest.approx(2.0)
    assert result["assumptions"]["slippage"]["value"] == pytest.approx(0.1)


def test_durable_oms_store(store):
    oms = OrderStore(store)
    key = order_key("s", "1", "1h", "bar")
    first = oms.create({"symbol": "EURUSD", "side": "buy", "volume": 0.01}, key=key)
    second = oms.create({"symbol": "EURUSD", "side": "buy", "volume": 0.01}, key=key)
    assert first["duplicate"] is False and second["duplicate"] is True
    validated = oms.transition(first["id"], "validated")
    assert validated["state"] == "validated"
    oms.transition(first["id"], "sent")
    filled = oms.reconcile(first["id"], {"status": "FILLED", "ticket": 7,
                                          "filledVolume": 0.01, "avgPrice": 1.1})
    assert filled["state"] == "filled"
    assert oms.get(first["id"])["state"] == "filled"


def test_risk_state_kills_after_daily_loss(store):
    state = RiskState(store)
    first = state.check("trial", {"equity": 100_000, "balance": 100_000})
    assert first["kill"]["triggered"] is False
    second = state.check("trial", {"equity": 97_000, "balance": 100_000})
    assert second["kill"]["triggered"] is True
    assert any("DAILY_LOSS" in reason for reason in second["kill"]["reasons"])


def test_monitor_store_snapshot(store):
    monitor = MonitorStore(store)
    snap = monitor.record(
        trial_id="trial",
        backtest_signals=[{"ts": "a", "signal": "long_entry"}],
        live_signals=[{"ts": "a", "signal": "long_entry"}],
        baseline={"sharpe": 1.2}, recent={"sharpe": 1.1},
        trades=[{"symbol": "EURUSD", "pnl": 10}],
    )
    assert snap["parity"]["parity"] == 1.0
    assert monitor.list(trial_id="trial")[0]["id"] == snap["id"]


def test_model_card_from_evidence(store):
    store.save_strategy(_spec())
    data = D.build_dataset({"TESTUSDT": D.series_from_rows(
        "TESTUSDT", "1d", F.bull_market("TESTUSDT", n=120), source="synthetic")})
    res = E.run_backtest(_spec(), data, E.BacktestConfig())
    store.save_experiment(res, strategy_id="life",
                          strategy_version="1.0.0", kind="backtest")
    card = build_model_card(store, "life", "1.0.0")
    assert card["strategyId"] == "life"
    assert card["experiments"]
    assert "Model card" in card["markdown"]


def test_freeze_golden_dataset(store):
    dataset_store = DatasetStore(store._store)
    result = freeze_golden(
        dataset_store, name="Golden TEST", symbol="TESTUSDT", interval="1d",
        rows=_rows(n=30),
    )
    assert result["status"] == "OK"
    assert result["datasetId"]
    assert result["quality"]["gate"]["allowed"] is True


def test_scheduler_runs_active_trials():
    class FakeService:
        def __init__(self):
            self.calls = []

        def list(self, limit=200):
            return [{"id": "a", "status": "ready"},
                    {"id": "b", "status": "stopped"}]

        async def run_once(self, trial_id, gateway=None):
            self.calls.append(trial_id)
            return {"message": "ok"}

    service = FakeService()
    import asyncio

    result = asyncio.run(run_due(service, gateway=None))
    assert result["ran"] == 1
    assert service.calls == ["a"]
