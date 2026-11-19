"""Backtests on an operator-declared dataset (Settings -> Data Sources).

The contract these tests pin down:

* naming a `dataSource` reads ONLY that dataset - the market gateway is never
  called, and there is no fallback to built-in providers;
* a failure is honest and typed (`CUSTOM_SOURCE_UNAVAILABLE` / `MISSING_DATA`);
* the requested window is enforced locally, so a source that ignores `from`/`to`
  cannot widen a backtest;
* a run built on user data says so in its metadata and warnings.
"""

from __future__ import annotations

import pytest

from harness.quant import datasets as DS
from harness.quant import fixtures as F
from harness.quant import tools as QT
from harness.quant.custom_source import normalize_data_source
from harness.quant.errors import (
    CustomSourceUnavailable,
    InvalidDataSource,
    MissingData,
)


class _ExplodingGateway:
    """Any market-provider call is a failure of the custom-source contract."""

    history_cache = None

    async def get_historical_prices(self, *a, **kw):  # noqa: D401 - test double
        raise AssertionError("the built-in market gateway must not be used")


class _Bridge:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, capability, params):
        self.calls.append((capability, dict(params)))
        return self.result


def _records(n=40, start_day=1, close_from=100.0):
    rows = F.bull_market("TESTUSDT", n=n)
    records = []
    for i, row in enumerate(rows):
        close = float(row["close"]) + close_from
        records.append({
            "recordKey": f"r{i}",
            # LSE-shaped columns: `time`, lowercase OHLCV.
            "values": {
                "time": f"2026-01-{start_day:02d}T{i // 24:02d}:{i % 24:02d}:00",
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000 + i,
            },
        })
    return records


def _ok(records):
    return {"status": "OK", "records": records, "count": len(records)}


def _spec():
    return {
        "strategy": {"id": "ema_cross", "name": "EMA Cross", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
            {"id": "atr", "type": "atr", "params": {"period": 14}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above",
                 "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2}},
        },
        "position_sizing": {"type": "percent_equity", "value": 90},
    }


def _spec_dict():
    from harness.quant import parse_strategy

    return parse_strategy(_spec()).to_dict()


def _ctx(bridge, store=None):
    class Ctx:
        pass

    ctx = Ctx()
    ctx.data_bridge = bridge
    ctx.market_gateway = _ExplodingGateway()
    ctx.quant_store = store
    return ctx


# ── normalize ────────────────────────────────────────────────────────────────

def test_normalize_accepts_the_documented_shapes():
    assert normalize_data_source(None) is None
    assert normalize_data_source("   ") is None
    assert normalize_data_source("my-lse") == {"dataset": "my-lse", "values": {}}
    assert normalize_data_source("custom:my-lse") == {"dataset": "my-lse", "values": {}}
    assert normalize_data_source(
        {"dataset": "my-lse", "values": {"market": "us_stocks", "limit": 10}}
    ) == {"dataset": "my-lse", "values": {"market": "us_stocks", "limit": 10}}


def test_a_malformed_source_is_refused_not_ignored():
    with pytest.raises(InvalidDataSource):
        normalize_data_source(["my-lse"])
    with pytest.raises(InvalidDataSource):
        normalize_data_source({"values": {}})
    with pytest.raises(InvalidDataSource):
        normalize_data_source({"dataset": "x", "values": {"nested": {"a": 1}}})


@pytest.mark.asyncio
async def test_no_bridge_refuses_instead_of_using_the_gateway():
    with pytest.raises(CustomSourceUnavailable) as err:
        await DS.resolve_dataset(
            _ExplodingGateway(), ["TESTUSDT"], primary="1d",
            data_source={"dataset": "my-lse"}, bridge=None,
        )
    assert "no bridge" in str(err.value).lower() or "bridge" in str(err.value).lower()


@pytest.mark.asyncio
async def test_a_strategy_may_pin_its_own_source():
    from harness.quant import parse_strategy

    spec = parse_strategy({
        **_spec(),
        "metadata": {"dataSource": "custom:my-lse"},
    })
    bridge = _Bridge(_ok(_records()))
    dataset = await DS.dataset_from_strategy(
        _ExplodingGateway(), spec, bridge=bridge
    )
    assert dataset.series["TESTUSDT"].source == "custom:my-lse"
    assert bridge.calls and bridge.calls[0][1]["dataset"] == "my-lse"


# ── resolve ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_declared_dataset_is_the_only_source():
    bridge = _Bridge(_ok(_records()))
    dataset = await DS.resolve_dataset(
        _ExplodingGateway(), ["TESTUSDT"], primary="1d",
        data_source={"dataset": "my-lse"}, bridge=bridge,
    )
    series = dataset.series["TESTUSDT"]
    assert series.source == "custom:my-lse"
    assert series.length == 40
    capability, params = bridge.calls[0]
    assert capability == "custom_dataset_records"
    assert params["dataset"] == "my-lse"
    assert params["values"]["symbol"] == "TESTUSDT"
    assert params["values"]["interval"] == "1d"


@pytest.mark.asyncio
async def test_source_failure_never_falls_back_to_providers():
    bridge = _Bridge({"status": "UNAVAILABLE", "error": "no connected dataset named \"my-lse\""})
    with pytest.raises(CustomSourceUnavailable) as err:
        await DS.resolve_dataset(
            _ExplodingGateway(), ["TESTUSDT"], primary="1d",
            data_source={"dataset": "my-lse"}, bridge=bridge,
        )
    assert err.value.code == "CUSTOM_SOURCE_UNAVAILABLE"
    assert "no connected dataset" in str(err.value)


@pytest.mark.asyncio
async def test_unusable_records_are_missing_data_with_a_fix():
    records = [{"values": {"time": "2026-01-01", "volume": 5}} for _ in range(5)]
    with pytest.raises(MissingData) as err:
        await DS.resolve_dataset(
            _ExplodingGateway(), ["TESTUSDT"], primary="1d",
            data_source={"dataset": "my-lse"}, bridge=_Bridge(_ok(records)),
        )
    assert "close" in str(err.value)


@pytest.mark.asyncio
async def test_window_is_enforced_locally():
    records = _records(n=60)
    bridge = _Bridge(_ok(records))
    dataset = await DS.resolve_dataset(
        _ExplodingGateway(), ["TESTUSDT"], primary="1d",
        start="2026-01-01", end="2026-01-02",
        data_source={"dataset": "my-lse"}, bridge=bridge,
    )
    stamps = dataset.series["TESTUSDT"].timestamps
    assert stamps, "expected bars inside the window"
    assert all(ts.startswith(("2026-01-01", "2026-01-02")) for ts in stamps)


# ── the tool surface ─────────────────────────────────────────────────────────

class _Store:
    def __init__(self, spec):
        self._spec = spec

    def get_strategy(self, strategy_id, version=None):
        return {"spec": self._spec, "id": strategy_id, "version": "1.0.0"}

    def save_experiment(self, *a, **kw):  # pragma: no cover - save=False
        raise AssertionError("save=False must not persist")


@pytest.mark.asyncio
async def test_run_backtest_tool_uses_the_declared_dataset_and_stamps_it():
    from harness.quant.tools import run_backtest_tool

    bridge = _Bridge(_ok(_records(n=120)))
    ctx = _ctx(bridge, _Store(_spec_dict()))
    text, data = await run_backtest_tool(
        {"strategyId": "ema_cross", "dataSource": {"dataset": "my-lse"},
         "initialCapital": 100_000, "save": False},
        ctx,
    )

    assert data["status"] == "OK", text
    assert data["observability"]["barsProcessed"] == 120
    assert data["metadata"]["dataSource"]["dataset"] == "my-lse"
    assert data["metadata"]["dataSource"]["verified"] is False
    assert any(w["code"] == "CUSTOM_DATA_SOURCE" for w in data["warnings"])


@pytest.mark.asyncio
async def test_tool_refuses_an_invalid_source_instead_of_running_on_defaults():
    from harness.quant.tools import run_backtest_tool

    ctx = _ctx(_Bridge(_ok(_records())), _Store(_spec_dict()))
    text, data = await run_backtest_tool(
        {"strategyId": "ema_cross", "dataSource": {"values": {}}, "save": False},
        ctx,
    )
    assert data["status"] == "ERROR"
    assert "INVALID_DATA_SOURCE" in text
