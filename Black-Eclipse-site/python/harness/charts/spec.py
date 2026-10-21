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

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic import model_validator

#: The wire shape is camelCase, like every other harness model (`to_camel`).
#: The snake_case field names stay valid too (`populate_by_name`), so a caller
#: may send either.
_CAMEL = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    extra="forbid",
)

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
    "gauge",
    "treemap",
    # The compositional form: panels of marks (see `scene.py`). Any chart is a
    # composition of the primitives, so a new chart is not a new "kind".
    "scene",
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

    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=120)
    data: list[Optional[float]] = Field(default_factory=list)
    #: A `#rrggbb` colour. When absent the theme assigns the next palette slot.
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    #: How the series is drawn when the chart supports more than one drawing
    #: style (a bar chart with a line overlay, for instance).
    style: Optional[Literal["line", "area", "bar", "step", "scatter"]] = None
    #: An optional range around the series, drawn as a translucent band.
    band: Optional[ChartBand] = None
    #: Per-point colours (`#rrggbb`), in the same order as `data`. A point with
    #: no colour takes the series colour. This is how a bar chart shows a
    #: sign (green up, red down) and how a pie shows one colour per slice.
    colors: list[Optional[str]] = Field(default_factory=list)
    #: Draw the series as a dashed line (a benchmark, a reference series).
    dashed: bool = False


class ChartPoint(BaseModel):
    """One point of a scatter chart."""

    model_config = _CAMEL

    x: float
    y: float
    label: Optional[str] = Field(default=None, max_length=120)
    size: Optional[float] = Field(default=None, gt=0)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class ChartBand(BaseModel):
    """A range drawn around a series (a confidence cone, a forecast band).

    The band is presentation weight, never a probability or a claim: it says
    "the series lives between these two lines", nothing more.
    """

    model_config = _CAMEL

    lower: list[Optional[float]] = Field(default_factory=list)
    upper: list[Optional[float]] = Field(default_factory=list)


class ChartReferenceLine(BaseModel):
    """A horizontal line across the chart (an entry, a stop, a target)."""

    model_config = _CAMEL

    label: str = Field(..., min_length=1, max_length=60)
    value: float
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    dashed: bool = True


class ChartTile(BaseModel):
    """One tile of a treemap: a name, a size (the area) and a colour.

    A tile may hold `children`: a group (a sector) whose area is the sum of
    its children's sizes, each laid out inside it.
    """

    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=60)
    value: float = Field(default=0.0, ge=0)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    label: Optional[str] = Field(default=None, max_length=120)
    children: list["ChartTile"] = Field(default_factory=list)


class ChartHighlight(BaseModel):
    """A shaded span of the category axis (a recession, a regime, a session)."""

    model_config = _CAMEL

    #: The category index the span starts at.
    start: int = Field(..., ge=0)
    #: The category index the span ends at (inclusive).
    end: int = Field(..., ge=0)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    label: Optional[str] = Field(default=None, max_length=60)


class Candle(BaseModel):
    """One OHLC bar."""

    model_config = _CAMEL

    open: float
    high: float
    low: float
    close: float


class ChartSpec(BaseModel):
    """What to draw. Data only — never code, never a callback, never a path."""

    model_config = _CAMEL

    kind: ChartKind
    title: Optional[str] = Field(default=None, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    #: A gauge's reading (0-100 by default) and its scale.
    value: Optional[float] = None
    gauge_max: Optional[float] = None
    #: A treemap's tiles: a name, a size and an optional colour.
    tiles: list[ChartTile] = Field(default_factory=list)
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
    #: Per-slice colours for a pie/donut (`#rrggbb`), in the same order as
    #: `values`. A slice with no colour takes the next theme colour.
    colors: list[Optional[str]] = Field(default_factory=list)

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
    #: How the VALUE axis is written. The engine draws numbers; a chart whose
    #: values are percents or dollars says so here rather than leaving the
    #: reader to guess what `0.25` means.
    value_format: Optional[Literal["percent", "currency", "compact", "r", "number"]] = None
    #: The currency symbol used by the `currency` value format.
    currency_symbol: str = Field(default="$", max_length=4)
    #: Horizontal reference lines drawn across the chart (an entry, a stop, a
    #: target). Each is named, so the reader knows what the line IS.
    reference_lines: list[ChartReferenceLine] = Field(default_factory=list)
    #: Shaded spans of the category axis (a recession, a regime).
    highlights: list[ChartHighlight] = Field(default_factory=list)
    #: A COMPOSITIONAL chart: panels of marks. When this is present the chart is
    #: drawn as a scene, and `kind` is only the scene's default.
    panels: list["ChartPanel"] = Field(default_factory=list)
    #: An optional volume pane under the chart (a price chart's volume bars).
    volume_data: list[Optional[float]] = Field(default_factory=list)
    #: The volume bars' colours (one per bar, or empty for the theme's own).
    volume_colors: list[Optional[str]] = Field(default_factory=list)
    #: Draw the value axis on a log scale.
    log_scale: bool = False

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
        if kind == "gauge":
            if self.value is None:
                raise ValueError("a gauge needs a value")
        if kind == "scene":
            if not self.panels:
                raise ValueError("a scene needs at least one panel")
            if not any(panel.marks for panel in self.panels):
                raise ValueError("a scene needs at least one mark")
        if kind == "treemap":
            if not self.tiles:
                raise ValueError("a treemap needs tiles")
            if self._treemap_size(self.tiles) <= 0:
                raise ValueError("a treemap needs at least one tile with a size")
        if len(self.categories) > MAX_CATEGORIES:
            raise ValueError(f"a chart carries at most {MAX_CATEGORIES} categories")
        return self

    # ── The wire shape ──────────────────────────────────────────────────────

    @staticmethod
    def _treemap_size(tiles: list["ChartTile"]) -> float:
        """The total area of a treemap: a group counts as its children."""
        total = 0.0
        for tile in tiles:
            if tile.children:
                total += ChartSpec._treemap_size(tile.children)
            else:
                total += tile.value
        return total

    def to_dict(self) -> dict[str, Any]:
        """The camelCase wire shape the front door and the tool share."""
        return self.model_dump(mode="json", by_alias=True)

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


# Resolve the forward reference (`ChartSpec.panels` -> `ChartPanel`).
from .scene import ChartPanel  # noqa: E402  (circular-import resolution)

ChartSpec.model_rebuild()


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
