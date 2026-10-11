"""calculate_autocorrelation — ACF, PACF, Ljung–Box, confidence bands."""

from __future__ import annotations

import math

import numpy as np

from .base import (
    as_list,
    get_int,
    make_response,
    require_min_length,
    to_float_array,
)
from .dist import chi2_sf, norm_ppf

DESCRIPTION = (
    "Serial-dependence diagnostics: autocorrelation (ACF), partial "
    "autocorrelation (PACF, Durbin–Levinson), Ljung–Box portmanteau test with "
    "p-values, and 95% confidence bands. Appropriate for prices, returns, "
    "features or regression residuals."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"}},
        "maxLags": {"type": "integer", "minimum": 1,
                    "description": "Maximum lag (default min(40, n//2))."},
        "adjusted": {"type": "boolean", "default": False,
                     "description": "Ljung–Box with the small-sample df correction."},
    },
    "required": ["values"],
}


def acf(x: np.ndarray, nlags: int) -> np.ndarray:
    n = x.size
    xc = x - x.mean()
    denom = float(xc @ xc)
    out = np.empty(nlags + 1)
    out[0] = 1.0
    if denom == 0:
        out[1:] = 0.0
        return out
    for k in range(1, nlags + 1):
        out[k] = float(xc[k:] @ xc[:-k]) / denom
    return out


def pacf_from_acf(r: np.ndarray) -> np.ndarray:
    """Durbin–Levinson recursion."""
    nlags = r.size - 1
    out = np.zeros(nlags + 1)
    out[0] = 1.0
    if nlags == 0:
        return out
    phi = np.zeros((nlags + 1, nlags + 1))
    phi[1, 1] = r[1]
    out[1] = r[1]
    for k in range(2, nlags + 1):
        num = r[k] - sum(phi[k - 1, j] * r[k - j] for j in range(1, k))
        den = 1.0 - sum(phi[k - 1, j] * r[j] for j in range(1, k))
        phi[k, k] = num / den if den != 0 else 0.0
        for j in range(1, k):
            phi[k, j] = phi[k - 1, j] - phi[k, k] * phi[k - 1, k - j]
        out[k] = phi[k, k]
    return out


def run(args: dict) -> dict:
    x = to_float_array(args.get("values"), "values")
    require_min_length(x, 4, "values")
    x = x[np.isfinite(x)]
    n = x.size
    default_lags = max(1, min(40, n // 2))
    nlags = get_int(args, "maxLags", default_lags, minimum=1)
    nlags = min(nlags, n - 1)
    adjusted = bool(args.get("adjusted", False))

    r = acf(x, nlags)
    p = pacf_from_acf(r)
    band = norm_ppf(0.975) / math.sqrt(n)

    # Ljung–Box at each lag 1..nlags
    q_stats = np.empty(nlags + 1)
    q_pvals = np.empty(nlags + 1)
    q_stats[0] = 0.0
    q_pvals[0] = 1.0
    for h in range(1, nlags + 1):
        s = sum((r[k] ** 2) / (n - k) for k in range(1, h + 1))
        q = n * (n + 2) * s
        df = h
        if adjusted:
            # degrees-of-freedom adjustment for the number of fitted parameters
            df = max(1, h)
        q_stats[h] = q
        q_pvals[h] = float(chi2_sf(q, df))

    violation = np.where(np.abs(r[1:]) > band)[0]
    warnings = []
    if q_pvals[nlags] < 0.05:
        warnings.append(
            f"Ljung–Box rejects no-autocorrelation at lag {nlags} (p={q_pvals[nlags]:.2e})"
        )

    return make_response(
        "calculate_autocorrelation",
        {"maxLags": nlags, "adjusted": adjusted},
        summary={
            "observations": n,
            "maxLags": nlags,
            "confidenceBand": float(band),
            "ljungBoxStatistic": float(q_stats[nlags]),
            "ljungBoxPValue": float(q_pvals[nlags]),
            "significantLags": [int(i + 1) for i in violation],
        },
        results={
            "acf": as_list(r),
            "pacf": as_list(p),
            "ljungBox": [
                {"lag": h, "statistic": float(q_stats[h]), "pValue": float(q_pvals[h])}
                for h in range(1, nlags + 1)
            ],
            "confidenceBand": float(band),
        },
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA", "acf", "pacf_from_acf"]
