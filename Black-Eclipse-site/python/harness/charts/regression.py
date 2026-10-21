"""A least-squares line through a set of points.

The engine draws a REGRESSION honestly: the points exactly as they were given,
one fitted line, and the R-squared that says how much of the variation the
line explains. Nothing is smoothed, weighted or robustly re-fitted behind the
reader's back - it is the ordinary least-squares line.

The arithmetic is plain on purpose: a chart that says ``R2 = 0.87`` has to
mean exactly what the arithmetic says, and a reader must be able to check it
from the picture. A fit that cannot be computed (too few points, no variation
in x, no variation in y) is REFUSED, not approximated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class LinearFit:
    """The ordinary least-squares line through a set of points."""

    slope: float
    intercept: float
    r_squared: float
    x_min: float
    x_max: float
    count: int

    def at(self, x: float) -> float:
        """The fitted value at ``x``."""
        return self.slope * x + self.intercept

    def describe(self) -> str:
        """The fit in words: the slope, the intercept, the R-squared, the n."""
        sign = "-" if self.slope < 0 else "+"
        return (
            f"y = {self.slope:.4g}x {sign} {abs(self.intercept):.4g}   "
            f"(R2 = {self.r_squared:.3f}, n = {self.count})"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _pairs(xs: Iterable[Any], ys: Iterable[Any]) -> list[tuple[float, float]]:
    """The (x, y) pairs that can be fitted.

    The pairing happens FIRST, so a missing reading drops its own point and
    never shifts the x axis under the points that remain.
    """
    out: list[tuple[float, float]] = []
    for x, y in zip(xs, ys):
        if _is_number(x) and _is_number(y):
            out.append((float(x), float(y)))
    return out


def linear_fit(xs: Iterable[Any], ys: Iterable[Any]) -> Optional[LinearFit]:
    """The least-squares line through the (x, y) pairs.

    Returns ``None`` when a line cannot be fitted: fewer than two points, no
    variation in x (the slope is undefined) or no variation in y (the R-squared
    is undefined). A chart that cannot fit a line says so instead of drawing
    one that means nothing.
    """
    points = _pairs(xs, ys)
    count = len(points)
    if count < 2:
        return None
    x_values = [p[0] for p in points]
    y_values = [p[1] for p in points]

    mean_x = sum(x_values) / count
    mean_y = sum(y_values) / count
    sxx = sum((x - mean_x) ** 2 for x in x_values)
    if sxx <= 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    syy = sum((y - mean_y) ** 2 for y in y_values)
    if syy <= 0:
        # Every y is the same: the line is flat and the R-squared is undefined.
        return None
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_values, y_values))
    r_squared = max(0.0, min(1.0, 1.0 - ss_res / syy))

    ordered = sorted(x_values)
    return LinearFit(
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        x_min=ordered[0],
        x_max=ordered[-1],
        count=count,
    )
