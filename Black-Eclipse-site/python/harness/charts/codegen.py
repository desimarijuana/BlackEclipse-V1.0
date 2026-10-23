"""The chart SPEC → an editable matplotlib starting script (Phase 21).

A chart in Eclipse is a validated SPEC, never code (see `spec.py`). That is the
right contract for the picture, but it leaves nothing for a reader to edit. This
module generates a small, readable Python program from the SAME spec so an
"Edit code" action can hand the reader a starting point.

Two rules keep the generated program honest:

* The numbers travel as DATA (`inputs["chart"]`), never as source text. A long
  series therefore cannot blow up the program, and the program cannot invent a
  point the spec did not carry.
* A chart kind or mark that this template cannot reproduce is NAMED in
  `unsupported`; it is never silently drawn as something else. The reader is told
  which parts are missing.

The result is deliberately a starting point, not a pixel-parity promise: the
declarative chart remains the canonical output.
"""

from __future__ import annotations

from .spec import ChartSpec

_SIMPLE_TEMPLATE = '''# Editable starting script generated from a chart in Eclipse.
# The chart's data is in `inputs["chart"]`; edit this program and run it.
# A picture is worked out by Eclipse -- it is never a source.
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

chart = inputs.get("chart") or {}
kind = str(chart.get("kind") or "line")
series = chart.get("series") or []
categories = chart.get("categories") or []
labels = chart.get("labels") or []
values = chart.get("values") or []
points = chart.get("points") or []
candles = chart.get("candles") or []


def _data(item):
    return [None if value is None else float(value) for value in (item.get("data") or [])]


def _xs(count):
    return categories if categories else list(range(count))


fig, ax = plt.subplots(figsize=(9, 4.6), dpi=110)

if kind in ("pie", "donut"):
    slice_labels = labels or [item.get("name") or "Series" for item in series]
    slice_values = values or (_data(series[0]) if series else [])
    wedge = {"width": 0.62} if kind == "donut" else None
    ax.pie(slice_values, labels=slice_labels, autopct="%1.1f%%", wedgeprops=wedge)
    ax.axis("equal")
elif kind in ("bar", "stackedBar"):
    count = max(1, len(series))
    width = 0.8 / count
    bottom = [0.0] * len(categories or (_data(series[0]) if series else []))
    for index, item in enumerate(series):
        vals = _data(item)
        if chart.get("stacked"):
            ax.bar(range(len(vals)), vals, bottom=bottom, label=item.get("name") or f"Series {index + 1}")
            bottom = [left + (value or 0.0) for left, value in zip(bottom, vals)]
        else:
            offset = (index - (count - 1) / 2) * width
            ax.bar([i + offset for i in range(len(vals))], vals, width=width,
                   label=item.get("name") or f"Series {index + 1}")
    if categories:
        ax.set_xticks(range(len(categories)))
        ax.set_xticklabels(categories, rotation=30, ha="right")
elif kind == "area":
    for index, item in enumerate(series):
        vals = _data(item)
        xs = _xs(len(vals))
        ax.fill_between(xs, vals, alpha=0.25)
        ax.plot(xs, vals, linewidth=1.4,
                label=item.get("name") or f"Series {index + 1}")
elif kind == "histogram":
    vals = values or (_data(series[0]) if series else [])
    ax.hist([value for value in vals if value is not None],
            bins=int(chart.get("bins") or 20), edgecolor="#0f172a", linewidth=0.4)
elif kind == "scatter":
    if points:
        ax.scatter([float(point.get("x")) for point in points],
                   [float(point.get("y")) for point in points], s=24)
    for index, item in enumerate(series):
        pairs = [value for value in (item.get("data") or [])
                 if isinstance(value, (list, tuple)) and len(value) >= 2]
        ax.scatter([float(pair[0]) for pair in pairs], [float(pair[1]) for pair in pairs],
                   label=item.get("name") or f"Series {index + 1}")
elif kind == "candlestick":
    for index, candle in enumerate(candles):
        open_, high, low, close = (float(candle.get(key, 0)) for key in
                                   ("open", "high", "low", "close"))
        ax.vlines(index, low, high, color="#94a3b8", linewidth=0.8)
        ax.add_patch(Rectangle((index - 0.3, min(open_, close)), 0.6,
                               max(abs(close - open_), 1e-9),
                               color="#10b981" if close >= open_ else "#ef4444"))
    ax.set_xlim(-0.6, max(0.6, len(candles) - 0.4))
else:
    for index, item in enumerate(series):
        vals = _data(item)
        ax.plot(_xs(len(vals)), vals, linewidth=1.5,
                label=item.get("name") or f"Series {index + 1}")
    if chart.get("stacked") and len(series) > 1:
        ax.stackplot(_xs(max((len(_data(item)) for item in series), default=0)),
                     *[_data(item) for item in series],
                     labels=[item.get("name") or f"Series {i + 1}" for i, item in enumerate(series)],
                     alpha=0.55)

if chart.get("title"):
    ax.set_title(str(chart["title"]))
if chart.get("xLabel"):
    ax.set_xlabel(str(chart["xLabel"]))
if chart.get("yLabel"):
    ax.set_ylabel(str(chart["yLabel"]))
if chart.get("logScale"):
    ax.set_yscale("log")
if series and kind not in ("pie", "donut"):
    ax.legend()
ax.grid(True, alpha=0.2)
fig.tight_layout()

buffer = io.BytesIO()
fig.savefig(buffer, format="png", transparent=True)
plt.close(fig)
write_artifact("chart.png", buffer.getvalue())
result = {"kind": kind, "series": len(series), "points": sum(len(_data(item)) for item in series)}
'''

_SCENE_TEMPLATE = '''# Editable starting script generated from a compositional chart in Eclipse.
# The chart's panels and marks are in `inputs["chart"]`; edit and run.
# A picture is worked out by Eclipse -- it is never a source.
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

chart = inputs.get("chart") or {}
panels = chart.get("panels") or []
if not panels:
    panels = [{"marks": []}]

skipped = []
fig, axes = plt.subplots(len(panels), 1, figsize=(9, 2.8 * len(panels) + 1.2),
                         dpi=110, squeeze=False)
for index, panel in enumerate(panels):
    ax = axes[index][0]
    for item in panel.get("marks") or []:
        mark_type = str(item.get("type") or "line")
        raw = item.get("y") or item.get("data") or item.get("values") or []
        ys = []
        for value in raw:
            if isinstance(value, (int, float)):
                ys.append(float(value))
            elif isinstance(value, (list, tuple)) and len(value) >= 2 and isinstance(value[1], (int, float)):
                ys.append(float(value[1]))
            else:
                ys.append(None)
        xs = item.get("x") or list(range(len(ys)))
        label = item.get("name") or None
        if mark_type in ("line", "stem", "regression"):
            ax.plot(xs, ys, linewidth=1.4, label=label)
            if mark_type == "stem":
                ax.vlines(xs, 0, ys, linewidth=0.8)
        elif mark_type == "area":
            ax.fill_between(xs, ys, alpha=0.25)
            ax.plot(xs, ys, linewidth=1.2, label=label)
        elif mark_type == "bar":
            ax.bar(xs, ys, label=label)
        elif mark_type in ("scatter", "bubble"):
            ax.scatter(xs, ys, label=label, s=22)
        elif mark_type == "histogram":
            ax.hist([value for value in ys if value is not None], bins=20,
                    edgecolor="#0f172a", linewidth=0.4)
        else:
            skipped.append(mark_type)
    if panel.get("title"):
        ax.set_title(str(panel["title"]))
    if panel.get("xLabel"):
        ax.set_xlabel(str(panel["xLabel"]))
    if panel.get("yLabel"):
        ax.set_ylabel(str(panel["yLabel"]))
    if panel.get("logScale"):
        ax.set_yscale("log")
    ax.grid(True, alpha=0.2)
    if any(item.get("name") for item in panel.get("marks") or []):
        ax.legend()

if chart.get("title"):
    fig.suptitle(str(chart["title"]))
fig.tight_layout()

buffer = io.BytesIO()
fig.savefig(buffer, format="png", transparent=True)
plt.close(fig)
write_artifact("chart.png", buffer.getvalue())
result = {"panels": len(panels), "skipped": sorted(set(skipped))}
'''

_SIMPLE_KINDS = {
    "line", "area", "bar", "stackedBar", "pie", "donut", "scatter",
    "histogram", "candlestick",
}
_SCENE_MARKS = {
    "line", "area", "bar", "scatter", "histogram", "stem", "regression",
    "bubble",
}


def generate_source(spec: ChartSpec) -> tuple[str, list[str]]:
    """Return (source, unsupported) for a resolved chart spec.

    `unsupported` names the marks/kinds the template could not reproduce, so the
    surface can say what is missing instead of implying full parity.
    """
    title = spec.title or "chart"
    header = f"# Chart: {title}\n"
    if spec.panels:
        unsupported = sorted({
            mark.type for panel in spec.panels for mark in panel.marks
            if mark.type not in _SCENE_MARKS
        })
        return header + _SCENE_TEMPLATE, unsupported
    unsupported = [] if spec.kind in _SIMPLE_KINDS else [spec.kind]
    return header + _SIMPLE_TEMPLATE, unsupported


__all__ = ["generate_source"]
