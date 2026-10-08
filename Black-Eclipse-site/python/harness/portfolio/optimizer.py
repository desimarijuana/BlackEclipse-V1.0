"""Portfolio optimization — a deterministic, constraint-aware allocator (§29).

Real projected-gradient optimization (no fake/placeholder results) for:
  * `min_variance` — minimize wᵀΣw
  * `mean_variance` — minimize ½·λ·wᵀΣw − μᵀw
  * `inverse_volatility` — wᵢ ∝ 1/σᵢ (risk parity for a diagonal covariance)

Constraints: long-only (`min_weights ≥ 0` by default), per-asset box bounds, and
weights summing to 1 (exact bounded-simplex projection). An optional turnover cap
blends toward the current allocation so the proposal never exceeds the cap.

Fully deterministic: fixed iteration count, no randomness.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

METHODS = ("min_variance", "mean_variance", "inverse_volatility")


def _project_bounded_simplex(v: Sequence[float], lo: Sequence[float], hi: Sequence[float],
                             total: float = 1.0, *, iters: int = 100) -> list[float]:
    """Project v onto {w : Σw = total, lo ≤ w ≤ hi} (exact via λ bisection)."""
    n = len(v)
    if sum(lo) > total + 1e-9 or sum(hi) < total - 1e-9:
        # Infeasible bounds: fall back to a feasible blend, reported by caller.
        base = [max(0.0, min(1.0, float(x))) for x in v]
        s = sum(base) or 1.0
        return [b / s * total for b in base]

    def total_at(lam: float) -> float:
        return sum(min(max(v[i] - lam, lo[i]), hi[i]) for i in range(n))

    # total_at is non-increasing in λ.
    lo_lam = min(v[i] - hi[i] for i in range(n)) - 1.0
    hi_lam = max(v[i] - lo[i] for i in range(n)) + 1.0
    lam = 0.0
    for _ in range(iters):
        lam = (lo_lam + hi_lam) / 2.0
        s = total_at(lam)
        if abs(s - total) < 1e-12:
            break
        if s > total:
            lo_lam = lam
        else:
            hi_lam = lam
    return [min(max(v[i] - lam, lo[i]), hi[i]) for i in range(n)]


def _matvec(m: Sequence[Sequence[float]], w: Sequence[float]) -> list[float]:
    return [sum(m[i][j] * w[j] for j in range(len(w))) for i in range(len(w))]


def _quad(w: Sequence[float], m: Sequence[Sequence[float]]) -> float:
    mv = _matvec(m, w)
    return sum(w[i] * mv[i] for i in range(len(w)))


def optimize(
    symbols: Sequence[str],
    *,
    expected_returns: Optional[Sequence[float]] = None,
    covariance: Optional[Sequence[Sequence[float]]] = None,
    current_weights: Optional[Sequence[float]] = None,
    method: str = "min_variance",
    risk_aversion: float = 1.0,
    min_weights: Optional[Sequence[float]] = None,
    max_weights: Optional[Sequence[float]] = None,
    turnover_cap: Optional[float] = None,
    iterations: int = 500,
    step: float = 0.01,
) -> dict[str, Any]:
    n = len(symbols)
    if n == 0:
        return {"available": False, "reason": "no symbols"}
    if method not in METHODS:
        method = "min_variance"

    cov = [list(map(float, row)) for row in covariance] if covariance else [
        [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)
    ]
    mu = list(map(float, expected_returns)) if expected_returns else [0.0] * n
    lo = list(map(float, min_weights)) if min_weights else [0.0] * n
    hi = list(map(float, max_weights)) if max_weights else [1.0] * n
    w0 = list(map(float, current_weights)) if current_weights else [1.0 / n] * n

    if method == "inverse_volatility":
        vols = [math.sqrt(max(cov[i][i], 1e-12)) for i in range(n)]
        raw = [1.0 / v for v in vols]
        s = sum(raw) or 1.0
        weights = [r / s for r in raw]
        weights = _project_bounded_simplex(weights, lo, hi)
    else:
        weights = _project_bounded_simplex([1.0 / n] * n, lo, hi)
        for _ in range(iterations):
            grad = _matvec(cov, weights)
            if method == "mean_variance":
                grad = [risk_aversion * grad[i] - mu[i] for i in range(n)]
            nxt = [weights[i] - step * grad[i] for i in range(n)]
            weights = _project_bounded_simplex(nxt, lo, hi)

    # Turnover cap: if the move from the current allocation exceeds it, scale back.
    raw_turnover = sum(abs(weights[i] - w0[i]) for i in range(n))
    applied_turnover = raw_turnover
    if turnover_cap is not None and raw_turnover > turnover_cap and raw_turnover > 0:
        scale = turnover_cap / raw_turnover
        weights = [w0[i] + scale * (weights[i] - w0[i]) for i in range(n)]
        weights = _project_bounded_simplex(weights, lo, hi)
        applied_turnover = sum(abs(weights[i] - w0[i]) for i in range(n))

    variance = _quad(weights, cov)
    exp_return = sum(weights[i] * mu[i] for i in range(n))
    return {
        "available": True,
        "method": method,
        "weights": {symbols[i]: round(weights[i], 8) for i in range(n)},
        "expectedReturn": round(exp_return, 8),
        "variance": round(variance, 12),
        "volatility": round(math.sqrt(max(variance, 0.0)), 8),
        "turnover": round(applied_turnover, 8),
        "turnoverCapped": bool(turnover_cap is not None and raw_turnover > turnover_cap),
        "boundsRespected": all(lo[i] - 1e-9 <= weights[i] <= hi[i] + 1e-9 for i in range(n)),
        "fullyInvested": abs(sum(weights) - 1.0) < 1e-6,
    }


__all__ = ["optimize", "METHODS"]
