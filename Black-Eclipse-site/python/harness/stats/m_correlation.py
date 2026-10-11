"""calculate_correlation — Pearson / Spearman / Kendall, matrices, rolling."""

from __future__ import annotations

import math

import numpy as np

from .base import (
    INVALID_INPUT,
    StatsError,
    as_list,
    get_int,
    get_str,
    make_response,
    safe_float,
    to_float_array,
)
from .dist import t_two_sided_p

DESCRIPTION = (
    "Correlation analysis: Pearson, Spearman rank and Kendall tau-b coefficients; "
    "covariance; full correlation/covariance matrices for N series; rolling "
    "correlation/covariance; pairwise agreement diagnostics; and two-sided "
    "significance. Missing data uses an explicit pairwise/listwise/reject policy."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "series": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                   "description": "N series (e.g. returns for N assets)."},
        "labels": {"type": "array", "items": {"type": "string"}},
        "x": {"type": "array", "items": {"type": "number"}},
        "y": {"type": "array", "items": {"type": "number"}},
        "method": {"type": "string", "enum": ["pearson", "spearman", "kendall"], "default": "pearson"},
        "window": {"type": "integer", "minimum": 2, "description": "Rolling window (pair mode)."},
        "missingPolicy": {"type": "string", "enum": ["pairwise", "listwise", "reject"], "default": "pairwise"},
        "minObservations": {"type": "integer", "minimum": 3, "default": 3},
        "significance": {"type": "boolean", "default": True},
    },
}


def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    # average ties
    sorted_vals = values[order]
    i = 0
    while i < sorted_vals.size:
        j = i
        while j + 1 < sorted_vals.size and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            avg = (i + j + 2) / 2.0  # ranks i+1..j+1 average
            ranks[order[i: j + 1]] = avg
        i = j + 1
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    ma, mb = a.mean(), b.mean()
    da, db = a - ma, b - mb
    denom = math.sqrt(float(da @ da) * float(db @ db))
    if denom == 0:
        return float("nan")
    return float(da @ db) / denom


def _kendall_tau_b(a: np.ndarray, b: np.ndarray) -> float:
    n = a.size
    if n < 2:
        return float("nan")
    conc = disc = tie_a = tie_b = 0
    for i in range(n - 1):
        da = a[i + 1:] - a[i]
        db = b[i + 1:] - b[i]
        prod = da * db
        conc += int(np.sum(prod > 0))
        disc += int(np.sum(prod < 0))
        tie_a += int(np.sum((da == 0) & (db != 0)))
        tie_b += int(np.sum((db == 0) & (da != 0)))
    pairs = n * (n - 1) / 2.0
    denom = math.sqrt((pairs - tie_a) * (pairs - tie_b))
    if denom == 0:
        return float("nan")
    return (conc - disc) / denom


def _coef(a: np.ndarray, b: np.ndarray, method: str) -> float:
    if method == "pearson":
        return _pearson(a, b)
    if method == "spearman":
        return _pearson(_rank(a), _rank(b))
    return _kendall_tau_b(a, b)


def _significance(r: float, n: int, method: str) -> dict:
    if not math.isfinite(r) or n < 3:
        return {"tStatistic": None, "pValue": None, "significant5pct": None}
    if method == "pearson":
        t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
        p = t_two_sided_p(t, n - 2)
    else:
        # Fisher z approximation (adequate for n moderately large)
        if abs(r) < 1.0:
            z = 0.5 * math.log((1 + r) / (1 - r)) * math.sqrt(n - 3)
            from .dist import norm_sf  # noqa: PLC0415

            p = 2 * norm_sf(abs(z))
        else:
            p = 0.0
        t = z if abs(r) < 1.0 else float("inf")
    return {"tStatistic": float(t), "pValue": float(p), "significant5pct": bool(p < 0.05)}


def _apply_policy(a: np.ndarray, b: np.ndarray, policy: str) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isfinite(a) & np.isfinite(b)
    if policy == "reject" and not mask.all():
        raise StatsError(INVALID_INPUT, "missing values present under 'reject' policy")
    return a[mask], b[mask]


def run(args: dict) -> dict:
    method = get_str(args, "method", "pearson")
    if method not in ("pearson", "spearman", "kendall"):
        raise StatsError(INVALID_INPUT, "method must be pearson, spearman or kendall")
    policy = get_str(args, "missingPolicy", "pairwise")
    min_obs = get_int(args, "minObservations", 3, minimum=3)
    significance = bool(args.get("significance", True))
    warnings: list[str] = []

    # ── pair mode ────────────────────────────────────────────────────────────
    if args.get("x") is not None and args.get("y") is not None:
        x = to_float_array(args.get("x"), "x")
        y = to_float_array(args.get("y"), "y")
        if x.size != y.size:
            raise StatsError(INVALID_INPUT, "x and y must have equal length")
        window = args.get("window")
        if window:
            w = get_int(args, "window", 2, minimum=2)
            rolling = np.full(x.size, np.nan)
            for i in range(w - 1, x.size):
                ca, cb = _apply_policy(x[i - w + 1: i + 1], y[i - w + 1: i + 1], "pairwise")
                if ca.size >= min_obs:
                    rolling[i] = _coef(ca, cb, method)
            return make_response(
                "calculate_correlation",
                {"method": method, "window": w, "missingPolicy": policy},
                summary={"kind": "rolling", "method": method, "window": w,
                         "latest": float(rolling[np.isfinite(rolling)][-1]) if np.isfinite(rolling).any() else None},
                results={"rolling": as_list(rolling)}, warnings=warnings,
            )
        a, b = _apply_policy(x, y, policy)
        if a.size < min_obs:
            raise StatsError(INVALID_INPUT, f"only {a.size} overlapping observations; need {min_obs}", 422)
        r = _coef(a, b, method)
        r_safe = safe_float(r)
        summary = {"kind": "pair", "method": method, "coefficient": r_safe, "observations": int(a.size)}
        results: dict = {"coefficient": r_safe}
        if significance:
            sig = _significance(r, a.size, method)
            results["significance"] = {
                "tStatistic": safe_float(sig["tStatistic"]),
                "pValue": safe_float(sig["pValue"]),
                "significant5pct": sig["significant5pct"],
            }
        return make_response(
            "calculate_correlation",
            {"method": method, "missingPolicy": policy},
            summary=summary, results=results, warnings=warnings,
        )

    # ── matrix mode ──────────────────────────────────────────────────────────
    series_arg = args.get("series")
    if not series_arg:
        raise StatsError(INVALID_INPUT, "provide either x/y or series")
    arrays = [to_float_array(s, f"series[{i}]") for i, s in enumerate(series_arg)]
    labels = args.get("labels") or [f"s{i}" for i in range(len(arrays))]
    if len(labels) != len(arrays):
        raise StatsError(INVALID_INPUT, "labels length must match series count")
    lengths = {a.size for a in arrays}
    if len(lengths) != 1:
        raise StatsError(INVALID_INPUT, "all series must have the same length")
    n = len(arrays)
    stacked = np.vstack(arrays)  # (n, T)

    corr = np.full((n, n), np.nan)
    cov = np.full((n, n), np.nan)
    counts = np.zeros((n, n), dtype=int)
    sig = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(i, n):
            a, b = _apply_policy(stacked[i], stacked[j], policy if policy != "listwise" else "pairwise")
            counts[i, j] = counts[j, i] = int(a.size)
            if a.size >= min_obs:
                corr[i, j] = corr[j, i] = _coef(a, b, method)
                cov[i, j] = cov[j, i] = float(np.cov(a, b, ddof=1)[0, 1]) if a.size > 1 else float("nan")
                if significance and method == "pearson":
                    sig[i, j] = sig[j, i] = _significance(corr[i, j], a.size, method)["pValue"]
    if not np.isfinite(corr).any():
        raise StatsError(INVALID_INPUT, f"no pair met the {min_obs}-observation minimum", 422)

    def m(a: np.ndarray) -> list:
        return [[None if not math.isfinite(v) else float(v) for v in row] for row in a]

    diagnostics = {"observationCounts": counts.tolist(),
                   "minObservations": min_obs,
                   "overlapWarning": bool((counts < min_obs).any())}
    if policy != "pairwise" and np.isfinite(corr).any():
        pass
    results = {"correlationMatrix": m(corr), "covarianceMatrix": m(cov), "labels": labels}
    if significance:
        results["pValueMatrix"] = m(sig)
        results["significance"] = {"method": "pearson-t" if method == "pearson" else "fisher-z"}
    return make_response(
        "calculate_correlation",
        {"method": method, "missingPolicy": policy},
        summary={"kind": "matrix", "method": method, "assets": labels,
                 "minPairwiseObservations": int(counts[counts > 0].min()) if counts.any() else 0},
        results=results, diagnostics=diagnostics, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
