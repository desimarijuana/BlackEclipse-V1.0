"""The Yahoo bridge must carry an EXPLICIT window, not a rolling `period`.

A 1y `period` is anchored to "now": its first session can fall outside the
window the caller asked for, so the series came back one session short — which
silently changes every return, drawdown and statistic computed from it. The
bridge now passes `start`/`end`, and yfinance's EXCLUSIVE `end` is made
inclusive so the last session is not dropped either.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

BRIDGE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "yfinance_bridge.py"


def _load_bridge():
    """Load the bridge script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("yfinance_bridge_under_test", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bridge():
    module = _load_bridge()
    calls: list[dict] = []

    class _FakeFrame(pd.DataFrame):
        pass

    def _download(**kwargs):
        calls.append(kwargs)
        index = pd.DatetimeIndex(["2025-10-20", "2026-10-20"])
        frame = pd.DataFrame(
            {
                ("Close", "AAPL"): [1.0, 2.0],
                ("High", "AAPL"): [1.0, 2.0],
                ("Low", "AAPL"): [1.0, 2.0],
                ("Open", "AAPL"): [1.0, 2.0],
                ("Volume", "AAPL"): [1, 2],
            },
            index=index,
        )
        return frame

    module.yf = type("FakeYf", (), {"download": staticmethod(_download)})
    module._DOWNLOAD_CALLS = calls
    return module


def test_explicit_window_is_passed_to_yfinance(bridge) -> None:
    bridge.fetch_history(["AAPL"], "1y", "1d", start="2025-10-20", end="2026-10-20")
    kwargs = bridge._DOWNLOAD_CALLS[0]
    assert kwargs["start"] == "2025-10-20"
    # yfinance's end is exclusive, so the bridge asks for the day AFTER the
    # window's last date — the window's end date itself is included.
    assert kwargs["end"] == "2026-10-21"
    # A rolling period would silently widen/narrow the window.
    assert "period" not in kwargs


def test_period_is_used_only_without_a_window(bridge) -> None:
    bridge.fetch_history(["AAPL"], "1y", "1d")
    kwargs = bridge._DOWNLOAD_CALLS[0]
    assert kwargs["period"] == "1y"
    assert "start" not in kwargs
    assert "end" not in kwargs


def test_start_without_end_keeps_the_start(bridge) -> None:
    bridge.fetch_history(["AAPL"], "1y", "1d", start="2025-10-20")
    kwargs = bridge._DOWNLOAD_CALLS[0]
    assert kwargs["start"] == "2025-10-20"
    assert "end" not in kwargs
    assert "period" not in kwargs


def test_a_malformed_end_does_not_break_the_request(bridge) -> None:
    bridge.fetch_history(["AAPL"], "1y", "1d", start="2025-10-20", end="not-a-date")
    kwargs = bridge._DOWNLOAD_CALLS[0]
    # The window still travels; the end is passed through rather than dropped.
    assert kwargs["start"] == "2025-10-20"
    assert kwargs["end"] == "not-a-date"
