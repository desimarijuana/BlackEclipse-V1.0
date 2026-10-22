"""The unattended nightly session.

Run the corpus, compare the result with the recorded baseline, and write a
dated report. A CRITICAL regression (safety, hallucination rate, task success,
financial accuracy, routing) makes the session FAIL - that is the exit code CI
reads. A warning (cost, latency, tokens) is reported but does not fail.

The baseline is only moved forward when the run is clean AND the caller asks
for it: a worse run never silently becomes the new normal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .baseline import get_baseline, save_baseline, suite_metrics
from .config import report_dir
from .regression import detect_regressions
from .runner import EvaluationRunner
from .store import EvaluationStore
from .tasks import load_all_builtin, load_builtin_dataset, select_tasks

DEFAULT_BASELINE = "nightly-corpus"

#: The measures that move on every run and would make a committed baseline
#: noisy. They are reported as warnings, never compared against a file.
VOLATILE_DIMENSIONS: tuple[str, ...] = ("cost", "latency", "token_usage")


def stable_aggregates(metrics: dict[str, Any]) -> dict[str, Any]:
    """The comparable measures (the volatile ones are dropped)."""
    aggregates = dict(metrics.get("aggregates") or {})
    for key in VOLATILE_DIMENSIONS:
        aggregates.pop(key, None)
    return aggregates


def write_baseline_file(path: str, payload: dict[str, Any]) -> str:
    """Write a COMMITTED baseline: the stable measures plus their provenance."""
    metrics = payload.get("metrics") or {}
    body = {
        "name": payload.get("baselineName") or DEFAULT_BASELINE,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "runId": payload.get("runId"),
        "dataset": payload.get("dataset"),
        "split": payload.get("split"),
        "taskCount": payload.get("taskCount"),
        "datasetChecksum": metrics.get("datasetChecksum"),
        "agentVersion": payload.get("agentVersion"),
        "gitCommit": payload.get("gitCommit"),
        "metrics": {
            "aggregates": stable_aggregates(metrics),
            "categories": metrics.get("categories") or {},
            "passRate": metrics.get("passRate"),
            "datasetChecksum": metrics.get("datasetChecksum"),
            "tier": metrics.get("tier"),
        },
    }
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2, sort_keys=True, default=str)
    return target


def read_baseline_file(path: str) -> dict[str, Any]:
    """Read a committed baseline file (fail-closed on a broken file)."""
    try:
        with open(path, encoding="utf-8") as handle:
            body = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"the baseline file could not be read: {exc}") from exc
    if not isinstance(body, dict) or "metrics" not in body:
        raise ValueError("a baseline file must be an object with a 'metrics' object")
    return body


def _critical(regressions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in regressions if row.get("severity") == "regression"]


def render_markdown(payload: dict[str, Any]) -> str:
    """The nightly report (a person and CI read the same file)."""
    metrics = payload.get("metrics") or {}
    aggregates = metrics.get("aggregates") or {}
    lines = [
        "# Nightly evaluation",
        "",
        f"- run: `{payload.get('runId')}`",
        f"- dataset: `{payload.get('dataset')}` (split `{payload.get('split')}`) · "
        f"tasks: {payload.get('taskCount')}",
        f"- verdict: {'PASS' if payload.get('ok') else 'FAIL'}",
        "",
        "## Measures",
        "",
        "| measure | value |",
        "|---|---|",
    ]
    for key in sorted(aggregates):
        value = aggregates[key]
        lines.append(f"| {key} | {'UNKNOWN' if value is None else value} |")
    regressions = payload.get("regressions") or []
    warnings = payload.get("warnings") or []
    lines += ["", "## Regressions", ""]
    if regressions:
        for row in regressions:
            lines.append(
                f"- **{row.get('dimension')}**: {row.get('baseline')} → "
                f"{row.get('current')} (delta {row.get('delta')})"
            )
    else:
        lines.append("- none")
    lines += ["", "## Warnings", ""]
    if warnings:
        for row in warnings:
            lines.append(
                f"- {row.get('dimension')}: {row.get('baseline')} → {row.get('current')}"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


async def run_nightly(
    store: Any,
    *,
    tasks: Optional[list[Any]] = None,
    dataset: str = "benchmark_v1",
    split: str = "validation",
    trials: int = 1,
    baseline_name: str = DEFAULT_BASELINE,
    promote: bool = False,
    directory: Optional[str] = None,
    baseline_file: Optional[str] = None,
    write_baseline: Optional[str] = None,
    live: bool = False,
    model_settings: Any = None,
) -> dict[str, Any]:
    """Run the corpus once and return the verdict (never raises for a failure)."""
    eval_store = EvaluationStore(store)
    dataset_name = dataset
    if tasks is None:
        if dataset == "all":
            loaded = load_all_builtin()
            dataset_name = "eclipse-benchmark"
        else:
            loaded = load_builtin_dataset(dataset)
            dataset_name = dataset
        tasks = select_tasks(loaded, split=split)
    runner = EvaluationRunner(store, eval_store=eval_store)
    if live:
        # The live tier answers the corpus with a REAL model: the only tier in
        # which a prompt change can move the result. The base is the production
        # agent restricted to the tools the evaluation registry exposes.
        from ..agents import get_agent  # noqa: PLC0415
        from ..self_improvement.models import HarnessSnapshot  # noqa: PLC0415
        from .candidate_invoker import CandidateAgentInvoker  # noqa: PLC0415
        from .runner import _build_registry  # noqa: PLC0415

        agent = get_agent("eclipse-agent")
        registered = set(_build_registry().names())
        base_snapshot = HarnessSnapshot(
            systemPrompt=agent.systemPrompt,
            toolNames=tuple(
                name for name in (agent.tools or ()) if name in registered
            ),
            maxSteps=min(int(agent.maxSteps or 8), 32),
            maxToolCalls=min(int(agent.maxToolCalls or 200), 200),
        )
        runner = EvaluationRunner(
            store,
            invoker=CandidateAgentInvoker(
                store, base_snapshot, base=base_snapshot,
                live=True, model_settings=model_settings,
            ),
            eval_store=eval_store,
        )
    suite = await runner.run_suite(
        tasks,
        dataset_name=dataset_name,
        dataset_version="1",
        trials=max(1, int(trials)),
        tier=0,
        run_id=(
            f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            f"-{uuid.uuid4().hex[:6]}"
        ),
        persist=True,
        split=split,
        metadata={"kind": "nightly", "baseline": baseline_name},
    )
    metrics = suite_metrics(suite)
    previous_metrics: dict[str, Any] = {}
    previous_id = ""
    if baseline_file:
        body = read_baseline_file(baseline_file)
        previous_metrics = body.get("metrics") or {}
        previous_id = str(body.get("recordedAt") or "")
    else:
        previous = get_baseline(eval_store, baseline_name)
        if previous:
            previous_metrics = previous.get("metrics") or {}
            previous_id = str(previous.get("id") or "")
    comparison = detect_regressions(previous_metrics, metrics) if previous_metrics else {
        "regressions": [], "warnings": [],
    }
    regressions = list(comparison.get("regressions") or [])
    warnings = list(comparison.get("warnings") or [])
    critical = _critical(regressions)
    payload = {
        "runId": suite.run_id,
        "dataset": dataset_name,
        "split": split,
        "taskCount": len(tasks),
        "trials": max(1, int(trials)),
        "baselineName": baseline_name,
        "hasBaseline": bool(previous_metrics),
        "baselineId": previous_id,
        "baselineFile": baseline_file,
        "tier": "live" if live else "scripted",
        "agentVersion": getattr(suite, "agent_version", None),
        "gitCommit": getattr(suite, "git_commit", None),
        "metrics": metrics,
        "regressions": regressions,
        "warnings": warnings,
        "ok": not critical,
    }

    target = directory or report_dir()
    os.makedirs(target, exist_ok=True)
    stem = f"nightly-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    json_path = os.path.join(target, f"{stem}.json")
    md_path = os.path.join(target, f"{stem}.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(payload))
    payload["report"] = {"json": json_path, "markdown": md_path}

    if promote and not critical:
        payload["baselineId"] = save_baseline(
            eval_store, baseline_name, suite,
        )
    if write_baseline:
        payload["writtenBaseline"] = write_baseline_file(write_baseline, payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.nightly",
        description="Run the corpus once, compare with the baseline, write the report.",
    )
    parser.add_argument("--dataset", default="benchmark_v1")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--out", default="", help="report directory")
    parser.add_argument("--baseline-file", default="",
                        help="compare against a COMMITTED baseline file")
    parser.add_argument("--write-baseline", default="",
                        help="write the current measures as a baseline file")
    parser.add_argument("--live", action="store_true",
                        help="answer the corpus with a real model (the only tier "
                             "in which a prompt change can move the result)")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--promote", action="store_true",
                        help="move the baseline forward when the run is clean")
    parser.add_argument("--run-db", default="")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    from ..persistence import AgentMemoryStore  # noqa: PLC0415

    store = AgentMemoryStore(args.run_db or None)
    try:
        import asyncio  # noqa: PLC0415

        model_settings = None
        if args.live:
            if not args.provider or not args.model:
                print("--live requires --provider and --model", file=sys.stderr)
                return 2
            from ..schemas import ModelSettings  # noqa: PLC0415

            model_settings = ModelSettings(
                provider=args.provider,
                model=args.model,
                base_url=args.base_url or None,
                api_key=os.environ.get("HARNESS_EVAL_API_KEY") or None,
            )
            print(
                "LIVE tier: real model requests will be sent for every trial",
                file=sys.stderr,
            )
        payload = asyncio.run(run_nightly(
            store,
            dataset=args.dataset,
            split=args.split,
            trials=args.trials,
            baseline_name=args.baseline,
            promote=bool(args.promote),
            directory=args.out or None,
            baseline_file=args.baseline_file or None,
            write_baseline=args.write_baseline or None,
            live=bool(args.live),
            model_settings=model_settings,
        ))
    finally:
        store.close()
    print(render_markdown(payload))
    print(f"report: {payload.get('report', {}).get('markdown')}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
