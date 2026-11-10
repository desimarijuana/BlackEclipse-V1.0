"""The Quant Figure Kit — deterministic figures built from stored artifacts.

Quant mode is visual-first: an answer should open with the picture that answers
the question, and the prose should interpret it. That only works if the figures
are *computed*, not authored by the model. Every builder here reads a stored
quant artifact (a backtest, a Monte-Carlo, an optimization, a walk-forward run)
and returns a chart-engine `ChartSpec`; nothing is typed in by a language model
and no builder invents a point.

Two rules are inherited from the rest of the engine:

* **A figure is computed, never evidence.** Every spec carries the engine's
  computed source label and the chart contract still marks it `isEvidence:
  false`.
* **What cannot be measured is not drawn.** A missing input raises
  `FigureUnavailable` with a reason; it never becomes an empty or plausible
  looking chart.

The figures are grouped into presets so a caller can ask for one thing instead
of a list of twelve:

    core        equity, underwater, monthly returns, trade distribution
    risk        exposure, rolling risk, cost waterfall
    robustness  Monte-Carlo, regime attribution, parameter surface
    validation  walk-forward
    everything  all of the above
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ..charts.spec import MAX_CATEGORIES, MAX_SERIES_POINTS, ChartSpec

#: The chart engine's tighter bound (the category axis).
MAX_POINTS = min(MAX_SERIES_POINTS, MAX_CATEGORIES)

SOURCE_LABEL = "Eclipse quant engine — computed"


class FigureUnavailable(ValueError):
    """A figure that cannot be drawn honestly, with the reason named."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class QuantFigure:
    """One figure: the name a caller asks for, its spec, and why it is absent."""

    name: str
    title: str
    spec: Optional[dict[str, Any]]
    available: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "available": self.available,
            "reason": self.reason,
            "spec": self.spec,
        }


#: The figure vocabulary. `label` is the human title a block carries.
FIGURE_CATALOG: dict[str, str] = {
    "equity": "Equity curve",
    "underwater": "Drawdown (underwater)",
    "monthly_returns": "Monthly returns",
    "exposure": "Exposure",
    "trade_distribution": "Trade P&L distribution",
    "trade_scatter": "Trades: P&L vs holding time",
    "rolling_risk": "Rolling risk",
    "cost_waterfall": "Execution costs",
    "montecarlo": "Monte-Carlo return distribution",
    "regime_attribution": "Realised P&L by market regime",
    "parameter_surface": "Parameter sensitivity surface (3D)",
    "walkforward": "Walk-forward: in-sample vs out-of-sample",
}

FIGURE_PRESETS: dict[str, tuple[str, ...]] = {
    "core": ("equity", "underwater", "monthly_returns", "trade_distribution"),
    "risk": ("exposure", "rolling_risk", "cost_waterfall"),
    "robustness": ("montecarlo", "regime_attribution", "parameter_surface"),
    "validation": ("walkforward",),
    "everything": tuple(FIGURE_CATALOG),
}

#: Figures whose source artifact is a research run, not the base backtest.
RESEARCH_FIGURES: dict[str, str] = {
    "montecarlo": "monteCarloExperimentId",
    "regime_attribution": "monteCarloExperimentId",
    "parameter_surface": "optimizationExperimentId",
    "walkforward": "walkForwardExperimentId",
}


def resolve_figures(requested: Optional[Iterable[str]]) -> list[str]:
    """Expand presets and de-duplicate, preserving the requested order."""
    wanted: list[str] = []
    for raw in requested or ("core",):
        name = str(raw or "").strip().lower()
        if not name:
            continue
        if name in FIGURE_PRESETS:
            wanted.extend(FIGURE_PRESETS[name])
        elif name in FIGURE_CATALOG:
            wanted.append(name)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in wanted:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


# ── Small, honest helpers ────────────────────────────────────────────────────


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _curve(artifact: dict[str, Any], key: str, field: str) -> tuple[list[float], list[str]]:
    points = artifact.get(key) or []
    values: list[float] = []
    labels: list[str] = []
    for index, point in enumerate(points):
        value = _num(point.get(field)) if isinstance(point, dict) else None
        values.append(value)
        labels.append(str(point.get("ts") or point.get("index") or index)
                      if isinstance(point, dict) else str(index))
    return values, labels


def _downsample(
    values: list[Optional[float]],
    labels: Optional[list[str]] = None,
    limit: int = MAX_POINTS,
) -> tuple[list[Optional[float]], Optional[list[str]], int, int]:
    """Keep the first and last point and sample the middle evenly.

    Returns `(values, labels, dropped, total)`. The shape is preserved; the
    resolution is not, and the figure's footnote says so.
    """
    total = len(values)
    if total <= limit or limit < 3:
        return values, labels, 0, total
    step = (total - 1) / (limit - 1)
    indices = sorted({int(round(i * step)) for i in range(limit)})
    sampled = [values[i] for i in indices]
    sampled_labels = [labels[i] for i in indices] if labels else None
    return sampled, sampled_labels, total - len(indices), total


def _sampling_note(dropped: int, total: int) -> Optional[str]:
    if not dropped:
        return None
    return (f"{dropped} of {total} points were sampled out to fit the chart engine's "
            f"{MAX_POINTS}-point bound; the shape is preserved, the resolution is not")


def _strategy_subtitle(artifact: dict[str, Any]) -> str:
    metadata = artifact.get("metadata") or {}
    strategy_id = str(metadata.get("strategyId") or "")
    symbols = ", ".join(str(s) for s in (metadata.get("symbols") or []))
    if strategy_id and symbols:
        return f"{strategy_id} · {symbols}"
    return strategy_id or symbols


def _spec(**kwargs: Any) -> dict[str, Any]:
    """Build and validate a spec, returning its camelCase wire shape."""
    return ChartSpec(**kwargs).to_dict()


def _missing(field: str) -> FigureUnavailable:
    return FigureUnavailable(f"the stored artifact carries no {field}")


# ── Core performance figures ─────────────────────────────────────────────────


def _equity(artifact: dict[str, Any]) -> dict[str, Any]:
    values, labels = _curve(artifact, "equityCurve", "equity")
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        raise _missing("equity curve")
    values, labels, dropped, total = _downsample(values, labels)
    return _spec(
        kind="area",
        title="Equity curve",
        subtitle=_strategy_subtitle(artifact) or None,
        x_label="bar",
        y_label="equity",
        categories=labels,
        series=[{"name": "Equity", "data": values}],
        footnote=_sampling_note(dropped, total),
        source=SOURCE_LABEL,
    )


def _underwater(artifact: dict[str, Any]) -> dict[str, Any]:
    values, labels = _curve(artifact, "drawdownCurve", "drawdown")
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        raise _missing("drawdown curve")
    values, labels, dropped, total = _downsample(values, labels)
    return _spec(
        kind="area",
        title="Drawdown (underwater)",
        subtitle="peak to trough, in per cent",
        x_label="bar",
        y_label="drawdown %",
        categories=labels,
        series=[{"name": "Drawdown %", "data": values}],
        footnote=_sampling_note(dropped, total),
        source=SOURCE_LABEL,
    )


def _monthly_returns(artifact: dict[str, Any]) -> dict[str, Any]:
    rows = artifact.get("monthlyReturns") or []
    months = [
        (str(row.get("month") or ""), _num(row.get("return")))
        for row in rows
        if isinstance(row, dict) and row.get("month")
    ]
    years = sorted({month[:4] for month, _ in months if len(month) >= 7})
    if not years:
        raise _missing("monthly returns")
    grid = {year: [0.0] * 12 for year in years}
    for month, value in months:
        if len(month) < 7 or value is None:
            continue
        year, month_number = month[:4], int(month[5:7])
        if year in grid and 1 <= month_number <= 12:
            grid[year][month_number - 1] = round(value, 4)
    return _spec(
        kind="heatmap",
        title="Monthly returns",
        subtitle="per cent, month by month",
        x_label="month",
        y_label="year",
        matrix=[grid[year] for year in years],
        row_labels=years,
        col_labels=["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        source=SOURCE_LABEL,
        footnote=("a month the run did not cover is shown as 0.0 for layout and "
                  "is not a measured return"),
    )


def _exposure(artifact: dict[str, Any]) -> dict[str, Any]:
    points = artifact.get("exposure") or []
    gross = [_num(p.get("grossExposure")) for p in points if isinstance(p, dict)]
    net = [_num(p.get("netExposure")) for p in points if isinstance(p, dict)]
    labels = [str(p.get("ts") or p.get("index") or i)
              for i, p in enumerate(points) if isinstance(p, dict)]
    if not any(v is not None and v != 0 for v in gross + net):
        raise _missing("exposure series")
    gross, labels, dropped, total = _downsample(gross, labels)
    net, _, _, _ = _downsample(net, None)
    return _spec(
        kind="line",
        title="Exposure",
        subtitle="gross and net, in account currency",
        x_label="bar",
        y_label="exposure",
        categories=labels,
        series=[
            {"name": "Gross exposure", "data": gross},
            {"name": "Net exposure", "data": net, "dashed": True},
        ],
        footnote=_sampling_note(dropped, total),
        source=SOURCE_LABEL,
    )


def _trade_distribution(artifact: dict[str, Any]) -> dict[str, Any]:
    trades = artifact.get("trades") or []
    pnl = [_num(t.get("netPnl")) for t in trades if isinstance(t, dict)]
    pnl = [v for v in pnl if v is not None]
    if len(pnl) < 5:
        raise FigureUnavailable("fewer than five completed trades; a distribution would be noise")
    return _spec(
        kind="scene",
        title="Trade P&L distribution",
        subtitle=f"{len(pnl)} completed trades, net of costs",
        panels=[{
            "title": "Net P&L per trade",
            "xLabel": "P&L",
            "yLabel": "trades",
            "valueFormat": "currency",
            "marks": [
                {"type": "histogram", "name": "Trades",
                 "values": pnl, "bins": min(40, max(8, len(pnl) // 6))},
                {"type": "box", "name": "Distribution", "values": pnl},
            ],
        }],
        source=SOURCE_LABEL,
    )


def _trade_scatter(artifact: dict[str, Any]) -> dict[str, Any]:
    trades = [t for t in (artifact.get("trades") or []) if isinstance(t, dict)]
    points: list[tuple[float, float]] = []
    colors: list[str] = []
    for trade in trades:
        pnl = _num(trade.get("netPnl"))
        bars = _num(trade.get("barsHeld"))
        if pnl is None or bars is None:
            continue
        points.append((bars, pnl))
        colors.append("#4ade80" if pnl >= 0 else "#f87171")
    if len(points) < 3:
        raise FigureUnavailable("fewer than three trades carry both P&L and holding time")
    return _spec(
        kind="scene",
        title="Trades: P&L vs holding time",
        subtitle="each point is one completed trade",
        panels=[{
            "title": "Net P&L by bars held",
            "xLabel": "bars held",
            "yLabel": "net P&L",
            "valueFormat": "currency",
            "marks": [{
                "type": "scatter",
                "name": "Trades",
                "x": [p[0] for p in points],
                "y": [p[1] for p in points],
                "colors": colors,
            }],
        }],
        source=SOURCE_LABEL,
        footnote="sign colour is the trade's net P&L; it is not a prediction",
    )


def _returns(artifact: dict[str, Any]) -> tuple[list[float], str]:
    values, _ = _curve(artifact, "equityCurve", "equity")
    clean = [v for v in values if v is not None and v != 0]
    if len(clean) < 2:
        raise _missing("equity curve")
    returns = [clean[i] / clean[i - 1] - 1.0 for i in range(1, len(clean))
               if clean[i - 1] != 0]
    interval = str((artifact.get("configuration") or {}).get("interval") or "1d")
    return returns, interval


def _annualization(interval: str) -> float:
    from .data import bars_per_year  # noqa: PLC0415 - keep visuals importable alone

    return bars_per_year(interval)


def _rolling_risk(artifact: dict[str, Any]) -> dict[str, Any]:
    returns, interval = _returns(artifact)
    if len(returns) < 30:
        raise FigureUnavailable("fewer than 30 return observations; a rolling statistic is not meaningful")
    window = min(60, max(20, len(returns) // 5))
    periods = _annualization(interval)
    volatility: list[Optional[float]] = []
    sharpe: list[Optional[float]] = []
    for end in range(window, len(returns) + 1):
        sample = returns[end - window:end]
        mean = sum(sample) / len(sample)
        variance = sum((r - mean) ** 2 for r in sample) / (len(sample) - 1)
        std = math.sqrt(variance)
        volatility.append(std * math.sqrt(periods) * 100.0 if std else None)
        sharpe.append((mean / std) * math.sqrt(periods) if std else None)
    if not any(v is not None for v in volatility):
        raise FigureUnavailable("the return series has no variation to measure")
    x = list(range(window, len(returns) + 1))
    return _spec(
        kind="scene",
        title="Rolling risk",
        subtitle=f"{window}-bar window, annualised",
        panels=[
            {"title": "Rolling volatility", "xLabel": "bar", "yLabel": "vol %",
             "valueFormat": "percent",
             "marks": [{"type": "line", "name": "Volatility", "x": x, "y": volatility}]},
            {"title": "Rolling Sharpe", "xLabel": "bar", "yLabel": "Sharpe",
             "marks": [{"type": "line", "name": "Sharpe", "x": x, "y": sharpe}]},
        ],
        source=SOURCE_LABEL,
    )


def _cost_waterfall(artifact: dict[str, Any]) -> dict[str, Any]:
    fills = [f for f in (artifact.get("fills") or []) if isinstance(f, dict)]
    if not fills:
        raise _missing("fills")
    commission = sum(_num(f.get("commission")) or 0.0 for f in fills)
    slippage = sum(_num(f.get("slippage")) or 0.0 for f in fills)
    spread = sum(_num(f.get("spreadCost")) or 0.0 for f in fills)
    impact = sum(_num(f.get("impact")) or 0.0 for f in fills)
    total = commission + slippage + spread + impact
    if total <= 0:
        raise FigureUnavailable(
            "the run recorded no execution costs (an explicit frictionless configuration)")
    return _spec(
        kind="waterfall",
        title="Execution costs",
        subtitle=f"{len(fills)} fills, in account currency",
        categories=["Commission", "Slippage", "Spread", "Impact", "Total"],
        series=[{
            "name": "Cost",
            "data": [round(commission, 4), round(slippage, 4), round(spread, 4),
                     round(impact, 4), round(total, 4)],
        }],
        value_format="currency",
        source=SOURCE_LABEL,
        footnote="components are the fills' own recorded costs; they are not re-estimated",
    )


# ── Research figures ─────────────────────────────────────────────────────────


def _montecarlo(artifact: dict[str, Any]) -> dict[str, Any]:
    percentiles = artifact.get("returnPercentiles") or {}
    order = [("p5", "p5"), ("p25", "p25"), ("p50", "p50"), ("p75", "p75"), ("p95", "p95")]
    bars = [(label, _num(percentiles.get(key))) for key, label in order]
    bars = [(label, value) for label, value in bars if value is not None]

    distribution = artifact.get("returnDistribution") or {}
    bins = distribution.get("bins") or []
    counts = distribution.get("counts") or []
    mids: list[str] = []
    values: list[float] = []
    if bins and counts:
        for i in range(min(len(bins) - 1, len(counts))):
            low, high = _num(bins[i]), _num(bins[i + 1])
            count = _num(counts[i])
            if low is None or high is None or count is None:
                continue
            mids.append(f"{(low + high) / 2.0:.1f}")
            values.append(float(count))

    panels: list[dict[str, Any]] = []
    if bars:
        panels.append({
            "title": "Return percentiles",
            "xLabel": "percentile",
            "yLabel": "return %",
            "valueFormat": "percent",
            "marks": [{"type": "bar", "name": "Return %",
                       "x": [label for label, _ in bars],
                       "y": [value for _, value in bars]}],
        })
    if mids:
        panels.append({
            "title": "Simulated return distribution",
            "xLabel": "return %",
            "yLabel": "paths",
            "marks": [{"type": "bar", "name": "Paths", "x": mids, "y": values}],
        })
    if not panels:
        raise _missing("Monte-Carlo percentiles or distribution")
    return _spec(
        kind="scene",
        title="Monte-Carlo return distribution",
        subtitle=str(artifact.get("method") or "resampled paths"),
        panels=panels,
        source=SOURCE_LABEL,
        footnote=(f"{artifact.get('successful')} successful paths"
                  if artifact.get("successful") is not None else None),
    )


def _regime_attribution(artifact: dict[str, Any]) -> dict[str, Any]:
    attribution = artifact.get("regimeAttribution") or artifact
    buckets = attribution.get("regimes") if isinstance(attribution, dict) else None
    buckets = buckets or attribution
    rows: list[tuple[str, float]] = []
    if isinstance(buckets, dict):
        for label, bucket in buckets.items():
            if not isinstance(bucket, dict):
                continue
            value = _num(bucket.get("netPnl"))
            if value is not None:
                rows.append((str(label), value))
    if not rows:
        raise FigureUnavailable(
            "the artifact carries no regime attribution (run the regime Monte-Carlo first)")
    rows.sort(key=lambda row: row[1])
    return _spec(
        kind="bar",
        title="Realised P&L by market regime",
        subtitle="trend × volatility, classified causally from the same bars",
        x_label="regime",
        y_label="net P&L",
        categories=[label for label, _ in rows],
        series=[{"name": "Net P&L", "data": [value for _, value in rows]}],
        value_format="currency",
        source=SOURCE_LABEL,
    )


def _parameter_surface(artifact: dict[str, Any]) -> dict[str, Any]:
    trials = [t for t in (artifact.get("trials") or []) if isinstance(t, dict)]
    trials = [t for t in trials if _num(t.get("score")) is not None]
    if len(trials) < 4:
        raise FigureUnavailable("fewer than four scored trials; a surface would be invented")
    param_keys = sorted({
        key for trial in trials
        for key, value in (trial.get("params") or {}).items()
        if _num(value) is not None
    })
    ranked = sorted(
        param_keys,
        key=lambda key: len({_num(t.get("params", {}).get(key)) for t in trials}),
        reverse=True,
    )
    axes = [key for key in ranked if len({_num(t.get("params", {}).get(key)) for t in trials}) >= 2]
    if len(axes) < 2:
        raise FigureUnavailable("fewer than two numeric parameters vary across the trials")
    x_key, y_key = axes[0], axes[1]
    objective = str(artifact.get("objective") or "objective")
    points = [
        (_num(t["params"].get(x_key)), _num(t["params"].get(y_key)), _num(t.get("score")))
        for t in trials
    ]
    points = [(x, y, z) for x, y, z in points if x is not None and y is not None and z is not None]
    xs = sorted({x for x, _, _ in points})
    ys = sorted({y for _, y, _ in points})
    cells: dict[tuple[float, float], list[float]] = {}
    for x, y, z in points:
        cells.setdefault((x, y), []).append(z)

    footnote: Optional[str] = None
    if len(axes) > 2:
        others = ", ".join(axes[2:])
        footnote = (f"other swept parameters ({others}) vary between trials; this is a "
                    f"projection of the search, not a controlled grid")

    # A surface needs one score per (x, y) cell. When the grid is incomplete a
    # point cloud is the honest drawing: a filled-in surface would invent points.
    complete = all(len(cells.get((x, y), [])) == 1 for x in xs for y in ys)
    if complete and len(xs) >= 2 and len(ys) >= 2:
        matrix = [[float(cells[(x, y)][0]) for x in xs] for y in ys]
        marks = [{"type": "surface", "name": objective, "x": xs, "y": ys, "matrix": matrix}]
        subtitle = f"{objective} over {x_key} × {y_key} (orbit to inspect)"
    else:
        marks = [{"type": "scatter3d", "name": objective,
                  "x": [p[0] for p in points], "y": [p[1] for p in points],
                  "z": [p[2] for p in points]}]
        subtitle = (f"{objective} over {x_key} × {y_key}; the grid is incomplete, "
                    f"so the trials are shown as a 3D point cloud")
        if footnote:
            footnote += "; the grid is incomplete, so no surface was fabricated"
        else:
            footnote = "the parameter grid is incomplete; the trials are shown as points"
    return _spec(
        kind="scene",
        title="Parameter sensitivity surface (3D)",
        subtitle=subtitle,
        panels=[{
            "title": f"{objective} by {x_key} and {y_key}",
            "xLabel": x_key,
            "yLabel": y_key,
            "marks": marks,
        }],
        source=SOURCE_LABEL,
        footnote=footnote,
    )


def _walkforward(artifact: dict[str, Any]) -> dict[str, Any]:
    windows = [w for w in (artifact.get("windows") or []) if isinstance(w, dict)]
    if not windows:
        raise _missing("walk-forward windows")
    is_values = [_num((w.get("inSample") or {}).get("sharpe")) for w in windows]
    oos_values = [_num((w.get("outOfSample") or {}).get("sharpe")) for w in windows]
    has_scores = any(v is not None for v in is_values + oos_values)
    combined = [p for p in (artifact.get("combinedEquity") or []) if isinstance(p, dict)]
    panels: list[dict[str, Any]] = []
    if has_scores:
        labels = [f"W{i + 1}" for i in range(len(windows))]
        panels.append({
            "title": "Sharpe per window",
            "xLabel": "window",
            "yLabel": "Sharpe",
            "marks": [
                {"type": "line", "name": "In-sample", "x": labels, "y": is_values},
                {"type": "line", "name": "Out-of-sample", "x": labels, "y": oos_values,
                 "style": "dashed"},
            ],
        })
    if combined:
        values = [_num(p.get("equity")) for p in combined]
        labels = [str(p.get("ts") or p.get("index") or i) for i, p in enumerate(combined)]
        values, labels, dropped, total = _downsample(values, labels)
        panels.append({
            "title": "Combined out-of-sample equity",
            "xLabel": "bar",
            "yLabel": "equity",
            "marks": [{"type": "line", "name": "Combined OOS", "x": labels, "y": values}],
        })
    if not panels:
        raise FigureUnavailable("the walk-forward artifact has neither scores nor an equity curve")
    divergence = artifact.get("divergence") or {}
    ratio = _num(divergence.get("ratio"))
    footnote = (f"OOS / IS objective ratio: {ratio:.2f}" if ratio is not None
                else "the artifact did not record an OOS/IS ratio")
    if len(panels) == 1 and panels[0].get("title") == "Combined out-of-sample equity":
        footnote = _sampling_note(0, 0) or footnote
    return _spec(
        kind="scene",
        title="Walk-forward: in-sample vs out-of-sample",
        subtitle=str(artifact.get("objective") or ""),
        panels=panels,
        source=SOURCE_LABEL,
        footnote=footnote,
    )


# ── The dispatch and the public surface ─────────────────────────────────────

_BUILDERS = {
    "equity": _equity,
    "underwater": _underwater,
    "monthly_returns": _monthly_returns,
    "exposure": _exposure,
    "trade_distribution": _trade_distribution,
    "trade_scatter": _trade_scatter,
    "rolling_risk": _rolling_risk,
    "cost_waterfall": _cost_waterfall,
    "montecarlo": _montecarlo,
    "regime_attribution": _regime_attribution,
    "parameter_surface": _parameter_surface,
    "walkforward": _walkforward,
}


def build_figure(name: str, artifact: dict[str, Any], *, theme: str = "eclipse-dark") -> QuantFigure:
    """Build one figure from the artifact that contains its data.

    The builder never mutates the artifact and never reads anything except the
    artifact it was handed. A failure is a named `FigureUnavailable`.
    """
    key = str(name or "").strip().lower()
    builder = _BUILDERS.get(key)
    title = FIGURE_CATALOG.get(key, key.replace("_", " ").title())
    if builder is None:
        return QuantFigure(name=key, title=title, spec=None, available=False,
                           reason=f"unknown quant figure {name!r}")
    try:
        spec = builder(artifact)
    except FigureUnavailable as exc:
        return QuantFigure(name=key, title=title, spec=None, available=False, reason=exc.reason)
    except Exception as exc:  # noqa: BLE001 - a bad artifact is a named absence, not a crash
        return QuantFigure(name=key, title=title, spec=None, available=False,
                           reason=f"the figure could not be built: {exc}")
    spec["theme"] = theme if theme in ("eclipse-dark", "eclipse-light") else "eclipse-dark"
    return QuantFigure(name=key, title=title, spec=spec, available=True)


def build_figures(
    artifact: dict[str, Any],
    *,
    figures: Optional[Iterable[str]] = None,
    theme: str = "eclipse-dark",
) -> list[QuantFigure]:
    """Build a preset (or an explicit list) against ONE artifact."""
    return [build_figure(name, artifact, theme=theme) for name in resolve_figures(figures)]


__all__ = [
    "FIGURE_CATALOG",
    "FIGURE_PRESETS",
    "FigureUnavailable",
    "QuantFigure",
    "RESEARCH_FIGURES",
    "build_figure",
    "build_figures",
    "resolve_figures",
]
