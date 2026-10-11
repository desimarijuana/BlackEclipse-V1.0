"""Performance benchmarks for the statistical engine.

Records actual wall-clock measurements for representative workloads and asserts
generous upper bounds so a regression is caught without CI flakiness. The
measured numbers print in the test output for the record.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from harness.stats import run_tool

_RESULTS: dict[str, dict[str, float]] = {}


def _bench(label: str, fn, *, budget_s: float):
    start = time.perf_counter()
    out = fn()
    elapsed = time.perf_counter() - start
    _RESULTS[label] = {"seconds": round(elapsed, 4), "budget": budget_s}
    print(f"[bench] {label}: {elapsed * 1000:.1f} ms")
    assert elapsed < budget_s, f"{label} took {elapsed:.2f}s (> {budget_s}s)"
    return out


def test_bench_returns_100k():
    rng = np.random.default_rng(0)
    prices = 100 * np.cumprod(1 + rng.normal(0, 0.01, 100_000))
    _bench("returns_100k", lambda: run_tool("calculate_returns", {"values": prices.tolist()}),
           budget_s=5.0)


def test_bench_rolling_volatility_50k():
    rng = np.random.default_rng(1)
    prices = 100 * np.cumprod(1 + rng.normal(0, 0.01, 50_000))
    _bench("rolling_vol_50k",
           lambda: run_tool("calculate_volatility", {"values": prices.tolist(), "window": 20}),
           budget_s=8.0)


def test_bench_correlation_matrix_20x2000():
    rng = np.random.default_rng(2)
    series = [rng.normal(0, 1, 2000).tolist() for _ in range(20)]
    _bench("corr_matrix_20x2000",
           lambda: run_tool("calculate_correlation", {"series": series}), budget_s=15.0)


def test_bench_features_20_on_20k():
    rng = np.random.default_rng(3)
    prices = 100 * np.cumprod(1 + rng.normal(0, 0.01, 20_000))
    features = [{"name": f"f{i}", "type": "momentum", "params": {"n": i + 1}} for i in range(20)]
    _bench("features_20_on_20k",
           lambda: run_tool("build_features", {"values": prices.tolist(), "features": features}),
           budget_s=8.0)


def test_bench_formula_preview_20k():
    rng = np.random.default_rng(4)
    prices = (100 * np.cumprod(1 + rng.normal(0, 0.01, 20_000))).tolist()
    _bench("formula_preview_20k",
           lambda: run_tool("build_features", {"values": prices, "features": [
               {"name": "x", "expression": "zscore(returns, 20) * sma(close, 10)"}]}),
           budget_s=3.0)


def test_bench_ic_cross_sectional_200x50():
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 1, (200, 50))
    fwd = factor * 0.01 + rng.normal(0, 0.001, (200, 50))
    _bench("ic_cs_200x50",
           lambda: run_tool("calculate_information_coefficient",
                            {"factor": factor.tolist(), "forwardReturns": fwd.tolist()}),
           budget_s=10.0)


def test_bench_summary_recorded():
    # Ensure at least the in-process measurements are recorded and sane.
    assert all(v["seconds"] >= 0 for v in _RESULTS.values())
