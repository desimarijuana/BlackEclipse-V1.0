"""The Edge Report — one artifact that says what the evidence actually shows.

Phases 1 and 2 produced two honest answers that used to be scattered across a
terminal: *where did the edge come from* (the regime attribution and the
regime-block Monte-Carlo) and *should it be trusted* (the Edge Verdict). This
module binds them into a single, durable document: a grade, the axes behind
it, the flags, the numbers, and the pictures.

The report is **not** advice and it does not compute anything of its own. Every
number in it was measured by the quant engine; every picture is a chart spec
that the ONE chart engine draws and records in the Artifact Center.

Two rules ride along:

* **A figure is computed, never evidence.** Every chart carries the
  `computed` label the chart contract requires.
* **What was not measured is stated.** The report names the axes it could not
  judge and the assumptions it made, so a reader never mistakes a missing
  measurement for a good result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..charts.spec import MAX_CATEGORIES, MAX_SERIES_POINTS, ChartSpec
from .verdict import VerdictConfig, grade_edge


class EdgeReportError(ValueError):
    pass


#: The chart engine's bounds. The categories bound is the tighter one, so a
#: report samples to it and says so in the figure's footnote.
MAX_POINTS = min(MAX_SERIES_POINTS, MAX_CATEGORIES)


@dataclass
class EdgeReport:
    """A finished report: the verdict, the document and the chart specs."""

    verdict: dict[str, Any]
    markdown: str
    charts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "markdown": self.markdown,
            "charts": self.charts,
            "warnings": self.warnings,
        }


def _downsample(values: list[float], limit: int = MAX_POINTS) -> tuple[list[float], int, list[int]]:
    """Keep the shape of a long series within the chart engine's bound.

    The first and last points are always kept, and the middle is sampled
    evenly, so the visible curve still starts and ends where the data does.
    """
    if len(values) <= limit:
        return list(values), 0, list(range(len(values)))
    step = (len(values) - 1) / (limit - 1)
    indices = sorted({int(round(i * step)) for i in range(limit)})
    return [values[i] for i in indices], len(values) - len(indices), indices


def _equity_series(artifact: dict[str, Any]) -> tuple[list[float], list[str], int]:
    curve = artifact.get("equityCurve") or []
    values = [float(p.get("equity") or 0.0) for p in curve]
    labels = [str(p.get("ts") or "") for p in curve]
    sampled, dropped, indices = _downsample(values)
    if dropped:
        labels = [labels[i] for i in indices if i < len(labels)]
    return sampled, labels, dropped


def _drawdown_series(artifact: dict[str, Any]) -> tuple[list[float], int]:
    curve = artifact.get("drawdownCurve") or []
    values = [float(p.get("drawdown") or 0.0) for p in curve]
    sampled, dropped, _ = _downsample(values)
    return sampled, dropped


def _regime_rows(regimes: Optional[dict[str, Any]]) -> list[tuple[str, float]]:
    buckets = (regimes or {}).get("regimes") or {}
    rows = [(str(label), float(bucket.get("netPnl") or 0.0))
            for label, bucket in buckets.items()]
    return sorted(rows, key=lambda row: row[1])


def _chart_specs(
    artifact: dict[str, Any],
    monte_carlo: Optional[dict[str, Any]],
    regimes: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The chart specs of the report, in the order they should be read."""
    charts: list[dict[str, Any]] = []
    metadata = artifact.get("metadata") or {}
    strategy_id = str(metadata.get("strategyId") or "")
    symbols = ", ".join(metadata.get("symbols") or [])

    equity, labels, dropped = _equity_series(artifact)
    if len(equity) >= 2:
        footnote = None
        if dropped:
            footnote = (f"{dropped} of {len(equity) + dropped} points were sampled out "
                        f"to fit the chart engine's {MAX_POINTS}-point bound; the "
                        f"shape is preserved, the resolution is not")
        charts.append({
            "name": "equity",
            "title": "Equity curve",
            "spec": ChartSpec(
                kind="line",
                title="Equity curve",
                subtitle=f"{strategy_id} · {symbols}" if symbols else strategy_id or None,
                x_label="bar",
                y_label="equity",
                categories=labels,
                series=[{"name": "Equity", "data": equity}],
                footnote=footnote,
                source="Eclipse quant engine — computed",
                show_points=False,
            ).to_dict(),
        })

    drawdown, dropped_dd = _drawdown_series(artifact)
    if len(drawdown) >= 2:
        charts.append({
            "name": "drawdown",
            "title": "Drawdown",
            "spec": ChartSpec(
                kind="area",
                title="Drawdown",
                subtitle="peak to trough, in per cent",
                x_label="bar",
                y_label="drawdown %",
                series=[{"name": "Drawdown %", "data": drawdown}],
                footnote=("points were sampled out to fit the chart engine's "
                          f"{MAX_POINTS}-point bound" if dropped_dd else None),
                source="Eclipse quant engine — computed",
            ).to_dict(),
        })

    if monte_carlo:
        percentiles = monte_carlo.get("returnPercentiles") or {}
        order = [("p5", "p5"), ("p25", "p25"), ("p50", "median"), ("p75", "p75"),
                 ("p95", "p95")]
        names = [label for _, label in order]
        values = [float(percentiles[key]) for key, _ in order
                  if percentiles.get(key) is not None]
        if values:
            charts.append({
                "name": "monte-carlo",
                "title": "Monte-Carlo return distribution",
                "spec": ChartSpec(
                    kind="bar",
                    title="Monte-Carlo return percentiles",
                    subtitle=monte_carlo.get("method") or None,
                    x_label="percentile",
                    y_label="return %",
                    categories=names[: len(values)],
                    series=[{"name": "Return %", "data": values}],
                    source="Eclipse quant engine — computed",
                ).to_dict(),
            })

        distribution = monte_carlo.get("returnDistribution") or {}
        bins = distribution.get("bins") or []
        counts = distribution.get("counts") or []
        if bins and counts:
            mids = [f"{(float(bins[i]) + float(bins[i + 1])) / 2:.1f}"
                    for i in range(min(len(bins) - 1, len(counts)))]
            values = [float(c) for c in counts[: len(mids)]]
            charts.append({
                "name": "distribution",
                "title": "Return distribution",
                "spec": ChartSpec(
                    kind="bar",
                    title="Simulated return distribution",
                    subtitle=f"{monte_carlo.get('successful')} paths",
                    x_label="return %",
                    y_label="paths",
                    categories=mids,
                    series=[{"name": "Paths", "data": values}],
                    source="Eclipse quant engine — computed",
                ).to_dict(),
            })

    rows = _regime_rows(regimes)
    if rows:
        charts.append({
            "name": "regimes",
            "title": "P&L by market regime",
            "spec": ChartSpec(
                kind="bar",
                title="Realised P&L by market regime",
                subtitle="trend × volatility, classified causally from the same bars",
                x_label="regime",
                y_label="net P&L",
                categories=[label for label, _ in rows],
                series=[{"name": "Net P&L", "data": [value for _, value in rows]}],
                source="Eclipse quant engine — computed",
            ).to_dict(),
        })

    return charts


def _component_table(verdict: dict[str, Any]) -> list[str]:
    lines = ["| Axis | Score | Graded on |", "| --- | --- | --- |"]
    components = verdict.get("components") or {}
    for name, component in components.items():
        score = component.get("score")
        lines.append(
            f"| {name} | {'—' if score is None else f'{score:.0f}/100'} | "
            f"{component.get('basis')} |")
    return lines


def _markdown(
    artifact: dict[str, Any],
    verdict: dict[str, Any],
    monte_carlo: Optional[dict[str, Any]],
    regimes: Optional[dict[str, Any]],
    charts: list[dict[str, Any]],
) -> str:
    metadata = artifact.get("metadata") or {}
    configuration = artifact.get("configuration") or {}
    metrics = artifact.get("metrics") or {}
    grade = verdict.get("grade")
    score = verdict.get("score")

    lines: list[str] = []
    lines.append(f"# Edge Report — {metadata.get('strategyId') or 'strategy'}")
    lines.append("")
    lines.append(f"**Grade {grade}** ({score:.0f}/100) — {verdict.get('summary', '')}")
    lines.append("")
    lines.append(f"- Experiment: `{metadata.get('strategyId') or '—'}` "
                 f"v{metadata.get('strategyVersion') or '—'}")
    lines.append(f"- Instruments: {', '.join(metadata.get('symbols') or []) or '—'}")
    lines.append(f"- Interval: {metadata.get('interval') or configuration.get('interval') or '—'}")
    lines.append(f"- Window: {configuration.get('start') or '—'} → {configuration.get('end') or '—'}")
    lines.append(f"- Engine: {metadata.get('engineVersion') or '—'} · seed "
                 f"{configuration.get('randomSeed') or configuration.get('seed') or '—'}")
    lines.append("")

    lines.append("## The axes")
    lines.append("")
    lines.extend(_component_table(verdict))
    lines.append("")

    flags = verdict.get("flags") or []
    if flags:
        lines.append("## What to look at")
        lines.append("")
        for flag in flags:
            lines.append(f"- **{flag.get('code')}** ({flag.get('severity')}): "
                         f"{flag.get('message')}")
        lines.append("")

    lines.append("## Measured")
    lines.append("")
    wanted = ("total_return", "cagr", "volatility", "sharpe", "sortino", "calmar",
              "max_drawdown", "ulcer_index", "var_95", "cvar_95", "omega",
              "profit_factor", "expectancy", "win_rate", "trade_count")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for name in wanted:
        value = metrics.get(name)
        if value is None:
            continue
        lines.append(f"| {name} | {value:.4f} |" if isinstance(value, (int, float))
                     else f"| {name} | {value} |")
    lines.append("")

    if monte_carlo:
        lines.append("## Under uncertainty")
        lines.append("")
        percentiles = monte_carlo.get("returnPercentiles") or {}
        for key in ("p5", "p25", "p50", "p75", "p95"):
            if percentiles.get(key) is not None:
                lines.append(f"- {key} return: {float(percentiles[key]):.2f}%")
        if monte_carlo.get("probabilityOfLoss") is not None:
            lines.append(f"- probability of loss: "
                         f"{float(monte_carlo['probabilityOfLoss']):.1f}%")
        if monte_carlo.get("probabilityOfRuin") is not None:
            lines.append(f"- probability of ruin: "
                         f"{float(monte_carlo['probabilityOfRuin']):.1f}%")
        if monte_carlo.get("method"):
            lines.append(f"- method: `{monte_carlo['method']}`")
        lines.append("")

    if regimes:
        rows = _regime_rows(regimes)
        if rows:
            lines.append("## Where the P&L came from")
            lines.append("")
            lines.append("| Regime | Net P&L |")
            lines.append("| --- | --- |")
            for label, value in rows:
                lines.append(f"| {label} | {value:.2f} |")
            lines.append("")

    if charts:
        lines.append("## Figures")
        lines.append("")
        for chart in charts:
            lines.append(f"- {chart.get('title')} (`{chart.get('name')}`) — "
                         f"computed by the chart engine, recorded in the Artifact Center")
        lines.append("")

    assumptions = verdict.get("assumptions") or {}
    not_graded = assumptions.get("notGradedOn") or []
    lines.append("## What this report does not say")
    lines.append("")
    if not_graded:
        lines.append(f"- The {', '.join(not_graded)} axis could not be judged from "
                     f"the inputs given; its weight was redistributed.")
    else:
        lines.append("- Every axis was judged from measured evidence.")
    lines.append("- A figure is computed, never evidence.")
    lines.append("- Intraday equity was not modelled; a drawdown that recovered "
                 "before the close cannot be seen from closed trades.")
    lines.append("- This grades evidence. It is not investment advice, and past "
                 "performance does not indicate future results.")
    lines.append("")
    return "\n".join(lines)


def build_edge_report(
    artifact: dict[str, Any],
    monte_carlo: Optional[dict[str, Any]] = None,
    *,
    verdict_config: Optional[VerdictConfig] = None,
) -> EdgeReport:
    """Build the Edge Report from a stored experiment artifact."""
    if not artifact:
        raise EdgeReportError("no experiment artifact was supplied")
    metrics = artifact.get("metrics") or {}
    trades = artifact.get("trades") or []
    equity_curve = artifact.get("equityCurve") or []
    regimes = (monte_carlo or {}).get("regimeAttribution")

    verdict = grade_edge(
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
        monte_carlo=monte_carlo,
        regimes=regimes,
        config=verdict_config,
    )
    charts = _chart_specs(artifact, monte_carlo, regimes)
    markdown = _markdown(artifact, verdict, monte_carlo, regimes, charts)

    warnings: list[dict[str, Any]] = []
    if not monte_carlo:
        warnings.append({
            "code": "EDGE_REPORT_WITHOUT_MONTE_CARLO",
            "severity": "info",
            "message": "no Monte-Carlo result was supplied, so the robustness axis "
                       "could not be judged and its weight was redistributed",
        })
    if not equity_curve:
        warnings.append({
            "code": "EDGE_REPORT_WITHOUT_EQUITY_CURVE",
            "severity": "info",
            "message": "the artifact carries no equity curve, so the equity and "
                       "drawdown figures are absent",
        })

    return EdgeReport(verdict=verdict, markdown=markdown, charts=charts,
                      warnings=warnings)


__all__ = [
    "EdgeReport",
    "EdgeReportError",
    "MAX_POINTS",
    "build_edge_report",
]
