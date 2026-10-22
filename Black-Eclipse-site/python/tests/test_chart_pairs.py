"""A mark may carry PAIRS — the way a model (and a person) writes a point.

The failure this fixes, in the model's own words from a real run: "The chart
did not render. The scatter-plus-regression block I built failed the
renderer's schema check on the mark data format." The model wrote its points
as `[x, y]` pairs and a mark only accepted scalars, so the whole block was
refused and the reader got prose instead of a chart.
"""

from __future__ import annotations

from harness.charts.scene import ChartMark
from harness.charts.spec import ChartSpec


def test_a_pairs_data_carries_its_own_x():
    mark = ChartMark(type="scatter", data=[[1, 10.0], [2, 20.5], [3, 31.0]])
    assert mark.x == [1, 2, 3]
    assert mark.the_values == [10.0, 20.5, 31.0]


def test_a_pairs_y_carries_its_own_x():
    mark = ChartMark(type="regression", y=[[1, 10.0], [2, 20.5]])
    assert mark.x == [1, 2]
    assert mark.y == [10.0, 20.5]


def test_plain_values_are_untouched():
    mark = ChartMark(type="line", y=[1, 2, 3])
    assert mark.y == [1.0, 2.0, 3.0]
    assert mark.x == []


def test_an_explicit_x_wins_over_a_pairs_x():
    mark = ChartMark(type="scatter", x=[9, 9, 9], data=[[1, 10.0], [2, 20.5], [3, 31.0]])
    assert mark.x == [9, 9, 9]
    assert mark.the_values == [10.0, 20.5, 31.0]


def test_a_scene_with_pairs_draws():
    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [{"type": "regression", "data": [[1, 10.0], [2, 20.5], [3, 31.0]]}]}],
    )
    mark = spec.panels[0].marks[0]
    assert mark.x == [1, 2, 3]
    assert mark.the_values == [10.0, 20.5, 31.0]
