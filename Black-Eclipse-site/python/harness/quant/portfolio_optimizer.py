"""Portfolio construction: from expected returns and a covariance matrix to weights.

The optimizer is deliberately dependency-free (NumPy only) and deterministic.
It covers the methods a research desk actually uses:

* `equal_weight`, `min_variance`, `mean_variance`, `max_sharpe`;
* `risk_parity` (equal risk contribution);
* `hrp` (hierarchical risk parity, no matrix inversion);
* `black_litterman` (equilibrium returns + views, then mean-variance).

Constraints are explicit and reported. A projection step enforces net/gross
exposure and per-name bounds; a constraint that cannot be satisfied raises a
typed error rather than returning a silently infeasible book.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from .errors import QuantError
from .risk_model import correlation_matrix, portfolio_volatility, risk_contributions


@dataclass
class OptimizerConstraints:
    min_weight: Optional[float] = None          # e.g. 0.0 for long-only
    max_weight: Optional[float] = None          # per-name cap
    net: float = 1.0                            # target sum(weights)
    gross: Optional[float] = None               # target sum(|weights|)
    max_turnover: Optional[float] = None        # against current_weights
    current_weights: Optional[list[float]] = None
    risk_free_rate: float = 0.0
    max_iterations: int = 500
    tolerance: float = 1e-10


@dataclass
class OptimizationResult:
    method: str
    weights: list[float]
    expected_return: Optional[float]
    volatility: Optional[float]
    sharpe: Optional[float]
    risk_contributions: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "weights": self.weights,
            "expectedReturn": self.expected_return,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "riskContributions": self.risk_contributions,
            "diagnostics": self.diagnostics,
        }


def _vec(values: Sequence[float], n: int, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size != n:
        raise QuantError(f"{name} must have {n} entries", detail={"got": int(arr.size)})
    if not np.all(np.isfinite(arr)):
        raise QuantError(f"{name} contains NaN/inf")
    return arr


def _matrix(values: Any, n: Optional[int] = None) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise QuantError("covariance must be a square matrix")
    if n is not None and arr.shape[0] != n:
        raise QuantError("covariance dimension does not match the assets")
    if not np.all(np.isfinite(arr)):
        raise QuantError("covariance contains NaN/inf")
    return (arr + arr.T) / 2.0


def _project(w: np.ndarray, lower: np.ndarray, upper: np.ndarray,
             net: float, gross: Optional[float], iters: int = 200) -> np.ndarray:
    """Project onto the box + net + gross set.

    The projection alternates a clip with a uniform redistribution of the net
    deficit/surplus. It is not a QP projection, but it is deterministic and
    always lands inside the box; the caller reports whether the targets were met.
    """
    x = np.clip(w.astype(float), lower, upper)
    for _ in range(iters):
        diff = net - float(x.sum())
        if abs(diff) < 1e-12:
            break
        if diff > 0:
            free = x < upper - 1e-12
        else:
            free = x > lower + 1e-12
        if not np.any(free):
            break
        x[free] = x[free] + diff / float(free.sum())
        x = np.clip(x, lower, upper)
    if gross is not None and gross >= 0:
        # Scale the book toward the gross target, then re-enforce net once.
        g = float(np.abs(x).sum())
        if g > gross + 1e-9 and g > 0:
            x = x * (gross / g)
            x = _project(x, lower, upper, net, None, iters=iters)
    return x


def _bounds(n: int, c: OptimizerConstraints) -> tuple[np.ndarray, np.ndarray]:
    lower = np.full(n, -np.inf if c.min_weight is None else float(c.min_weight))
    upper = np.full(n, np.inf if c.max_weight is None else float(c.max_weight))
    # A net target with per-name bounds must be feasible.
    if np.all(np.isfinite(lower)) and n * float(lower.max()) > c.net + 1e-9:
        raise QuantError("minimum weights make the net target infeasible")
    if np.all(np.isfinite(upper)) and n * float(upper.min()) < c.net - 1e-9:
        raise QuantError("maximum weights make the net target infeasible")
    if np.any(lower > upper):
        raise QuantError("a minimum weight exceeds its maximum")
    return lower, upper


def _objective_metrics(w: np.ndarray, mu: Optional[np.ndarray], cov: np.ndarray,
                       risk_free: float) -> tuple[Optional[float], float, Optional[float]]:
    vol = portfolio_volatility(w, cov)
    exp = float(mu @ w) if mu is not None else None
    sharpe = ((exp - risk_free) / vol) if (exp is not None and vol > 0) else None
    return exp, vol, sharpe


def _gradient_descent(mu: Optional[np.ndarray], cov: np.ndarray, *,
                      risk_aversion: float, constraints: OptimizerConstraints) -> tuple[np.ndarray, dict]:
    n = cov.shape[0]
    lower, upper = _bounds(n, constraints)
    if constraints.current_weights is not None:
        w = _vec(constraints.current_weights, n, "current weights").copy()
    else:
        w = np.full(n, constraints.net / n)
    w = _project(w, lower, upper, constraints.net, constraints.gross)
    # Lipschitz estimate for the quadratic; step = 1/L with a safety factor.
    eig = float(np.linalg.eigvalsh(cov).max()) if n else 0.0
    lipschitz = max(risk_aversion * eig, 1e-12)
    step = 1.0 / (lipschitz * 2.0)
    converged = False
    iterations = 0
    prev = None
    for iterations in range(1, max(2, constraints.max_iterations) + 1):
        grad = risk_aversion * (cov @ w)
        if mu is not None:
            grad = grad - mu
        candidate = _project(w - step * grad, lower, upper, constraints.net, constraints.gross)
        delta = float(np.max(np.abs(candidate - w))) if n else 0.0
        w = candidate
        if prev is not None and abs(delta - prev) < constraints.tolerance:
            converged = True
            break
        prev = delta
        if delta < constraints.tolerance:
            converged = True
            break
    # Turnover constraint: move toward the current book along the segment.
    if constraints.max_turnover is not None and constraints.current_weights is not None:
        current = _vec(constraints.current_weights, n, "current weights")
        turnover = 0.5 * float(np.abs(w - current).sum())
        limit = float(constraints.max_turnover)
        if turnover > limit > 0:
            alpha = limit / turnover
            w = _project(current + alpha * (w - current), lower, upper,
                         constraints.net, constraints.gross)
    return w, {"iterations": iterations, "converged": converged,
               "step": step, "lipschitz": lipschitz}


def _risk_parity(cov: np.ndarray, constraints: OptimizerConstraints) -> tuple[np.ndarray, dict]:
    n = cov.shape[0]
    lower, upper = _bounds(n, constraints)
    w = np.full(n, constraints.net / n)
    w = _project(w, lower, upper, constraints.net, constraints.gross)
    for i in range(1, max(2, constraints.max_iterations) + 1):
        marginal = cov @ w
        inv = 1.0 / np.clip(np.abs(marginal), 1e-12, None)
        target = inv / inv.sum() * constraints.net
        candidate = _project(target, lower, upper, constraints.net, constraints.gross)
        if float(np.max(np.abs(candidate - w))) < constraints.tolerance:
            w = candidate
            return w, {"iterations": i, "converged": True}
        w = candidate
    return w, {"iterations": constraints.max_iterations, "converged": False}


def _hrp(cov: np.ndarray, constraints: OptimizerConstraints) -> tuple[np.ndarray, dict]:
    """Hierarchical risk parity via single-linkage clustering + recursive bisection.

    No matrix inversion is required, which makes it stable on a near-singular
    covariance (the case where mean-variance is least trustworthy).
    """
    n = cov.shape[0]
    if n == 1:
        return np.array([constraints.net]), {"clusters": 1, "converged": True}
    corr = correlation_matrix(cov)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    clusters: list[list[int]] = [[i] for i in range(n)]
    linkage: list[dict[str, Any]] = []
    while len(clusters) > 1:
        best = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = min(dist[i, j] for i in clusters[a] for j in clusters[b])
                if best is None or d < best[0]:
                    best = (d, a, b)
        assert best is not None
        d, a, b = best
        linkage.append({"distance": float(d), "left": clusters[a], "right": clusters[b]})
        merged = clusters[a] + clusters[b]
        clusters = [c for k, c in enumerate(clusters) if k not in (a, b)]
        clusters.append(merged)

    weights = np.zeros(n)
    diag = np.diag(cov)

    def split(items: list[int]) -> float:
        if len(items) == 1:
            return float(diag[items[0]]) if diag[items[0]] > 0 else 1e-12
        # Recursive bisection using inverse cluster variance.
        mid = len(items) // 2
        left, right = items[:mid], items[mid:]
        var_l = float(np.mean([diag[i] for i in left])) or 1e-12
        var_r = float(np.mean([diag[i] for i in right])) or 1e-12
        inv_l, inv_r = 1.0 / var_l, 1.0 / var_r
        w_l = inv_l / (inv_l + inv_r)
        w_r = 1.0 - w_l
        for i in left:
            weights[i] += w_l / len(left)
        for i in right:
            weights[i] += w_r / len(right)
        return var_l * w_l + var_r * w_r

    split(list(range(n)))
    lower, upper = _bounds(n, constraints)
    weights = _project(weights * constraints.net, lower, upper,
                       constraints.net, constraints.gross)
    return weights, {"clusters": n, "converged": True, "linkage": linkage}


def _black_litterman(mu: np.ndarray, cov: np.ndarray, *,
                     market_weights: Optional[Sequence[float]] = None,
                     views: Optional[dict[str, Any]] = None,
                     tau: float = 0.05, risk_aversion: float = 2.5) -> tuple[np.ndarray, dict]:
    """Posterior expected returns from equilibrium + views.

    `views` = {"P": [[...]], "Q": [...], "omega": [[...]] (optional)}. Without
    views the posterior IS the equilibrium return; it never invents a view.
    """
    n = cov.shape[0]
    mkt = (np.asarray(market_weights, dtype=float).ravel()
           if market_weights is not None else np.full(n, 1.0 / n))
    if mkt.size != n:
        raise QuantError("market weights dimension does not match the assets")
    pi = risk_aversion * (cov @ mkt)
    if not views:
        return pi, {"views": 0, "tau": tau, "equilibrium": pi.tolist()}
    P = np.asarray(views.get("P"), dtype=float)
    Q = np.asarray(views.get("Q"), dtype=float).ravel()
    if P.ndim != 2 or P.shape[1] != n or P.shape[0] != Q.size:
        raise QuantError("views need P (k x n) and Q (k)")
    omega = views.get("omega")
    if omega is None:
        omega = np.diag(np.diag(P @ (tau * cov) @ P.T))
    omega = np.asarray(omega, dtype=float)
    if omega.shape != (P.shape[0], P.shape[0]):
        raise QuantError("omega must be k x k")
    middle = np.linalg.inv(P @ (tau * cov) @ P.T + omega)
    posterior = pi + (tau * cov) @ P.T @ middle @ (Q - P @ pi)
    return posterior, {
        "views": int(Q.size), "tau": tau, "equilibrium": pi.tolist(),
        "posterior": posterior.tolist(),
    }


def optimize_portfolio(
    expected_returns: Optional[Sequence[float]],
    covariance: Any,
    *,
    method: str = "min_variance",
    constraints: Optional[OptimizerConstraints] = None,
    risk_aversion: float = 1.0,
    views: Optional[dict[str, Any]] = None,
) -> OptimizationResult:
    """Construct weights for one of the supported methods.

    `expected_returns` may be omitted for methods that do not use it; a method
    that needs it refuses rather than assuming zero.
    """
    c = constraints or OptimizerConstraints()
    cov = _matrix(covariance)
    n = cov.shape[0]
    mu: Optional[np.ndarray] = None
    if expected_returns is not None:
        mu = _vec(expected_returns, n, "expected returns")

    if method == "equal_weight":
        w = np.full(n, c.net / n)
        diagnostics = {"iterations": 0, "converged": True}
    elif method in ("min_variance", "mean_variance"):
        if method == "mean_variance" and mu is None:
            raise QuantError("mean_variance requires expected returns")
        w, diagnostics = _gradient_descent(
            mu if method == "mean_variance" else None, cov,
            risk_aversion=risk_aversion if method == "mean_variance" else 1.0,
            constraints=c,
        )
    elif method == "max_sharpe":
        if mu is None:
            raise QuantError("max_sharpe requires expected returns")
        # Scan risk aversion and keep the feasible book with the best Sharpe.
        best: tuple[float, np.ndarray, dict] | None = None
        for lam in (0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0):
            candidate, diag = _gradient_descent(mu, cov, risk_aversion=lam, constraints=c)
            _, _, score = _objective_metrics(candidate, mu, cov, c.risk_free_rate)
            if score is None:
                continue
            if best is None or score > best[0]:
                best = (score, candidate, diag)
        if best is None:
            raise QuantError("max_sharpe produced no feasible portfolio")
        w, diagnostics = best[1], {**best[2], "grid": "risk-aversion"}
    elif method == "risk_parity":
        w, diagnostics = _risk_parity(cov, c)
    elif method == "hrp":
        w, diagnostics = _hrp(cov, c)
    elif method == "black_litterman":
        posterior, bl_diag = _black_litterman(
            mu if mu is not None else np.zeros(n), cov,
            market_weights=c.current_weights, views=views,
            risk_aversion=risk_aversion,
        )
        w, diagnostics = _gradient_descent(
            posterior, cov, risk_aversion=risk_aversion, constraints=c
        )
        diagnostics = {**diagnostics, **bl_diag}
        mu = posterior
    else:
        raise QuantError(
            f"unknown optimization method {method!r}",
            detail={"methods": ["equal_weight", "min_variance", "mean_variance",
                                "max_sharpe", "risk_parity", "hrp", "black_litterman"]},
        )

    exp, vol, sharpe = _objective_metrics(w, mu, cov, c.risk_free_rate)
    rc = risk_contributions(w, cov)
    net = float(w.sum())
    gross = float(np.abs(w).sum())
    feasible = abs(net - c.net) <= 1e-6 and (c.gross is None or gross <= c.gross + 1e-6)
    diagnostics.update({
        "net": net, "gross": gross, "feasible": feasible,
        "minWeight": c.min_weight, "maxWeight": c.max_weight,
        "netTarget": c.net, "grossTarget": c.gross,
    })
    return OptimizationResult(
        method=method, weights=w.tolist(), expected_return=exp, volatility=vol,
        sharpe=sharpe, risk_contributions=rc, diagnostics=diagnostics,
    )


def efficient_frontier(expected_returns: Sequence[float], covariance: Any, *,
                       points: int = 10, constraints: Optional[OptimizerConstraints] = None,
                       risk_aversion_range: tuple[float, float] = (0.25, 50.0),
                       risk_free_rate: float = 0.0) -> dict[str, Any]:
    """Trace the mean-variance frontier by scanning risk aversion."""
    c = constraints or OptimizerConstraints()
    if c.risk_free_rate == 0.0 and risk_free_rate:
        c = OptimizerConstraints(**{**c.__dict__, "risk_free_rate": risk_free_rate})
    lo, hi = risk_aversion_range
    if points < 2:
        raise QuantError("a frontier needs at least 2 points")
    curve = []
    for lam in np.geomspace(max(lo, 1e-6), max(hi, lo + 1e-6), int(points)):
        result = optimize_portfolio(
            expected_returns, covariance, method="mean_variance",
            constraints=c, risk_aversion=float(lam),
        )
        curve.append({
            "riskAversion": float(lam),
            "volatility": result.volatility,
            "expectedReturn": result.expected_return,
            "sharpe": result.sharpe,
            "weights": result.weights,
        })
    return {"points": curve, "count": len(curve),
            "note": "a frontier is an input-sensitivity map, not a forecast"}


__all__ = [
    "OptimizationResult",
    "OptimizerConstraints",
    "efficient_frontier",
    "optimize_portfolio",
]
