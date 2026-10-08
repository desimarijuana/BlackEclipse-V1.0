"""Evaluation reporting: JSON, JSONL, Markdown and HTML.

Every report is machine- and human-readable and keeps metrics SEPARATE. It names
overall/per-task/per-category/per-model/per-grader scores, regressions, failures,
flaky tasks, cost, latency, tokens and trajectory links — and prints ``UNKNOWN``
for anything unmeasured (never ``0``).
"""

from __future__ import annotations

import html
import json
import os
from typing import Any, Optional

from .scoring import DIMENSIONS


def _fmt(value: Optional[float], *, pct: bool = False) -> str:
    if value is None:
        return "UNKNOWN"
    return f"{value * 100:.1f}%" if pct else f"{value:.4f}"


def to_json(suite: Any, *, indent: int = 2) -> str:
    return json.dumps(suite.to_dict(), indent=indent, sort_keys=True, default=str)


def to_jsonl(suite: Any) -> str:
    lines = []
    for task_result in suite.tasks:
        for trial in task_result.trials:
            lines.append(json.dumps({
                "runId": suite.run_id,
                "taskId": trial.task_id,
                "taskVersion": trial.task_version,
                "trialId": trial.trial_id,
                "category": task_result.task.category,
                "passed": trial.passed,
                "unmeasured": trial.unmeasured,
                "labels": trial.labels,
                "dimensions": trial.score.dimensions,
                "composite": trial.score.composite,
            }, sort_keys=True, default=str))
    return "\n".join(lines)


def to_markdown(suite: Any) -> str:
    aggregates = suite.aggregates
    lines = [
        f"# Evaluation report - {suite.run_id}",
        "",
        f"- dataset: `{suite.dataset_name}` @ `{suite.dataset_version}` "
        f"(checksum `{suite.dataset_checksum}`)",
        f"- tier: {suite.tier}",
        f"- gate: {'PASS' if suite.passed else 'FAIL'}",
        "",
        "## Metrics (kept separate - no blended score)",
        "",
        "| dimension | value |",
        "|---|---|",
    ]
    for dimension in DIMENSIONS:
        if dimension in aggregates:
            lines.append(f"| {dimension} | {_fmt(aggregates[dimension])} |")
    lines += ["", "## Per category", "", "| category | passed / measured | unmeasured | pass rate |", "|---|---|---|---|"]
    for category, row in suite.categories.items():
        lines.append(
            f"| {category} | {row['passed']}/{row['measured']} | {row['unmeasured']} | "
            f"{_fmt(row['passRate'], pct=True)} |"
        )
    if suite.unmeasured_tasks:
        lines += ["", "## Unmeasured tasks", ""]
        lines += [f"- `{task_id}`" for task_id in suite.unmeasured_tasks]
    if suite.flaky_tasks:
        lines += ["", "## Flaky tasks (not stable)", ""]
        lines += [f"- `{task_id}`" for task_id in suite.flaky_tasks]
    if suite.thresholds.get("failures"):
        lines += ["", "## Gate failures", ""]
        lines += [f"- {failure}" for failure in suite.thresholds["failures"]]
    if suite.failures:
        lines += ["", "## Failures (by task/trial)", "", "| task | trial | labels |", "|---|---|---|"]
        for failure in suite.failures:
            lines.append(
                f"| {failure['taskId']} | {failure['trialId']} | {', '.join(failure['labels']) or '-'} |"
            )
    lines += ["", "## Trajectories", ""]
    for task_result in suite.tasks:
        for trial in task_result.trials:
            lines.append(f"- `{trial.trial_id}` -> run `{trial.trajectory.run_id}`")
    return "\n".join(lines)


def to_html(suite: Any) -> str:
    def rows() -> str:
        out = []
        for dimension in DIMENSIONS:
            if dimension in suite.aggregates:
                out.append(
                    f"<tr><td>{html.escape(dimension)}</td>"
                    f"<td>{_fmt(suite.aggregates[dimension])}</td></tr>"
                )
        return "".join(out)

    category_rows = "".join(
        f"<tr><td>{html.escape(c)}</td><td>{r['passed']}/{r['measured']}</td>"
        f"<td>{r['unmeasured']}</td><td>{_fmt(r['passRate'], pct=True)}</td></tr>"
        for c, r in suite.categories.items()
    )
    failure_rows = "".join(
        f"<tr><td>{html.escape(f['taskId'])}</td><td>{html.escape(f['trialId'])}</td>"
        f"<td>{html.escape(', '.join(f['labels']) or '-')}</td></tr>"
        for f in suite.failures
    )
    gate = "PASS" if suite.passed else "FAIL"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Eclipse Evaluation — {html.escape(suite.run_id)}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #e6e6e6; background: #0b0b0b; }}
 table {{ border-collapse: collapse; margin: 1rem 0; }}
 td, th {{ border: 1px solid #333; padding: 4px 10px; text-align: left; }}
 h1, h2 {{ font-weight: 600; }}
 .gate {{ font-weight: bold; color: {'#4ade80' if suite.passed else '#f87171'}; }}
</style></head><body>
<h1>Eclipse Evaluation — {html.escape(suite.run_id)}</h1>
<p>dataset <code>{html.escape(suite.dataset_name)}@{html.escape(suite.dataset_version)}</code>
 · tier {suite.tier} · gate <span class="gate">{gate}</span></p>
<h2>Metrics</h2><table><tr><th>dimension</th><th>value</th></tr>{rows()}</table>
<h2>Per category</h2><table><tr><th>category</th><th>passed/measured</th><th>unmeasured</th><th>pass rate</th></tr>{category_rows}</table>
<h2>Failures</h2><table><tr><th>task</th><th>trial</th><th>labels</th></tr>{failure_rows}</table>
</body></html>"""


def write_report(
    suite: Any,
    directory: str,
    *,
    formats: tuple[str, ...] = ("json", "md"),
    name: Optional[str] = None,
) -> list[str]:
    os.makedirs(directory, exist_ok=True)
    stem = name or suite.run_id
    paths: list[str] = []
    renderers = {
        "json": (".json", to_json),
        "jsonl": (".jsonl", to_jsonl),
        "md": (".md", to_markdown),
        "html": (".html", to_html),
    }
    for fmt in formats:
        if fmt not in renderers:
            raise ValueError(f"unknown report format '{fmt}'")
        suffix, render = renderers[fmt]
        path = os.path.join(directory, f"{stem}{suffix}")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(render(suite))
        paths.append(path)
    return paths


__all__ = ["to_html", "to_json", "to_jsonl", "to_markdown", "write_report"]
