"""The live FIGURE — a real, vector, interactive chart.

The chat's charts are not pictures: the engine authors them in Python and the
browser renders them as vector SVG with zoom, pan, hover and a legend. These
tests pin that contract: the figure is well formed, it has no background, and
every chart kind and every mark reaches a trace.
"""

from __future__ import annotations

import pytest

from harness.charts.plotly_figure import build_figure
from harness.charts.spec import ChartSpec
from harness.charts.theme import get_theme

THEME = get_theme("eclipse-dark")


def _figure(spec: ChartSpec) -> dict:
    return build_figure(spec, THEME)


def test_a_line_chart_becomes_a_trace_with_the_app_ink():
    spec = ChartSpec(
        kind="line",
        categories=["Jan", "Feb"],
        series=[{"name": "NAV", "data": [100, 104]}],
    )
    figure = _figure(spec)
    assert figure["data"][0]["type"] == "scatter"
    assert figure["data"][0]["x"] == ["Jan", "Feb"]
    assert figure["data"][0]["y"] == [100, 104]
    assert figure["layout"]["font"]["color"] == "#e5e7eb"


def test_the_figure_has_NO_background():
    """The chart sits on the app's frosted surface: it must not hide the frost."""
    spec = ChartSpec(kind="line", categories=["a"], series=[{"name": "s", "data": [1]}])
    layout = _figure(spec)["layout"]
    assert layout["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert layout["plot_bgcolor"] == "rgba(0,0,0,0)"


def test_a_candlestick_keeps_its_ohlc():
    spec = ChartSpec(
        kind="candlestick",
        categories=["d1", "d2"],
        candles=[
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"open": 1.5, "high": 1.8, "low": 1.1, "close": 1.2},
        ],
    )
    trace = _figure(spec)["data"][0]
    assert trace["type"] == "candlestick"
    assert trace["open"] == [1, 1.5]
    assert trace["high"] == [2, 1.8]
    assert trace["low"] == [0.5, 1.1]
    assert trace["close"] == [1.5, 1.2]


def test_a_scene_stacks_its_panels_on_their_own_axes():
    spec = ChartSpec(
        kind="scene",
        panels=[
            {"title": "price", "marks": [{"type": "line", "y": [1, 2, 3]}]},
            {"title": "volume", "marks": [{"type": "bar", "y": [4, 5, 6]}]},
        ],
    )
    figure = _figure(spec)
    assert [trace["type"] for trace in figure["data"]] == ["scatter", "bar"]
    # The second panel rides its own axes.
    assert figure["data"][1]["yaxis"] == "y2"
    assert "yaxis2" in figure["layout"]


def test_a_right_axis_mark_gets_its_own_overlaying_scale():
    """`yAxis: "right"` is a real second scale, not a label the engine ignores."""
    spec = ChartSpec(
        kind="scene",
        panels=[{
            "marks": [
                {"type": "line", "y": [100, 101]},
                {"type": "bar", "y": [500, 700], "yAxis": "right"},
            ],
        }],
    )
    figure = _figure(spec)
    assert figure["data"][1]["yaxis"] == "y2"
    assert figure["data"][0].get("yaxis", "y") == "y"
    right = figure["layout"]["yaxis2"]
    assert right["overlaying"] == "y"
    assert right["side"] == "right"
    assert figure["layout"]["margin"]["r"] >= 60


def test_a_3d_scene_orbits_instead_of_panning():
    """The 2-D `dragmode: "pan"` must never disable orbiting a 3-D scene."""
    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [{"type": "scatter3d", "x": [1, 2], "y": [1, 2], "z": [1, 2]}]}],
    )
    assert _figure(spec)["layout"]["scene"]["dragmode"] == "turntable"


@pytest.mark.parametrize(
    "mark,expected",
    [
        ({"type": "line", "y": [1, 2]}, "scatter"),
        ({"type": "area", "y": [1, 2]}, "scatter"),
        ({"type": "bar", "y": [1, 2]}, "bar"),
        ({"type": "scatter", "x": [1], "y": [2]}, "scatter"),
        ({"type": "box", "values": [1, 2, 3]}, "box"),
        ({"type": "violin", "values": [1, 2, 3]}, "violin"),
        ({"type": "histogram", "values": [1, 2, 3]}, "histogram"),
        ({"type": "heatmap", "matrix": [[1, 2]]}, "heatmap"),
        ({"type": "pie", "y": [1, 2], "labels": ["a", "b"]}, "pie"),
        ({"type": "donut", "y": [1, 2], "labels": ["a", "b"]}, "pie"),
        ({"type": "waterfall", "y": [1, -2]}, "waterfall"),
        ({"type": "treemap", "values": [1], "labels": ["a"]}, "treemap"),
        ({"type": "sunburst", "values": [1], "labels": ["a"]}, "sunburst"),
        ({"type": "funnel", "y": [1], "labels": ["a"]}, "funnel"),
    ],
)
def test_every_mark_reaches_a_trace(mark, expected):
    spec = ChartSpec(kind="scene", panels=[{"marks": [mark]}])
    traces = _figure(spec)["data"]
    assert traces, f"the mark {mark['type']} produced no trace"
    assert traces[0]["type"] == expected


def test_a_band_becomes_two_traces_that_fill_between():
    spec = ChartSpec(
        kind="scene",
        panels=[{
            "marks": [{
                "type": "band", "lower": [1, 2], "upper": [3, 4], "name": "range",
            }],
        }],
    )
    traces = _figure(spec)["data"]
    assert len(traces) == 2
    assert traces[1]["fill"] == "tonexty"


def test_the_figure_is_json_serialisable():
    import json

    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [{"type": "violin", "values": [1, 2, 3]}]}],
    )
    payload = json.dumps(_figure(spec))
    assert '"data"' in payload and '"layout"' in payload
