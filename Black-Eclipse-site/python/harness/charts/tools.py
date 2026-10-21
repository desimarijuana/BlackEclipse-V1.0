"""The `python_chart` tool — draw a chart from a spec.

This is the agent-facing door of the chart engine. The model describes WHAT to
draw (a kind, some series, a title); the engine decides how it looks. That
division is the point: a model cannot hand over a callback, a URL or a path,
so a chart it asks for is always data the engine can check.

The tool is honest by construction:

* a figure is labelled ``computed`` — it is never evidence (ADR-H123);
* a spec that does not satisfy its kind is REFUSED with the missing part
  named, so the model can fix it in one more call;
* a missing matplotlib is reported as a missing picture, not as a chart.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .render import (
    CHART_RENDER_FAILED,
    CHART_RENDER_UNAVAILABLE,
    CHART_SPEC_INVALID,
    ChartRenderError,
)
from .service import register_chart_artifact, render_spec
from .spec import ChartSpec

CHART_KINDS = (
    "line", "area", "bar", "stackedBar", "pie", "donut", "scatter",
    "histogram", "heatmap", "candlestick", "waterfall", "radar",
)


def chart_schema() -> dict[str, Any]:
    """The tool's input schema — the chart spec, field by field."""
    return {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": list(CHART_KINDS),
                "description": "What to draw: a line/area/bar/stackedBar trend, a pie/donut split, a scatter, a histogram, a heatmap, a candlestick chart, a waterfall or a radar profile.",
            },
            "title": {"type": "string", "description": "A short title."},
            "subtitle": {"type": "string", "description": "One line under the title — what the chart shows."},
            "footnote": {"type": "string", "description": "A note under the chart (for example: 'what-if, not a forecast')."},
            "source": {"type": "string", "description": "Where the numbers came from, drawn at the corner."},
            "x_label": {"type": "string", "description": "The x-axis label."},
            "y_label": {"type": "string", "description": "The y-axis label."},
            "categories": {
                "type": "array", "items": {"type": "string"},
                "description": "The x-axis labels (dates, tickers, periods), in order.",
            },
            "series": {
                "type": "array",
                "description": "The series to draw. Each one has a name and its values, in the same order as the categories.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "data": {
                            "type": "array",
                            "items": {"type": ["number", "null"]},
                            "description": "The values. Use null for a missing reading — never 0 for one.",
                        },
                        "color": {"type": "string", "description": "Optional #rrggbb colour."},
                        "style": {"type": "string", "enum": ["line", "area", "bar", "step", "scatter"]},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
            "labels": {
                "type": "array", "items": {"type": "string"},
                "description": "The slice names for a pie/donut chart, or the axes for a radar chart.",
            },
            "values": {
                "type": "array", "items": {"type": "number"},
                "description": "The values for a pie/donut chart, a waterfall or a radar chart.",
            },
            "points": {
                "type": "array",
                "description": "The points of a scatter chart.",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "label": {"type": "string"},
                        "size": {"type": "number"},
                        "color": {"type": "string"},
                    },
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
            },
            "matrix": {
                "type": "array",
                "description": "The cells of a heatmap — rows of numbers.",
                "items": {"type": "array", "items": {"type": "number"}},
            },
            "row_labels": {"type": "array", "items": {"type": "string"}, "description": "The heatmap's row labels."},
            "col_labels": {"type": "array", "items": {"type": "string"}, "description": "The heatmap's column labels."},
            "candles": {
                "type": "array",
                "description": "The bars of a candlestick chart.",
                "items": {
                    "type": "object",
                    "properties": {
                        "open": {"type": "number"},
                        "high": {"type": "number"},
                        "low": {"type": "number"},
                        "close": {"type": "number"},
                    },
                    "required": ["open", "high", "low", "close"],
                    "additionalProperties": False,
                },
            },
            "stacked": {"type": "boolean", "description": "Stack the series on top of each other."},
            "normalized": {"type": "boolean", "description": "Show each slice as a percentage of the whole."},
            "smooth": {"type": "boolean", "description": "Draw a smooth curve instead of straight segments."},
            "show_points": {"type": "boolean", "description": "Mark each point of a line chart."},
            "theme": {
                "type": "string", "enum": ["eclipse-dark", "eclipse-light"],
                "description": "The palette family. The dark one matches the app's default surface.",
            },
            "panels": {
                "type": "array",
                "description": (
                    "A COMPOSITIONAL chart: panels of marks, drawn exactly as given. Use this "
                    "for anything the simple kinds do not cover (a violin, a box plot, a Gantt, a "
                    "funnel, a ridgeline, a dual-axis chart). Each panel has its own axes and marks."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "xLabel": {"type": "string"},
                        "yLabel": {"type": "string"},
                        "valueFormat": {
                            "type": "string",
                            "enum": ["percent", "currency", "compact", "r", "number"],
                            "description": "How the value axis is written.",
                        },
                        "logScale": {"type": "boolean", "description": "Draw the value axis on a log scale."},
                        "height": {"type": "number", "description": "The panel's height relative to the others."},
                        "marks": {
                            "type": "array",
                            "description": "The drawn things. Each mark carries its own data.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "line", "area", "bar", "scatter", "band", "rule", "label",
                                            "box", "violin", "histogram", "errorbar", "heatmap", "pie",
                                            "donut", "candlestick", "waterfall", "ridge", "stem",
                                        ],
                                        "description": "The primitive to draw.",
                                    },
                                    "name": {"type": "string", "description": "The series name (the legend)."},
                                    "y": {"type": "array", "items": {"type": ["number", "null"]}, "description": "The values."},
                                    "x": {"type": "array", "items": {"type": ["number", "null"]}, "description": "Explicit x values."},
                                    "values": {"type": "array", "items": {"type": ["number", "null"]}, "description": "A distribution's samples (a box, a violin, a histogram)."},
                                    "lower": {"type": "array", "items": {"type": ["number", "null"]}, "description": "The band's lower edge."},
                                    "upper": {"type": "array", "items": {"type": ["number", "null"]}, "description": "The band's upper edge."},
                                    "sizes": {"type": "array", "items": {"type": ["number", "null"]}, "description": "The scatter's point sizes."},
                                    "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "The cells (a heatmap) or the OHLC rows (a candlestick)."},
                                    "labels": {"type": "array", "items": {"type": "string"}, "description": "The slice labels (a pie/donut)."},
                                    "rowLabels": {"type": "array", "items": {"type": "string"}},
                                    "colLabels": {"type": "array", "items": {"type": "string"}},
                                    "color": {"type": "string", "description": "#rrggbb."},
                                    "alpha": {"type": "number", "description": "0-1."},
                                    "width": {"type": "number"},
                                    "style": {"type": "string", "enum": ["solid", "dashed", "dotted"]},
                                    "fill": {"type": "boolean", "description": "Fill the area under a line."},
                                    "label": {"type": "string", "description": "A text label at the mark."},
                                    "yAxis": {"type": "string", "enum": ["left", "right"], "description": "Which value axis the mark belongs to (a dual-axis chart)."},
                                    "stack": {"type": "string", "description": "The stack the mark joins."},
                                    "bins": {"type": "integer", "description": "The histogram's bin count."},
                                },
                                "required": ["type"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["marks"],
                    "additionalProperties": False,
                },
            },
            "width": {"type": "integer", "description": "The picture width in pixels (320-2400)."},
            "height": {"type": "integer", "description": "The picture height in pixels (240-2400)."},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    data = {"status": "refused", "code": code, "reason": reason}
    return f"REFUSED ({code}): {reason}", data


async def python_chart(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Draw a chart from a spec and record it in the Artifact Center."""
    payload = {k: v for k, v in (args or {}).items() if v is not None}
    try:
        spec = ChartSpec(**payload)
    except Exception as exc:  # noqa: BLE001 - a malformed spec is a refusal
        return _refusal(CHART_SPEC_INVALID, f"that chart cannot be described: {exc}")

    try:
        rendered = render_spec(spec)
    except ChartRenderError as exc:
        if exc.code == CHART_RENDER_UNAVAILABLE:
            return _refusal(
                CHART_RENDER_UNAVAILABLE,
                "the chart engine is not available on this computer right now",
            )
        return _refusal(exc.code, exc.reason)

    entry = register_chart_artifact(ctx, rendered, source_tool="python_chart")
    figure = rendered.to_dict()
    if entry is not None:
        figure["artifactId"] = getattr(entry, "id", None) or getattr(entry, "artifact_id", None)

    title = spec.title or spec.summary()
    lines = [
        f"Drew a {spec.kind} chart: {spec.summary()}.",
        f"Title: {title}." if spec.title else "",
        "A chart is a picture of numbers Eclipse worked out — it is not a source and not a forecast.",
    ]
    text = "\n".join(line for line in lines if line)
    data = {
        "status": "ok",
        "figure": figure,
        "spec": spec.to_dict(),
        "artifact": {
            "id": getattr(entry, "id", None) if entry is not None else None,
            "name": rendered.name,
            "bytes": rendered.bytes,
            "sha256": rendered.sha256,
        } if entry is not None else {
            "id": None,
            "name": rendered.name,
            "bytes": rendered.bytes,
            "sha256": rendered.sha256,
        },
    }
    return text, data


def register_chart_tools(registry: ToolRegistry) -> list[str]:
    """Register the chart engine's agent tools."""
    registry.register(ToolDefinition(
        name="python_chart",
        description=(
            "Draw a chart from the numbers you have. Give the chart's kind and its data — "
            "the engine does the rest. A chart is always labelled as worked out by Eclipse, "
            "never as a source. If the data is missing, ask for it — never invent a point."
        ),
        input_schema=chart_schema(),
        handler=python_chart,
        permission="read", risk="low", timeout_ms=120_000,
    ))
    return ["python_chart"]


__all__ = [
    "CHART_KINDS",
    "CHART_RENDER_FAILED",
    "CHART_RENDER_UNAVAILABLE",
    "CHART_SPEC_INVALID",
    "chart_schema",
    "python_chart",
    "register_chart_tools",
]
