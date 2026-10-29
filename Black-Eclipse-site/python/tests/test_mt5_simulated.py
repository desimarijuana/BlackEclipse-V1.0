"""End-to-end adapter behaviour against a scripted MT5 terminal.

The pure request-builder tests prove validation. These prove the wire: what the
adapter reports after a fill, a lost reply, a dropped bracket, a partial close and
a modify the broker silently ignores. No package and no IPC are involved.
"""

from __future__ import annotations

import pytest

import harness.trade.adapters.mt5 as mt5_module
from harness.trade.adapters.mt5 import AdapterUnavailable, MT5Adapter
from harness.trade.model import OrderIntent

from mt5_sim import SimTerminal


@pytest.fixture()
def sim(monkeypatch):
    terminal = SimTerminal()
    monkeypatch.setattr(mt5_module, "_MODULE", terminal)
    monkeypatch.setattr(mt5_module, "_IMPORT_ERROR", None)
    monkeypatch.setattr(mt5_module, "_terminal_path", lambda config: "sim-terminal")
    return terminal


def _adapter() -> MT5Adapter:
    return MT5Adapter({"terminalPath": "sim-terminal", "magic": 777001})


def _intent(**overrides) -> OrderIntent:
    base = dict(
        connection_id="brk_1", symbol="XAUUSD", side="buy", order_type="market",
        volume=0.01, stop_loss=3990.0, take_profit=4030.0, magic=777001,
    )
    base.update(overrides)
    return OrderIntent(**base)


def test_a_fill_is_verified_against_the_stored_bracket(sim):
    result = _adapter().submit_order(_intent())
    assert result["ok"] is True
    assert result["verified"] is True
    assert sim.send_calls == 1
    position = sim.positions[result["ticket"]]
    assert position.sl == 3990.0
    assert position.tp == 4030.0


def test_a_dropped_bracket_is_reported_unverified(sim):
    sim.drop_bracket = True
    result = _adapter().submit_order(_intent())
    assert result["ok"] is True  # the fill really happened
    assert result["verified"] is False
    assert "SL 0" in result["verifyNote"]
    assert result["storedStopLoss"] == 0.0


def test_a_lost_send_reply_is_an_error_and_is_not_retried(sim):
    sim.ambiguous_once = True
    with pytest.raises(AdapterUnavailable):
        _adapter().submit_order(_intent())
    # The broker did receive it once: one send, one position, no blind retry.
    assert sim.send_calls == 1
    assert len(sim.positions) == 1


def test_a_disconnected_terminal_is_a_named_error(sim):
    sim.disconnect = True
    with pytest.raises(AdapterUnavailable) as caught:
        _adapter().submit_order(_intent())
    assert caught.value.code in {"IPC_FAILED", "MT5_UNAVAILABLE", "NOT_LOGGED_IN"}


def test_a_partial_close_reports_the_remaining_volume(sim):
    adapter = _adapter()
    opened = adapter.submit_order(_intent(volume=0.02))
    ticket = opened["ticket"]
    result = adapter.close_position(ticket, volume=0.01)
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["volume"] == 0.01
    assert result["remainingVolume"] == 0.01
    assert result["verified"] is True
    assert sim.positions[ticket].volume == 0.01


def test_a_modify_is_verified_and_a_ignored_modify_is_not(sim):
    adapter = _adapter()
    ticket = adapter.submit_order(_intent())["ticket"]
    moved = adapter.modify_position(ticket, stop_loss=3995.0, take_profit=4035.0)
    assert moved["verified"] is True
    assert sim.positions[ticket].sl == 3995.0

    sim.ignore_bracket = True
    ignored = adapter.modify_position(ticket, stop_loss=3996.0)
    assert ignored["ok"] is True
    assert ignored["verified"] is False
    assert "stored bracket" in ignored["verifyNote"]
    assert sim.positions[ticket].sl == 3995.0


def test_bars_are_normalized_from_the_terminal(sim):
    payload = _adapter().bars("XAUUSD", "H1", 120)
    assert payload["count"] == 120
    assert payload["symbol"] == "XAUUSD"
    assert payload["contractSize"] == 100.0
    last = payload["bars"][-1]
    assert {"time", "open", "high", "low", "close"} <= set(last)


def test_deal_history_is_readable(sim):
    adapter = _adapter()
    adapter.submit_order(_intent())
    deals = adapter.deals_since(0)
    assert deals and deals[0]["symbol"] == "XAUUSD"
    assert deals[0]["entry"] == "in"


def test_unknown_timeframe_is_refused_without_touching_the_terminal(sim):
    with pytest.raises(AdapterUnavailable) as caught:
        _adapter().bars("XAUUSD", "H7", 10)
    assert caught.value.code == "INVALID_TIMEFRAME"
    assert sim.initialize_calls == 0
