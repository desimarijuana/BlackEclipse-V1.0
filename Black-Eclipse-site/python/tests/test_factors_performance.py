"""Factor engine performance on realistic panels (bounded, deterministic)."""

from __future__ import annotations

import time

import numpy as np

from harness.factors import engine as E


def test_large_panel_pipeline_within_budget():
    rng = np.random.default_rng(0)
    T, N = 2000, 150
    factor = rng.normal(size=(T, N))
    returns = rng.normal(0, 0.01, size=(T, N))
    prices = np.cumprod(1.0 + returns, axis=0) * 100.0

    started = time.perf_counter()
    ic, counts = E.cross_sectional_ic(factor, returns, method="spearman")
    decay = E.factor_decay(factor, prices, [1, 5, 21])
    portfolio = E.quantile_portfolio(factor, returns, quantiles=10, rebalance=21, cost_bps=10.0)
    elapsed = time.perf_counter() - started

    assert np.isfinite(ic).any()
    assert len(decay["curve"]) == 3
    assert portfolio["longShortMetrics"]["available"] is True
    # Generous ceiling: measured well under 1s; this only guards a regression that
    # reintroduces per-cell Python loops.
    assert elapsed < 20.0, f"factor pipeline took {elapsed:.2f}s"


def test_membership_masking_scales():
    from harness.factors.universe import apply_membership

    rng = np.random.default_rng(1)
    T, N = 2000, 150
    panel = rng.normal(size=(T, N))
    mask = rng.random((T, N)) > 0.3
    started = time.perf_counter()
    masked = apply_membership(panel, mask)
    elapsed = time.perf_counter() - started
    assert np.isnan(masked[~mask]).all()
    assert elapsed < 2.0, f"masking took {elapsed:.2f}s"
