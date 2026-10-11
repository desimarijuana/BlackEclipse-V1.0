"""Statistical distributions implemented from first principles.

The engine deliberately avoids SciPy so it runs on the vendored interpreter with
no heavyweight dependency. These routines are the standard Numerical Recipes
regularized incomplete gamma/beta continued fractions plus the normal CDF from
the standard library; each is unit-tested against published values
(`tests/test_stats_dist.py`).

Functions: normal, Student-t, chi-square, F — cdf, survival and (for t/normal)
quantiles. Accuracy is ~1e-10 in the interior, which is far tighter than any
financial conclusion drawn from these numbers.
"""

from __future__ import annotations

import math
from statistics import NormalDist

_EPS = 3.0e-12
_FPMIN = 1.0e-300
_MAX_ITER = 500

_NORMAL = NormalDist()


def norm_cdf(x: float) -> float:
    return _NORMAL.cdf(x)


def norm_sf(x: float) -> float:
    return 1.0 - _NORMAL.cdf(x)


def norm_ppf(p: float) -> float:
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    return _NORMAL.inv_cdf(p)


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _gammainc_lower(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x) (series expansion)."""
    if x <= 0.0:
        return 0.0
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(_MAX_ITER):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gammainc_upper_cf(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) (continued fraction)."""
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAX_ITER):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammainc_upper(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x)."""
    if x < 0.0 or a <= 0.0:
        raise ValueError("gammainc requires a > 0 and x >= 0")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gammainc_lower(a, x)
    return _gammainc_upper_cf(a, x)


def gammainc_lower(a: float, x: float) -> float:
    return 1.0 - gammainc_upper(a, x)


def chi2_sf(x: float, df: float) -> float:
    """Survival function P(X > x) for chi-square with `df` degrees of freedom."""
    if df <= 0:
        raise ValueError("df must be positive")
    if x <= 0:
        return 1.0
    return gammainc_upper(df / 2.0, x / 2.0)


def chi2_cdf(x: float, df: float) -> float:
    return 1.0 - chi2_sf(x, df)


def _betacf(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    """Survival function P(T > t) for Student-t with `df` degrees of freedom."""
    if df <= 0:
        raise ValueError("df must be positive")
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return p if t > 0 else 1.0 - p


def t_cdf(t: float, df: float) -> float:
    return 1.0 - t_sf(t, df)


def t_ppf(p: float, df: float) -> float:
    """Inverse Student-t CDF via bisection on a bracketed interval."""
    if not 0.0 < p < 1.0:
        if p <= 0.0:
            return float("-inf")
        return float("inf")
    lo, hi = -1.0e6, 1.0e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value P(|T| > |t|)."""
    return 2.0 * t_sf(abs(t), df)


def f_sf(x: float, df1: float, df2: float) -> float:
    """Survival function for the F distribution."""
    if x <= 0:
        return 1.0
    z = df2 / (df2 + df1 * x)
    return betainc(df2 / 2.0, df1 / 2.0, z)


__all__ = [
    "norm_cdf",
    "norm_sf",
    "norm_ppf",
    "norm_pdf",
    "gammainc_upper",
    "gammainc_lower",
    "chi2_sf",
    "chi2_cdf",
    "betainc",
    "t_sf",
    "t_cdf",
    "t_ppf",
    "t_two_sided_p",
    "f_sf",
]
