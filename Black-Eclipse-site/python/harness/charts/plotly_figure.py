"""The chart FIGURE — a real, vector, interactive chart.

A PNG is a picture: it cannot be zoomed, panned, or read with a pointer. This
module turns the same chart SPEC into a **Plotly figure** — vector SVG, with
zoom, pan, hover and a legend — so the browser renders a real chart instead of
an image of one.

The figure is authored in PYTHON (the same spec, the same data, the same
palette), and it is serialised to JSON: the browser draws it with plotly.js.
There is no background: the figure is transparent, so it sits on the app's
frosted surface without hiding the frost.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .regression import linear_fit
from .scene import ChartMark, ChartPanel
from .spec import ChartSpec
from .theme import ChartTheme

#: The palette the app's charts use, in the theme's language.
INK = "#e5e7eb"
MUTED = "#a3a3a3"
GRID = "rgba(163,163,163,0.16)"


def _rgba(hex_color: str, alpha: float) -> str:
    """`#rrggbb` + alpha → `rgba(...)` (Plotly's fill colour)."""
    clean = hex_color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return hex_color
    r = int(clean[0:2], 16)
    g = int(clean[2:4], 16)
    b = int(clean[4:6], 16)
    return f"rgba({r},{g},{b},{max(0.0, min(1.0, alpha))})"


def _dash(style: Optional[str]) -> Optional[str]:
    return {"solid": "solid", "dashed": "dash", "dotted": "dot"}.get(style or "solid", "solid")


def _heat_scale(theme: ChartTheme) -> list[list[Any]]:
    """A neutral (low → high) scale, so a heatmap never invents a hue meaning."""
    return [[0.0, theme.heat_low], [0.5, theme.surface or "rgba(0,0,0,0)"], [1.0, theme.heat_high]]


def _x_values(mark: ChartMark, count: int) -> list[Any]:
    if mark.x:
        return [v if v is not None else None for v in mark.x]
    return list(range(count))


def _axis_layout(title: Optional[str] = None, **over: Any) -> dict[str, Any]:
    layout: dict[str, Any] = {
        "showgrid": True,
        "gridcolor": GRID,
        "zerolinecolor": GRID,
        "linecolor": GRID,
        "tickfont": {"color": MUTED, "size": 11},
        "title": {"font": {"color": MUTED, "size": 11}},
    }
    if title:
        layout["title"] = {"text": title, "font": {"color": MUTED, "size": 11}}
    for key, value in list(over.items()):
        if value is None:
            layout.pop(key, None)
        else:
            layout[key] = value
    return layout


def _base_layout(spec: ChartSpec, theme: ChartTheme) -> dict[str, Any]:
    """The layout: the app's ink, a TRANSPARENT background, the app's fonts."""
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": INK, "family": "ui-monospace, SFMono-Regular, Menlo, monospace", "size": 12},
        "title": (
            {"text": spec.title, "font": {"color": INK, "size": 15}, "x": 0, "xanchor": "left"}
            if spec.title
            else None
        ),
        "margin": {"l": 62, "r": 18, "t": 44 if spec.title else 18, "b": 44},
        "hoverlabel": {
            "bgcolor": "rgba(18,18,20,0.92)",
            "bordercolor": "rgba(255,255,255,0.14)",
            "font": {"color": INK, "size": 12},
        },
        "hovermode": "x unified",
        "dragmode": "pan",
        "xaxis": _axis_layout(spec.x_label),
        "yaxis": _axis_layout(spec.y_label),
    }


def _mark_traces(
    mark: ChartMark,
    theme: ChartTheme,
    index: int,
    panel: ChartPanel,
) -> list[dict[str, Any]]:
    """One mark → its Plotly traces."""
    color = mark.color or theme.series_color(index)
    name = mark.name or f"series {index + 1}"
    traces: list[dict[str, Any]] = []

    if mark.type in ("line", "area", "ridge", "stem"):
        ys = mark.the_values or []
        x = _x_values(mark, len(ys))
        if mark.type == "area":
            traces.append({
                "type": "scatter", "x": x, "y": ys, "name": name, "mode": "lines",
                "line": {"color": color, "width": mark.width or 2, "dash": _dash(mark.style)},
                "fill": "tozeroy", "fillcolor": _rgba(color, 0.22),
            })
        elif mark.type == "ridge":
            offset = float(mark.width or 0.0)
            traces.append({
                "type": "scatter", "x": x, "y": [offset + (v or 0.0) for v in ys], "name": name,
                "mode": "lines", "line": {"color": color, "width": 1},
                "fill": "tonexty", "fillcolor": _rgba(color, 0.55),
            })
        elif mark.type == "stem":
            traces.append({
                "type": "scatter", "x": x, "y": ys, "name": name, "mode": "markers",
                "marker": {"color": color, "size": 6},
            })
        else:
            traces.append({
                "type": "scatter", "x": x, "y": ys, "name": name, "mode": "lines",
                "line": {"color": color, "width": mark.width or 2, "dash": _dash(mark.style)},
            })
        return traces

    if mark.type == "bar":
        ys = mark.the_values or []
        traces.append({
            "type": "bar", "x": _x_values(mark, len(ys)), "y": ys, "name": name,
            "marker": {"color": color},
            "opacity": mark.alpha if mark.alpha is not None else 1,
        })
        return traces

    if mark.type == "scatter":
        ys = mark.the_values or []
        sizes = [s for s in (mark.sizes or []) if s is not None]
        traces.append({
            "type": "scatter", "x": _x_values(mark, len(ys)), "y": ys, "name": name,
            "mode": "markers",
            "marker": {
                "color": color,
                "size": [s for s in (mark.sizes or [])] or 7,
                "sizemode": "area" if sizes else "diameter",
                "opacity": 0.85,
                "line": {"width": 0},
            },
        })
        return traces

    if mark.type == "regression":
        # The points as they were given, ONE least-squares line, and the
        # R-squared in the legend. A fit that cannot be computed is not drawn:
        # the points are, and the trace says why.
        ys = mark.the_values or []
        xs = _x_values(mark, len(ys))
        points = [
            (x, y)
            for x, y in zip(xs, ys)
            if isinstance(x, (int, float)) and not isinstance(x, bool)
            and isinstance(y, (int, float)) and not isinstance(y, bool)
        ]
        if len(points) < 2:
            traces.append({
                "type": "scatter", "x": [p[0] for p in points], "y": [p[1] for p in points],
                "name": f"{name} (not enough points to fit)", "mode": "markers",
                "marker": {"color": color, "size": 7, "opacity": 0.85},
            })
            return traces
        fit = linear_fit([p[0] for p in points], [p[1] for p in points])
        if fit is None:
            traces.append({
                "type": "scatter", "x": [p[0] for p in points], "y": [p[1] for p in points],
                "name": f"{name} (no line to fit)", "mode": "markers",
                "marker": {"color": color, "size": 7, "opacity": 0.85},
            })
            return traces
        traces.append({
            "type": "scatter", "x": [p[0] for p in points], "y": [p[1] for p in points],
            "name": name, "mode": "markers",
            "marker": {
                "color": color, "size": 7, "opacity": 0.85, "line": {"width": 0},
            },
        })
        traces.append({
            "type": "scatter",
            "x": [fit.x_min, fit.x_max],
            "y": [fit.at(fit.x_min), fit.at(fit.x_max)],
            "name": f"{name} fit (R2 = {fit.r_squared:.3f})",
            "mode": "lines",
            "line": {"color": color, "width": 2, "dash": "dash"},
            "hovertemplate": f"y = {fit.slope:.4g}x {fit.intercept:+.4g}<br>R2 = {fit.r_squared:.3f}<extra></extra>",
        })
        return traces

    if mark.type == "band":
        lower = mark.lower or []
        upper = mark.upper or []
        count = min(len(lower), len(upper))
        x = list(range(count))
        traces.append({
            "type": "scatter", "x": x, "y": lower[:count], "name": f"{name} lower",
            "mode": "lines", "line": {"width": 0}, "hoverinfo": "skip", "showlegend": False,
        })
        traces.append({
            "type": "scatter", "x": x, "y": upper[:count], "name": name, "mode": "lines",
            "line": {"width": 0},
            "fill": "tonexty", "fillcolor": _rgba(color, 0.2),
        })
        return traces

    if mark.type == "rule":
        value = (mark.y or [None])[0]
        if value is not None:
            traces.append({
                "type": "scatter", "x": [None], "y": [None], "mode": "lines",
                "name": mark.label or name, "showlegend": False,
                "line": {"color": color, "width": 1, "dash": _dash(mark.style)},
                "visible": "legendonly" if False else True,
            })
        return traces

    if mark.type == "label":
        ys = mark.the_values or []
        traces.append({
            "type": "scatter", "x": _x_values(mark, len(ys)), "y": ys, "name": name,
            "mode": "text", "text": [mark.label or ""] * len(ys),
            "textfont": {"color": color, "size": 12},
        })
        return traces

    if mark.type == "box":
        traces.append({
            "type": "box", "y": mark.values or [], "name": name,
            "marker": {"color": color}, "boxpoints": False,
            "line": {"color": color},
        })
        return traces

    if mark.type == "violin":
        traces.append({
            "type": "violin", "y": mark.values or [], "name": name,
            "line": {"color": color}, "fillcolor": _rgba(color, 0.45),
            "box": {"visible": True}, "meanline": {"visible": True},
        })
        return traces

    if mark.type == "histogram":
        traces.append({
            "type": "histogram", "x": mark.values or [], "name": name,
            "marker": {"color": color}, "opacity": 0.9,
        })
        return traces

    if mark.type == "errorbar":
        ys = mark.the_values or []
        lower = mark.lower or []
        upper = mark.upper or []
        count = min(len(ys), len(lower), len(upper))
        traces.append({
            "type": "scatter", "x": _x_values(mark, count), "y": ys[:count], "name": name,
            "mode": "markers", "marker": {"color": color, "size": 6},
            "error_y": {
                "type": "data", "symmetric": False,
                "arrayminus": [max(0.0, (ys[i] or 0.0) - (lower[i] or 0.0)) for i in range(count)],
                "arrayplus": [max(0.0, (upper[i] or 0.0) - (ys[i] or 0.0)) for i in range(count)],
            },
        })
        return traces

    if mark.type == "heatmap":
        traces.append({
            "type": "heatmap", "z": mark.matrix or [],
            "x": mark.col_labels or None, "y": mark.row_labels or None,
            "name": name, "colorscale": _heat_scale(theme), "hoverongaps": False,
        })
        return traces

    if mark.type in ("pie", "donut"):
        traces.append({
            "type": "pie", "labels": mark.labels or [], "values": mark.values or [],
            "name": name, "hole": 0.45 if mark.type == "donut" else 0,
            "textinfo": "label+percent", "showlegend": True,
        })
        return traces

    if mark.type == "candlestick":
        candles = mark.matrix or []
        traces.append({
            "type": "candlestick", "name": name,
            "x": mark.labels or list(range(len(candles))),
            "open": [c[0] for c in candles], "high": [c[1] for c in candles],
            "low": [c[2] for c in candles], "close": [c[3] for c in candles],
            "increasing": {"line": {"color": theme.up}},
            "decreasing": {"line": {"color": theme.down}},
        })
        return traces

    if mark.type == "waterfall":
        values = mark.the_values or []
        traces.append({
            "type": "waterfall", "x": _x_values(mark, len(values)), "y": values, "name": name,
            "increasing": {"marker": {"color": theme.up}},
            "decreasing": {"marker": {"color": theme.down}},
        })
        return traces

    if mark.type == "scatter3d":
        traces.append({
            "type": "scatter3d", "name": name, "scene": "scene",
            "x": mark.x or [], "y": mark.the_values or [], "z": mark.z or [],
            "mode": "markers",
            "marker": {
                "color": mark.z or [],
                "size": 5,
                "colorscale": "Viridis",
                "showscale": True,
                "colorbar": {"title": {"text": "z"}},
            },
        })
        return traces

    if mark.type == "surface":
        traces.append({
            "type": "surface", "name": name, "scene": "scene",
            "z": mark.matrix or [],
            "x": mark.x or None, "y": mark.y or None,
            "colorscale": "Viridis",
            "showscale": True,
        })
        return traces

    if mark.type == "treemap":
        traces.append({
            "type": "treemap", "name": name,
            "labels": mark.labels or [], "parents": mark.parents or [""] * len(mark.labels or []),
            "values": mark.values or [], "marker": {"colors": mark.colors or None},
        })
        return traces

    if mark.type == "sunburst":
        traces.append({
            "type": "sunburst", "name": name,
            "labels": mark.labels or [], "parents": mark.parents or [""] * len(mark.labels or []),
            "values": mark.values or [],
        })
        return traces

    if mark.type == "funnel":
        traces.append({
            "type": "funnel", "name": name,
            "y": mark.labels or [], "x": mark.values or [],
        })
        return traces

    if mark.type == "sankey":
        traces.append({
            "type": "sankey", "name": name,
            "labels": mark.labels or [],
            "source": mark.sources or [], "target": mark.targets or [], "value": mark.weights or [],
        })
        return traces

    return traces


def _simple_traces(spec: ChartSpec, theme: ChartTheme) -> list[dict[str, Any]]:
    """The simple (kind-based) form → its traces."""
    kind = spec.kind
    traces: list[dict[str, Any]] = []

    if kind in ("line", "area", "stackedBar"):
        for index, series in enumerate(spec.series):
            color = series.color or theme.series_color(index)
            x = spec.categories or list(range(len(series.data)))
            if kind == "area":
                traces.append({
                    "type": "scatter", "x": x, "y": series.data, "name": series.name,
                    "mode": "lines", "line": {"color": color, "width": 2},
                    "fill": "tozeroy", "fillcolor": _rgba(color, 0.2),
                })
            elif kind == "stackedBar":
                traces.append({
                    "type": "bar", "x": x, "y": series.data, "name": series.name,
                    "marker": {"color": color},
                })
            else:
                traces.append({
                    "type": "scatter", "x": x, "y": series.data, "name": series.name,
                    "mode": "lines", "line": {"color": color, "width": 2},
                })
            if series.band and series.band.lower and series.band.upper:
                count = min(len(series.band.lower), len(series.band.upper))
                traces.append({
                    "type": "scatter", "x": list(range(count)), "y": series.band.lower[:count],
                    "name": f"{series.name} lower", "mode": "lines", "line": {"width": 0},
                    "hoverinfo": "skip", "showlegend": False,
                })
                traces.append({
                    "type": "scatter", "x": list(range(count)), "y": series.band.upper[:count],
                    "name": f"{series.name} band", "mode": "lines", "line": {"width": 0},
                    "fill": "tonexty", "fillcolor": _rgba(color, 0.2), "showlegend": False,
                })
        return traces

    if kind == "bar":
        for index, series in enumerate(spec.series):
            color = series.color or theme.series_color(index)
            traces.append({
                "type": "bar", "x": spec.categories or list(range(len(series.data))),
                "y": series.data, "name": series.name, "marker": {"color": color},
            })
        return traces

    if kind in ("pie", "donut"):
        traces.append({
            "type": "pie", "labels": spec.labels or [], "values": spec.values or [],
            "name": spec.series[0].name if spec.series else "share",
            "hole": 0.45 if kind == "donut" else 0,
            "textinfo": "label+percent",
        })
        return traces

    if kind == "scatter":
        for index, series in enumerate(spec.series):
            color = series.color or theme.series_color(index)
            traces.append({
                "type": "scatter", "mode": "markers", "name": series.name,
                "x": [p[0] for p in series.data if isinstance(p, (list, tuple)) and len(p) >= 2],
                "y": [p[1] for p in series.data if isinstance(p, (list, tuple)) and len(p) >= 2],
                "marker": {"color": color, "size": 8, "opacity": 0.85},
            })
        return traces

    if kind == "histogram":
        series = spec.series[0] if spec.series else None
        traces.append({
            "type": "histogram", "x": series.data if series else [], "name": series.name if series else "values",
            "marker": {"color": theme.series_color(0)}, "opacity": 0.9,
        })
        return traces

    if kind == "heatmap":
        traces.append({
            "type": "heatmap", "z": spec.matrix or [],
            "x": spec.col_labels or None, "y": spec.row_labels or None,
            "colorscale": _heat_scale(theme), "hoverongaps": False,
        })
        return traces

    if kind == "candlestick":
        traces.append({
            "type": "candlestick", "name": "price",
            "x": spec.categories or list(range(len(spec.candles))),
            "open": [c.open for c in spec.candles],
            "high": [c.high for c in spec.candles],
            "low": [c.low for c in spec.candles],
            "close": [c.close for c in spec.candles],
            "increasing": {"line": {"color": theme.up}},
            "decreasing": {"line": {"color": theme.down}},
        })
        return traces

    if kind == "waterfall":
        series = spec.series[0] if spec.series else None
        traces.append({
            "type": "waterfall", "x": spec.categories or [], "y": series.data if series else [],
            "name": series.name if series else "change",
            "increasing": {"marker": {"color": theme.up}},
            "decreasing": {"marker": {"color": theme.down}},
        })
        return traces

    if kind == "radar":
        series = spec.series[0] if spec.series else None
        traces.append({
            "type": "scatterpolar", "r": series.data if series else [], "theta": spec.labels or [],
            "name": series.name if series else "profile", "fill": "toself",
            "line": {"color": theme.series_color(0)}, "fillcolor": _rgba(theme.series_color(0), 0.25),
        })
        return traces

    if kind == "gauge":
        traces.append({
            "type": "indicator", "mode": "gauge+number", "value": spec.value or 0,
            "gauge": {
                "axis": {"range": [0, spec.gauge_max or 100]},
                "bar": {"color": theme.series_color(0)},
                "bgcolor": "rgba(255,255,255,0.06)",
            },
        })
        return traces

    if kind == "treemap":
        traces.append({
            "type": "treemap", "labels": [t.name for t in spec.tiles],
            "parents": ["" for _ in spec.tiles], "values": [t.value for t in spec.tiles],
            "marker": {"colors": [t.color for t in spec.tiles]},
            "textinfo": "label+value+percent parent",
        })
        return traces

    return traces


def _scene_layout(spec: ChartSpec, theme: ChartTheme, panels: list[ChartPanel]) -> dict[str, Any]:
    """A scene's layout: one row per panel, each with its own axes."""
    layout = _base_layout(spec, theme)
    layout.pop("xaxis", None)
    layout.pop("yaxis", None)
    layout["margin"] = {"l": 62, "r": 18, "t": 44 if spec.title else 18, "b": 44}
    for index, panel in enumerate(panels, start=1):
        # Plotly's axis keys: `xaxis`/`yaxis`, then `xaxis2`/`yaxis2` for the
        # second panel.
        suffix = "" if index == 1 else str(index)
        axis = f"yaxis{suffix}"
        xaxis = f"xaxis{suffix}"
        layout[axis] = _axis_layout(panel.y_label)
        layout[xaxis] = _axis_layout(panel.x_label, showgrid=False)
        if index > 1:
            layout[xaxis]["matches"] = "x"
    return layout


#: The 3D scene: the axes, the camera and the box's proportions.
def _scene3d_layout(spec: ChartSpec) -> dict[str, Any]:
    """The layout of a 3D chart: a camera, three axes, and a box."""
    return {
        "scene": {
            "xaxis": {"title": {"text": spec.x_label or "x"}, "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": GRID, "showbackground": False},
            "yaxis": {"title": {"text": spec.y_label or "y"}, "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": GRID, "showbackground": False},
            "zaxis": {"title": {"text": "z"}, "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": GRID, "showbackground": False},
            "aspectmode": "cube",
            "camera": {"eye": {"x": 1.6, "y": 1.5, "z": 1.1}},
        }
    }


def build_figure(spec: ChartSpec, theme: ChartTheme) -> dict[str, Any]:
    """The spec → a Plotly figure (JSON-serialisable)."""
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"plotly is not available: {exc}") from exc

    if spec.panels:
        panels = spec.panels
        traces: list[dict[str, Any]] = []
        for panel_index, panel in enumerate(panels):
            for mark_index, mark in enumerate(panel.marks):
                built = _mark_traces(mark, theme, mark_index, panel)
                for trace in built:
                    trace = dict(trace)
                    if panel_index > 0:
                        # A scene's panels stack: the later panels ride their own axes.
                        suffix = str(panel_index + 1)
                        trace["xaxis"] = f"x{suffix}"
                        trace["yaxis"] = f"y{suffix}"
                    traces.append(trace)
        layout = _scene_layout(spec, theme, panels)
        if any(trace.get("type") in ("scatter3d", "surface") for trace in traces):
            # A 3D chart lives in its own scene; the flat axes would fight it.
            layout.pop("xaxis", None)
            layout.pop("yaxis", None)
            layout.update(_scene3d_layout(spec))
        figure = go.Figure(data=traces, layout=layout)
        return json.loads(figure.to_json())

    traces = _simple_traces(spec, theme)
    layout = _base_layout(spec, theme)
    if spec.subtitle:
        layout["title"] = {
            "text": f"{spec.title}<br><sup>{spec.subtitle}</sup>" if spec.title else spec.subtitle,
            "font": {"color": INK, "size": 15}, "x": 0, "xanchor": "left",
        }
    if spec.value_format:
        layout["yaxis"] = dict(layout.get("yaxis") or {})
        layout["yaxis"]["tickformat"] = _TICK_FORMATS.get(spec.value_format)
    figure = go.Figure(data=traces, layout=layout)
    return json.loads(figure.to_json())


#: The value axis formats, in Plotly's `tickformat` language.
_TICK_FORMATS = {
    "percent": ".0%",
    "currency": ",.0f",
    "compact": "~s",
    "r": ".1f",
    "number": None,
}


__all__ = ["build_figure"]
