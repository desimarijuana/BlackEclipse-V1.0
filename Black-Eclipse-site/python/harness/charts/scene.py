"""A chart SCENE — the compositional form of the chart spec.

A fixed list of chart kinds (`line`, `bar`, `pie`, …) can only ever draw the
charts someone thought of. A **scene** can draw any chart: it is a stack of
**panels**, and each panel is a stack of **marks**. A mark is a primitive with
its own data and styling, so a violin, a box plot, a Gantt, a funnel, a
ridgeline or a dual-axis chart is not a new "kind" — it is a composition of the
primitives.

The simple `kind` form stays supported (it is what the common cases use); a
spec with `panels` is drawn as a scene.

The rules are the engine's rules: a mark draws what it is given and never
invents a point, a value or a scale.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .spec import _CAMEL, ChartHighlight, ChartReferenceLine

MarkType = Literal[
    "line",
    "area",
    "bar",
    "scatter",
    "band",
    "rule",
    "label",
    "box",
    "violin",
    "histogram",
    "errorbar",
    "heatmap",
    "pie",
    "donut",
    "candlestick",
    "waterfall",
    "ridge",
    "stem",
    "treemap",
    "sunburst",
    "funnel",
    "sankey",
]


class ChartMark(BaseModel):
    """One drawn thing, with its own data and styling."""

    model_config = _CAMEL

    type: MarkType
    name: Optional[str] = Field(default=None, max_length=120)

    #: The values along the category (or y) axis.
    y: list[Optional[float]] = Field(default_factory=list)
    #: Explicit x values (a scatter, a line over a numeric axis).
    x: list[Optional[float]] = Field(default_factory=list)
    #: A distribution's samples (a box plot, a violin, a histogram).
    values: list[Optional[float]] = Field(default_factory=list)
    #: The band's lower/upper edges (a forecast band, an error bar).
    lower: list[Optional[float]] = Field(default_factory=list)
    upper: list[Optional[float]] = Field(default_factory=list)
    #: A matrix of cells (a heatmap) or the OHLC rows (a candlestick).
    matrix: list[list[float]] = Field(default_factory=list)
    #: The slice labels (a pie/donut).
    labels: list[str] = Field(default_factory=list)

    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    alpha: float = Field(default=1.0, ge=0.0, le=1.0)
    width: Optional[float] = Field(default=None, gt=0)
    #: `solid`, `dashed` or `dotted`.
    style: Optional[Literal["solid", "dashed", "dotted"]] = None
    #: Fill the area under a line (a line mark with `fill: true`).
    fill: bool = False
    #: A text label drawn at the mark's position.
    label: Optional[str] = Field(default=None, max_length=200)
    #: Which value axis the mark belongs to (a dual-axis chart).
    y_axis: Literal["left", "right"] = "left"
    #: The stack the mark joins (marks with the same stack name stack together).
    stack: Optional[str] = Field(default=None, max_length=60)
    #: The histogram's bin count.
    bins: Optional[int] = Field(default=None, ge=1, le=200)
    #: The scatter's point sizes.
    sizes: list[Optional[float]] = Field(default_factory=list)
    #: The row/column labels (a heatmap).
    row_labels: list[str] = Field(default_factory=list)
    col_labels: list[str] = Field(default_factory=list)
    #: The parent of each node (a treemap/sunburst: "" is the root).
    parents: list[str] = Field(default_factory=list)
    #: Per-item colours (a treemap's tiles, a sunburst's branches).
    colors: list[Optional[str]] = Field(default_factory=list)
    #: A sankey's links: the source node index, the target node index, the weight.
    sources: list[int] = Field(default_factory=list)
    targets: list[int] = Field(default_factory=list)
    weights: list[float] = Field(default_factory=list)


class ChartPanel(BaseModel):
    """One panel of a scene: its own axes, its own marks."""

    model_config = _CAMEL

    title: Optional[str] = Field(default=None, max_length=200)
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    marks: list[ChartMark] = Field(default_factory=list)
    #: How the value axis is written.
    value_format: Optional[Literal["percent", "currency", "compact", "r", "number"]] = None
    #: Draw the value axis on a log scale.
    log_scale: bool = False
    #: The panel's height relative to the others.
    height: Optional[float] = Field(default=None, gt=0)
    #: Named horizontal lines for this panel.
    reference_lines: list[ChartReferenceLine] = Field(default_factory=list)
    #: Shaded spans of the category axis.
    highlights: list[ChartHighlight] = Field(default_factory=list)


__all__ = ["ChartMark", "ChartPanel", "MarkType"]
