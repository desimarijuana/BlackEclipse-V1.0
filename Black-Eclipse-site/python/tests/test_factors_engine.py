"""Factor engine — hand-computed correctness and edge cases."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.factors import engine as E


def test_forward_returns_simple_and_log():
    px = np.array([[100.0, 50.0], [110.0, 55.0], [121.0, 60.5]])
    fwd = E.forward_returns(px, 1)
    assert fwd[0, 0] == pytest.approx(0.10)
    assert fwd[0, 1] == pytest.approx(0.10)
    assert math.isnan(fwd[2, 0])
    two = E.forward_returns(px, 2)
    assert two[0, 0] == pytest.approx(0.21)
    logs = E.forward_returns(px, 2, log=True)
    assert logs[0, 0] == pytest.approx(math.log(1.21))


def test_ic_perfect_and_rank():
    f = np.array([[1.0, 2, 3, 4, 5], [5, 4, 3, 2, 1]])
    r = np.array([[0.01, 0.02, 0.03, 0.04, 0.05], [0.05, 0.04, 0.03, 0.02, 0.01]])
    ic, counts = E.cross_sectional_ic(f, r)
    assert np.allclose(ic, [1.0, 1.0])
    assert list(counts) == [5, 5]
    ric, _ = E.cross_sectional_ic(f, r, method="spearman")
    assert np.allclose(ric, [1.0, 1.0])


def test_ic_constant_cross_section_is_nan():
    f = np.array([[2.0, 2, 2, 2], [1, 2, 3, 4]])
    r = np.array([[0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 0.4]])
    ic, counts = E.cross_sectional_ic(f, r, min_obs=3)
    assert math.isnan(ic[0])
    assert ic[1] == pytest.approx(1.0)


def test_spearman_ties_average_rank():
    # x has a tie; y strictly increasing
    x = np.array([1.0, 1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0, 4.0])
    rho = E._spearman(x, y)  # noqa: SLF001
    # ranks x = [1.5,1.5,3,4], y=[1,2,3,4]
    manual = E._pearson(np.array([1.5, 1.5, 3, 4]), y)  # noqa: SLF001
    assert rho == pytest.approx(manual)


def test_ic_summary_information_ratio():
    ic = np.array([0.05, 0.03, 0.07, 0.01, 0.04])
    summ = E.ic_summary(ic)
    assert summ["meanIC"] == pytest.approx(0.04)
    assert summ["informationRatio"] == pytest.approx(0.04 / np.std(ic, ddof=1))
    assert summ["hitRate"] == pytest.approx(1.0)


def test_newey_west_matches_simple_mean():
    x = np.array([0.01, 0.02, 0.03, 0.02, 0.01, 0.0, 0.02, 0.03])
    nw = E.newey_west_mean(x)
    assert nw["mean"] == pytest.approx(float(x.mean()))
    assert nw["standardError"] > 0


def test_zscore_and_winsorize():
    panel = np.array([[1.0, 2.0, 3.0, 4.0]])
    z = E.zscore(panel)
    assert abs(float(np.nansum(z))) < 1e-9
    assert float(z.std(ddof=1)) == pytest.approx(1.0, abs=1e-6)
    w = E.winsorize(np.array([[0.0, 1.0, 2.0, 100.0]]), limits=(0.25, 0.25))
    assert w[0, 3] < 100.0


def test_quantile_portfolio_hand_computed():
    factor = np.array([[1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0]])
    rets = np.array([[0.01, 0.02, 0.03, 0.04], [0.01, 0.02, 0.03, 0.04]])
    out = E.quantile_portfolio(factor, rets, quantiles=2, long_short=True, rebalance=1, cost_bps=0.0,
                               min_obs=2)
    # day0 ls = 0.5*(0.03+0.04) - 0.5*(0.01+0.02) = 0.02 ; same day1
    expected = (1.02 * 1.02) - 1.0
    assert out["longShortMetrics"]["totalReturn"] == pytest.approx(expected)
    # entry into a dollar-neutral book is one-way turnover 1.0; day-1 rebalance is 0
    assert out["turnover"]["average"] == pytest.approx(0.5)
    # top quantile long-only (assets 2,3) avg of 3% and 4%
    assert out["quantileMetrics"]["Q2"]["averagePeriodReturn"] == pytest.approx(0.035)


def test_quantile_cost_reduces_net_return():
    rng = np.random.default_rng(7)
    factor = rng.normal(size=(60, 20))
    rets = rng.normal(0, 0.01, size=(60, 20))
    gross = E.quantile_portfolio(factor, rets, quantiles=5, cost_bps=0.0, rebalance=5)
    net = E.quantile_portfolio(factor, rets, quantiles=5, cost_bps=50.0, rebalance=5)
    assert net["longShortMetrics"]["totalReturn"] < gross["longShortMetrics"]["totalReturn"]
    assert net["cost"]["totalCost"] > 0


def test_portfolio_metrics_known_values():
    m = E.portfolio_metrics([0.10, -0.10], periods_per_year=2)
    assert m["totalReturn"] == pytest.approx(-0.01)
    assert m["annualizedVolatility"] == pytest.approx(0.2)
    assert m["maxDrawdown"] == pytest.approx(-0.10)
    assert m["sharpe"] == pytest.approx(0.0)


def test_portfolio_metrics_degenerate_is_honest():
    m = E.portfolio_metrics([0.05], periods_per_year=252)
    assert m["available"] is False
    assert "reason" in m


def test_combine_factors_equal_and_ic_weighted():
    a = np.array([[1.0, 2, 3, 4], [1, 2, 3, 4]])
    b = np.array([[4.0, 3, 2, 1], [4, 3, 2, 1]])
    combo = E.combine_factors([a, b], method="equal_zscore")
    assert combo["weights"] == pytest.approx([0.5, 0.5])
    assert tuple(combo["composite"].shape) == (2, 4)
    # b is a perfect predictor of the forward return -> ic_weighted favours b
    fwd = np.array([[0.01, 0.02, 0.03, 0.04], [0.01, 0.02, 0.03, 0.04]])
    icw = E.combine_factors([a, b], method="ic_weighted", forward=fwd)
    assert icw["weights"][1] != icw["weights"][0]


def test_redundancy_detects_correlated_pair():
    a = np.array([[1.0, 2, 3, 4], [5, 6, 7, 8]])
    b = a * 2.0
    c = -a
    result = E.detect_redundancy([a, b, c], threshold=0.9)
    pairs = {(p["i"], p["j"]) for p in result["pairs"]}
    assert (0, 1) in pairs
    assert (0, 2) in pairs


def test_validation_gate_fails_on_insignificant_ic():
    gate = E.validation_gate(ic_mean=0.01, ic_pvalue=0.4, expected_direction="positive",
                             average_cross_section=50, net_cumulative=0.02, average_turnover=0.2,
                             quantile_returns=[0.0, 0.01, 0.02, 0.03, 0.04])
    assert gate["outcome"] == "failed"
    assert gate["validated"] is False


def test_rank_ic_invariant_under_monotone_transform():
    rng = np.random.default_rng(2)
    f = rng.normal(size=(40, 12))
    r = rng.normal(size=(40, 12))
    base, _ = E.cross_sectional_ic(f, r, method="spearman", min_obs=5)
    # a strictly increasing transform (3x + 7) cannot change ranks
    shifted, _ = E.cross_sectional_ic(f * 3.0 + 7.0, r, method="spearman", min_obs=5)
    mask = np.isfinite(base)
    assert np.allclose(base[mask], shifted[mask])


def test_long_short_book_is_dollar_neutral_and_deterministic():
    rng = np.random.default_rng(9)
    f = rng.normal(size=(80, 20))
    r = rng.normal(0, 0.01, size=(80, 20))
    a = E.quantile_portfolio(f, r, quantiles=5, long_short=True, rebalance=10, cost_bps=5.0)
    b = E.quantile_portfolio(f, r, quantiles=5, long_short=True, rebalance=10, cost_bps=5.0)
    # dollar-neutral: long weights sum to +1, short to -1 -> total ~ 0
    total = sum(w["weight"] for w in a["finalWeights"])
    assert total == pytest.approx(0.0, abs=1e-9)
    # determinism: identical inputs give identical results
    assert a["longShortMetrics"]["totalReturn"] == b["longShortMetrics"]["totalReturn"]


def test_validation_gate_passes_when_checks_pass():
    gate = E.validation_gate(ic_mean=0.05, ic_pvalue=0.001, expected_direction="positive",
                             average_cross_section=80, net_cumulative=0.3, average_turnover=0.3,
                             quantile_returns=[-0.01, 0.0, 0.01, 0.02, 0.03])
    assert gate["outcome"] == "passed"
    assert gate["validated"] is True
