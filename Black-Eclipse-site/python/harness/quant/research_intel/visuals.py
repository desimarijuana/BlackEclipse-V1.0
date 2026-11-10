"""Deterministic research figures — the data a quant would actually look at.

Every figure is built from real inputs: method coverage, suitability scores,
price bars, returns, or a reproduction record. A figure with no input is an
`unavailable` entry with a reason; it is never a decorative empty chart.

The output is chat `chart` blocks carrying computed data. The model embeds the
blocks verbatim; it never retypes the numbers.
"""

from __future__ import annotations

import math
import json
from typing import Any, Iterable

from ...charts.spec import MAX_CATEGORIES, ChartSpec

SOURCE = "Eclipse quant research — computed"
_HORIZONS = ("intraday", "swing", "position", "long-term")


def _downsample(values: list[Any], labels: list[str], limit: int = 300) -> tuple[list[Any], list[str], int]:
    total = len(values)
    if total <= limit:
        return values, labels, 0
    step = max(1, total // limit)
    idx = list(range(0, total, step))
    if idx[-1] != total - 1:
        idx.append(total - 1)
    return [values[i] for i in idx], [labels[i] for i in idx], total - len(idx)


def _spec(**kwargs: Any) -> dict[str, Any]:
    return ChartSpec(**kwargs).to_dict()


def _block(spec: dict[str, Any], block_id: str, *, note: str = "") -> dict[str, Any]:
    kind = str(spec.get("kind") or "line")
    chart_type = {"stackedBar": "stacked_bar"}.get(kind, kind)
    block: dict[str, Any] = {
        "type": "chart",
        "id": block_id[:120],
        "chartType": chart_type if chart_type in {
            "line", "area", "bar", "stacked_bar", "grouped_bar", "pie",
            "scatter", "histogram", "heatmap", "gauge", "radar", "waterfall",
        } else "auto",
        "title": spec.get("title") or "Research figure",
        "source": spec.get("source") or SOURCE,
        "categories": spec.get("categories") or [],
        "series": spec.get("series") or [],
    }
    if spec.get("xLabel"):
        block["xLabel"] = spec["xLabel"]
    if spec.get("yLabel"):
        block["yLabel"] = spec["yLabel"]
    if note:
        block["description"] = note[:300]
    return block


def _unavailable(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "available": False, "reason": reason}


# ── Method coverage ─────────────────────────────────────────────────────────

def method_matrix_figures(methods: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(methods)
    if not rows:
        return {"figures": [], "blocks": [], "unavailable": [_unavailable("method_matrix", "no methods")]}
    counts = {h: 0 for h in _HORIZONS}
    for method in rows:
        for horizon in method.get("horizons") or []:
            if horizon in counts:
                counts[horizon] += 1
    spec = _spec(
        kind="bar", title="Method coverage by horizon",
        subtitle=f"{len(rows)} methods in the open catalog",
        x_label="horizon", y_label="methods",
        categories=list(_HORIZONS),
        series=[{"name": "Methods", "data": [counts[h] for h in _HORIZONS]}],
        footnote="The catalog is a seed. Register a literature-derived method to extend it.",
        source=SOURCE,
    )
    families: dict[str, int] = {}
    for method in rows:
        family = str(method.get("family") or "unspecified")
        families[family] = families.get(family, 0) + 1
    ordered = sorted(families.items(), key=lambda item: (-item[1], item[0]))[:20]
    family_spec = _spec(
        kind="bar", title="Methods by family",
        x_label="family", y_label="methods",
        categories=[name for name, _ in ordered],
        series=[{"name": "Methods", "data": [count for _, count in ordered]}],
        source=SOURCE,
    )
    blocks = [_block(spec, "research_method_horizons"),
              _block(family_spec, "research_method_families")]
    return {
        "figures": [
            {"name": "method_matrix", "available": True, "title": spec["title"]},
            {"name": "method_families", "available": True, "title": family_spec["title"]},
        ],
        "blocks": blocks,
        "unavailable": [],
        "counts": counts,
    }


# ── Market data profile ─────────────────────────────────────────────────────

def _rows(series: Iterable[Any]) -> list[dict[str, Any]]:
    out = []
    for row in series or []:
        if isinstance(row, dict) and row.get("close") is not None:
            out.append(row)
    return out


def price_figures(series: Iterable[Any], *, symbol: str = "") -> dict[str, Any]:
    rows = _rows(series)
    if len(rows) < 5:
        return {"figures": [], "blocks": [], "unavailable": [_unavailable("price", "fewer than 5 bars")]}
    closes = [float(r["close"]) for r in rows]
    labels = [str(r.get("ts") or r.get("timestamp") or i) for i, r in enumerate(rows)]
    closes, labels, dropped = _downsample(closes, labels)
    subtitle = f"{symbol} · {len(rows)} bars" if symbol else f"{len(rows)} bars"
    price = _spec(
        kind="line", title="Price", subtitle=subtitle,
        x_label="time", y_label="price", categories=labels,
        series=[{"name": symbol or "Close", "data": closes}],
        footnote=(f"Downsampled by {dropped} points for display; the source series is intact."
                  if dropped else "Every source bar is shown."),
        source=SOURCE,
    )
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
               if closes[i - 1] > 0 and closes[i] > 0]
    blocks = [_block(price, f"research_price_{symbol or 'series'}")]
    figures = [{"name": "price", "available": True, "title": "Price"}]

    if len(returns) >= 10:
        window = min(20, max(5, len(returns) // 10))
        vol: list[float | None] = []
        for i in range(len(returns)):
            if i < window:
                vol.append(None)
                continue
            sample = returns[i - window + 1:i + 1]
            mean = sum(sample) / len(sample)
            var = sum((x - mean) ** 2 for x in sample) / (len(sample) - 1)
            vol.append(math.sqrt(max(var, 0.0)) * math.sqrt(252))
        vol_c, vol_l, vol_dropped = _downsample(vol, labels[1:])
        vol_spec = _spec(
            kind="line", title=f"Rolling volatility ({window} bars, annualised)",
            subtitle=subtitle, x_label="time", y_label="volatility",
            categories=vol_l, series=[{"name": "Rolling volatility", "data": vol_c}],
            footnote="Computed from log returns; the warm-up region is blank.",
            source=SOURCE,
        )
        blocks.append(_block(vol_spec, f"research_vol_{symbol or 'series'}"))
        figures.append({"name": "rolling_volatility", "available": True,
                        "title": f"Rolling volatility ({window})"})
    else:
        figures.append(_unavailable("rolling_volatility", "fewer than 10 returns"))

    if len(returns) >= 20:
        lo, hi = min(returns), max(returns)
        if hi > lo:
            bins = 16
            width = (hi - lo) / bins
            counts = [0] * bins
            for value in returns:
                idx = min(bins - 1, int((value - lo) / width))
                counts[idx] += 1
            labels_b = [f"{lo + i * width:.4f}" for i in range(bins)]
            hist = _spec(
                kind="bar", title="Return distribution",
                subtitle=f"{len(returns)} log returns · {bins} bins",
                x_label="return", y_label="count", categories=labels_b,
                series=[{"name": "Count", "data": counts}],
                footnote="A histogram of the observed sample, not a fitted distribution.",
                source=SOURCE,
            )
            blocks.append(_block(hist, f"research_returns_{symbol or 'series'}"))
            figures.append({"name": "return_distribution", "available": True,
                            "title": "Return distribution"})
    return {"figures": figures, "blocks": blocks, "unavailable": [],
            "observations": len(rows)}


# ── Suitability / comparison ────────────────────────────────────────────────

def suitability_figures(comparison: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(comparison)
    if not rows:
        return {"figures": [], "blocks": [], "unavailable": [_unavailable("suitability", "no comparison")]}
    rows = sorted(rows, key=lambda r: float(r.get("score") or 0), reverse=True)[:15]
    spec = _spec(
        kind="bar", title="Method suitability",
        subtitle="Methodological fit, not a probability of profit",
        x_label="method", y_label="score / 100",
        categories=[str(r.get("name") or r.get("methodId"))[:40] for r in rows],
        series=[{"name": "Fit score", "data": [float(r.get("score") or 0) for r in rows]}],
        footnote="Each score is the sum of explained factors; assumptions remain untested.",
        source=SOURCE,
    )
    return {"figures": [{"name": "suitability", "available": True,
                         "title": "Method suitability"}],
            "blocks": [_block(spec, "research_suitability")], "unavailable": []}


# ── Reproduction fit ────────────────────────────────────────────────────────

def reproduction_figures(reproduction: dict[str, Any]) -> dict[str, Any]:
    observed = reproduction.get("observedMetrics") or {}
    benchmark = reproduction.get("publishedBenchmark") or {}
    numeric = [(key, value) for key, value in benchmark.items()
               if isinstance(value, (int, float))]
    lookup = {str(k).replace("_", "").lower(): v for k, v in observed.items()
              if isinstance(v, (int, float))}
    rows = []
    for key, expected in numeric:
        got = lookup.get(str(key).replace("_", "").lower())
        if isinstance(got, (int, float)):
            rows.append((key, float(expected), float(got)))
    if not rows:
        return {"figures": [], "blocks": [],
                "unavailable": [_unavailable(
                    "reproduction_fit",
                    "no numeric benchmark and observed pair is available",
                )]}
    spec = _spec(
        kind="bar", title="Reproduction: published vs observed",
        x_label="metric", y_label="value",
        categories=[row[0] for row in rows],
        series=[{"name": "Published", "data": [row[1] for row in rows]},
                {"name": "Observed", "data": [row[2] for row in rows]}],
        footnote="A close value is a reproduction check, not a trading edge.",
        source=SOURCE,
    )
    return {"figures": [{"name": "reproduction_fit", "available": True,
                         "title": "Reproduction fit"}],
            "blocks": [_block(spec, "research_reproduction_fit")], "unavailable": []}


# ── Composition ─────────────────────────────────────────────────────────────

def build_research_figures(
    *,
    methods: Iterable[dict[str, Any]] | None = None,
    comparison: Iterable[dict[str, Any]] | None = None,
    series: Iterable[Any] | None = None,
    symbol: str = "",
    reproduction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    figures: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []

    def add(result: dict[str, Any]) -> None:
        figures.extend(result.get("figures") or [])
        blocks.extend(result.get("blocks") or [])
        unavailable.extend(result.get("unavailable") or [])

    if methods:
        add(method_matrix_figures(methods))
    if comparison:
        add(suitability_figures(comparison))
    if series:
        add(price_figures(series, symbol=symbol))
    if reproduction:
        add(reproduction_figures(reproduction))
    return {"figures": figures, "blocks": blocks, "unavailable": unavailable,
            "source": SOURCE}


def figures_markdown(blocks: Iterable[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        lines.append("```chart")
        lines.append(json.dumps(block, ensure_ascii=False, separators=(",", ":")))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "build_research_figures",
    "figures_markdown",
    "method_matrix_figures",
    "price_figures",
    "reproduction_figures",
    "suitability_figures",
]
