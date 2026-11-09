"""Eclipse attaches to MetaTrader 5; it never starts it on its own.

`mt5.initialize(path=...)` launches terminal64.exe whenever it is closed. Because
dashboard widgets and the journal auto-sync read the broker in the background, an
unguarded call popped the terminal open every time it was closed. The guard must
refuse BEFORE initialize unless the connection opted in.
"""

from __future__ import annotations

import pytest

import harness.trade.adapters.mt5 as mt5_module
from harness.trade.adapters.mt5 import AdapterUnavailable, MT5Adapter
from harness.trade.model import BrokerConfigError, validate_config

from mt5_sim import SimTerminal


@pytest.fixture()
def sim(monkeypatch):
    terminal = SimTerminal()
    monkeypatch.setattr(mt5_module, "_MODULE", terminal)
    monkeypatch.setattr(mt5_module, "_IMPORT_ERROR", None)
    monkeypatch.setattr(
        mt5_module, "_terminal_path", lambda config: "C:/MT5/terminal64.exe"
    )
    return terminal


def _adapter(**config):
    return MT5Adapter({"terminalPath": "C:/MT5/terminal64.exe", **config})


def test_a_closed_terminal_is_refused_without_launching(sim, monkeypatch):
    monkeypatch.setattr(mt5_module, "terminal_running", lambda path=None: False)
    with pytest.raises(AdapterUnavailable) as excinfo:
        _adapter().account()
    assert excinfo.value.code == "TERMINAL_NOT_RUNNING"
    assert sim.initialize_calls == 0


def test_probe_reports_a_closed_terminal_without_launching(sim, monkeypatch):
    monkeypatch.setattr(mt5_module, "terminal_running", lambda path=None: False)
    payload = _adapter().probe()
    assert payload["code"] == "TERMINAL_NOT_RUNNING"
    assert payload["connected"] is False
    assert payload["account"] is None
    assert sim.initialize_calls == 0


def test_a_running_terminal_is_attached(sim, monkeypatch):
    monkeypatch.setattr(mt5_module, "terminal_running", lambda path=None: True)
    account = _adapter().account()
    assert account["login"] == 114826727
    assert sim.initialize_calls == 1


def test_auto_launch_is_opt_in(sim, monkeypatch):
    monkeypatch.setattr(mt5_module, "terminal_running", lambda path=None: False)
    account = _adapter(autoLaunchTerminal=True).account()
    assert account["login"] == 114826727
    assert sim.initialize_calls == 1


def test_launch_policy_is_a_persistable_boolean():
    config = validate_config({"autoLaunchTerminal": "false", "portable": "0"})
    assert config["autoLaunchTerminal"] is False
    assert config["portable"] is False
    assert validate_config({"autoLaunchTerminal": True})["autoLaunchTerminal"] is True
    with pytest.raises(BrokerConfigError):
        validate_config({"autoLaunchTerminal": "sometimes"})
