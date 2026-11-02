"""Phase 9 trading primitives: pure sizing/bracket/guards and position management."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.trading_calc_nodes import session_state
from harness.trade import bootstrap

REGISTRY = build_default_registry()


class FakeService:
    def __init__(self, positions, *, modify=None, close=None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._positions = positions
        self._modify = modify or {"available": True, "modified": True,
                                  "result": {"ok": True, "verified": True}}
        self._close = close or {"available": True, "closed": True,
                                "result": {"ok": True, "verified": True,
                                           "remainingVolume": 0.2}}

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def positions(self, connection_id):
        self._record("positions", connection_id)
        return {"available": True, "data": list(self._positions)}

    def modify_position(self, connection_id, ticket, *, stop_loss=None, take_profit=None):
        self._record("modify_position", connection_id, ticket, stop_loss=stop_loss)
        return self._modify

    def close_position(self, connection_id, ticket, *, volume=None, deviation=20):
        self._record("close_position", connection_id, ticket, volume=volume)
        return self._close


def _exec(node_type: str, config: dict, inputs: dict):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.PAPER,
        inputs=inputs, config=config,
    ))


@pytest.fixture
def service():
    fake = FakeService([
        {"ticket": 11, "symbol": "EURUSD", "side": "buy", "volume": 0.4,
         "openPrice": 100.0, "currentPrice": 102.0, "stopLoss": 95.0},
        {"ticket": 12, "symbol": "EURUSD", "side": "sell", "volume": 1.0,
         "openPrice": 100.0, "currentPrice": 98.0, "stopLoss": 105.0},
    ])
    bootstrap.set_service(fake)
    try:
        yield fake
    finally:
        bootstrap.set_service(None)


# ── size by risk ─────────────────────────────────────────────────────────────


def test_size_by_risk_turns_a_budget_and_a_stop_into_a_volume():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 10_000.0, "riskPct": 1.0, "contractSize": 1.0, "volumeStep": 0.01},
        {"entry": 100.0, "stop": 95.0},
    )
    assert result["ok"] is True
    assert result["quantity"] == pytest.approx(20.0)
    assert result["riskBudget"] == pytest.approx(100.0)
    assert result["riskAtStop"] == pytest.approx(100.0)


def test_size_by_risk_floors_to_the_step_so_the_budget_is_never_exceeded():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 10_000.0, "riskPct": 1.0, "volumeStep": 1.0},
        {"entry": 100.0, "stop": 97.0},
    )
    # 100 / 3 = 33.33 units -> floored to 33 whole units.
    assert result["quantity"] == pytest.approx(33.0)
    assert result["riskAtStop"] <= result["riskBudget"]


def test_size_by_risk_uses_the_brokers_contract_size_and_step():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 10_000.0, "riskPct": 1.0},
        {
            "entry": 4025.0,
            "stop": 4003.0,
            "quote": {"available": True, "data": {
                "contractSize": 100.0, "volumeStep": 0.01, "volumeMin": 0.01,
            }},
        },
    )
    assert result["quantity"] == pytest.approx(0.04)


def test_size_by_risk_refuses_when_the_budget_is_below_one_step():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 100.0, "riskPct": 1.0, "volumeStep": 1.0},
        {"entry": 100.0, "stop": 98.0},
    )
    assert result["ok"] is False
    assert result["quantity"] == 0.0
    assert "volume step" in result["reason"]


def test_size_by_risk_refuses_a_size_below_the_symbol_minimum():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 10_000.0, "riskPct": 1.0, "volumeStep": 0.01},
        {"entry": 4025.0, "stop": 4003.0,
         "quote": {"contractSize": 100.0, "volumeMin": 0.1}},
    )
    assert result["ok"] is False
    assert "below the symbol minimum" in result["reason"]


def test_size_by_risk_caps_at_the_symbol_maximum():
    result = _exec(
        "trading.size_by_risk",
        {"equity": 10_000_000.0, "riskPct": 100.0, "volumeStep": 1.0},
        {"entry": 100.0, "stop": 99.0, "quote": {"volumeMax": 50.0}},
    )
    assert result["quantity"] == pytest.approx(50.0)
    assert result["capped"] is True


def test_size_by_risk_needs_a_real_stop_distance():
    with pytest.raises(ValueError, match="must differ"):
        _exec(
            "trading.size_by_risk",
            {"equity": 10_000.0, "volumeStep": 0.01},
            {"entry": 100.0, "stop": 100.0},
        )


# ── bracket ─────────────────────────────────────────────────────────────────


def test_bracket_derives_a_stop_and_target_from_atr():
    result = _exec(
        "trading.bracket",
        {"side": "buy", "atrMultiple": 1.5, "rewardRisk": 2.0},
        {"entry": 100.0, "atr": 10.0},
    )
    assert result["stopLoss"] == pytest.approx(85.0)
    assert result["takeProfit"] == pytest.approx(130.0)
    assert result["basis"] == "atr"
    assert result["riskDistance"] == pytest.approx(15.0)


def test_bracket_is_direction_aware_for_a_short():
    result = _exec(
        "trading.bracket",
        {"side": "sell", "atrMultiple": 1.0, "rewardRisk": 1.5},
        {"entry": 100.0, "atr": 10.0},
    )
    assert result["stopLoss"] == pytest.approx(110.0)
    assert result["takeProfit"] == pytest.approx(85.0)


def test_an_explicit_stop_distance_beats_the_atr():
    result = _exec(
        "trading.bracket",
        {"side": "buy", "atrMultiple": 3.0, "stopDistance": 4.0, "rewardRisk": 2.0},
        {"entry": 100.0, "atr": 10.0},
    )
    assert result["basis"] == "stopDistance"
    assert result["riskDistance"] == pytest.approx(4.0)
    assert result["stopLoss"] == pytest.approx(96.0)


def test_bracket_without_a_distance_is_an_outcome_not_a_guess():
    result = _exec("trading.bracket", {"side": "buy"}, {"entry": 100.0})
    assert result["ok"] is False
    assert result["stopLoss"] is None
    assert result["basis"] == "none"


def test_a_zero_reward_risk_emits_no_target():
    result = _exec(
        "trading.bracket", {"side": "buy", "rewardRisk": 0.0},
        {"entry": 100.0, "atr": 10.0},
    )
    assert result["stopLoss"] == pytest.approx(85.0)
    assert result["takeProfit"] is None


# ── spread guard ────────────────────────────────────────────────────────────


def test_the_spread_guard_allows_a_tight_spread():
    result = _exec(
        "trading.spread_guard", {"maxSpreadPoints": 10.0},
        {"quote": {"available": True, "data": {"spreadPoints": 4.5}}},
    )
    assert result["ok"] is True
    assert result["spreadPoints"] == pytest.approx(4.5)


def test_the_spread_guard_blocks_a_wide_spread_with_the_numbers():
    result = _exec(
        "trading.spread_guard", {"maxSpreadPoints": 10.0},
        {"quote": {"data": {"spreadPoints": 12.0}}},
    )
    assert result["ok"] is False
    assert result["reason"] == "spread 12 points is above the 10 cap"


def test_a_missing_spread_is_not_a_tight_spread():
    result = _exec(
        "trading.spread_guard", {"maxSpreadPoints": 10.0},
        {"quote": {"available": False}},
    )
    assert result["ok"] is False
    assert result["spreadPoints"] is None
    assert "no spread" in result["reason"]


def test_the_spread_guard_accepts_the_spread_directly():
    result = _exec(
        "trading.spread_guard", {"maxSpreadPoints": 10.0}, {"spreadPoints": 3.0},
    )
    assert result["ok"] is True


# ── session filter ──────────────────────────────────────────────────────────


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_the_session_window_is_inclusive_of_start_and_exclusive_of_end():
    kwargs = {"start": "09:00", "end": "17:00", "weekdays": "mon,tue,wed,thu,fri"}
    assert session_state(_utc("2026-11-02T09:00:00"), **kwargs)[0] is True
    assert session_state(_utc("2026-11-02T16:59:00"), **kwargs)[0] is True
    assert session_state(_utc("2026-11-02T17:00:00"), **kwargs)[0] is False


def test_the_session_window_wraps_over_midnight():
    kwargs = {"start": "22:00", "end": "06:00", "weekdays": "mon,tue,wed,thu,fri,sat,sun"}
    assert session_state(_utc("2026-11-02T23:30:00"), **kwargs)[0] is True
    assert session_state(_utc("2026-11-02T02:00:00"), **kwargs)[0] is True
    assert session_state(_utc("2026-11-02T12:00:00"), **kwargs)[0] is False


def test_the_weekday_filter_blocks_the_weekend():
    open_now, reason = session_state(
        _utc("2026-11-07T10:00:00"),  # a Saturday
        start="00:00", end="00:00", weekdays="mon,tue,wed,thu,fri",
    )
    assert open_now is False
    assert "Saturday" in reason


def test_the_broker_trade_mode_can_close_the_session():
    open_now, reason = session_state(
        _utc("2026-11-02T10:00:00"), start="00:00", end="00:00",
        weekdays="mon,tue,wed,thu,fri,sat,sun", trade_mode="close_only",
    )
    assert open_now is False
    assert "close-only" in reason


def test_a_long_only_symbol_blocks_a_sell():
    closed, reason = session_state(
        _utc("2026-11-02T10:00:00"), start="00:00", end="00:00",
        weekdays="mon,tue,wed,thu,fri,sat,sun", trade_mode="long_only", side="sell",
    )
    assert closed is False
    assert "long-only" in reason


def test_an_unknown_trade_mode_is_refused_not_assumed():
    open_now, _reason = session_state(
        _utc("2026-11-02T10:00:00"), start="00:00", end="00:00",
        weekdays="mon,tue,wed,thu,fri,sat,sun", trade_mode="unknown",
    )
    assert open_now is False


def test_the_session_node_reads_the_quote_and_an_explicit_time():
    result = _exec(
        "trading.session_filter",
        {"startUtc": "09:00", "endUtc": "17:00", "weekdays": "mon,tue,wed,thu,fri"},
        {"quote": {"data": {"tradeMode": "full"}}, "side": "buy",
         "time": "2026-11-02T10:00:00Z"},
    )
    assert result["ok"] is True
    assert result["open"] is True
    assert result["tradeMode"] == "full"


# ── break even ──────────────────────────────────────────────────────────────


def test_break_even_waits_for_the_trigger(service):
    result = _exec(
        "trading.break_even", {"connectionId": "brk_1", "triggerR": 1.0},
        {"ticket": 11, "price": 102.0},
    )
    assert result["moved"] is False
    assert result["ok"] is True
    assert "not triggered" in result["reason"]
    assert service.calls == [("positions", ("brk_1",), {})]


def test_break_even_moves_the_stop_to_entry_once_triggered(service):
    result = _exec(
        "trading.break_even", {"connectionId": "brk_1", "triggerR": 1.0},
        {"ticket": 11, "price": 106.0},
    )
    assert result["moved"] is True
    assert result["stopLoss"] == pytest.approx(100.0)
    assert service.calls[-1][0] == "modify_position"
    assert service.calls[-1][2]["stop_loss"] == pytest.approx(100.0)


def test_break_even_does_nothing_when_already_at_break_even(service):
    service._positions[0]["stopLoss"] = 100.5
    result = _exec(
        "trading.break_even", {"connectionId": "brk_1"},
        {"ticket": 11, "price": 106.0},
    )
    assert result["moved"] is False
    assert "already" in result["reason"]


def test_break_even_needs_an_existing_stop(service):
    service._positions[0]["stopLoss"] = None
    result = _exec(
        "trading.break_even", {"connectionId": "brk_1"},
        {"ticket": 11, "price": 106.0},
    )
    assert result["ok"] is False
    assert "no stop" in result["reason"]


def test_break_even_reports_a_missing_ticket(service):
    result = _exec(
        "trading.break_even", {"connectionId": "brk_1"}, {"ticket": 99, "price": 106.0},
    )
    assert result["ok"] is False
    assert "no open position with ticket 99" in result["reason"]


# ── trail stop ──────────────────────────────────────────────────────────────


def test_trail_stop_moves_the_stop_behind_the_price(service):
    result = _exec(
        "trading.trail_stop", {"connectionId": "brk_1", "distance": 5.0},
        {"ticket": 11, "price": 110.0},
    )
    assert result["moved"] is True
    assert result["stopLoss"] == pytest.approx(105.0)
    assert service.calls[-1][2]["stop_loss"] == pytest.approx(105.0)


def test_trail_stop_never_widens_risk(service):
    result = _exec(
        "trading.trail_stop", {"connectionId": "brk_1", "distance": 5.0},
        {"ticket": 11, "price": 99.0},
    )
    assert result["moved"] is False
    assert result["stopLoss"] == pytest.approx(95.0)
    assert "would not tighten" in result["reason"]


def test_trail_stop_sets_a_first_stop_when_none_exists(service):
    service._positions[0]["stopLoss"] = None
    result = _exec(
        "trading.trail_stop", {"connectionId": "brk_1", "distance": 5.0},
        {"ticket": 11, "price": 110.0},
    )
    assert result["moved"] is True
    assert result["stopLoss"] == pytest.approx(105.0)


def test_trail_stop_honours_the_minimum_step(service):
    service._positions[0]["stopLoss"] = 104.5
    result = _exec(
        "trading.trail_stop", {"connectionId": "brk_1", "distance": 5.0, "minStep": 1.0},
        {"ticket": 11, "price": 110.0},
    )
    assert result["moved"] is False  # 105 is only 0.5 better than 104.5


def test_trail_stop_works_for_a_short(service):
    result = _exec(
        "trading.trail_stop", {"connectionId": "brk_1", "distance": 3.0},
        {"ticket": 12, "price": 95.0},
    )
    assert result["moved"] is True
    assert result["stopLoss"] == pytest.approx(98.0)


# ── partial close ───────────────────────────────────────────────────────────


def test_a_partial_close_closes_the_configured_fraction(service):
    result = _exec(
        "trading.partial_close", {"connectionId": "brk_1", "fraction": 0.5},
        {"ticket": 11},
    )
    assert result["closed"] is True
    assert result["volume"] == pytest.approx(0.2)
    assert service.calls[-1][2]["volume"] == pytest.approx(0.2)


def test_a_partial_close_floors_to_the_symbol_step(service):
    service._positions[1]["volume"] = 1.0
    result = _exec(
        "trading.partial_close", {"connectionId": "brk_1", "fraction": 0.33},
        {"ticket": 12, "quote": {"data": {"volumeStep": 0.1}}},
    )
    assert result["volume"] == pytest.approx(0.3)


def test_a_fraction_below_one_step_closes_nothing(service):
    result = _exec(
        "trading.partial_close", {"connectionId": "brk_1", "fraction": 0.01},
        {"ticket": 11, "quote": {"data": {"volumeStep": 0.1}}},
    )
    assert result["closed"] is False
    assert result["ok"] is False
    assert "volume step" in result["reason"]
    assert service.calls == [("positions", ("brk_1",), {})]


def test_an_explicit_volume_is_used_as_is(service):
    result = _exec(
        "trading.partial_close", {"connectionId": "brk_1"}, {"ticket": 11, "volume": 0.3},
    )
    assert result["volume"] == pytest.approx(0.3)


def test_a_full_fraction_closes_the_whole_position(service):
    result = _exec(
        "trading.partial_close", {"connectionId": "brk_1", "fraction": 1.0},
        {"ticket": 11},
    )
    assert result["volume"] == pytest.approx(0.4)
