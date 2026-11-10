"""Governed live-strategy trials: gates, signal, one order, results, stop."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.live import LiveStrategyService
from harness.quant.store import QuantStore


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "live_test", "name": "Live test", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 10},
    })


def _dataset():
    rows = F.bull_market("TESTUSDT", n=120)
    return D.build_dataset({
        "TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")
    })


class FakeBroker:
    def __init__(self):
        self.submitted = []
        self.mandates = {}
        self.positions_data = []
        self.revoked = []

    def get_connection(self, connection_id):
        return {
            "id": connection_id, "mode": "live", "label": "Test Live",
            "armedUntil": (datetime.now(timezone.utc) + timedelta(hours=1))
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def create_mandate(self, connection_id, payload):
        mandate = {"id": "man_test", **payload}
        self.mandates[mandate["id"]] = mandate
        return mandate

    def submit_order(self, connection_id, payload, **kwargs):
        self.submitted.append({**payload, **kwargs})
        return {"status": "filled", "sent": True, "filled": True,
                "connectionId": connection_id}

    def quote(self, connection_id, symbol):
        return {"available": True, "data": {
            "symbol": symbol, "bid": 1.115, "ask": 1.1151,
            "spreadPoints": 1, "contractSize": 100000, "margin": 111.5,
            "volumeMin": 0.01, "volumeStep": 0.01,
        }}

    def positions(self, connection_id):
        return {"available": True, "data": list(self.positions_data)}

    def account(self, connection_id):
        return {"available": True, "data": {"balance": 100000, "equity": 100000}}

    def orders(self, connection_id):
        return {"available": True, "data": []}

    def close_position(self, connection_id, ticket, **kwargs):
        self.positions_data = [p for p in self.positions_data if p["ticket"] != ticket]
        return {"closed": True, "ticket": ticket}

    def revoke_mandate(self, mandate_id):
        self.revoked.append(mandate_id)
        return {"id": mandate_id, "status": "revoked"}


@pytest.fixture()
def env(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    store.save_strategy(_spec())
    approval = store.request_approval("live_test", "1.0.0")
    store.decide_approval(approval["id"], approve=True)
    result = E.run_backtest(_spec(), _dataset(), E.BacktestConfig())
    store.save_experiment(result, strategy_id="live_test",
                          strategy_version="1.0.0", kind="backtest")
    broker = FakeBroker()
    return LiveStrategyService(store, broker=broker), broker, store


def _prepare(service, **overrides):
    payload = {
        "strategy_id": "live_test", "version": "1.0.0",
        "connection_id": "conn", "symbols": ["TESTUSDT"],
        "timeframe": "D1", "volume": 0.1, "max_orders": 2,
        "max_margin": 500.0, "ttl_seconds": 3600,
        "confirmation": "LIVE TRIAL live_test 1.0.0",
    }
    payload.update(overrides)
    return service.prepare(**payload)


def test_prepare_requires_approval(env):
    service, _, store = env
    store._db.execute("UPDATE QuantStrategyApproval SET status='requested'")
    store._db.commit()
    with pytest.raises(Exception) as exc:
        _prepare(service)
    assert getattr(exc.value, "code", "") == "APPROVAL_REQUIRED"


def test_prepare_requires_typed_phrase(env):
    service, _, _ = env
    with pytest.raises(Exception) as exc:
        _prepare(service, confirmation="yes")
    assert getattr(exc.value, "code", "") == "CONFIRMATION_REQUIRED"


def test_prepare_requires_armed_live_connection(env):
    service, broker, _ = env
    broker.get_connection = lambda connection_id: {
        "id": connection_id, "mode": "live", "label": "Test Live",
        "armedUntil": "2020-01-01T00:00:00Z",
    }
    with pytest.raises(Exception) as exc:
        _prepare(service)
    assert getattr(exc.value, "code", "") == "LIVE_NOT_ARMED"


def test_signal_run_results_and_stop(env):
    service, broker, store = env
    trial = _prepare(service)
    assert trial["status"] == "ready"
    assert trial["mandateId"] == "man_test"
    assert trial["pin"] == "strategy:live_test:1.0.0"
    assert trial["warnings"]

    dataset = _dataset()
    signal = asyncio.run(service.signal(trial["id"], dataset=dataset))
    assert signal["action"] in ("buy", "close", "none")

    result = asyncio.run(service.run_once(trial["id"], dataset=dataset))
    assert result["signal"]["symbol"] == "TESTUSDT"
    assert broker.submitted, result
    assert broker.submitted[0]["side"] == "buy"
    assert broker.submitted[0]["workflow_id"] == "strategy:live_test:1.0.0"
    assert broker.submitted[0]["stopLoss"] is not None
    assert broker.submitted[0]["takeProfit"] is not None

    broker.positions_data = [{"ticket": 11, "symbol": "TESTUSDT", "profit": 12.5,
                              "swap": -1.0, "commission": -0.5}]
    results = service.results(trial["id"])
    assert results["openPositions"] == 1
    assert results["openPnl"] == pytest.approx(11.0)

    stopped = service.stop(trial["id"])
    assert stopped["status"] == "stopped"
    assert broker.revoked == ["man_test"]


def test_second_run_does_not_stack_a_position(env):
    service, broker, _ = env
    trial = _prepare(service)
    dataset = _dataset()
    asyncio.run(service.run_once(trial["id"], dataset=dataset))
    broker.positions_data = [{"ticket": 1, "symbol": "TESTUSDT"}]
    result = asyncio.run(service.run_once(trial["id"], dataset=dataset))
    assert "already exist" in result["message"]
