"""A small, dependency-free optimizer (Nelder–Mead simplex).

Used by GARCH(1,1) maximum-likelihood estimation and the two-state Gaussian HMM
fallback. Deterministic: the initial simplex is fixed from the start point, so a
fit is reproducible run to run.
"""

from __future__ import annotations

from typing import Callable, Sequence


def nelder_mead(
    func: Callable[[list[float]], float],
    x0: Sequence[float],
    *,
    step: float = 0.1,
    max_iter: int = 2000,
    tol: float = 1e-10,
) -> tuple[list[float], float, bool]:
    """Minimize `func` from `x0`. Returns (best_x, best_f, converged)."""
    n = len(x0)
    if n == 0:
        raise ValueError("x0 must be non-empty")

    def make_simplex(x: Sequence[float]) -> list[list[float]]:
        simplex = [list(x)]
        for i in range(n):
            point = list(x)
            point[i] += step if point[i] != 0 else 0.00025
            simplex.append(point)
        return simplex

    simplex = make_simplex(x0)
    fvals = [func(p) for p in simplex]
    alpha, gamma, rho, sigma = 1.0, 2.0, 0.5, 0.5
    converged = False

    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: fvals[i])
        simplex = [simplex[i] for i in order]
        fvals = [fvals[i] for i in order]
        if abs(fvals[-1] - fvals[0]) <= tol * (abs(fvals[0]) + tol):
            converged = True
            break

        centroid = [sum(simplex[i][j] for i in range(n)) / n for j in range(n)]
        worst = simplex[-1]
        xr = [centroid[j] + alpha * (centroid[j] - worst[j]) for j in range(n)]
        fr = func(xr)
        if fr < fvals[0]:
            xe = [centroid[j] + gamma * (xr[j] - centroid[j]) for j in range(n)]
            fe = func(xe)
            if fe < fr:
                simplex[-1], fvals[-1] = xe, fe
            else:
                simplex[-1], fvals[-1] = xr, fr
        elif fr < fvals[-2]:
            simplex[-1], fvals[-1] = xr, fr
        else:
            xc = [centroid[j] + rho * (worst[j] - centroid[j]) for j in range(n)]
            fc = func(xc)
            if fc < fvals[-1]:
                simplex[-1], fvals[-1] = xc, fc
            else:
                best = simplex[0]
                for i in range(1, n + 1):
                    simplex[i] = [
                        best[j] + sigma * (simplex[i][j] - best[j]) for j in range(n)
                    ]
                    fvals[i] = func(simplex[i])

    order = sorted(range(n + 1), key=lambda i: fvals[i])
    return simplex[order[0]], fvals[order[0]], converged


__all__ = ["nelder_mead"]
