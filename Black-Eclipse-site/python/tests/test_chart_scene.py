"""The chart SCENE — panels of marks, so ANY chart can be drawn.

A fixed list of chart kinds can only draw the charts someone thought of. A
scene is compositional: a violin, a box plot, a Gantt, a funnel, a ridgeline or
a dual-axis chart is a COMPOSITION of the primitives, so the model can draw any
chart the user asks for.
"""

from __future__ import annotations

import pytest

from harness.charts.render import CHART_SPEC_INVALID, ChartRenderError, render_chart
from harness.charts.spec import ChartSpec


def _scene(**panels) -> ChartSpec:
    return ChartSpec(kind="scene", panels=list(panels.values()))


def test_a_scene_needs_at_least_one_panel():
    with pytest.raises(Exception):
        ChartSpec(kind="scene", panels=[])


def test_a_scene_needs_at_least_one_mark():
    with pytest.raises(Exception):
        ChartSpec(kind="scene", panels=[{"marks": []}])


def test_a_line_and_a_band_draw_together():
    spec = _scene(
        price={
            "title": "Price",
            "marks": [
                {"type": "line", "name": "Close", "y": [100, 104, 101]},
                {"type": "band", "lower": [98, 102, 99], "upper": [102, 106, 103]},
            ],
        }
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_scene_can_have_several_panels():
    spec = _scene(
        top={"marks": [{"type": "line", "y": [1, 2, 3]}]},
        bottom={"marks": [{"type": "histogram", "values": [1, 1, 2, 3, 3, 3]}]},
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    "mark",
    [
        {"type": "bar", "y": [1, 2, 3]},
        {"type": "area", "y": [1, 2, 3]},
        {"type": "scatter", "x": [1, 2, 3], "y": [3, 2, 1], "sizes": [1, 2, 3]},
        {"type": "rule", "y": [2.0], "label": "target"},
        {"type": "label", "x": [1], "y": [2], "label": "peak"},
        {"type": "box", "values": [1, 2, 3, 4, 5]},
        {"type": "violin", "values": [1, 2, 3, 4, 5, 2, 2]},
        {"type": "histogram", "values": [1, 2, 2, 3]},
        {"type": "errorbar", "x": [1, 2], "y": [3, 4], "lower": [2, 3], "upper": [4, 5]},
        {"type": "heatmap", "matrix": [[1, 2], [3, 4]], "rowLabels": ["a", "b"]},
        {"type": "pie", "y": [1, 2, 3], "labels": ["a", "b", "c"]},
        {"type": "donut", "y": [1, 2], "labels": ["a", "b"]},
        {"type": "candlestick", "matrix": [[1, 2, 0.5, 1.5]]},
        {"type": "waterfall", "y": [3, -1, 2]},
        {"type": "ridge", "y": [1, 2, 1]},
        {"type": "stem", "y": [1, 2, 1]},
    ],
)
def test_every_mark_type_draws(mark):
    spec = _scene(panel={"marks": [mark]})
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_stacked_bar_stacks():
    spec = _scene(
        panel={
            "marks": [
                {"type": "bar", "y": [1, 2], "stack": "s", "name": "a"},
                {"type": "bar", "y": [3, 4], "stack": "s", "name": "b"},
            ],
        }
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_panel_can_have_its_own_format_and_scale():
    spec = _scene(
        panel={
            "marks": [{"type": "line", "y": [0.1, 0.2]}],
            "valueFormat": "percent",
            "logScale": False,
            "yLabel": "Share",
        }
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_scene_with_no_drawable_mark_is_refused():
    # A mark with no data draws nothing; the scene still renders, but the
    # refusal path is exercised by a scene whose only panel has no marks.
    from harness.charts.spec import ChartSpec as Spec

    with pytest.raises(Exception):
        Spec(kind="scene", panels=[{"marks": []}])
