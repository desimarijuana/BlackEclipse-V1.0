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

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .spec import _CAMEL, ChartHighlight, ChartReferenceLine

#: Every primitive the engine can draw.
MARK_TYPES = frozenset({
    "line", "area", "bar", "scatter", "band", "rule", "label", "box", "violin",
    "histogram", "errorbar", "heatmap", "pie", "donut", "candlestick",
    "waterfall", "ridge", "stem", "treemap", "sunburst", "funnel", "sankey",
    "scatter3d", "surface",
    # The points, the least-squares line through them, and its R-squared.
    "regression",
})

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
    # The 3D family: a point cloud, a surface.
    "scatter3d",
    "surface",
    "regression",
]


class ChartDataSource(BaseModel):
    """WHERE the numbers come from, instead of the numbers themselves.

    A chart of a market series does not need the series typed out: the engine
    fetches it through the same market gateway every other price comes from,
    and the chart is drawn from what the gateway returned. That is what keeps
    a 250-point chart out of the model's mouth - a chart block that spells
    out every price is a long message, and a long message gets truncated.
    """

    model_config = _CAMEL

    #: The instrument to fetch (`AAPL`, `^VIX`, `GC=F`).
    symbol: str = Field(..., min_length=1, max_length=40)
    #: The market the symbol belongs to (`US`). Optional: the gateway resolves
    #: the instrument from its own master.
    market: Optional[str] = Field(default=None, max_length=8)
    #: The bar size (`1d`).
    interval: str = Field(default="1d", max_length=8)
    #: An explicit window. Without one the gateway's default window is used.
    start: Optional[str] = Field(default=None, max_length=20)
    end: Optional[str] = Field(default=None, max_length=20)
    #: Which value the chart draws. The close, by default.
    field: Literal["close", "open", "high", "low", "volume"] = "close"
    #: The series name in the legend.
    name: Optional[str] = Field(default=None, max_length=120)


class ChartMark(BaseModel):
    """One drawn thing, with its own data and styling."""

    model_config = _CAMEL

    type: str = Field(default="line", max_length=40)
    name: Optional[str] = Field(default=None, max_length=120)

    #: The values along the category (or y) axis. A NUMBER, a label (a 3D
    #: bar's categories), or an [x, y] PAIR - the way a person writes a point.
    #: A pair carries its own x (see `_split_pairs`).
    y: list[Optional[float] | str | list[Any]] = Field(default_factory=list)
    #: WHERE these values come from. When it is set, the engine fetches the
    #: series and fills the values itself - the mark does not carry them.
    data_source: Optional[ChartDataSource] = Field(default=None)
    #: The same values under the name a SERIES uses (`data`). An alias for `y`.
    data: list[Optional[float] | str | list[Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _split_pairs(self) -> "ChartMark":
        """A [x, y] pair carries its own x.

        A model writes points the way a person does - `[1, 258.45]` - so a
        mark accepts pairs as well as scalars. The pair's x becomes the mark's
        x (unless the mark already has one) and its y the value; the mark is
        then drawn exactly as a mark with separate x and y would be.
        """
        for field in ("y", "data"):
            values = getattr(self, field, None) or []
            if not values or not any(isinstance(v, (list, tuple)) for v in values):
                continue
            xs: list[Optional[float] | str] = []
            ys: list[Optional[float] | str] = []
            for value in values:
                if isinstance(value, (list, tuple)):
                    pair = list(value)
                    xs.append(pair[0] if pair else None)
                    ys.append(pair[1] if len(pair) > 1 else None)
                else:
                    xs.append(None)
                    ys.append(value)
            if not self.x:
                object.__setattr__(self, "x", xs)
            setattr(self, field, ys)
        return self

    @field_validator("type", mode="before")
    @classmethod
    def _known_type(cls, value: Any) -> str:
        """The mark's primitive, normalised.

        A producer may write a synonym (`candles`, `bars`, `donut`) or a word
        the engine does not know (`price`). An unknown type becomes a `line`:
        the mark is still drawn (with its values), instead of the whole chart
        being refused.
        """
        raw = str(value or "line").strip().lower()
        aliases = {
            "candles": "candlestick", "candle": "candlestick", "ohlc": "candlestick",
            "bars": "bar", "columns": "bar", "line_chart": "line",
            "donut": "donut", "doughnut": "donut", "points": "scatter",
            "boxplot": "box", "violinplot": "violin", "area_chart": "area",
            "linear": "regression", "linear_regression": "regression",
            "trend": "regression", "trendline": "regression", "ols": "regression",
            "fit": "regression",
        }
        resolved = aliases.get(raw, raw)
        return resolved if resolved in MARK_TYPES else "line"

    @property
    def the_values(self) -> list[Optional[float] | str]:
        """The mark's values, whether they arrived as `y` or as `data`."""
        values = self.y or self.data
        # A pair that survived the split (a malformed one) is not a value.
        return [v for v in values if not isinstance(v, list)]
    #: Explicit x values (a scatter, a line over a numeric axis). A NUMBER, or
    #: a label (a 3D bar's categories).
    x: list[Optional[float] | str] = Field(default_factory=list)
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
    #: The third dimension (a 3D mark's z).
    z: list[Optional[float]] = Field(default_factory=list)


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
