"""Numerical correctness of the hand-rolled distributions (vs published values)."""

from __future__ import annotations

import pytest

from harness.stats import dist


def test_norm_cdf_known_values():
    assert dist.norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert dist.norm_cdf(1.96) == pytest.approx(0.975002, abs=1e-5)
    assert dist.norm_cdf(-1.0) == pytest.approx(0.158655, abs=1e-5)
    assert dist.norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-5)


def test_chi2_sf_known_values():
    # Critical values: chi2 with df=1 at 5% -> 3.8415 ; df=5 at 5% -> 11.0705
    assert dist.chi2_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-4)
    assert dist.chi2_sf(11.070498, 5) == pytest.approx(0.05, abs=1e-4)
    assert dist.chi2_sf(0.0, 3) == pytest.approx(1.0, abs=1e-12)


def test_t_sf_and_ppf_known_values():
    # t with df=10 at 5% two-sided critical value is 2.228139
    assert dist.t_two_sided_p(2.228139, 10) == pytest.approx(0.05, abs=1e-4)
    assert dist.t_ppf(0.975, 10) == pytest.approx(2.228139, abs=1e-4)
    # large df -> normal
    assert dist.t_ppf(0.975, 100000) == pytest.approx(1.959964, abs=1e-2)


def test_betainc_symmetry():
    assert dist.betainc(2.0, 3.0, 0.5) == pytest.approx(0.6875, abs=1e-9)
    assert dist.betainc(3.0, 2.0, 0.5) == pytest.approx(0.3125, abs=1e-9)


def test_f_sf_known_value():
    # F(2,10) 5% critical value ~ 4.102821
    assert dist.f_sf(4.102821, 2, 10) == pytest.approx(0.05, abs=1e-4)


def test_gammainc_monotone_bounds():
    assert dist.gammainc_upper(1.0, 1e-12) == pytest.approx(1.0, abs=1e-9)
    assert dist.gammainc_upper(1.0, 100.0) == pytest.approx(0.0, abs=1e-9)
