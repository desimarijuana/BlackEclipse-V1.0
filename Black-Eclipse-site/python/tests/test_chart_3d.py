"""The 3D marks — a point cloud, a surface, a 3D bar.

3D is a mark, not a new chart: a 3D chart is a scene whose marks carry a
third dimension (`z`). The figure lives in Plotly's `scene` (a camera, three
axes, a cube), and the flat axes step aside.
"""

from __future__ import annotations

from harness.charts.plotly_figure import build_figure
from harness.charts.spec import ChartSpec
from harness.charts.theme import get_theme

THEME = get_theme("eclipse-dark")


def _figure(spec: ChartSpec) -> dict:
    return build_figure(spec, THEME)


def test_a_3d_point_cloud_becomes_a_scatter3d():
    spec = ChartSpec(
        kind="scene",
        panels=[{
            "marks": [{
                "type": "scatter3d", "name": "points",
                "x": [1, 2, 3], "y": [2, 4, 6], "z": [3, 6, 9],
            }],
        }],
    )
    trace = _figure(spec)["data"][0]
    assert trace["type"] == "scatter3d"
    assert trace["z"] == [3, 6, 9]
    assert trace["scene"] == "scene"


def test_a_3d_chart_lives_in_the_scene_and_drops_the_flat_axes():
    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [{"type": "scatter3d", "x": [1], "y": [1], "z": [1]}]}],
    )
    layout = _figure(spec)["layout"]
    assert "scene" in layout
    assert "xaxis" not in layout
    assert "yaxis" not in layout
    assert layout["scene"]["aspectmode"] == "cube"
    assert layout["scene"]["camera"]["eye"]["x"] > 0


def test_a_surface_carries_its_matrix():
    spec = ChartSpec(
        kind="scene",
        panels=[{
            "marks": [{
                "type": "surface", "name": "surface",
                "matrix": [[1, 2], [3, 4]],
                "x": [10, 20], "y": [30, 40],
            }],
        }],
    )
    trace = _figure(spec)["data"][0]
    assert trace["type"] == "surface"
    assert trace["z"] == [[1, 2], [3, 4]]
    assert trace["x"] == [10, 20]


def test_a_flat_chart_has_no_scene():
    spec = ChartSpec(kind="line", categories=["a"], series=[{"name": "s", "data": [1]}])
    assert "scene" not in _figure(spec)["layout"]
