"""The chart's INTERACTION MAP — the picture's geometry, so it can be hovered.

A PNG cannot be hovered. The engine therefore returns, with the picture, where
each category sits on it and what each series' value is there. The browser
draws the crosshair and the tooltip over the picture from that map.
"""

from __future__ import annotations

from harness.charts.render import render_chart_with_interaction
from harness.charts.spec import ChartSpec


def test_a_line_chart_reports_its_columns():
    spec = ChartSpec(
        kind="line",
        categories=["Jan", "Feb", "Mar"],
        series=[{"name": "NAV", "data": [100, 104, 101]}],
    )
    png, interaction = render_chart_with_interaction(spec)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert interaction is not None
    assert interaction["width"] > 0 and interaction["height"] > 0
    assert len(interaction["columns"]) == 3
    first = interaction["columns"][0]
    assert first["label"] == "Jan"
    assert first["values"][0]["name"] == "NAV"
    assert first["values"][0]["value"] == 100.0
    # The columns get further right as the categories do.
    xs = [column["x"] for column in interaction["columns"]]
    assert xs == sorted(xs)


def test_the_map_carries_the_plot_box_inside_the_picture():
    spec = ChartSpec(
        kind="bar",
        categories=["a", "b"],
        series=[{"name": "s", "data": [1, 2]}],
    )
    _, interaction = render_chart_with_interaction(spec)
    assert interaction is not None
    plot = interaction["plot"]
    assert 0 <= plot["left"] < plot["right"] <= interaction["width"]
    assert 0 <= plot["top"] < plot["bottom"] <= interaction["height"]


def test_a_gap_is_not_a_value():
    spec = ChartSpec(
        kind="line",
        categories=["a", "b", "c"],
        series=[{"name": "s", "data": [1, None, 3]}],
    )
    _, interaction = render_chart_with_interaction(spec)
    assert interaction is not None
    middle = interaction["columns"][1]
    assert middle["values"] == []


def test_a_pie_has_no_columns_to_hover():
    spec = ChartSpec(kind="pie", labels=["a", "b"], values=[1, 2])
    _, interaction = render_chart_with_interaction(spec)
    assert interaction is None


def test_a_scene_has_no_columns_to_hover():
    spec = ChartSpec(kind="scene", panels=[{"marks": [{"type": "line", "y": [1, 2]}]}])
    _, interaction = render_chart_with_interaction(spec)
    assert interaction is None
