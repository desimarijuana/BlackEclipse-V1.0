"""The chart's INTERACTION MAP — what makes a drawn picture interactive.

A PNG cannot be hovered. But the engine knows two things a PNG cannot say:
where each category sits on the picture, and what each series' value is there.
So the engine returns the picture AND a small map of the picture's geometry
(the axes' box, in the PNG's own pixels) plus the values per category.

The browser then draws the hover layer over the picture: a crosshair at the
nearest category and a tooltip with the values. Because the map is in PNG
pixels and the browser converts it to percentages, the interaction survives any
display size — the picture is never stretched, and the crosshair still lands on
the right column.

The map is a convenience, never a claim: the numbers it carries are the SAME
numbers the picture was drawn from.
"""

from __future__ import annotations

from typing import Any, Optional

from .spec import ChartSpec
from .theme import ChartTheme

#: The kinds whose x axis is a category axis (so a hover can pick a column).
CATEGORY_KINDS = frozenset({"line", "area", "bar", "stackedBar"})


def _series_color(theme: ChartTheme, index: int, explicit: Optional[str]) -> str:
    return explicit or theme.series_color(index)


def build_interaction(
    spec: ChartSpec,
    theme: ChartTheme,
    axes: Any,
) -> Optional[dict[str, Any]]:
    """Describe the drawn chart so the browser can hover it.

    Returns None when the chart has no category axis to hover (a pie, a
    heatmap, a scene) — the browser then shows the picture and nothing else.
    """
    if spec.kind not in CATEGORY_KINDS or not spec.categories:
        return None
    if not axes or not spec.series:
        return None

    figure = axes.get_figure()
    if figure is None:
        return None
    try:
        figure.canvas.draw()
    except Exception:  # noqa: BLE001 - the map is a convenience
        return None

    try:
        box = axes.get_window_extent()
    except Exception:  # noqa: BLE001
        return None

    transform = axes.transData
    columns: list[dict[str, Any]] = []
    for index, label in enumerate(spec.categories):
        try:
            x_pixel = float(transform.transform((float(index), 0.0))[0])
        except Exception:  # noqa: BLE001
            return None
        values: list[dict[str, Any]] = []
        for series_index, series in enumerate(spec.series):
            if index >= len(series.data):
                continue
            value = series.data[index]
            if value is None:
                continue
            values.append({
                "name": series.name,
                "value": float(value),
                "color": _series_color(theme, series_index, series.color),
            })
        columns.append({"label": str(label), "x": round(x_pixel, 2), "values": values})

    if not columns:
        return None

    return {
        "width": int(figure.get_figwidth() * figure.dpi),
        "height": int(figure.get_figheight() * figure.dpi),
        "plot": {
            "left": round(float(box.x0), 2),
            "right": round(float(box.x1), 2),
            "top": round(float(box.y0), 2),
            "bottom": round(float(box.y1), 2),
        },
        "columns": columns,
    }


__all__ = ["CATEGORY_KINDS", "build_interaction"]
