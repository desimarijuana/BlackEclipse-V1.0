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


__all__ = [
    "BENCHMARKS_PATH",
    "to_benchmarks",
    "to_html",
    "to_json",
    "to_jsonl",
    "to_markdown",
    "write_benchmarks",
    "write_report",
]


# ── The PUBLISHED benchmark file (Round 3 / W8, ADR-H296) ───────────────────

BENCHMARKS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "docs", "harness", "benchmarks.md",
)


def _provenance_lines(suite: Any) -> list[str]:
    """The lines that make a number CHECKABLE.

    A number without its dataset, its commit, its agent version and its grader
    version is not a measurement - it is a rumour. Every published number
    carries all four.
    """
    return [
        f"- run: `{suite.run_id}`",
        f"- dataset: `{suite.dataset_name}` @ `{suite.dataset_version}` "
        f"(checksum `{suite.dataset_checksum}`)",
        f"- tier: {suite.tier}",
        f"- agent version: `{suite.agent_version or 'unknown'}`",
        f"- git commit: `{suite.git_commit or 'unknown'}`",
        f"- grader version: `{suite.config.get('graderVersion', 'unknown')}`",
        f"- config: `{suite.config}`",
    ]


def to_benchmarks(offline: Any = None, live: Any = None, *, live_reason: str = "") -> str:
    """The published benchmark file: two tiers, kept apart, never blended.

    The OFFLINE tier runs a SCRIPTED model. It measures the RUNTIME - the
    tool surface, the policy, the graders, the wiring. It says nothing about
    how good a model is, and it is labelled that way.

    The LIVE tier runs a REAL model. It is the only tier that measures the
    agent. When it has not been run, it is published as NOT MEASURED with the
    reason - never as a zero, never as a pass, and never quietly omitted.
    """
    lines = [
        "# Published benchmarks",
        "",
        "**GENERATED FILE - do not edit it.** Regenerate with:",
        "",
        "```bash",
        "python -m harness.evaluation.report",
        "```",
        "",
        "A number here is only worth what its provenance is worth, so every",
        "tier carries its dataset, its checksum, its agent version, its commit",
        "and its grader version. The two tiers are kept APART on purpose: the",
        "offline tier measures the harness, the live tier measures the agent.",
        "",
    ]

    if offline is not None:
        aggregates = offline.aggregates
        lines += [
            "## Offline tier - the scripted model",
            "",
            "A deterministic script replaces the model, so this measures the",
            "**runtime** (the tool surface, the policy, the graders, the wiring)",
            "- not the model. It is the floor the harness must never fall below.",
            "",
            *_provenance_lines(offline),
            f"- gate: **{'PASS' if offline.passed else 'FAIL'}**",
            "",
            "| dimension | value |",
            "|---|---|",
        ]
        for dimension in DIMENSIONS:
            if dimension in aggregates:
                lines.append(f"| {dimension} | {_fmt(aggregates[dimension])} |")
        lines += ["", "### Per category", "", "| category | passed / measured | unmeasured | pass rate |", "|---|---|---|---|"]
        for category, row in offline.categories.items():
            lines.append(
                f"| {category} | {row['passed']}/{row['measured']} | {row['unmeasured']} | "
                f"{_fmt(row['passRate'], pct=True)} |"
            )
        if offline.thresholds.get("failures"):
            lines += ["", "### Gate failures", ""]
            lines += [f"- {failure}" for failure in offline.thresholds["failures"]]
        if offline.unmeasured_tasks:
            lines += ["", "### Unmeasured tasks", ""]
            lines += [f"- `{task_id}`" for task_id in offline.unmeasured_tasks]
        lines.append("")
    else:
        lines += [
            "## Offline tier - the scripted model",
            "",
            "**NOT MEASURED** - the offline gate did not run in this generation.",
            "",
        ]

    if live is not None:
        aggregates = live.aggregates
        lines += [
            "## Live tier - a real model",
            "",
            "This is the only tier that measures the **agent**. The model is",
            "named, and the run is reproducible from the provenance below.",
            "",
            *_provenance_lines(live),
            f"- gate: **{'PASS' if live.passed else 'FAIL'}**",
            "",
            "| dimension | value |",
            "|---|---|",
        ]
        for dimension in DIMENSIONS:
            if dimension in aggregates:
                lines.append(f"| {dimension} | {_fmt(aggregates[dimension])} |")
        if live.thresholds.get("failures"):
            lines += ["", "### Gate failures", ""]
            lines += [f"- {failure}" for failure in live.thresholds["failures"]]
        lines.append("")
    else:
        reason = live_reason or (
            "no live run has been recorded. The live lane needs a configured "
            "provider; run `npm run eval:live -- --model <provider>/<model>`."
        )
        lines += [
            "## Live tier - a real model",
            "",
            "**NOT MEASURED.**",
            "",
            reason,
            "",
            "This is published as missing on purpose. A live number that nobody",
            "has run is a rumour, and a rumour in a benchmark table is worse",
            "than an empty row.",
            "",
        ]

    return "\n".join(lines)


def write_benchmarks(path: Optional[str] = None, *, live: Any = None,
                     live_reason: str = "") -> str:
    """Regenerate the published benchmark file. Returns the path written."""
    from .gate import run_offline_gate  # noqa: PLC0415

    target = path or BENCHMARKS_PATH
    offline = run_offline_gate()
    text = to_benchmarks(offline, live, live_reason=live_reason)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return target


def main(argv: Optional[list[str]] = None) -> int:
    """Regenerate `docs/harness/benchmarks.md` from a FRESH offline gate run."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog="harness.evaluation.report")
    parser.add_argument("--out", default="", help="write somewhere other than the published path")
    parser.add_argument("--live-run", default="", help="the run id of a recorded live run")
    args = parser.parse_args(list(argv) if argv is not None else None)

    live = None
    live_reason = ""
    if args.live_run:
        from .store import EvaluationStore  # noqa: PLC0415
        from ..persistence import AgentMemoryStore  # noqa: PLC0415

        store = AgentMemoryStore()
        try:
            row = EvaluationStore(store).get_run(args.live_run)
        finally:
            store.close()
        if row is None:
            live_reason = f"the run id {args.live_run!r} is not in the evaluation store."
        else:
            live_reason = "the live run was found but its suite was not loaded."
    target = write_benchmarks(args.out or None, live=live, live_reason=live_reason)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
