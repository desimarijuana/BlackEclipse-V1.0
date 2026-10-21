"""Tests for the Pine runtime.

The engine tests that need Node and the installed engine are SKIPPED when
either is missing — the Python side must never pretend the engine is there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.quant.pine import (
    PINE_ENGINE_UNAVAILABLE,
    PINE_REQUEST_INVALID,
    PineError,
    PineRunConfig,
    PineRunner,
    engine_dir,
    plot_series,
    plot_times,
)

SOURCE = """//@version=6
indicator("Eclipse probe")
plot(ta.ema(close, 9), "Fast")
plot(ta.sma(close, 20), "Slow")
"""


def _bars(n=120):
    bars = []
    price = 100.0
    for i in range(n):
        price *= 1.0 + (0.004 if i % 5 < 3 else -0.002)
        bars.append({"time": 1700000000000 + i * 86400000, "o": price, "h": price * 1.01,
                     "l": price * 0.99, "c": price, "v": 1000.0})
    return bars


# ── the runner's contract ────────────────────────────────────────────────────

def test_the_engine_lives_beside_the_package():
    path = engine_dir()
    assert path.name == "pine-engine"
    assert (path / "runner.mjs").exists()


def test_a_missing_engine_is_a_named_refusal():
    runner = PineRunner(engine=Path("/definitely/not/here"))
    assert runner.available is False
    reason = runner.unavailable_reason()
    assert reason
    with pytest.raises(PineError) as excinfo:
        runner.run(SOURCE, _bars())
    assert excinfo.value.detail.get("code") == PINE_ENGINE_UNAVAILABLE


def test_an_empty_script_is_refused():
    runner = PineRunner()
    if not runner.available:
        pytest.skip("the Pine engine is not installed")
    with pytest.raises(PineError) as excinfo:
        runner.run("   ", _bars())
    assert excinfo.value.detail.get("code") == PINE_REQUEST_INVALID


def test_bars_are_required():
    runner = PineRunner()
    if not runner.available:
        pytest.skip("the Pine engine is not installed")
    with pytest.raises(PineError) as excinfo:
        runner.run(SOURCE, [])
    assert excinfo.value.detail.get("code") == PINE_REQUEST_INVALID


def test_a_source_over_the_cap_is_refused_before_the_engine_runs():
    runner = PineRunner()
    if not runner.available:
        pytest.skip("the Pine engine is not installed")
    with pytest.raises(PineError) as excinfo:
        runner.run("x" * 5_000, _bars(), config=PineRunConfig(max_source_chars=100))
    assert excinfo.value.detail.get("code") == PINE_REQUEST_INVALID


def test_the_bars_are_capped():
    runner = PineRunner()
    if not runner.available:
        pytest.skip("the Pine engine is not installed")
    result = runner.run(SOURCE, _bars(50), config=PineRunConfig(max_bars=2))
    # The cap is applied to the request, so the engine only ever sees two bars.
    assert result.diagnostics["barCount"] == 2


# ── the engine, when it is there ─────────────────────────────────────────────

@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_a_pine_script_runs_on_our_own_bars():
    result = PineRunner().run(SOURCE, _bars())
    assert result.diagnostics["engine"] == "pinets"
    assert result.diagnostics["barCount"] == 120
    assert set(result.plots) == {"Fast", "Slow"}
    values = plot_series(result, "Fast")
    assert len(values) == 120
    # The EMA warms up: the first values are None, the later ones are numbers.
    assert values[0] is None
    assert isinstance(values[-1], float)
    times = plot_times(result, "Fast")
    assert times[0] == 1700000000000


@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_a_pine_strategy_reports_its_trades():
    source = """//@version=6
strategy("Eclipse cross", overlay = true, initial_capital = 100000)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
"""
    result = PineRunner().run(source, _bars(400))
    assert result.diagnostics["barCount"] == 400
    assert result.diagnostics["initialCapital"] == 100000
    for trade in result.trades:
        assert trade["entryPrice"] is not None
        assert trade["direction"] in ("long", "short")


@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_a_broken_script_reports_the_scripts_own_error():
    with pytest.raises(PineError) as excinfo:
        PineRunner().run("//@version=6\nindicator(\"x\")\nthis is not pine\n", _bars())
    assert excinfo.value.detail.get("code") == "PINE_RUNTIME_ERROR"
    assert excinfo.value.message


@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_the_child_never_inherits_the_runtimes_secrets():
    """The engine must not see the runtime's credentials."""
    import os

    os.environ["HARNESS_TEST_SECRET"] = "super-secret"
    try:
        result = PineRunner().run(SOURCE, _bars(30))
        assert "super-secret" not in json.dumps(result.to_dict())
    finally:
        os.environ.pop("HARNESS_TEST_SECRET", None)
