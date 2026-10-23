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
from .live_baseline import DEFAULT_LIVE_BASELINE
from .regression import detect_regressions
from .runner import EvaluationRunner
from .store import EvaluationStore
from .tasks import load_all_builtin, load_builtin_dataset, select_tasks

DEFAULT_BASELINE = "nightly-corpus"

#: The hard bound on a single session's task count. A live run is the only one
#: that spends money, so an unbounded slice is refused before any request.
MAX_TASKS = 500

#: The app root (the parent of `python/`). The published report is resolved
#: against it so the Python child's cwd (`python/`) cannot redirect the write
#: into `python/docs/`.
APP_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
DEFAULT_PUBLISH = os.path.join(APP_ROOT, "docs", "self-improvement")

#: The measures that move on every run and would make a committed baseline
#: noisy. They are reported as warnings, never compared against a file.
VOLATILE_DIMENSIONS: tuple[str, ...] = ("cost", "latency", "token_usage")


def validate_budget(
    *,
    live: bool,
    limit: Optional[int] = None,
    max_cost: Optional[float] = None,
) -> None:
    """Refuse an unbounded or uncapped run BEFORE any task is sent (fail-closed).

    A live session costs real money: it must name a positive cap, and no
    session may exceed the task bound. A scripted session needs neither, but
    the task bound still applies when a limit is given.
    """
    if limit is not None and (int(limit) <= 0 or int(limit) > MAX_TASKS):
        raise ValueError(
            f"--limit must be between 1 and {MAX_TASKS} tasks; got {limit}"
        )
    if live and (max_cost is None or float(max_cost) <= 0):
        raise ValueError(
            "--live requires a positive --max-cost: an uncapped paid run is refused"
        )


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
    ]
    budget = []
    if payload.get("limit") is not None:
        budget.append(f"limit {payload.get('limit')}")
    if payload.get("maxCostUsd") is not None:
        budget.append(f"max cost ${payload.get('maxCostUsd')}")
    if payload.get("estimatedWorstCaseTrials"):
        budget.append(f"worst-case trials {payload.get('estimatedWorstCaseTrials')}")
    if budget:
        lines.append(f"- budget: {' · '.join(budget)}")
    lines += [
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
    provider: str = "",
    model: str = "",
    base_url: str = "",
    temperature: Optional[float] = None,
    live_baseline: Optional[str] = None,
    write_live_baseline: Optional[str] = None,
    publish: Optional[str] = None,
    limit: Optional[int] = None,
    max_cost: Optional[float] = None,
) -> dict[str, Any]:
    """Run the corpus once and return the verdict (never raises for a failure)."""
    validate_budget(live=live, limit=limit, max_cost=max_cost)
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
    tasks = list(tasks)
    if limit is not None:
        tasks = tasks[: int(limit)]
    trials = max(1, int(trials))
    runner = EvaluationRunner(store, eval_store=eval_store)
    prompt_hash = ""
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
        prompt_hash = base_snapshot.sourceDigest
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
        trials=trials,
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
        "trials": trials,
        "limit": limit,
        "maxCostUsd": max_cost,
        "estimatedWorstCaseTrials": len(tasks) * trials,
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

    if live:
        from .live_baseline import (  # noqa: PLC0415 - live-only dependency
            build_live_baseline,
            compare_live_baseline,
            find_live_baseline,
            publish_report,
            read_live_baselines,
            write_live_baseline as write_live_registry,
        )

        resolved_provider = provider or str(
            getattr(model_settings, "provider", "") or ""
        )
        resolved_model = model or str(getattr(model_settings, "model", "") or "")
        resolved_base = base_url or str(
            getattr(model_settings, "base_url", "") or ""
        )
        entry = build_live_baseline(
            suite,
            provider=resolved_provider,
            model=resolved_model,
            tier="live",
            base_url=resolved_base,
            temperature=temperature,
            prompt_hash=prompt_hash,
        )
        payload["liveBaseline"] = {
            "key": entry["key"],
            "provider": entry["provider"],
            "model": entry["model"],
            "promptHash": entry["promptHash"],
            "datasetChecksum": entry["datasetChecksum"],
        }
        if live_baseline:
            registry = read_live_baselines(live_baseline)
            prior = find_live_baseline(
                registry,
                provider=resolved_provider,
                model=resolved_model,
                base_url=resolved_base,
                temperature=temperature,
                prompt_hash=prompt_hash,
                dataset_checksum=getattr(suite, "dataset_checksum", ""),
            )
            if prior is None:
                payload["liveComparison"] = {
                    "ok": None,
                    "reason": "no_pinned_baseline",
                }
            else:
                comparison = compare_live_baseline(prior, suite)
                payload["liveComparison"] = comparison
                if comparison.get("ok") is False:
                    payload["ok"] = False
        if write_live_baseline:
            write_live_registry(entry, path=write_live_baseline)
            payload["writtenLiveBaseline"] = write_live_baseline
        if publish:
            payload["published"] = publish_report(
                entry,
                comparison=payload.get("liveComparison"),
                path=publish,
            )

    if promote and not critical:
        payload["baselineId"] = save_baseline(
            eval_store, baseline_name, suite,
        )
    if write_baseline:
        payload["writtenBaseline"] = write_baseline_file(write_baseline, payload)

    # Write the report LAST: the live comparison, promotion and baseline write
    # all mutate `payload` (notably `ok`), and a report that says PASS while the
    # process exits 1 is a lie. The published live report is a separate file.
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
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.nightly",
        description="Run the corpus once, compare with the baseline, write the report.",
    )
    parser.add_argument("--dataset", default="benchmark_v1")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None,
                        help=f"run only the first N tasks (1..{MAX_TASKS})")
    parser.add_argument("--max-cost", type=float, default=None,
                        help="USD cap for the session; required with --live")
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
    parser.add_argument("--live-baseline", nargs="?", const=DEFAULT_LIVE_BASELINE,
                        default="",
                        help="compare the live run against a pinned live baseline")
    parser.add_argument("--write-live-baseline", nargs="?",
                        const=DEFAULT_LIVE_BASELINE, default="",
                        help="pin this live run as a baseline entry")
    parser.add_argument("--publish", nargs="?", const=DEFAULT_PUBLISH,
                        default="",
                        help="write the live-tier Markdown report here "
                             "(defaults to docs/self-improvement in the app root)")
    parser.add_argument("--run-db", default="")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_budget(
            live=bool(args.live), limit=args.limit, max_cost=args.max_cost,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if (args.live_baseline or args.write_live_baseline or args.publish) and not args.live:
        print(
            "--live-baseline/--write-live-baseline/--publish require --live: "
            "only the live tier is model evidence",
            file=sys.stderr,
        )
        return 2
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
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            live_baseline=args.live_baseline or None,
            write_live_baseline=args.write_live_baseline or None,
            publish=args.publish or None,
            limit=args.limit,
            max_cost=args.max_cost,
        ))
    finally:
        store.close()
    print(render_markdown(payload))
    print(f"report: {payload.get('report', {}).get('markdown')}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
