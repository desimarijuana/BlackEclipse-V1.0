"""The ``eclipse eval`` command line.

Every action actually executes evaluations against the real runtime — there are no
command stubs. Exit codes: 0 = pass, 1 = a gate/regression failed, 2 = usage error.

Examples::

    python -m harness.evaluation run --suite finance --trials 5
    python -m harness.evaluation smoke
    python -m harness.evaluation regression --baseline main
    python -m harness.evaluation benchmark --report --format md,json
    python -m harness.evaluation run --task finance.sharpe.001
    python -m harness.evaluation run --model ollama/llama3.1   # live tier
    python -m harness.evaluation run --affected --paths src/lib/harness/x.ts
    python -m harness.evaluation replay --trajectory .black-eclipse/evaluation/trajectories/x.json
    python -m harness.evaluation mine --run <production-run-id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Optional

from .config import EvaluationConfig, report_dir, trajectory_dir
from .dependencies import affected_categories, affected_tasks
from .report import to_markdown, write_report
from .runner import EvaluationRunner, ScriptedAgentInvoker
from .store import EvaluationStore
from .tasks import (
    Dataset,
    available_datasets,
    load_all_builtin,
    load_builtin_dataset,
    select_tasks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eclipse eval", description="Eclipse Agent Evaluation System")
    parser.add_argument("action", nargs="?", default="run",
                        choices=["run", "smoke", "regression", "benchmark", "list",
                                 "replay", "report", "mine", "improve", "affected"])
    parser.add_argument("--dataset", default="", help="built-in dataset name (default: all)")
    parser.add_argument("--suite", default="", help="suite/category filter")
    parser.add_argument("--task", default="", help="a single task id")
    parser.add_argument("--category", default="")
    parser.add_argument("--difficulty", default="")
    parser.add_argument("--tier", type=int, default=None)
    parser.add_argument("--trials", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--model", default="", help="provider/model for the LIVE tier")
    parser.add_argument("--base-url", default="", dest="base_url")
    parser.add_argument("--live", action="store_true", help="use the live model tier")
    parser.add_argument("--report", action="store_true", help="write report files")
    parser.add_argument("--format", default="json,md", help="report formats (json,jsonl,md,html)")
    parser.add_argument("--baseline", default="", help="save/compare a named baseline")
    parser.add_argument("--compare", default="", help="compare against this baseline name")
    parser.add_argument("--failed", action="store_true", help="print failures")
    parser.add_argument("--affected", action="store_true", help="run only affected suites")
    parser.add_argument("--paths", default="", help="comma-separated changed paths (affected mode)")
    parser.add_argument("--run", default="", help="a production run id (mine mode)")
    parser.add_argument("--trajectory", default="", help="a trajectory json file (replay mode)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--limit", type=int, default=50)
    return parser


def _open_store() -> Any:
    from ..persistence import AgentMemoryStore

    return AgentMemoryStore()


def _load_dataset(args: argparse.Namespace) -> Dataset:
    if args.dataset:
        return load_builtin_dataset(args.dataset)
    return load_all_builtin()


def _select(args: argparse.Namespace) -> tuple[Dataset, list[Any]]:
    dataset = _load_dataset(args)
    tasks = select_tasks(
        dataset,
        task_id=args.task or None,
        suite=args.suite or None,
        category=args.category or None,
        difficulty=args.difficulty or None,
        tier=args.tier,
    )
    if args.action == "smoke" and args.tier is None:
        tasks = select_tasks(dataset, tier=0)
    if args.affected:
        paths = [p for p in (args.paths or "").split(",") if p.strip()]
        if not paths:
            print("[eval] --affected requires --paths", file=sys.stderr)
        tasks = affected_tasks(tasks, paths)
    return dataset, tasks


def _invoker(args: argparse.Namespace, agent_store: Any) -> Any:
    if args.live or args.model:
        from .runner import ServiceAgentInvoker
        from ..schemas import ModelSettings

        provider, _, model = (args.model or "ollama/llama3.1").partition("/")
        try:
            from ..deps import service

            settings = ModelSettings(provider=provider, model=model or provider,
                                     base_url=args.base_url or None)
            return ServiceAgentInvoker(service, settings, allow_external_side_effects=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[eval] live tier unavailable: {exc}", file=sys.stderr)
            raise SystemExit(2)
    return ScriptedAgentInvoker(agent_store)


def _cmd_run(args: argparse.Namespace) -> int:
    agent_store = _open_store()
    eval_store = EvaluationStore(agent_store)
    config = EvaluationConfig.from_env({
        "trials": args.trials,
        "max_concurrency": args.concurrency,
    })
    runner = EvaluationRunner(agent_store, invoker=_invoker(args, agent_store),
                              config=config, eval_store=eval_store)
    dataset, tasks = _select(args)
    if not tasks:
        print("[eval] no tasks selected", file=sys.stderr)
        return 2
    suite = asyncio.run(runner.run_suite(
        tasks, dataset_name=dataset.name, dataset_version=dataset.version,
        dataset_checksum=dataset.checksum, suite=args.suite, trials=args.trials,
        tier=args.tier or 0, persist=True,
    ))
    status = _emit_suite(suite, args)

    if args.baseline:
        from .baseline import save_baseline

        save_baseline(eval_store, args.baseline, suite)
        print(f"[eval] baseline '{args.baseline}' saved (run {suite.run_id})")

    compare_name = args.compare or (args.baseline if args.action == "regression" else "")
    if compare_name:
        from .baseline import get_baseline
        from .regression import detect_regressions

        baseline = get_baseline(eval_store, compare_name)
        if baseline is None:
            print(f"[eval] baseline '{compare_name}' not found", file=sys.stderr)
            return 2
        outcome = detect_regressions(baseline.get("metrics") or {}, suite_metrics(suite))
        for regression in outcome["regressions"]:
            print(f"[eval] REGRESSION {regression['dimension']}: "
                  f"{regression['baseline']} -> {regression['current']}")
        for warning in outcome["warnings"]:
            print(f"[eval] warning {warning['dimension']}: "
                  f"{warning['baseline']} -> {warning['current']}")
        if not outcome["passed"]:
            status = 1
    return status


def _cmd_list(args: argparse.Namespace) -> int:
    dataset = _load_dataset(args)
    if args.json:
        print(json.dumps({
            "datasets": available_datasets(),
            "tasks": [t.to_dict() for t in dataset.tasks],
        }, indent=2, default=str))
        return 0
    print(f"datasets: {', '.join(available_datasets()) or 'none'}")
    for task in dataset.tasks:
        print(f"  {task.id} [{task.category}/{task.difficulty}] {task.name}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    from .replay import inspect
    from .trajectory import Trajectory

    if not args.trajectory:
        print("[eval] replay requires --trajectory", file=sys.stderr)
        return 2
    with open(args.trajectory, encoding="utf-8") as handle:
        trajectory = Trajectory.from_dict(json.load(handle))
    print(json.dumps(inspect(trajectory), indent=2, default=str))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    agent_store = _open_store()
    eval_store = EvaluationStore(agent_store)
    runs = eval_store.list_runs(limit=1)
    if not runs:
        print("[eval] no evaluation runs recorded", file=sys.stderr)
        return 2
    run = runs[0]
    trials = eval_store.list_trials(run["id"])
    payload = {
        "run": run,
        "trials": len(trials),
        "passed": sum(1 for t in trials if t["passed"]),
        "unmeasured": sum(1 for t in trials if t["unmeasured"]),
        "failures": eval_store.list_failures(run_id=run["id"], limit=args.limit),
        "regressions": eval_store.list_regressions(run_id=run["id"], limit=args.limit),
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _cmd_mine(args: argparse.Namespace) -> int:
    from .mining import mine_from_store

    agent_store = _open_store()
    eval_store = EvaluationStore(agent_store)
    if not args.run:
        print("[eval] mine requires --run <production-run-id>", file=sys.stderr)
        return 2
    outcome = mine_from_store(eval_store, agent_store, args.run)
    print(json.dumps(outcome, indent=2, default=str))
    return 0


def _cmd_improve(args: argparse.Namespace) -> int:
    from .improvement import propose_improvements, summarize_failures

    agent_store = _open_store()
    eval_store = EvaluationStore(agent_store)
    runs = eval_store.list_runs(limit=1)
    if not runs:
        print("[eval] no evaluation runs to analyze", file=sys.stderr)
        return 2
    run = runs[0]
    trials = eval_store.list_trials(run["id"])
    payload = {
        "runId": run["id"],
        "failures": [{"labels": t["score"].get("labels", [])} for t in trials if not t["passed"]],
    }
    counts: dict[str, int] = {}
    for failure in payload["failures"]:
        for label in failure["labels"]:
            counts[label] = counts.get(label, 0) + 1
    print(json.dumps({
        "failureCounts": counts,
        "proposedImprovements": propose_improvements(counts),
        "note": "proposals name WHERE to change; verify a change with `eclipse eval regression`",
    }, indent=2, default=str))
    return 0


def _cmd_affected(args: argparse.Namespace) -> int:
    dataset, _ = _select(args)
    paths = [p for p in (args.paths or "").split(",") if p.strip()]
    categories = affected_categories(paths)
    tasks = affected_tasks(dataset.tasks, paths)
    print(json.dumps({"categories": categories, "tasks": [t.id for t in tasks]}, indent=2))
    return 0


def _emit_suite(suite: Any, args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(suite.to_dict(), indent=2, default=str))
    else:
        print(to_markdown(suite))
    if args.report:
        formats = tuple(f.strip() for f in args.format.split(",") if f.strip())
        paths = write_report(suite, report_dir(), formats=formats, name=suite.run_id)
        print("[eval] reports: " + ", ".join(paths))
    if args.failed:
        for failure in suite.failures:
            print(f"[eval] FAILED {failure['taskId']} ({failure['trialId']}): "
                  f"{', '.join(failure['labels']) or '-'}")
    return 0 if suite.passed else 1


def suite_metrics(suite: Any) -> dict[str, Any]:
    return {"aggregates": dict(suite.aggregates), "categories": dict(suite.categories)}


_DISPATCH = {
    "run": _cmd_run,
    "smoke": _cmd_run,
    "benchmark": _cmd_run,
    "regression": _cmd_run,
    "list": _cmd_list,
    "replay": _cmd_replay,
    "report": _cmd_report,
    "mine": _cmd_mine,
    "improve": _cmd_improve,
    "affected": _cmd_affected,
}


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _DISPATCH[args.action](args)


def main(argv: Optional[list[str]] = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
