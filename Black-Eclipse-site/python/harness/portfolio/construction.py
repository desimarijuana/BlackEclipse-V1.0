"""Portfolio construction engine (§11–§22).

A single shared solver path for every allocation algorithm: validated inputs, an
explicit constraint set, a documented objective, a numerical status, and an
INDEPENDENT validation of the returned weights. The validator never trusts the
solver's own bookkeeping — it re-checks the budget, bounds, group caps, factor
caps and turnover from scratch.

Solver: projected gradient descent with an exact projection onto the constraint
polytope via Dykstra's alternating projections. Each projection is exact
(bounded-simplex and halfspace projections), so the method is a genuine
constrained optimizer, not a heuristic post-hoc clamp.

Statuses (`SolverStatus`) mirror §14: OPTIMAL, OPTIMAL_INACCURATE,
FEASIBLE_LIMIT_REACHED, INFEASIBLE, NUMERICAL_FAILURE, SOLVER_ERROR, CANCELLED.

Methods: equal_weight, benchmark_weight, min_variance, mean_variance,
risk_parity, volatility_target, black_litterman, factor_constrained, and an
efficient frontier. Every method returns the same envelope with `weights`,
`status`, `validation`, `metrics` and `diagnostics`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Optional, Sequence

import numpy as np

from .risk import TRADING_DAYS, _norm_ppf

METHODS = (
    "equal_weight", "benchmark_weight", "min_variance", "mean_variance",
    "risk_parity", "volatility_target", "black_litterman", "factor_constrained",
)


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    OPTIMAL_INACCURATE = "OPTIMAL_INACCURATE"
    FEASIBLE_LIMIT_REACHED = "FEASIBLE_LIMIT_REACHED"
    INFEASIBLE = "INFEASIBLE"
    UNBOUNDED = "UNBOUNDED"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    SOLVER_ERROR = "SOLVER_ERROR"
    CANCELLED = "CANCELLED"


@dataclass
class LinearConstraint:
    """A linear constraint `minimum <= coeffᵀw <= maximum` over a scope."""
    name: str
    scope: dict[str, float] = field(default_factory=dict)  # symbol -> coefficient
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    hard: bool = True

    def coeffs(self, symbols: Sequence[str]) -> np.ndarray:
        return np.array([float(self.scope.get(s, 0.0)) for s in symbols], dtype=float)


@dataclass
class ConstraintSet:
    symbols: list[str]
    budget: float = 1.0
    long_only: bool = True
    fully_invested: bool = True
    min_weights: Optional[dict[str, float]] = None
    max_weights: Optional[dict[str, float]] = None
    groups: list[LinearConstraint] = field(default_factory=list)
    factor_constraints: list[LinearConstraint] = field(default_factory=list)
    turnover_cap: Optional[float] = None
    current_weights: Optional[dict[str, float]] = None
    transaction_cost_rate: float = 0.0
    # Risk caps (per-period, matching the covariance units). `max_var` is a
    # parametric (normal) VaR cap mapped to an equivalent volatility cap.
    max_volatility: Optional[float] = None
    max_var: Optional[float] = None
    var_confidence: float = 0.95
    # Cardinality / tradability (enforced as a documented iterative heuristic).
    max_positions: Optional[int] = None
    min_position_weight: Optional[float] = None
    lot_size: Optional[float] = None
    tolerance: float = 1e-6

    def box(self) -> tuple[np.ndarray, np.ndarray]:
        lo = np.array([
            float((self.min_weights or {}).get(s, 0.0 if self.long_only else -self.budget * 10))
            for s in self.symbols
        ], dtype=float)
        hi = np.array([
            float((self.max_weights or {}).get(s, self.budget))
            for s in self.symbols
        ], dtype=float)
        return lo, hi

    def linear(self) -> list[tuple[str, np.ndarray, float, float, bool]]:
        out: list[tuple[str, np.ndarray, float, float, bool]] = []
        for c in list(self.groups) + list(self.factor_constraints):
            out.append((
                c.name, c.coeffs(self.symbols),
                c.minimum if c.minimum is not None else -math.inf,
                c.maximum if c.maximum is not None else math.inf,
                c.hard,
            ))
        return out


# ── Projection ────────────────────────────────────────────────────────────────

def project_bounded_simplex(
    v: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float, *, iters: int = 100,
) -> np.ndarray:
    """Exact Euclidean projection onto {w : Σw = total, lo ≤ w ≤ hi}."""
    if lo.sum() > total + 1e-9 or hi.sum() < total - 1e-9:
        return np.clip(v, lo, hi)
    low = float((v - hi).min()) - 1.0
    high = float((v - lo).max()) + 1.0
    lam = 0.0
    for _ in range(iters):
        lam = (low + high) / 2.0
        s = float(np.clip(v - lam, lo, hi).sum())
        if abs(s - total) < 1e-13:
            break
        if s > total:
            low = lam
        else:
            high = lam
    return np.clip(v - lam, lo, hi)


def project(
    v: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float,
    linear: Sequence[tuple[str, np.ndarray, float, float, bool]], *, iters: int = 400,
) -> np.ndarray:
    """Dykstra projection onto the intersection of the bounded simplex and each
    linear halfspace constraint."""
    x = project_bounded_simplex(v, lo, hi, total)
    inc: list[np.ndarray] = [np.zeros_like(v) for _ in range(1 + len(linear))]
    for _ in range(iters):
        y = project_bounded_simplex(x + inc[0], lo, hi, total)
        inc[0] = x + inc[0] - y
        x = y
        for k, (_name, a, lb, ub, _hard) in enumerate(linear, start=1):
            ax = float(a @ x)
            corrected = x
            if ax > ub and ub != math.inf:
                corrected = x - ((ax - ub) / float(a @ a)) * a
            elif ax < lb and lb != -math.inf:
                corrected = x + ((lb - ax) / float(a @ a)) * a
            inc[k] = x + inc[k] - corrected
            x = corrected
    return x


def feasibility_violation(
    w: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float,
    linear: Sequence[tuple[str, np.ndarray, float, float, bool]],
) -> float:
    worst = max(0.0, float((lo - w).max()), float((w - hi).max()))
    if abs(float(w.sum()) - total) > 1e-6:
        worst = max(worst, abs(float(w.sum()) - total))
    for _name, a, lb, ub, _hard in linear:
        ax = float(a @ w)
        if ub != math.inf:
            worst = max(worst, ax - ub)
        if lb != -math.inf:
            worst = max(worst, lb - ax)
    return worst


# ── Independent validation ────────────────────────────────────────────────────

def validate_constraints(
    weights: dict[str, float], constraints: ConstraintSet,
    covariance: Optional[Sequence[Sequence[float]]] = None,
) -> dict[str, Any]:
    """Independently re-check every constraint against the returned weights."""
    tol = constraints.tolerance
    checks: list[dict[str, Any]] = []
    present = {s: float(weights.get(s, 0.0)) for s in constraints.symbols}

    total = sum(present.values())
    if constraints.fully_invested:
        checks.append({"name": "budget", "passed": abs(total - constraints.budget) <= max(tol, 1e-6),
                       "value": round(total, 10), "target": constraints.budget})

    lo, hi = constraints.box()
    for i, s in enumerate(constraints.symbols):
        if present[s] < lo[i] - tol or present[s] > hi[i] + tol:
            checks.append({"name": f"bounds:{s}", "passed": False,
                           "value": round(present[s], 10),
                           "bound": [round(float(lo[i]), 10), round(float(hi[i]), 10)]})
    if all(c["name"] != "bounds" for c in checks):
        checks.append({"name": "bounds", "passed": True})

    if constraints.long_only:
        neg = [s for s, w in present.items() if w < -tol]
        checks.append({"name": "long_only", "passed": not neg, "violations": neg})

    for c in constraints.groups:
        exposure = sum(present[s] * c.scope.get(s, 0.0) for s in constraints.symbols)
        ok = True
        if c.maximum is not None and exposure > c.maximum + tol:
            ok = False
        if c.minimum is not None and exposure < c.minimum - tol:
            ok = False
        checks.append({"name": f"group:{c.name}", "passed": ok, "value": round(exposure, 10),
                       "bound": [c.minimum, c.maximum]})

    for c in constraints.factor_constraints:
        exposure = sum(present[s] * c.scope.get(s, 0.0) for s in constraints.symbols)
        ok = True
        if c.maximum is not None and exposure > c.maximum + tol:
            ok = False
        if c.minimum is not None and exposure < c.minimum - tol:
            ok = False
        checks.append({"name": f"factor:{c.name}", "passed": ok, "value": round(exposure, 10),
                       "bound": [c.minimum, c.maximum]})

    if constraints.turnover_cap is not None and constraints.current_weights is not None:
        current = {s: float((constraints.current_weights or {}).get(s, 0.0)) for s in constraints.symbols}
        turnover = 0.5 * sum(abs(present[s] - current[s]) for s in constraints.symbols)
        checks.append({"name": "turnover", "passed": turnover <= constraints.turnover_cap + tol,
                       "value": round(turnover, 10), "target": constraints.turnover_cap})

    cap = volatility_cap(constraints)
    if cap is not None and covariance is not None:
        w = np.array([present[s] for s in constraints.symbols])
        vol = _portfolio_vol(w, _prepare(constraints.symbols, covariance))
        checks.append({"name": "volatility_cap", "passed": vol <= cap + tol,
                       "value": round(vol, 10), "target": round(cap, 10)})

    if constraints.max_positions is not None:
        active = [s for s, w in present.items() if abs(w) > 1e-8]
        checks.append({"name": "max_positions", "passed": len(active) <= constraints.max_positions,
                       "value": len(active), "target": constraints.max_positions})

    if constraints.min_position_weight is not None:
        below = [s for s, w in present.items() if 1e-8 < w < constraints.min_position_weight - tol]
        checks.append({"name": "min_position_weight", "passed": not below, "violations": below,
                       "target": constraints.min_position_weight})

    if constraints.lot_size:
        lot = constraints.lot_size
        off = [s for s, w in present.items()
               if abs(w) > 1e-8 and abs(w / lot - round(w / lot)) > 1e-4]
        checks.append({"name": "lot_size", "passed": not off, "violations": off, "lot": lot})

    violations = [c for c in checks if not c["passed"]]
    return {"satisfied": not violations, "checks": checks, "violations": violations,
            "tolerance": tol}


# ── Solver ────────────────────────────────────────────────────────────────────

def _projected_gradient(
    objective: Callable[[np.ndarray], float],
    gradient: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    lo: np.ndarray, hi: np.ndarray, total: float,
    linear: Sequence[tuple[str, np.ndarray, float, float, bool]],
    *, iterations: int = 1500, tolerance: float = 1e-10, step0: float = 1.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    x = project(x0, lo, hi, total, linear)
    step = step0
    converged = False
    for it in range(iterations):
        g = gradient(x)
        if not np.all(np.isfinite(g)):
            return x, {"converged": False, "iterations": it, "reason": "non-finite gradient"}
        accepted = False
        for _ in range(40):
            x_new = project(x - step * g, lo, hi, total, linear)
            delta = x - x_new
            decrease = float(g @ delta)
            if objective(x_new) <= objective(x) - decrease + (np.dot(delta, delta) / (2 * step)):
                accepted = True
                break
            step *= 0.5
        if not accepted:
            return x, {"converged": False, "iterations": it, "reason": "line search failed"}
        move = float(np.linalg.norm(x_new - x))
        x = x_new
        step = min(step * 1.2, 1e6)
        if move < tolerance:
            converged = True
            break
    return x, {"converged": converged, "iterations": it + 1, "step": step}


def volatility_cap(constraints: ConstraintSet) -> Optional[float]:
    """The effective per-period volatility ceiling, from `max_volatility` and/or
    a parametric `max_var` (VaR loss = z·σ, so σ_max = VaR_max / z)."""
    cap = constraints.max_volatility
    if constraints.max_var is not None:
        z = abs(_norm_ppf(1.0 - constraints.var_confidence))
        var_cap = constraints.max_var / z if z > 0 else None
        cap = var_cap if cap is None else min(cap, var_cap)
    return cap


def _quad_form(w: np.ndarray, cov: np.ndarray) -> float:
    return float(w @ cov @ w)


def _portfolio_vol(w: np.ndarray, cov: np.ndarray) -> float:
    return math.sqrt(max(_quad_form(w, cov), 0.0))


def _result(
    symbols: Sequence[str], weights: np.ndarray, constraints: ConstraintSet, status: SolverStatus,
    meta: dict[str, Any], cov: Optional[np.ndarray] = None, mu: Optional[np.ndarray] = None,
    diagnostics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if status == SolverStatus.INFEASIBLE:
        return {
            "available": True, "status": status.value, "weights": {},
            "reason": (diagnostics or {}).get("reason", "the constraint set is infeasible"),
            "metrics": {}, "diagnostics": diagnostics or {},
        }
    weight_map = {s: round(float(weights[i]), 10) for i, s in enumerate(symbols)}
    validation = validate_constraints(weight_map, constraints,
                                      covariance=cov.tolist() if cov is not None else None)
    if status == SolverStatus.OPTIMAL and not validation["satisfied"]:
        status = SolverStatus.OPTIMAL_INACCURATE
    metrics: dict[str, Any] = {}
    if cov is not None:
        metrics["expectedVolatility"] = round(_portfolio_vol(weights, cov), 10)
    if cov is not None and mu is not None:
        metrics["expectedReturn"] = round(float(mu @ weights), 10)
    return {
        "available": True,
        "status": status.value,
        "weights": weight_map,
        "validation": validation,
        "metrics": metrics,
        "diagnostics": diagnostics or {},
        **meta,
    }


# ── Methods ───────────────────────────────────────────────────────────────────

def _prepare(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]],
) -> np.ndarray:
    cov = np.array(covariance, dtype=float)
    n = len(symbols)
    if cov.shape != (n, n):
        raise ValueError(f"covariance must be {n}x{n}, got {cov.shape}")
    return (cov + cov.T) / 2.0


def equal_weight(
    constraints: ConstraintSet, *, covariance: Optional[Sequence[Sequence[float]]] = None,
    expected_returns: Optional[Sequence[float]] = None,
) -> dict[str, Any]:
    n = len(constraints.symbols)
    raw = np.full(n, 1.0 / n)
    lo, hi = constraints.box()
    linear = constraints.linear()
    w = project(raw, lo, hi, constraints.budget, linear)
    unconstrained = bool(np.allclose(w, raw)) and not linear and constraints.fully_invested
    cov = _prepare(constraints.symbols, covariance) if covariance is not None else None
    mu = np.array(expected_returns, dtype=float) if expected_returns is not None else None
    meta = {"method": "equal_weight",
            "allocation": "equal" if unconstrained else "constrained_equal_weight"}
    return _result(constraints.symbols, w, constraints, SolverStatus.OPTIMAL, meta, cov, mu)


def benchmark_weight(
    constraints: ConstraintSet, benchmark_weights: dict[str, float],
    *, covariance: Optional[Sequence[Sequence[float]]] = None,
) -> dict[str, Any]:
    missing = [s for s in constraints.symbols if s not in benchmark_weights]
    if missing:
        return {"available": False, "status": SolverStatus.INFEASIBLE.value,
                "reason": f"benchmark weights missing for {missing}", "weights": {}}
    w = np.array([float(benchmark_weights[s]) for s in constraints.symbols])
    if w.sum() <= 0:
        return {"available": False, "status": SolverStatus.INFEASIBLE.value,
                "reason": "benchmark weights sum to zero", "weights": {}}
    w = w / w.sum() * constraints.budget
    cov = _prepare(constraints.symbols, covariance) if covariance is not None else None
    meta = {"method": "benchmark_weight", "allocation": "benchmark_replication"}
    return _result(constraints.symbols, w, constraints, SolverStatus.OPTIMAL, meta, cov)


def _solve_quadratic(
    symbols: Sequence[str], cov: np.ndarray, mu: Optional[np.ndarray], constraints: ConstraintSet,
    *, risk_aversion: float = 1.0,
) -> tuple[np.ndarray, SolverStatus, dict[str, Any]]:
    n = len(symbols)
    lo, hi = constraints.box()
    linear = constraints.linear()

    cost = max(0.0, float(getattr(constraints, "transaction_cost_rate", 0.0)))
    w0 = None
    if cost > 0 and constraints.current_weights:
        w0 = np.array([float((constraints.current_weights or {}).get(s, 0.0)) for s in symbols])
    vol_cap = volatility_cap(constraints)
    var_cap_sq = (vol_cap * vol_cap) if vol_cap is not None else None
    risk_penalty = 1e3 * max(1.0, float(np.linalg.norm(cov, 2)))

    def _excess(w: np.ndarray) -> float:
        if var_cap_sq is None:
            return 0.0
        return max(0.0, _quad_form(w, cov) - var_cap_sq)

    def objective(w: np.ndarray) -> float:
        val = 0.5 * risk_aversion * _quad_form(w, cov)
        if mu is not None:
            val -= float(mu @ w)
        if cost > 0 and w0 is not None:
            val += cost * float(np.abs(w - w0).sum())
        if var_cap_sq is not None:
            excess = _excess(w)
            val += risk_penalty * excess * excess
        return val

    def gradient(w: np.ndarray) -> np.ndarray:
        g = risk_aversion * (cov @ w)
        if mu is not None:
            g = g - mu
        if cost > 0 and w0 is not None:
            g = g + cost * np.sign(w - w0)
        if var_cap_sq is not None:
            excess = _excess(w)
            if excess > 0:
                g = g + risk_penalty * 2.0 * excess * 2.0 * (cov @ w)
        return g

    start = feasible_start(lo, hi, constraints.budget, linear)
    if start is None:
        return np.zeros(n), SolverStatus.INFEASIBLE, {"reason": "constraints are infeasible"}
    w, info = _projected_gradient(objective, gradient, start, lo, hi, constraints.budget, linear)
    if vol_cap is not None and _portfolio_vol(w, cov) > vol_cap + 1e-6:
        return w, SolverStatus.INFEASIBLE, {
            "reason": f"a per-period volatility cap of {vol_cap} is not reachable "
                      f"under the constraints (minimum achievable is "
                      f"{round(_portfolio_vol(w, cov), 8)})"}
    status = SolverStatus.OPTIMAL if info["converged"] else SolverStatus.FEASIBLE_LIMIT_REACHED
    diag: dict[str, Any] = {"solver": info}
    if cost > 0:
        diag["transactionCostRate"] = round(cost, 10)
    if vol_cap is not None:
        diag["volatilityCap"] = round(vol_cap, 10)
    return w, status, diag


def feasible_start(
    lo: np.ndarray, hi: np.ndarray, total: float,
    linear: Sequence[tuple[str, np.ndarray, float, float, bool]], *, tol: float = 1e-7,
) -> Optional[np.ndarray]:
    """A projection start guaranteed feasible, or None when the set is empty."""
    if lo.sum() > total + 1e-9 or hi.sum() < total - 1e-9:
        return None
    w = project(np.clip(np.full(len(lo), total / len(lo)), lo, hi), lo, hi, total, linear)
    if feasibility_violation(w, lo, hi, total, linear) > max(tol, 1e-6):
        return None
    return w


def _risk_parity_ccd(
    cov: np.ndarray, budgets: np.ndarray, *, iterations: int = 5000, tolerance: float = 1e-14,
) -> tuple[Optional[np.ndarray], dict[str, Any]]:
    """Exact risk-budgeting solution via cyclical coordinate descent.

    Solves the first-order conditions wᵢ(Σw)ᵢ = bᵢ directly (Griveau-Billion,
    Richard & Roncalli 2013). With Σbᵢ = 1 the solution is normalized so the
    portfolio variance equals 1 and Σwᵢ = 1.
    """
    n = len(budgets)
    w = np.full(n, 1.0 / n)
    for it in range(iterations):
        max_move = 0.0
        for i in range(n):
            a = float(cov[i][i])
            if a <= 0:
                return None, {"reason": f"non-positive variance for asset {i}"}
            q = float(sum(cov[i][j] * w[j] for j in range(n) if j != i))
            new_w = (-q + math.sqrt(q * q + 4.0 * a * float(budgets[i]))) / (2.0 * a)
            max_move = max(max_move, abs(new_w - w[i]))
            w[i] = new_w
        if max_move < tolerance:
            total = float(w.sum())
            if total > 0:
                w = w / total
            return w, {"iterations": it + 1, "maxMove": max_move,
                       "algorithm": "cyclical_coordinate_descent"}
    return None, {"reason": "did not converge within iteration budget"}


def min_variance(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]], constraints: ConstraintSet,
) -> dict[str, Any]:
    cov = _prepare(symbols, covariance)
    w, status, diag = _solve_quadratic(symbols, cov, None, constraints)
    return _result(symbols, w, constraints, status, {"method": "min_variance", "objective": "minimize wᵀΣw"},
                   cov, None, diag)


def mean_variance(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]],
    expected_returns: Sequence[float], constraints: ConstraintSet, *, risk_aversion: float = 1.0,
) -> dict[str, Any]:
    cov = _prepare(symbols, covariance)
    mu = np.array(expected_returns, dtype=float)
    if len(mu) != len(symbols):
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                "reason": "expected returns length must match symbols", "weights": {}}
    w, status, diag = _solve_quadratic(symbols, cov, mu, constraints, risk_aversion=risk_aversion)
    return _result(symbols, w, constraints, status,
                   {"method": "mean_variance", "riskAversion": risk_aversion,
                    "objective": "maximize wᵀμ − (λ/2)wᵀΣw"}, cov, mu, diag)


def risk_parity(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]], constraints: ConstraintSet,
    *, budgets: Optional[Sequence[float]] = None,
) -> dict[str, Any]:
    """Risk-budgeted allocation via the convex log-barrier formulation.

    Minimize ½wᵀΣw − Σ bᵢ ln(wᵢ). With bᵢ = 1/N the solution is the equal
    risk-contribution portfolio: each asset's component risk is σ²/N.
    """
    n = len(symbols)
    cov = _prepare(symbols, covariance)
    if constraints.long_only is False:
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                "reason": "risk parity requires a long-only constraint set", "weights": {}}
    b = np.array(budgets, dtype=float) if budgets is not None else np.full(n, 1.0 / n)
    if len(b) != n or b.sum() <= 0:
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                "reason": "risk budgets must be positive and match symbols", "weights": {}}
    b = b / b.sum()
    lo, hi = constraints.box()
    linear = constraints.linear()
    w, info = _risk_parity_ccd(cov, b)
    if w is None:
        return {"available": False, "status": SolverStatus.NUMERICAL_FAILURE.value,
                "reason": "risk-parity coordinate descent did not converge", "weights": {}}
    status = SolverStatus.OPTIMAL
    in_box = bool(np.all(w >= lo - 1e-9) and np.all(w <= hi + 1e-9))
    if not in_box or linear:
        # Bounds/groups bind: project the ERC solution onto the feasible set and
        # report the achieved (not assumed) risk budget deviation.
        w = project(w, lo, hi, constraints.budget, linear)
        status = SolverStatus.FEASIBLE_LIMIT_REACHED
    result = _result(symbols, w, constraints, status,
                     {"method": "risk_parity", "riskBudgets": {symbols[i]: round(float(b[i]), 8)
                                                               for i in range(n)}},
                     cov, None, {"solver": info})
    from .risk_engine import risk_contributions
    result["riskContributions"] = risk_contributions(
        {symbols[i]: float(w[i]) for i in range(n)}, cov.tolist(), names=list(symbols))
    return result


def volatility_target(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]], constraints: ConstraintSet,
    *, target: float, base_method: str = "risk_parity", periods: int = TRADING_DAYS,
) -> dict[str, Any]:
    """Scale a base allocation to a target annualized volatility.

    Scaling is only valid while the box bounds are respected; if the scaled
    portfolio violates a bound the method re-optimizes with a volatility penalty
    and reports the achieved volatility, which may differ from the target.
    """
    cov = _prepare(symbols, covariance)
    if base_method == "min_variance":
        base = min_variance(symbols, cov.tolist(), constraints)
    else:
        base = risk_parity(symbols, cov.tolist(), constraints)
    if not base.get("available"):
        return base
    w = np.array([base["weights"][s] for s in symbols], dtype=float)
    vol = _portfolio_vol(w, cov) * math.sqrt(periods)
    if vol <= 0:
        return {"available": False, "status": SolverStatus.NUMERICAL_FAILURE.value,
                "reason": "base allocation has zero volatility", "weights": base["weights"]}
    scale = target / vol
    scaled = w * scale
    lo, hi = constraints.box()
    meta = {"method": "volatility_target", "targetVolatility": target, "base": base_method,
            "annualization": periods}
    # A volatility-targeted portfolio is not required to be fully invested: the
    # residual is cash when scale < 1 and leverage when scale > 1. Validate
    # against the bound/group constraints with the budget check disabled.
    vt_constraints = replace(constraints, fully_invested=False)
    if np.all(scaled <= hi + 1e-9) and np.all(scaled >= lo - 1e-9):
        result = _result(symbols, scaled, vt_constraints, SolverStatus.OPTIMAL, meta, cov)
        result["metrics"]["achievedVolatility"] = round(_portfolio_vol(scaled, cov) * math.sqrt(periods), 10)
        result["scaling"] = "direct"
        result["cashWeight"] = round(1.0 - float(scaled.sum()), 10)
        result["grossExposure"] = round(float(np.abs(scaled).sum()), 10)
        return result
    # Bounds bind: re-optimize min-variance under the same constraints, then report
    # the achieved (not assumed) volatility. The target may be unreachable.
    w2, status, diag = _solve_quadratic(symbols, cov, None, constraints)
    vol2 = _portfolio_vol(w2, cov) * math.sqrt(periods)
    meta["scaling"] = "bounds_limited_reopt"
    result = _result(symbols, w2, vt_constraints, status, meta, cov, None, diag)
    result["metrics"]["achievedVolatility"] = round(vol2, 10)
    result["diagnostics"]["targetUnreachableUnderConstraints"] = abs(vol2 - target) > 1e-6
    result["diagnostics"]["achievedVolatility"] = round(vol2, 10)
    return result


def black_litterman(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]], market_weights: Sequence[float],
    constraints: ConstraintSet, *, risk_aversion: float = 2.5, tau: float = 0.05,
    views: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Black–Litterman equilibrium + posterior returns, then mean-variance.

    Equilibrium: Π = δΣw_mkt. Each view is a dict with ``scope`` (symbol→coeff),
    ``return`` (Q) and optional ``confidence`` (0–1, mapped to view variance).
    """
    n = len(symbols)
    cov = _prepare(symbols, covariance)
    w_mkt = np.array(market_weights, dtype=float)
    if len(w_mkt) != n or w_mkt.sum() <= 0:
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                "reason": "market weights must sum positive and match symbols", "weights": {}}
    w_mkt = w_mkt / w_mkt.sum()
    tau_cov = tau * cov
    pi = risk_aversion * (cov @ w_mkt)
    views = views or []
    if views:
        k = len(views)
        P = np.zeros((k, n))
        Q = np.zeros(k)
        omega = np.zeros((k, k))
        for i, v in enumerate(views):
            for s, c in (v.get("scope") or {}).items():
                if s in symbols:
                    P[i, symbols.index(s)] = float(c)
            Q[i] = float(v.get("return", 0.0))
            conf = float(v.get("confidence", 0.5))
            base_var = float(P[i] @ tau_cov @ P[i])
            omega[i, i] = base_var * (1.0 - min(max(conf, 0.0), 0.999)) / max(conf, 1e-6)
        inv_tau = np.linalg.inv(tau_cov)
        inv_omega = np.linalg.inv(np.maximum(omega, np.eye(k) * 1e-12))
        posterior_precision = inv_tau + P.T @ inv_omega @ P
        posterior_cov = np.linalg.inv(posterior_precision)
        mu_bl = posterior_cov @ (inv_tau @ pi + P.T @ inv_omega @ Q)
    else:
        posterior_cov = tau_cov
        mu_bl = pi
    w, status, diag = _solve_quadratic(symbols, cov, mu_bl, constraints, risk_aversion=risk_aversion)
    result = _result(symbols, w, constraints, status,
                     {"method": "black_litterman", "riskAversion": risk_aversion, "tau": tau,
                      "viewCount": len(views)}, cov, mu_bl, diag)
    result["equilibriumReturns"] = {symbols[i]: round(float(pi[i]), 10) for i in range(n)}
    result["posteriorReturns"] = {symbols[i]: round(float(mu_bl[i]), 10) for i in range(n)}
    result["marketWeights"] = {symbols[i]: round(float(w_mkt[i]), 8) for i in range(n)}
    result["posteriorCovariance"] = [[round(float(posterior_cov[i][j]), 12) for j in range(n)]
                                     for i in range(n)]
    if result["diagnostics"].get("solver"):
        result["diagnostics"]["solver"] = result["diagnostics"]["solver"]
    return result


def factor_constrained(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]],
    expected_returns: Sequence[float], constraints: ConstraintSet, *,
    risk_aversion: float = 1.0,
) -> dict[str, Any]:
    """Mean-variance with explicit factor-exposure caps (fp = Bᵀw)."""
    result = mean_variance(symbols, covariance, expected_returns, constraints,
                           risk_aversion=risk_aversion)
    if result.get("available"):
        result["method"] = "factor_constrained"
        result["factorExposures"] = {
            c.name: round(sum(result["weights"][s] * c.scope.get(s, 0.0) for s in symbols), 10)
            for c in constraints.factor_constraints
        }
    return result


def efficient_frontier(
    symbols: Sequence[str], covariance: Sequence[Sequence[float]],
    expected_returns: Sequence[float], constraints: ConstraintSet, *, points: int = 12,
) -> dict[str, Any]:
    """Trace the frontier by sweeping the risk-aversion parameter."""
    cov = _prepare(symbols, covariance)
    mu = np.array(expected_returns, dtype=float)
    frontier: list[dict[str, Any]] = []
    for i in range(points):
        lam = 10 ** (-2 + 3 * (i / max(points - 1, 1)))
        w, status, _ = _solve_quadratic(symbols, cov, mu, constraints, risk_aversion=lam)
        frontier.append({
            "riskAversion": round(lam, 6),
            "expectedReturn": round(float(mu @ w), 10),
            "volatility": round(_portfolio_vol(w, cov), 10),
            "status": status.value,
        })
    return {"available": True, "method": "efficient_frontier", "frontier": frontier,
            "symbols": list(symbols)}


def compare_allocations(
    *, symbols: Sequence[str], covariance: Sequence[Sequence[float]],
    expected_returns: Optional[Sequence[float]] = None,
    methods: Optional[Sequence[str]] = None,
    constraints_payload: Optional[dict[str, Any]] = None,
    benchmark_weights: Optional[dict[str, float]] = None,
    market_weights: Optional[Sequence[float]] = None,
    risk_budgets: Optional[Sequence[float]] = None,
    target_volatility: Optional[float] = None,
    risk_aversion: float = 1.0,
    views: Optional[list[dict[str, Any]]] = None,
    factor_loadings: Optional[dict[str, dict[str, float]]] = None,
    factor_constraints: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run several methods over the SAME inputs and compare on a common basis.

    Expected return and volatility are recomputed from the shared covariance /
    expected-return inputs for every method (so equal-weight is compared on the
    same yardstick as the optimizers). The comparison reports each method's
    status and whether its output passed independent validation; it does not
    declare a "winner".
    """
    from .risk import concentration

    methods = list(methods or ["equal_weight", "min_variance", "risk_parity"])
    cov = _prepare(symbols, covariance)
    mu = np.array(expected_returns, dtype=float) if expected_returns is not None else None
    rows: list[dict[str, Any]] = []
    for method in methods:
        r = construct(
            symbols=symbols, method=method, covariance=covariance,
            constraints_payload=constraints_payload or {}, expected_returns=expected_returns,
            benchmark_weights=benchmark_weights, market_weights=market_weights,
            risk_budgets=risk_budgets, risk_aversion=risk_aversion, target_volatility=target_volatility,
            views=views, factor_loadings=factor_loadings, factor_constraints=factor_constraints,
        )
        row: dict[str, Any] = {"method": method, "available": bool(r.get("available")),
                               "status": r.get("status")}
        weights = r.get("weights") or {}
        if weights:
            w = np.array([float(weights[s]) for s in symbols])
            row["expectedVolatility"] = round(_portfolio_vol(w, cov), 10)
            if mu is not None:
                row["expectedReturn"] = round(float(mu @ w), 10)
            row["concentration"] = concentration(list(weights.values()))
            row["constraintsSatisfied"] = bool(r.get("validation", {}).get("satisfied", False))
            if constraints_payload and constraints_payload.get("current_weights"):
                current = np.array([float((constraints_payload["current_weights"]).get(s, 0.0))
                                    for s in symbols])
                row["turnover"] = round(0.5 * float(np.abs(w - current).sum()), 10)
            row["weights"] = {s: round(float(weights[s]), 8) for s in symbols}
        rows.append(row)
    return {"available": True, "comparison": rows, "methods": methods,
            "commonInputs": {"symbols": list(symbols), "hasExpectedReturns": expected_returns is not None,
                             "hasConstraints": bool(constraints_payload)}}


# ── Envelope for the service/tool layer ───────────────────────────────────────

def construct(
    *,
    symbols: Sequence[str],
    method: str,
    covariance: Sequence[Sequence[float]],
    constraints_payload: Optional[dict[str, Any]] = None,
    expected_returns: Optional[Sequence[float]] = None,
    benchmark_weights: Optional[dict[str, float]] = None,
    market_weights: Optional[Sequence[float]] = None,
    risk_budgets: Optional[Sequence[float]] = None,
    risk_aversion: float = 1.0,
    target_volatility: Optional[float] = None,
    tau: float = 0.05,
    views: Optional[list[dict[str, Any]]] = None,
    factor_loadings: Optional[dict[str, dict[str, float]]] = None,
    factor_constraints: Optional[list[dict[str, Any]]] = None,
    periods: int = TRADING_DAYS,
) -> dict[str, Any]:
    """Build the constraint set from a plain payload, dispatch to a method, and
    return the validated envelope. This is the ONE entry point used by the
    service and the agent tool."""
    if not symbols:
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value, "reason": "no symbols"}
    constraints = build_constraints(list(symbols), constraints_payload or {},
                                    factor_loadings=factor_loadings,
                                    factor_constraints=factor_constraints)
    try:
        if method == "equal_weight":
            result = equal_weight(constraints, covariance=covariance,
                                  expected_returns=expected_returns)
        elif method == "benchmark_weight":
            result = benchmark_weight(constraints, benchmark_weights or {}, covariance=covariance)
        elif method == "min_variance":
            result = min_variance(symbols, covariance, constraints)
        elif method == "mean_variance":
            if expected_returns is None:
                return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                        "reason": "mean_variance requires expected_returns", "weights": {}}
            result = mean_variance(symbols, covariance, expected_returns, constraints,
                                   risk_aversion=risk_aversion)
        elif method == "risk_parity":
            result = risk_parity(symbols, covariance, constraints, budgets=risk_budgets)
        elif method == "volatility_target":
            if target_volatility is None:
                return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                        "reason": "volatility_target requires target_volatility", "weights": {}}
            result = volatility_target(symbols, covariance, constraints, target=target_volatility,
                                       periods=periods)
        elif method == "black_litterman":
            if market_weights is None:
                return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                        "reason": "black_litterman requires market_weights", "weights": {}}
            result = black_litterman(symbols, covariance, market_weights, constraints,
                                     risk_aversion=risk_aversion, tau=tau, views=views)
        elif method == "factor_constrained":
            if expected_returns is None:
                return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                        "reason": "factor_constrained requires expected_returns", "weights": {}}
            result = factor_constrained(symbols, covariance, expected_returns, constraints,
                                        risk_aversion=risk_aversion)
        elif method == "efficient_frontier":
            if expected_returns is None:
                return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                        "reason": "efficient_frontier requires expected_returns"}
            result = efficient_frontier(symbols, covariance, expected_returns, constraints)
        else:
            return {"available": False, "status": SolverStatus.SOLVER_ERROR.value,
                    "reason": f"unknown method {method!r}; methods are {METHODS}"}
    except (ValueError, np.linalg.LinAlgError) as exc:
        return {"available": False, "status": SolverStatus.SOLVER_ERROR.value, "reason": str(exc),
                "weights": {}}

    if result.get("available") and result.get("weights"):
        result = _apply_cardinality_and_lot(symbols, method, covariance, result, constraints)
    return result


def _apply_cardinality_and_lot(
    symbols: Sequence[str], method: str, covariance: Sequence[Sequence[float]],
    result: dict[str, Any], constraints: ConstraintSet,
) -> dict[str, Any]:
    """Enforce position-count / minimum-position / lot constraints.

    These are combinatorial and are not enforced by the continuous solver, so
    they are applied as a documented post-processing step: drop sub-minimum
    positions, keep the largest `max_positions`, re-project onto the convex
    constraints, then round to lot multiples. The result is re-validated
    independently and downgraded to `FEASIBLE_LIMIT_REACHED` (never `OPTIMAL`).
    Not supported for `benchmark_weight`, `black_litterman`, `volatility_target`
    or `efficient_frontier`, which do not accept this post-processing.
    """
    if constraints.max_positions is None and constraints.min_position_weight is None \
            and not constraints.lot_size:
        return result
    if method not in ("min_variance", "mean_variance", "risk_parity", "factor_constrained",
                      "equal_weight"):
        result["diagnostics"]["cardinalitySupported"] = False
        result["notes"] = "position/lot constraints are not supported for this method"
        return result

    n = len(symbols)
    w = np.array([float(result["weights"].get(s, 0.0)) for s in symbols])
    lo, hi = constraints.box()
    linear = constraints.linear()
    changed = False
    min_pos = constraints.min_position_weight or 0.0

    def _prune(vec: np.ndarray) -> np.ndarray:
        active = [i for i in range(n) if vec[i] > 1e-8]
        if min_pos > 0:
            drop = {i for i in active if vec[i] < min_pos}
            for i in drop:
                vec[i] = 0.0
        if constraints.max_positions is not None:
            active = [i for i in range(n) if vec[i] > 1e-8]
            if len(active) > constraints.max_positions:
                keep = set(sorted(active, key=lambda i: -vec[i])[:constraints.max_positions])
                for i in active:
                    if i not in keep:
                        vec[i] = 0.0
        return vec

    new = _prune(w.copy())
    if not np.allclose(new, w):
        changed = True
        new = project(new, lo, hi, constraints.budget, linear)
        new = _prune(new)
        new = project(new, lo, hi, constraints.budget, linear)

    if constraints.lot_size:
        lot = constraints.lot_size
        total_lots = round(float(new.sum()) / lot)
        if total_lots > 0 and abs(total_lots * lot - float(new.sum())) < 1e-6:
            q = np.round(new / lot)
            q = np.maximum(q, 0.0)
            diff = total_lots - int(q.sum())
            if diff != 0:
                idx = int(np.argmax(q))
                q[idx] = max(0.0, q[idx] + diff)
            rounded = q * lot
            if not np.allclose(rounded, new, atol=1e-6):
                changed = True
                new = rounded

    weight_map = {s: round(float(new[i]), 10) for i, s in enumerate(symbols)}
    cov = _prepare(symbols, covariance)
    result["weights"] = weight_map
    result["validation"] = validate_constraints(weight_map, constraints, covariance=cov.tolist())
    if cov is not None:
        result.setdefault("metrics", {})["expectedVolatility"] = round(_portfolio_vol(new, cov), 10)
    if changed:
        if result.get("status") == SolverStatus.OPTIMAL.value:
            result["status"] = SolverStatus.FEASIBLE_LIMIT_REACHED.value
        result["diagnostics"]["cardinalityHeuristic"] = True
    return result


def build_constraints(
    symbols: list[str], payload: dict[str, Any], *,
    factor_loadings: Optional[dict[str, dict[str, float]]] = None,
    factor_constraints: Optional[list[dict[str, Any]]] = None,
) -> ConstraintSet:
    groups: list[LinearConstraint] = []
    for g in payload.get("groups") or payload.get("sector_limits") or []:
        members = g.get("members") or {}
        scope = {s: float(members.get(s, 0.0)) for s in symbols}
        groups.append(LinearConstraint(name=str(g.get("name") or "group"), scope=scope,
                                       minimum=g.get("min"), maximum=g.get("max"),
                                       hard=bool(g.get("hard", True))))
    # A simple {sector: cap} mapping with an explicit membership map.
    membership = payload.get("group_membership") or payload.get("sector_membership") or {}
    for name, cap in (payload.get("group_caps") or {}).items():
        scope = {s: (1.0 if membership.get(s) == name else 0.0) for s in symbols}
        groups.append(LinearConstraint(name=str(name), scope=scope, maximum=float(cap)))

    factor_constraints_out: list[LinearConstraint] = []
    if factor_constraints and factor_loadings:
        for fc in factor_constraints:
            factor = fc.get("factor")
            scope = {s: float((factor_loadings.get(s) or {}).get(factor, 0.0)) for s in symbols}
            factor_constraints_out.append(LinearConstraint(
                name=str(factor), scope=scope, minimum=fc.get("min"), maximum=fc.get("max")))

    return ConstraintSet(
        symbols=list(symbols),
        budget=float(payload.get("budget", 1.0)),
        long_only=bool(payload.get("long_only", True)),
        fully_invested=bool(payload.get("fully_invested", True)),
        min_weights={k: float(v) for k, v in (payload.get("min_weights") or {}).items()},
        max_weights={k: float(v) for k, v in (payload.get("max_weights") or {}).items()},
        groups=groups,
        factor_constraints=factor_constraints_out,
        turnover_cap=(float(payload["turnover_cap"]) if payload.get("turnover_cap") is not None else None),
        current_weights=({k: float(v) for k, v in (payload.get("current_weights") or {}).items()}
                         or None),
        transaction_cost_rate=float(payload.get("transaction_cost")
                                    or payload.get("transaction_cost_rate") or 0.0),
        max_volatility=(float(payload["max_volatility"]) if payload.get("max_volatility") is not None
                        else None),
        max_var=(float(payload["max_var"]) if payload.get("max_var") is not None else None),
        var_confidence=float(payload.get("var_confidence") or 0.95),
        max_positions=(int(payload["max_positions"]) if payload.get("max_positions") is not None else None),
        min_position_weight=(float(payload["min_position_weight"])
                             if payload.get("min_position_weight") is not None else None),
        lot_size=(float(payload["lot_size"]) if payload.get("lot_size") is not None else None),
    )


__all__ = [
    "METHODS", "SolverStatus", "LinearConstraint", "ConstraintSet",
    "construct", "build_constraints", "validate_constraints",
    "project", "project_bounded_simplex", "feasible_start",
    "equal_weight", "benchmark_weight", "min_variance", "mean_variance",
    "risk_parity", "volatility_target", "black_litterman", "factor_constrained",
    "efficient_frontier", "compare_allocations",
]
