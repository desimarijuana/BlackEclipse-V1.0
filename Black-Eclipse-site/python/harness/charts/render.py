"""The chart RENDERER — a validated spec becomes a PNG.

The renderer is deliberately dumb and total:

* it draws what the spec says and NOTHING else — it never invents a point, a
  mean, an axis or a scale;
* it never labels a chart as evidence. A figure is a *computed* picture; the
  label rides the metadata, not the pixels (ADR-H123);
* when matplotlib is not installed, it says so honestly
  (``CHART_RENDER_UNAVAILABLE``) instead of shipping an empty image.

Rendering happens in the harness process, not in the analysis sandbox: a chart
SPEC is *data* (validated by pydantic, free of code and paths), so it needs
no code isolation — and rendering it here means the figure, the artifact and
the run record all come from one place.
"""

from __future__ import annotations

import io
import math
from typing import Any, Optional

from .spec import Candle, ChartPoint, ChartSeries, ChartSpec
from .theme import ChartTheme, get_theme

#: The refusal codes the renderer reports. Stable and testable.
CHART_RENDER_UNAVAILABLE = "CHART_RENDER_UNAVAILABLE"
CHART_RENDER_FAILED = "CHART_RENDER_FAILED"
CHART_SPEC_INVALID = "CHART_SPEC_INVALID"


class ChartRenderError(RuntimeError):
    """A rendering refusal. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _pyplot() -> Any:
    """Import matplotlib lazily and honestly.

    A missing matplotlib is a missing PICTURE, not a missing chart: the
    numbers that came with the spec are still true. So the failure is named,
    not swallowed.
    """
    try:
        import matplotlib  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise ChartRenderError(
            CHART_RENDER_UNAVAILABLE,
            "matplotlib is not installed, so the chart cannot be drawn: "
            f"{exc}",
        ) from exc
    try:
        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise ChartRenderError(
            CHART_RENDER_UNAVAILABLE,
            f"matplotlib could not start: {exc}",
        ) from exc
    return plt


def _numpy() -> Any:
    try:
        import numpy as np  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise ChartRenderError(
            CHART_RENDER_UNAVAILABLE,
            f"numpy could not start: {exc}",
        ) from exc
    return np


def _clean(values: list[Optional[float]]) -> list[float]:
    """Drop the gaps (a `None` is a missing reading, never a zero)."""
    return [float(v) for v in values if v is not None]


def _axis_categories(spec: ChartSpec, length: int) -> Any:
    """The x positions: the categories when they fit, else the index."""
    if spec.categories and len(spec.categories) >= length:
        return list(range(length)), list(spec.categories[:length])
    return list(range(length)), [str(i) for i in range(length)]


def _apply_titles(ax: Any, spec: ChartSpec) -> None:
    if spec.title:
        ax.set_title(spec.title, loc="left", pad=14 if spec.subtitle else 8)
    if spec.subtitle:
        ax.annotate(
            spec.subtitle,
            xy=(0, 1.0),
            xycoords="axes fraction",
            xytext=(0, 8),
            textcoords="offset points",
            ha="left",
            va="bottom",
            color=_theme_of(ax).muted,
            fontsize=9.5,
        )
    if spec.x_label:
        ax.set_xlabel(spec.x_label)
    if spec.y_label:
        ax.set_ylabel(spec.y_label)


def _theme_of(ax: Any) -> ChartTheme:
    return getattr(ax, "_eclipse_theme", None) or get_theme(None)


def _draw_line_family(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    np = _numpy()
    series = spec.series
    longest = max((len(s.data) for s in series), default=0)
    positions, labels = _axis_categories(spec, longest)
    plotted = False
    for index, entry in enumerate(series):
        values = entry.data
        if not values:
            continue
        color = entry.color or theme.series_color(index)
        xs = list(range(len(values)))
        ys = [float(v) if v is not None else float("nan") for v in values]
        style = entry.style or ("area" if spec.kind == "area" else "line")
        if style == "bar":
            ax.bar(xs, ys, color=color, width=0.7, label=entry.name, alpha=0.9)
        elif style == "scatter":
            ax.scatter(xs, ys, color=color, s=18, label=entry.name)
        else:
            if spec.smooth and len(ys) > 2:
                finite = [(i, v) for i, v in enumerate(ys) if not math.isnan(v)]
                if len(finite) > 2:
                    fx = [p[0] for p in finite]
                    fy = [p[1] for p in finite]
                    dense = np.linspace(fx[0], fx[-1], min(len(fx) * 3, 2_000))
                    ys = list(np.interp(dense, fx, fy))
                    xs = list(dense)
            if style == "area":
                ax.fill_between(xs, ys, color=color, alpha=0.22, label=entry.name)
                ax.plot(xs, ys, color=color, linewidth=1.6, label=entry.name)
            elif style == "step":
                ax.step(xs, ys, where="post", color=color, linewidth=1.6, label=entry.name)
            else:
                ax.plot(xs, ys, color=color, linewidth=1.6, label=entry.name)
            if spec.show_points:
                ax.scatter(xs, ys, color=color, s=14)
        band = entry.band
        if band and band.lower and band.upper:
            # A forecast band: the range the series lives in, drawn as a
            # translucent area. It is presentation, never a probability.
            lower = [float(v) if v is not None else float("nan") for v in band.lower]
            upper = [float(v) if v is not None else float("nan") for v in band.upper]
            count = min(len(lower), len(upper))
            if count > 1:
                ax.fill_between(
                    list(range(count)), lower[:count], upper[:count],
                    color=color, alpha=0.16, linewidth=0,
                )
        plotted = True
    if spec.stacked and len(series) > 1:
        # A stacked family is drawn as cumulative areas so the stack is real.
        ax.clear()
        bottom = [0.0] * longest
        for index, entry in enumerate(series):
            values = list(entry.data) + [None] * (longest - len(entry.data))
            ys = [float(v) if v is not None else 0.0 for v in values]
            color = entry.color or theme.series_color(index)
            ax.fill_between(
                positions, bottom, [b + y for b, y in zip(bottom, ys)],
                color=color, alpha=0.55, label=entry.name,
            )
            bottom = [b + y for b, y in zip(bottom, ys)]
    if not plotted:
        raise ChartRenderError(CHART_SPEC_INVALID, "the chart has no values to draw")
    if len(labels) <= 24:
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=0)
    if len(series) > 1 or spec.kind == "area":
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=min(4, len(series)))


def _draw_bar_family(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    series = spec.series
    longest = max((len(s.data) for s in series), default=0)
    positions, labels = _axis_categories(spec, longest)
    if spec.stacked:
        bottom = [0.0] * longest
        for index, entry in enumerate(series):
            values = list(entry.data) + [None] * (longest - len(entry.data))
            ys = [float(v) if v is not None else 0.0 for v in values]
            color = entry.color or theme.series_color(index)
            ax.bar(
                positions, ys, bottom=bottom, color=color, width=0.68,
                label=entry.name, alpha=0.92,
            )
            bottom = [b + y for b, y in zip(bottom, ys)]
    else:
        width = 0.8 / max(1, len(series))
        for index, entry in enumerate(series):
            values = list(entry.data) + [None] * (longest - len(entry.data))
            ys = [float(v) if v is not None else float("nan") for v in values]
            color = entry.color or theme.series_color(index)
            offset = (index - (len(series) - 1) / 2) * width
            ax.bar(
                [p + offset for p in positions], ys, width=width, color=color,
                label=entry.name, alpha=0.92,
            )
    if len(labels) <= 24:
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
    else:
        ax.set_xticks(positions[:: max(1, len(positions) // 12)])
    if len(series) > 1:
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=min(4, len(series)))


def _draw_pie(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    values = [float(v) for v in spec.values]
    labels = list(spec.labels)
    total = sum(abs(v) for v in values)
    if total <= 0:
        raise ChartRenderError(CHART_SPEC_INVALID, "a pie chart needs at least one non-zero value")
    colors = [theme.series_color(i) for i in range(len(values))]
    wedges, _texts, autotexts = ax.pie(
        values,
        labels=labels if len(labels) <= 12 else None,
        colors=colors,
        autopct="%1.0f%%" if len(values) <= 12 else None,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "none"} if spec.kind == "donut" else {"edgecolor": "none"},
    )
    for text in autotexts:
        text.set_color("#0b0b0d")
        text.set_fontsize(9)
    if not labels and len(values) <= 12:
        legend_labels = [f"{i + 1}" for i in range(len(values))]
        ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(0.98, 0.5))
    if spec.kind == "donut":
        ax.text(0, 0, f"{total:,.0f}", ha="center", va="center",
                color=theme.ink, fontsize=15, fontweight="semibold")
        ax.text(0, -0.12, "total", ha="center", va="center", color=theme.muted, fontsize=9)


def _draw_scatter(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    points = spec.points
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    sizes = [p.size for p in points]
    if any(s is not None for s in sizes):
        biggest = max((s for s in sizes if s is not None), default=1.0) or 1.0
        scaled = [24 + 220 * ((s or biggest) / biggest) for s in sizes]
    else:
        scaled = [40] * len(points)
    for point, size in zip(points, scaled):
        color = point.color or theme.direction_color(point.y)
        ax.scatter([point.x], [point.y], s=size, color=color, alpha=0.85,
                   edgecolors="none")
    if len(points) <= 14:
        for point in points:
            if point.label:
                ax.annotate(
                    point.label, (point.x, point.y),
                    textcoords="offset points", xytext=(6, 6), fontsize=8.5,
                    color=theme.muted,
                )
    ax.axhline(0, color=theme.axis, linewidth=0.8)


def _draw_histogram(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    values = _clean(spec.series[0].data)
    if not values:
        raise ChartRenderError(CHART_SPEC_INVALID, "the histogram has no values to draw")
    count = len(values)
    bins = min(40, max(5, count // 8 if count else 5))
    ax.hist(values, bins=bins, color=spec.series[0].color or theme.series_color(0),
            edgecolor="none", alpha=0.9)
    if count >= 2:
        mean = sum(values) / count
        ax.axvline(mean, color=theme.ink, linewidth=1.0, linestyle="--", alpha=0.8)
        ax.annotate(
            f"mean {mean:,.4g}", xy=(mean, ax.get_ylim()[1]),
            xytext=(4, -12), textcoords="offset points", fontsize=8.5,
            color=theme.ink,
        )


def _draw_heatmap(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    np = _numpy()
    matrix = np.array(spec.matrix, dtype=float)
    image = ax.imshow(matrix, cmap="coolwarm", aspect="auto")
    ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    if spec.row_labels:
        ax.set_yticks(range(len(spec.row_labels)))
        ax.set_yticklabels(spec.row_labels)
    if spec.col_labels:
        ax.set_xticks(range(len(spec.col_labels)))
        ax.set_xticklabels(spec.col_labels, rotation=45, ha="right")
    ax.grid(False)


def _draw_candlestick(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    from matplotlib.patches import Rectangle  # noqa: PLC0415

    candles = spec.candles
    for index, candle in enumerate(candles):
        rising = candle.close >= candle.open
        color = theme.up if rising else theme.down
        ax.plot([index, index], [candle.low, candle.high], color=color, linewidth=0.9)
        body_low = min(candle.open, candle.close)
        body_high = max(candle.open, candle.close)
        height = max(body_high - body_low, 1e-9)
        ax.add_patch(Rectangle(
            (index - 0.32, body_low), 0.64, height,
            facecolor=color, edgecolor="none", alpha=0.9,
        ))
    if spec.categories and len(spec.categories) >= len(candles):
        step = max(1, len(candles) // 12)
        ax.set_xticks(range(0, len(candles), step))
        ax.set_xticklabels([str(spec.categories[i]) for i in range(0, len(candles), step)])


def _draw_waterfall(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    values = [float(v) for v in spec.series[0].data if v is not None]
    if not values:
        raise ChartRenderError(CHART_SPEC_INVALID, "the waterfall has no values to draw")
    running = 0.0
    bottoms: list[float] = []
    heights: list[float] = []
    colors: list[str] = []
    for value in values:
        bottoms.append(running if value >= 0 else running + value)
        heights.append(abs(value))
        colors.append(theme.up if value >= 0 else theme.down)
        running += value
    ax.bar(range(len(values)), heights, bottom=bottoms, color=colors, width=0.66)
    ax.axhline(0, color=theme.axis, linewidth=0.8)
    if spec.categories and len(spec.categories) >= len(values):
        ax.set_xticks(range(len(values)))
        ax.set_xticklabels([str(c) for c in spec.categories[: len(values)]], rotation=30, ha="right")


def _draw_radar(ax: Any, spec: ChartSpec, theme: ChartTheme, plt: Any) -> None:
    values = [float(v) for v in spec.values]
    labels = list(spec.labels)
    count = len(values)
    angles = [n / count * 2 * math.pi for n in range(count)]
    angles.append(angles[0])
    closed = values + [values[0]]
    ax.plot(angles, closed, color=theme.series_color(0), linewidth=1.6)
    ax.fill(angles, closed, color=theme.series_color(0), alpha=0.22)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels if labels else [str(i) for i in range(count)])
    ax.set_yticklabels([])
    ax.grid(True, alpha=0.25)


_DISPATCH = {
    "line": _draw_line_family,
    "area": _draw_line_family,
    "bar": _draw_bar_family,
    "stackedBar": _draw_bar_family,
    "pie": _draw_pie,
    "donut": _draw_pie,
    "scatter": _draw_scatter,
    "histogram": _draw_histogram,
    "heatmap": _draw_heatmap,
    "candlestick": _draw_candlestick,
    "waterfall": _draw_waterfall,
    "radar": _draw_radar,
}


def render_chart(spec: ChartSpec) -> bytes:
    """Render the spec into PNG bytes.

    The bytes are a transparent-background PNG, ready to sit on a frosted
    glass card without hiding the frost.
    """
    plt = _pyplot()
    theme = get_theme(spec.theme)
    kind = spec.kind
    drawer = _DISPATCH.get(kind)
    if drawer is None:  # pragma: no cover - the spec's Literal already refuses it
        raise ChartRenderError(CHART_SPEC_INVALID, f"unknown chart kind {kind!r}")

    with plt.rc_context(theme.rc):
        figure = plt.figure(figsize=(spec.width / 100.0, spec.height / 100.0), dpi=100)
        try:
            if kind == "radar":
                ax = figure.add_subplot(111, polar=True)
            else:
                ax = figure.add_subplot(111)
            setattr(ax, "_eclipse_theme", theme)
            drawer(ax, spec, theme, plt)
            _apply_titles(ax, spec)
            if spec.footnote:
                figure.text(
                    0.01, 0.015, spec.footnote, ha="left", va="bottom",
                    color=theme.muted, fontsize=8.5,
                )
            if spec.source:
                figure.text(
                    0.99, 0.015, spec.source, ha="right", va="bottom",
                    color=theme.muted, fontsize=8.5,
                )
            figure.tight_layout(rect=(0, 0.05 if (spec.footnote or spec.source) else 0, 1, 1))
            buffer = io.BytesIO()
            figure.savefig(buffer, format="png", transparent=True)
            return buffer.getvalue()
        except ChartRenderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChartRenderError(
                CHART_RENDER_FAILED, f"the chart could not be drawn: {exc}",
            ) from exc
        finally:
            plt.close(figure)


def render_chart_to_png(spec: ChartSpec, path: str) -> int:
    """Render the spec and write the PNG to ``path``. Returns the byte count."""
    data = render_chart(spec)
    with open(path, "wb") as handle:
        handle.write(data)
    return len(data)


__all__ = [
    "CHART_RENDER_FAILED",
    "CHART_RENDER_UNAVAILABLE",
    "CHART_SPEC_INVALID",
    "ChartRenderError",
    "render_chart",
    "render_chart_to_png",
]
