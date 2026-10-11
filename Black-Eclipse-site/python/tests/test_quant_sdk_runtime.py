"""Managed SDK runtime: real subprocess isolation, limits, honest failures."""

from __future__ import annotations

from harness.quant import fixtures as F
from harness.quant.sdk_runtime import run_strategy_source

ROWS = {"TESTUSDT": F.bull_market("TESTUSDT", n=200)}

STRATEGY = """
from harness.quant.sdk import Strategy

class Sub(Strategy):
    name = "sub"
    def initialize(self, ctx):
        ctx.declare_indicator("fast", "ema", {"period": 5})
        ctx.declare_indicator("slow", "ema", {"period": 20})
    def on_data(self, ctx, bar):
        f = ctx.indicator("fast"); s = ctx.indicator("slow")
        if f is None or s is None:
            return
        if ctx.position().is_flat and f > s:
            ctx.buy(weight=0.9)
        elif not ctx.position().is_flat and f < s:
            ctx.close()
"""


def test_runtime_runs_source_in_subprocess():
    result, err = run_strategy_source(STRATEGY, ROWS, symbols=["TESTUSDT"], timeout_s=60)
    assert err is None, err
    assert result is not None and result.status == "OK"
    assert result.observability["barsProcessed"] > 0


def test_runtime_reports_module_error():
    result, err = run_strategy_source("raise RuntimeError('boom')", ROWS, symbols=["TESTUSDT"])
    assert result is None
    assert err is not None and err["code"] == "SDK_STRATEGY_ERROR"
    assert "boom" in err["message"]


def test_runtime_reports_on_data_error():
    src = (
        "from harness.quant.sdk import Strategy\n"
        "class S(Strategy):\n"
        "    name='s'\n"
        "    def on_data(self, ctx, bar):\n"
        "        raise ValueError('bad bar')\n"
    )
    result, err = run_strategy_source(src, ROWS, symbols=["TESTUSDT"])
    assert result is None
    assert err is not None and err["code"] == "SDK_STRATEGY_ERROR"
    assert "bad bar" in err["message"]


def test_runtime_enforces_timeout():
    result, err = run_strategy_source("while True:\n    pass\n", ROWS,
                                      symbols=["TESTUSDT"], timeout_s=2)
    assert result is None
    assert err is not None and err["code"] == "SDK_TIMEOUT"


def test_runtime_rejects_empty_source():
    result, err = run_strategy_source("   ", ROWS, symbols=["TESTUSDT"])
    assert result is None
    assert err is not None and err["code"] == "SDK_EMPTY_SOURCE"


def test_reference_examples_run_in_runtime():
    for name, cls in (("ma_crossover", "MaCrossover"),
                      ("mean_reversion", "MeanReversion"),
                      ("vol_target_trend", "VolTargetTrend")):
        src = f"from harness.quant.examples.{name} import {cls}\n"
        result, err = run_strategy_source(src, ROWS, symbols=["TESTUSDT"], timeout_s=60)
        assert err is None, (name, err)
        assert result is not None and result.status == "OK", name
