"""A LINEAR REGRESSION chart: the points, the fitted line, and the R-squared.

A regression is a first-class chart kind, not a scatter the reader has to
interpret: the engine fits the ordinary least-squares line from the same
numbers it draws and shows the R-squared, so the picture and the number can
never disagree.
"""

from __future__ import annotations

import pytest

from harness.charts.regression import linear_fit
from harness.charts.render import render_chart
from harness.charts.scene import ChartMark
from harness.charts.spec import ChartSpec


def test_a_perfect_line_has_an_r_squared_of_one():
    fit = linear_fit([1, 2, 3, 4], [2, 4, 6, 8])
    assert fit is not None
    assert fit.slope == pytest.approx(2.0)
    assert fit.intercept == pytest.approx(0.0)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.count == 4


def test_the_fit_is_the_ordinary_least_squares_line():
    # y = 3x + 1 with the last point moved up: the slope shifts toward it.
    fit = linear_fit([0, 1, 2, 3], [1, 4, 7, 11])
    assert fit is not None
    assert fit.slope == pytest.approx(3.3, rel=1e-6)
    assert fit.intercept == pytest.approx(0.8, rel=1e-6)
    assert 0.9 < fit.r_squared < 1.0


def test_a_fit_that_cannot_be_computed_is_refused():
    assert linear_fit([1], [2]) is None          # one point
    assert linear_fit([], []) is None
    assert linear_fit([1, 1, 1], [2, 3, 4]) is None   # no variation in x
    assert linear_fit([1, 2, 3], [5, 5, 5]) is None   # no variation in y


def test_a_missing_reading_does_not_shift_the_x_axis():
    # The middle reading is missing: the fit is over the two points that
    # remain, NOT over a point that has been moved into its place.
    fit = linear_fit([1, None, 3], [2, None, 6])
    assert fit is not None
    assert fit.slope == pytest.approx(2.0)
    assert fit.count == 2


def test_the_fit_says_what_it_is():
    fit = linear_fit([1, 2, 3], [2, 4, 6])
    assert fit is not None
    text = fit.describe()
    assert "R2" in text
    assert "n = 3" in text


def test_a_regression_mark_draws():
    spec = ChartSpec(
        kind="scene",
        panels=[
            {
                "marks": [
                    {
                        "type": "regression",
                        "name": "Price",
                        "x": [1, 2, 3, 4, 5],
                        "y": [2.1, 3.9, 6.2, 7.8, 10.1],
                    }
                ]
            }
        ],
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_regression_mark_is_part_of_the_vocabulary():
    mark = ChartMark(type="regression", x=[1, 2, 3], y=[2, 4, 6])
    assert mark.type == "regression"
    # A producer's synonym lands on the same mark.
    assert ChartMark(type="linear_regression", x=[1, 2, 3], y=[2, 4, 6]).type == "regression"
    assert ChartMark(type="trendline", x=[1, 2, 3], y=[2, 4, 6]).type == "regression"
