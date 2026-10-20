"""The chart SPEC — the one data contract every Eclipse chart speaks.

This is the Python counterpart of the ECharts option object that used to be
built in TypeScript. The difference is what matters: an ECharts option is a
*program* for the browser's renderer (a deeply nested object of callbacks,
gradients and per-series styling), while a chart SPEC is **data** — a plain,
validated description of what to draw. Data can be checked before a single
pixel is drawn, so a malformed chart is a refusal, never a broken picture.

Why the spec is the whole design:

* **One contract, many surfaces.** The agent's `python_chart` tool, the HTTP
  route the front door calls, and a future widget all describe a chart the
  same way. Nothing has to know whether the chart came from a chat turn or a
  dashboard panel.
* **Validated, not interpreted.** A spec carries numbers, names and colours.
  It never carries code, a callback, a URL or a path. That is what makes it
  safe to render outside the analysis sandbox.
* **Honest by construction.** Every spec is a *computed* figure. There is no
  field that can mark a chart as retrieved evidence — the same rule ADR-H123
  applies to the sandbox's matplotlib recipes.

Every field is optional except `kind`, and a per-kind validator states what
that kind actually needs. A spec that does not satisfy its kind is refused
with a message that names the missing part.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChartKind = Literal[
    "line",
    "area",
    "bar",
    "stackedBar",
    "pie",
    "donut",
    "scatter",
    "histogram",
    "heatmap",
    "candlestick",
    "waterfall",
    "radar",
]

ChartTheme = Literal["eclipse-dark", "eclipse-light"]

#: The maximum points one series may carry. A chart is a picture, not a data
#: dump: past this size the picture stops being readable and the render stops
#: being cheap. A caller that needs more asks for an artifact, not a picture.
MAX_SERIES_POINTS = 5_000
#: The maximum number of series on one chart.
MAX_SERIES = 24
#: The maximum categories (x labels) on one chart.
MAX_CATEGORIES = 2_000
#: The rendered pixel budget. A chart wider/taller than this is refused rather
#: than rendered into a multi-megabyte image.
MAX_WIDTH = 2_400
MAX_HEIGHT = 2_400


class ChartSeries(BaseModel):
    """One named series of values."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    data: list[Optional[float]] = Field(default_factory=list)
    #: A `#rrggbb` colour. When absent the theme assigns the next palette slot.
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    #: How the series is drawn when the chart supports more than one drawing
    #: style (a bar chart with a line overlay, for instance).
    style: Optional[Literal["line", "area", "bar", "step", "scatter"]] = None


class ChartPoint(BaseModel):
    """One point of a scatter chart."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    label: Optional[str] = Field(default=None, max_length=120)
    size: Optional[float] = Field(default=None, gt=0)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class Candle(BaseModel):
    """One OHLC bar."""

    model_config = ConfigDict(extra="forbid")

    open: float
    high: float
    low: float
    close: float


class ChartSpec(BaseModel):
    """What to draw. Data only — never code, never a callback, never a path."""

    model_config = ConfigDict(extra="forbid")

    kind: ChartKind
    title: Optional[str] = Field(default=None, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    #: A short note drawn under the chart: where the numbers came from, what
    #: the chart is NOT (a forecast, a recommendation).
    footnote: Optional[str] = Field(default=None, max_length=300)
    source: Optional[str] = Field(default=None, max_length=200)

    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)

    #: The x-axis categories (dates, tickers, periods) for a category chart.
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)

    #: A pie/donut's slices.
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)

    #: A scatter chart's points.
    points: list[ChartPoint] = Field(default_factory=list)

    #: A heatmap's cells, with its two label axes.
    matrix: list[list[float]] = Field(default_factory=list)
    row_labels: list[str] = Field(default_factory=list)
    col_labels: list[str] = Field(default_factory=list)

    #: A candlestick chart's bars.
    candles: list[Candle] = Field(default_factory=list)

    #: Stack the series on top of each other (a stacked bar / stacked area).
    stacked: bool = False
    #: Show each slice as a percentage of the whole.
    normalized: bool = False
    #: Draw a smooth curve instead of straight segments.
    smooth: bool = False
    #: Mark each point of a line chart.
    show_points: bool = False
    #: The palette family. Dark matches the app's default surface.
    theme: ChartTheme = "eclipse-dark"

    width: int = Field(default=960, ge=320, le=MAX_WIDTH)
    height: int = Field(default=440, ge=240, le=MAX_HEIGHT)

    # ── The per-kind requirements ──────────────────────────────────────────

    @model_validator(mode="after")
    def _check_kind(self) -> "ChartSpec":
        kind = self.kind
        if kind in ("line", "area", "bar", "stackedBar"):
            if not self.series:
                raise ValueError(f"a {kind} chart needs at least one series")
            if len(self.series) > MAX_SERIES:
                raise ValueError(f"a chart carries at most {MAX_SERIES} series")
            for series in self.series:
                if len(series.data) > MAX_SERIES_POINTS:
                    raise ValueError(
                        f"series {series.name!r} carries {len(series.data)} points; "
                        f"a chart carries at most {MAX_SERIES_POINTS}"
                    )
        if kind == "pie" or kind == "donut":
            if not self.values:
                raise ValueError(f"a {kind} chart needs values")
            if len(self.values) != len(self.labels):
                raise ValueError(
                    "a pie chart needs one label per value "
                    f"({len(self.labels)} labels, {len(self.values)} values)"
                )
        if kind == "scatter":
            if not self.points:
                raise ValueError("a scatter chart needs points")
        if kind == "histogram":
            if not self.series or not self.series[0].data:
                raise ValueError("a histogram needs a series with values")
        if kind == "heatmap":
            if not self.matrix:
                raise ValueError("a heatmap needs a matrix of values")
            widths = {len(row) for row in self.matrix}
            if len(widths) > 1:
                raise ValueError("every row of a heatmap must have the same length")
            if self.row_labels and len(self.row_labels) != len(self.matrix):
                raise ValueError(
                    "a heatmap needs one row label per row "
                    f"({len(self.row_labels)} labels, {len(self.matrix)} rows)"
                )
            if self.col_labels and self.col_labels and len(self.col_labels) != len(self.matrix[0]):
                raise ValueError(
                    "a heatmap needs one column label per column "
                    f"({len(self.col_labels)} labels, {len(self.matrix[0])} columns)"
                )
        if kind == "candlestick":
            if not self.candles:
                raise ValueError("a candlestick chart needs candles")
            if len(self.candles) > MAX_SERIES_POINTS:
                raise ValueError(
                    f"a chart carries at most {MAX_SERIES_POINTS} candles"
                )
        if kind == "waterfall":
            if not self.series or not self.series[0].data:
                raise ValueError("a waterfall needs a series of values")
        if kind == "radar":
            if not self.values:
                raise ValueError("a radar chart needs values")
            if self.labels and len(self.labels) != len(self.values):
                raise ValueError(
                    "a radar chart needs one label per value "
                    f"({len(self.labels)} labels, {len(self.values)} values)"
                )
        if len(self.categories) > MAX_CATEGORIES:
            raise ValueError(f"a chart carries at most {MAX_CATEGORIES} categories")
        return self

    # ── The wire shape ──────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """The camelCase wire shape the front door and the tool share."""
        return self.model_dump(mode="json", by_alias=False)

    def summary(self) -> str:
        """One line describing what would be drawn — for the tool's text."""
        kind = self.kind
        if self.series:
            names = ", ".join(s.name for s in self.series[:6])
            extra = "" if len(self.series) <= 6 else f" (+{len(self.series) - 6} more)"
            return f"{kind} chart of {names}{extra}"
        if kind == "scatter":
            return f"scatter chart of {len(self.points)} points"
        if kind == "heatmap":
            rows = len(self.matrix)
            cols = len(self.matrix[0]) if rows else 0
            return f"heatmap of {rows}x{cols} cells"
        if kind == "candlestick":
            return f"candlestick chart of {len(self.candles)} bars"
        return f"{kind} chart of {len(self.values)} values"


__all__ = [
    "Candle",
    "ChartKind",
    "ChartPoint",
    "ChartSeries",
    "ChartSpec",
    "ChartTheme",
    "MAX_CATEGORIES",
    "MAX_HEIGHT",
    "MAX_SERIES",
    "MAX_SERIES_POINTS",
    "MAX_WIDTH",
]
