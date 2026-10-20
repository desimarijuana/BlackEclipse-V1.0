"""The chart engine — Eclipse's one chart renderer.

Eclipse draws its charts with Python (matplotlib), in this package. The parts:

* `spec`     — the chart SPEC: the validated data contract every surface uses.
* `theme`    — the Eclipse palette, so a figure matches the app's design system.
* `render`   — spec → PNG. It draws what the spec says and nothing else.
* `service`  — spec → artifact: the picture is recorded in the Artifact Center.
* `tools`    — the `python_chart` agent tool.

A figure is always `computed`, never evidence (ADR-H123).
"""

from .render import (
    CHART_RENDER_FAILED,
    CHART_RENDER_UNAVAILABLE,
    CHART_SPEC_INVALID,
    ChartRenderError,
    render_chart,
)
from .service import RenderedChart, register_chart_artifact, render_spec, spec_digest
from .spec import (
    Candle,
    ChartPoint,
    ChartSeries,
    ChartSpec,
    ChartTheme,
)
from .theme import DARK_THEME, LIGHT_THEME, get_theme
from .tools import chart_schema, python_chart, register_chart_tools

__all__ = [
    "CHART_RENDER_FAILED",
    "CHART_RENDER_UNAVAILABLE",
    "CHART_SPEC_INVALID",
    "Candle",
    "ChartPoint",
    "ChartRenderError",
    "ChartSeries",
    "ChartSpec",
    "ChartTheme",
    "DARK_THEME",
    "LIGHT_THEME",
    "RenderedChart",
    "chart_schema",
    "get_theme",
    "python_chart",
    "register_chart_artifact",
    "register_chart_tools",
    "render_chart",
    "render_spec",
    "spec_digest",
]
