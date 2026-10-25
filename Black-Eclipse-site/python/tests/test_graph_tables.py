"""Tabular transform nodes + gateway-backed quote/history nodes."""

from __future__ import annotations

import pytest

from harness.graph_runtime.finance_nodes import set_market_gateway
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.market.errors import DATA_NOT_AVAILABLE, MarketError

REGISTRY = build_default_registry()


def _exec(node_type: str, inputs: dict, config: dict | None = None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config or {},
    ))


ROWS = [
    {"symbol": "AAPL", "sector": "Tech", "close": 100.0},
    {"symbol": "MSFT", "sector": "Tech", "close": 300.0},
    {"symbol": "JPM", "sector": "Financials", "close": 200.0},
]


def test_select_and_rename():
    result = _exec("transform.select", {"rows": ROWS}, {"fields": "symbol,close", "rename": '{"close":"last"}'})
    assert result["rows"] == [
        {"symbol": "AAPL", "last": 100.0},
        {"symbol": "MSFT", "last": 300.0},
        {"symbol": "JPM", "last": 200.0},
    ]


def test_sort_and_limit():
    result = _exec("transform.sort_limit", {"rows": ROWS}, {"field": "close", "order": "desc", "limit": 2})
    assert [row["symbol"] for row in result["rows"]] == ["MSFT", "JPM"]


def test_aggregate_overall_and_grouped():
    overall = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "avg"})
    assert overall["value"] == pytest.approx(200.0)
    grouped = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "sum", "groupBy": "sector"})
    groups = {row["sector"]: row for row in grouped["groups"]}
    assert groups["Tech"]["value"] == pytest.approx(400.0)
    assert groups["Financials"]["value"] == pytest.approx(200.0)
    assert groups["Tech"]["count"] == 2


def test_deduplicate_and_join():
    dupes = ROWS + [{"symbol": "AAPL", "sector": "Tech", "close": 101.0}]
    deduped = _exec("logic.deduplicate", {"items": dupes}, {"keys": "symbol"})
    assert deduped["dropped"] == 1
    assert len(deduped["items"]) == 3

    right = [{"symbol": "AAPL", "pe": 30.0}, {"symbol": "JPM", "pe": 12.0}]
    joined = _exec("transform.join", {"left": ROWS, "right": right}, {"leftKey": "symbol", "rightKey": "symbol"})
    assert joined["matched"] == 2
    by_symbol = {row["symbol"]: row for row in joined["rows"]}
    assert by_symbol["AAPL"]["pe"] == 30.0
    assert "MSFT" not in by_symbol
    left = _exec("transform.join", {"left": ROWS, "right": right}, {"leftKey": "symbol", "how": "left"})
    assert len(left["rows"]) == 3


def test_a_non_array_is_refused():
    with pytest.raises(ValueError, match="array of objects"):
        _exec("transform.select", {"rows": {"not": "a list"}}, {})


class _Record:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class _FakeGateway:
    async def get_quote(self, symbol, market, *, freshness="realtime"):
        return _Record({
            "price": 123.45, "symbol": symbol,
            "timestamp": "2026-10-25T15:00:00Z",
            "meta": {"provider": "stub", "symbol": symbol, "freshness": freshness,
                     "retrieved_at": "2026-10-25T15:00:01Z", "quality": "ok"},
        })

    async def get_historical_prices(self, symbol, market, **kwargs):
        return _Record({
            "interval": kwargs.get("interval", "1d"),
            "adjusted": kwargs.get("adjusted", True),
            "bars": [
                {"timestamp": "2026-10-24T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
                {"timestamp": "2026-10-25T00:00:00Z", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 20.0},
            ],
            "meta": {"provider": "stub", "symbol": symbol, "retrieved_at": "2026-10-25T15:00:01Z"},
        })


class _BrokenGateway:
    async def get_quote(self, symbol, market, *, freshness="realtime"):
        return MarketError(DATA_NOT_AVAILABLE, "data bridge not configured")


@pytest.fixture()
def gateway():
    set_market_gateway(_FakeGateway())
    try:
        yield
    finally:
        set_market_gateway(None)


def test_quote_uses_the_gateway_and_reports_provenance(gateway):
    result = _exec("finance.quote", {}, {"symbol": "aapl", "freshness": "intraday"})
    assert result["quote"]["price"] == 123.45
    assert result["provenance"]["provider"] == "stub"
    assert result["provenance"]["symbol"] == "AAPL"
    assert result["provenance"]["freshness"] == "intraday"


def test_history_returns_ohlcv_rows(gateway):
    result = _exec("finance.history", {}, {"symbol": "AAPL", "interval": "1d", "limit": 1})
    assert result["series"]["rows"][-1]["close"] == 2.0
    assert len(result["series"]["rows"]) == 1
    assert result["provenance"]["rows"] == 1
    assert result["provenance"]["provider"] == "stub"


def test_quote_failure_is_explicit():
    set_market_gateway(_BrokenGateway())
    try:
        with pytest.raises(ValueError, match="DATA_NOT_AVAILABLE"):
            _exec("finance.quote", {}, {"symbol": "AAPL"})
    finally:
        set_market_gateway(None)
