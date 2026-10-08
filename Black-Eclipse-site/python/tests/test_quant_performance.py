"""A coarse throughput guard: a large single-symbol backtest must stay linear.

The ceiling is deliberately generous (it catches an accidental O(n²) — e.g. a
per-bar full-ledger recompute — not micro-regressions on a slow machine).
"""

from __future__ import annotations

import time

from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "perf", "name": "Perf", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 12}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 50}},
            {"id": "rsi", "type": "rsi", "params": {"period": 14}},
            {"id": "atr", "type": "atr", "params": {"period": 14}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2},
                     "take_profit": {"type": "risk_reward", "value": 2}},
        },
        "position_sizing": {"type": "percent_equity", "value": 90},
        "execution": {"commission": {"type": "percentage", "value": 0.05}},
    })


def test_large_backtest_is_not_quadratic():
    n = 5000
    rows = F.bull_market("TESTUSDT", n=n, seed=1)
    ds = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})
    started = time.monotonic()
    res = E.run_backtest(_spec(), ds, E.BacktestConfig(initial_capital=100_000))
    elapsed = time.monotonic() - started
    assert res.observability["barsProcessed"] == n
    # Generous: on any reasonable machine this is well under 5s. 20s catches a
    # quadratic blow-up without being flaky.
    assert elapsed < 20.0, f"5000-bar backtest took {elapsed:.1f}s"
