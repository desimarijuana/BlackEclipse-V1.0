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


# ── select: dotted paths, aliases and missing fields ────────────────────────

NESTED = [
    {"symbol": "AAPL", "close": 100.0, "fundamentals": {"pe": 30.0}},
    {"symbol": "MSFT", "close": 300.0, "fundamentals": {}},
]


def test_select_resolves_dotted_paths_and_aliases():
    result = _exec("transform.select", {"rows": NESTED},
                   {"fields": "symbol, pe=fundamentals.pe"})
    assert result["rows"][0] == {"symbol": "AAPL", "pe": 30.0}
    # The typed path is the column name when no alias is given.
    plain = _exec("transform.select", {"rows": NESTED}, {"fields": "fundamentals.pe"})
    assert plain["rows"][0] == {"fundamentals.pe": 30.0}


def test_select_missing_field_policies():
    as_null = _exec("transform.select", {"rows": NESTED}, {"fields": "symbol, fundamentals.pe"})
    assert as_null["rows"][1] == {"symbol": "MSFT", "fundamentals.pe": None}
    assert as_null["dropped"] == 0

    dropped = _exec("transform.select", {"rows": NESTED},
                    {"fields": "symbol, fundamentals.pe", "onMissing": "drop"})
    assert [row["symbol"] for row in dropped["rows"]] == ["AAPL"]
    assert dropped["dropped"] == 1

    with pytest.raises(ValueError, match="has no field"):
        _exec("transform.select", {"rows": NESTED},
              {"fields": "fundamentals.pe", "onMissing": "error"})


def test_select_rejects_a_rename_that_would_lose_a_column():
    with pytest.raises(ValueError, match="maps more than one field"):
        _exec("transform.select", {"rows": NESTED},
              {"fields": "symbol, close", "rename": '{"close":"symbol"}'})


# ── sort / limit: numeric strings, multi-key, nulls, offset ─────────────────

def test_sort_treats_numeric_strings_as_numbers():
    rows = [{"v": "9"}, {"v": "100"}, {"v": "10"}]
    ordered = _exec("transform.sort_limit", {"rows": rows}, {"field": "v"})
    assert [row["v"] for row in ordered["rows"]] == ["9", "10", "100"]


def test_sort_keeps_nulls_last_in_both_directions():
    rows = [{"v": 2}, {"v": None}, {"v": 1}]
    asc = _exec("transform.sort_limit", {"rows": rows}, {"field": "v"})
    desc = _exec("transform.sort_limit", {"rows": rows}, {"field": "v", "order": "desc"})
    assert [row["v"] for row in asc["rows"]] == [1, 2, None]
    assert [row["v"] for row in desc["rows"]] == [2, 1, None]


def test_sort_by_several_keys_with_per_key_direction():
    rows = [
        {"symbol": "AAA", "date": "2026-01-02", "close": 10},
        {"symbol": "BBB", "date": "2026-01-02", "close": 20},
        {"symbol": "CCC", "date": "2026-01-03", "close": 5},
    ]
    result = _exec("transform.sort_limit", {"rows": rows}, {"field": "date desc, symbol asc"})
    assert [row["symbol"] for row in result["rows"]] == ["CCC", "AAA", "BBB"]


def test_sort_offset_and_limit_slice_the_window():
    rows = [{"v": n} for n in (5, 4, 3, 2, 1)]
    result = _exec("transform.sort_limit", {"rows": rows}, {"field": "v", "offset": 1, "limit": 2})
    assert [row["v"] for row in result["rows"]] == [2, 3]


def test_sort_refuses_an_unknown_direction():
    with pytest.raises(ValueError, match="order must be"):
        _exec("transform.sort_limit", {"rows": ROWS}, {"field": "close", "order": "descending"})


def test_sort_can_ignore_text_case():
    rows = [{"symbol": "apple"}, {"symbol": "Zebra"}]
    exact = _exec("transform.sort_limit", {"rows": rows}, {"field": "symbol"})
    folded = _exec("transform.sort_limit", {"rows": rows}, {"field": "symbol", "caseInsensitive": True})
    # ASCII puts "Zebra" before "apple"; folding gives the human order.
    assert [row["symbol"] for row in exact["rows"]] == ["Zebra", "apple"]
    assert [row["symbol"] for row in folded["rows"]] == ["apple", "Zebra"]


def test_aggregate_and_deduplicate_fire_their_done_control():
    aggregated = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "sum"})
    deduped = _exec("logic.deduplicate", {"items": ROWS}, {"keys": "sector"})
    assert aggregated["_control"] == ["done"]
    assert deduped["_control"] == ["done"]


def test_aggregate_statistics():
    median = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "median"})
    assert median["value"] == 200.0

    stddev = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "stddev"})
    assert stddev["value"] == 100.0  # sample stddev of 100/300/200

    p25 = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "percentile", "percentile": 25})
    assert p25["value"] == 150.0
    p95 = _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "percentile"})
    assert p95["value"] == 200.0  # default p50 over three points


def test_aggregate_refuses_a_percentile_outside_zero_to_one_hundred():
    with pytest.raises(ValueError, match="between 0 and 100"):
        _exec("logic.aggregate", {"items": ROWS}, {"field": "close", "op": "percentile", "percentile": 120})


def test_aggregate_coerces_numeric_strings():
    rows = [{"v": "1.5"}, {"v": 2}, {"v": "3"}]
    assert _exec("logic.aggregate", {"items": rows}, {"field": "v", "op": "sum"})["value"] == 6.5


def test_aggregate_sorts_groups_by_value_not_by_text():
    rows = [{"sector": "10", "close": 1}, {"sector": "9", "close": 1}]
    groups = _exec("logic.aggregate", {"items": rows}, {"field": "close", "op": "sum", "groupBy": "sector"})
    assert [group["sector"] for group in groups["groups"]] == ["9", "10"]


def test_deduplicate_uses_the_join_identity_rule():
    rows = [{"id": 1, "v": "a"}, {"id": 1.0, "v": "b"}, {"id": "1", "v": "c"}, {"id": 2, "v": "d"}]
    result = _exec("logic.deduplicate", {"items": rows}, {"keys": "id"})
    assert [row["v"] for row in result["items"]] == ["a", "d"]
    assert result["dropped"] == 2


# ── join: composite keys, normalisation and the non-inner modes ─────────────

def test_join_on_a_composite_key():
    left = [
        {"symbol": "AAPL", "date": "2026-01-02", "close": 100.0},
        {"symbol": "AAPL", "date": "2026-01-03", "close": 101.0},
    ]
    right = [{"symbol": "AAPL", "date": "2026-01-03", "pe": 30.0}]
    result = _exec("transform.join", {"left": left, "right": right},
                   {"leftKey": "symbol,date", "rightKey": "symbol,date"})
    assert result["matched"] == 1
    assert result["rows"] == [
        {"symbol": "AAPL", "date": "2026-01-03", "close": 101.0, "pe": 30.0},
    ]


def test_join_normalises_numeric_and_case_keys():
    left = [{"symbol": "aapl", "id": 1}]
    right = [{"symbol": "AAPL", "id": "1.0", "pe": 30.0}]
    loose = _exec("transform.join", {"left": left, "right": right},
                  {"leftKey": "symbol", "rightKey": "symbol", "caseInsensitive": True})
    assert loose["matched"] == 1
    numeric = _exec("transform.join", {"left": left, "right": right},
                    {"leftKey": "id", "rightKey": "id"})
    assert numeric["matched"] == 1


def test_join_duplicate_right_keys_are_explicit_not_silent():
    left = [{"symbol": "AAPL"}]
    right = [{"symbol": "AAPL", "dividend": 0.25}, {"symbol": "AAPL", "dividend": 0.26}]
    first = _exec("transform.join", {"left": left, "right": right}, {"leftKey": "symbol"})
    assert len(first["rows"]) == 1
    last = _exec("transform.join", {"left": left, "right": right},
                 {"leftKey": "symbol", "onDuplicate": "last"})
    assert last["rows"][0]["dividend"] == 0.26
    every = _exec("transform.join", {"left": left, "right": right},
                  {"leftKey": "symbol", "onDuplicate": "all"})
    assert [row["dividend"] for row in every["rows"]] == [0.25, 0.26]


def test_join_anti_and_right_modes():
    left = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
    right = [{"symbol": "AAPL", "pe": 30.0}, {"symbol": "JPM", "pe": 12.0}]
    anti = _exec("transform.join", {"left": left, "right": right},
                 {"leftKey": "symbol", "how": "anti"})
    assert anti["rows"] == [{"symbol": "MSFT"}]
    right_join = _exec("transform.join", {"left": left, "right": right},
                       {"leftKey": "symbol", "how": "right"})
    assert {row["symbol"] for row in right_join["rows"]} == {"AAPL", "JPM"}
    assert {"symbol": "JPM", "pe": 12.0} in right_join["rows"]


def test_left_join_nulls_the_right_columns_it_could_not_fill():
    left = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
    right = [{"symbol": "AAPL", "pe": 30.0}]
    result = _exec("transform.join", {"left": left, "right": right},
                   {"leftKey": "symbol", "how": "left"})
    assert result["rows"][1] == {"symbol": "MSFT", "pe": None}


def test_join_suffix_keeps_a_colliding_right_column():
    left = [{"symbol": "AAPL", "close": 100.0}]
    right = [{"symbol": "AAPL", "close": 100.5}]
    result = _exec("transform.join", {"left": left, "right": right},
                   {"leftKey": "symbol", "suffix": "_right"})
    assert result["rows"][0] == {"symbol": "AAPL", "close": 100.0, "close_right": 100.5}


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

def test_aggregate_empty_input_is_null_not_a_fabricated_zero():
    overall = _exec("logic.aggregate", {"items": []}, {"field": "close", "op": "sum"})
    assert overall["value"] is None
    assert overall["groups"] == []
    # count is a count: zero rows really is 0.
    assert _exec("logic.aggregate", {"items": []}, {"op": "count"})["value"] == 0.0
    # A group of rows with no numeric value for the field is also unknown.
    rows = [{"sector": "Tech", "close": None}]
    grouped = _exec("logic.aggregate", {"items": rows}, {"field": "close", "op": "avg", "groupBy": "sector"})
    assert grouped["groups"][0]["value"] is None
