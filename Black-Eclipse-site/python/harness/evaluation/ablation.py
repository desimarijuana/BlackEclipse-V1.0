"""Three-arm harness ablation: baseline vs surface vs surface+lessons.

The RSL loop can prove that a single candidate beats the current state on one
suite. It cannot answer the question an operator actually asks: *does the
surface (and do adopted lessons) improve the harness relative to doing nothing,
on the same tasks, seeds and trials?* This module runs that comparison.

It is deliberately offline-first. The scripted invoker is deterministic, so the
same arms always produce the same table; a live-model tier can be injected via
`runner_factory` when one is available. Every arm is a validated
`HarnessSnapshot` and every run is persisted through the existing
`EvaluationRunner` / `EvaluationStore` -- there is no second evaluator and no
second database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..agents import get_agent
from .candidate_invoker import (
    CandidateAgentInvoker,
    base_snapshot_from_agent,
)
from .config import report_dir
from .runner import EvaluationRunner
from .stats import wilson_interval
from .store import EvaluationStore
from .tasks import (
    dataset_checksum,
    load_builtin_dataset,
    select_tasks,
)

CRITICAL_CATEGORIES: tuple[str, ...] = ("safety", "adversarial")


@dataclass(frozen=True)
class AblationArm:
    """One measured harness variant.

    `prompt_suffix` is a static string or a callable taking the task and
    returning bounded text (the lessons arm uses this to inject a per-task
    verified lesson manifest).
    """

    name: str
    snapshot: Any
    prompt_suffix: Any = ""


@dataclass
class ArmEvidence:
    arm: str
    run_id: str
    task_success: Optional[float]
    successes: int
    measured_trials: int
    total_trials: int
    ci_low: Optional[float]
    ci_high: Optional[float]
    dimensions: dict[str, Optional[float]]
    categories: dict[str, dict[str, Any]]
    task_rates: dict[str, float]
    task_categories: dict[str, str]
    cost_usd: Optional[float]
    latency_ms: Optional[float]
    critical_regressions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "runId": self.run_id,
            "taskSuccess": self.task_success,
            "successes": self.successes,
            "measuredTrials": self.measured_trials,
            "totalTrials": self.total_trials,
            "ci": [self.ci_low, self.ci_high],
            "dimensions": self.dimensions,
            "categories": self.categories,
            "taskRates": self.task_rates,
            "taskCategories": self.task_categories,
            "costUsd": self.cost_usd,
            "latencyMs": self.latency_ms,
            "criticalRegressions": self.critical_regressions,
        }


def _slug(value: str) -> str:
    raw = str(value or "arm").strip().lower().replace("+", "-")
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)[:40] or "arm"


def arm_evidence(suite: Any, arm: str) -> ArmEvidence:
    """Project one `SuiteResult` into the comparison table's row."""
    measured = [
        trial
        for task_result in suite.tasks
        for trial in task_result.trials
        if not trial.unmeasured
    ]
    successes = sum(1 for trial in measured if trial.passed)
    low, high = wilson_interval(successes, len(measured))

    task_rates: dict[str, float] = {}
    task_categories: dict[str, str] = {}
    for task_result in suite.tasks:
        task = task_result.task
        task_categories[task.id] = task.category
        trials = [trial for trial in task_result.trials if not trial.unmeasured]
        if trials:
            task_rates[task.id] = sum(1 for trial in trials if trial.passed) / len(trials)

    costs = [
        trial.score.cost for trial in measured
        if getattr(trial.score, "cost", None) is not None
    ]
    latencies = [
        trial.score.latency_ms for trial in measured
        if getattr(trial.score, "latency_ms", None) is not None
    ]
    return ArmEvidence(
        arm=arm,
        run_id=str(getattr(suite, "run_id", "")),
        task_success=suite.aggregates.get("task_success"),
        successes=successes,
        measured_trials=len(measured),
        total_trials=sum(len(task_result.trials) for task_result in suite.tasks),
        ci_low=low,
        ci_high=high,
        dimensions={
            key: value for key, value in suite.aggregates.items()
            if key != "task_success"
        },
        categories=dict(suite.categories),
        task_rates=task_rates,
        task_categories=task_categories,
        cost_usd=round(sum(float(cost) for cost in costs), 6) if costs else None,
        latency_ms=(
            round(sum(float(value) for value in latencies) / len(latencies), 3)
            if latencies else None
        ),
    )


def compare_arms(
    arms: list[ArmEvidence],
    *,
    baseline: str = "baseline",
    critical_categories: tuple[str, ...] = CRITICAL_CATEGORIES,
) -> dict[str, dict[str, Any]]:
    """Compare every arm against the baseline. A critical drop always vetoes."""
    if not arms:
        return {}
    base = next((arm for arm in arms if arm.arm == baseline), arms[0])
    critical = set(critical_categories)
    comparisons: dict[str, dict[str, Any]] = {}
    for arm in arms:
        if arm.arm == base.arm:
            continue
        delta = (
            None if arm.task_success is None or base.task_success is None
            else arm.task_success - base.task_success
        )
        regressions = sorted(
            task_id for task_id, rate in arm.task_rates.items()
            if base.task_rates.get(task_id, 0.0) > 0.0
            and rate < base.task_rates[task_id]
            and arm.task_categories.get(task_id) in critical
        )
        arm.critical_regressions = regressions
        if delta is None:
            verdict = "unmeasured"
        elif regressions:
            verdict = "vetoed"
        elif delta > 0.01:
            verdict = "improved"
        elif delta < -0.01:
            verdict = "regressed"
        else:
            verdict = "flat"
        comparisons[arm.arm] = {
            "baseline": base.arm,
            "delta": delta,
            "verdict": verdict,
            "criticalRegressions": regressions,
            "costUsd": arm.cost_usd,
            "costPerSuccess": (
                round(arm.cost_usd / arm.successes, 6)
                if arm.cost_usd is not None and arm.successes > 0 else None
            ),
        }
    return comparisons


@dataclass
class AblationReport:
    dataset_name: str
    dataset_version: str
    split: str
    trials: int
    seed: int
    arms: list[ArmEvidence]
    comparisons: dict[str, dict[str, Any]]
    critical_categories: tuple[str, ...] = CRITICAL_CATEGORIES
    tier: str = "scripted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset_name,
            "datasetVersion": self.dataset_version,
            "split": self.split,
            "tier": self.tier,
            "trials": self.trials,
            "seed": self.seed,
            "criticalCategories": list(self.critical_categories),
            "arms": [arm.to_dict() for arm in self.arms],
            "comparisons": self.comparisons,
        }

    def to_markdown(self) -> str:
        lines = [
            "# RSL harness ablation",
            "",
            f"- dataset: `{self.dataset_name}` @ `{self.dataset_version}` "
            f"(split `{self.split}`)",
            f"- trials per task: {self.trials} · seed: {self.seed}",
            f"- tier: {self.tier}",
            "",
            "| arm | task success | 95% CI | measured | critical regressions | cost (USD) |",
            "|---|---|---|---|---|---|",
        ]
        for arm in self.arms:
            ci = (
                "UNKNOWN" if arm.ci_low is None
                else f"{arm.ci_low:.3f}–{arm.ci_high:.3f}"
            )
            success = "UNKNOWN" if arm.task_success is None else f"{arm.task_success:.3f}"
            cost = "UNKNOWN" if arm.cost_usd is None else f"{arm.cost_usd:.4f}"
            lines.append(
                f"| {arm.arm} | {success} | {ci} | {arm.measured_trials}/"
                f"{arm.total_trials} | {len(arm.critical_regressions)} | {cost} |"
            )
        if self.comparisons:
            lines += [
                "",
                "## Comparison vs baseline",
                "",
                "| arm | delta | verdict | critical regressions | cost / success |",
                "|---|---|---|---|---|",
            ]
            for name, row in self.comparisons.items():
                delta = "UNKNOWN" if row["delta"] is None else f"{row['delta']:+.3f}"
                cps = (
                    "UNKNOWN" if row["costPerSuccess"] is None
                    else f"{row['costPerSuccess']:.4f}"
                )
                lines.append(
                    f"| {name} | {delta} | {row['verdict']} | "
                    f"{len(row['criticalRegressions'])} | {cps} |"
                )
        lines += [
            "",
            "## Per category",
            "",
            "| arm | category | passed/measured | pass rate |",
            "|---|---|---|---|",
        ]
        for arm in self.arms:
            for category, row in sorted(arm.categories.items()):
                rate = row.get("passRate")
                lines.append(
                    f"| {arm.arm} | {category} | {row.get('passed', 0)}/"
                    f"{row.get('measured', 0)} | "
                    f"{'UNKNOWN' if rate is None else f'{rate:.3f}'} |"
                )
        if self.tier == "live":
            note = (
                "> Live-tier results measure a real model. Intervals are Wilson "
                "95% intervals; small samples stay wide and are not significance "
                "claims. A critical regression vetoes regardless of the mean. The "
                "isolated evaluation bridge still reports external data "
                "UNAVAILABLE, so this is not a production-data replay."
            )
        else:
            note = (
                "> Scripted-tier results prove the harness path is deterministic "
                "and that the comparison is wired correctly. They are not evidence "
                "of live-model improvement; do not present them as such."
            )
        lines += ["", note]
        return "\n".join(lines)

    def write(self, directory: Optional[str] = None) -> list[str]:
        target = Path(directory or report_dir())
        target.mkdir(parents=True, exist_ok=True)
        stem = f"rsl-ablation-{self.split}-{uuid.uuid4().hex[:8]}"
        paths = []
        json_path = target / f"{stem}.json"
        json_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        paths.append(str(json_path))
        md_path = target / f"{stem}.md"
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        paths.append(str(md_path))
        return paths


async def run_ablation(
    store: Any,
    tasks: list[Any],
    arms: list[AblationArm],
    *,
    dataset_name: str,
    dataset_version: str,
    split: str = "validation",
    trials: int = 1,
    seed: int = 1,
    concurrency: Optional[int] = None,
    persist: bool = True,
    runner_factory: Optional[Callable[[AblationArm], Any]] = None,
    critical_categories: tuple[str, ...] = CRITICAL_CATEGORIES,
    live: bool = False,
    model_settings: Any = None,
) -> AblationReport:
    """Run each arm on the SAME tasks, then compare against the first arm."""
    if not arms:
        raise ValueError("an ablation needs at least one arm")
    if not tasks:
        raise ValueError("an ablation needs at least one task")
    base = arms[0].snapshot
    checksum = dataset_checksum(tasks)
    evidence: list[ArmEvidence] = []
    for arm in arms:
        if runner_factory is not None:
            runner = runner_factory(arm)
        else:
            invoker = CandidateAgentInvoker(
                store, arm.snapshot, base=base,
                prompt_suffix=arm.prompt_suffix,
                live=live, model_settings=model_settings,
            )
            runner = EvaluationRunner(
                store, invoker=invoker, eval_store=EvaluationStore(store),
            )
        suite = await runner.run_suite(
            tasks,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            dataset_checksum=checksum,
            suite=f"ablation-{_slug(arm.name)}",
            trials=trials,
            tier=0,
            run_id=f"ablation-{_slug(arm.name)}-{uuid.uuid4().hex[:8]}",
            persist=persist,
            concurrency=concurrency,
            split=split,
            seed=seed,
            metadata={"kind": "rsl-ablation", "arm": arm.name},
            extra_config={"kind": "rsl-ablation", "arm": arm.name},
        )
        evidence.append(arm_evidence(suite, arm.name))
    report = AblationReport(
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        split=split,
        trials=max(1, int(trials)),
        seed=int(seed),
        arms=evidence,
        comparisons={},
        critical_categories=critical_categories,
        tier="live" if live else "scripted",
    )
    report.comparisons = compare_arms(
        report.arms, critical_categories=critical_categories,
    )
    return report


def baseline_snapshot(
    agent_id: str = "eclipse-agent",
    *,
    registered: Optional[set[str]] = None,
) -> Any:
    """The agent's real prompt + only tools the evaluation registry exposes.

    The production preset names tools the offline evaluation registry does not
    register; passing one to `CandidateAgentInvoker` is a hard failure. The
    ablation baseline is therefore the prompt plus the intersection with the
    registry that actually runs the trial.
    """
    agent = get_agent(agent_id)
    names = tuple(getattr(agent, "tools", ()) or ())
    if registered is not None:
        names = tuple(name for name in names if name in registered)
    return base_snapshot_from_agent(agent, tool_names=names)


def load_snapshot(path: str) -> Any:
    from ..self_improvement.models import HarnessSnapshot  # noqa: PLC0415

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("a snapshot file must contain a JSON object")
    return HarnessSnapshot(**payload)


def lesson_suffix_factory(memory_store: Any, run_store: Any) -> Callable[[Any], str]:
    """A per-task suffix built from verified, cue-matched lessons."""
    def suffix(task: Any) -> str:
        try:
            from ..prompt_segments import build_lesson_manifest  # noqa: PLC0415
            from ..self_improvement.lessons import select_lessons  # noqa: PLC0415

            cue = str((getattr(task, "input", {}) or {}).get("prompt") or getattr(task, "name", ""))
            lessons = select_lessons(
                memory_store, cue=cue, eval_store=EvaluationStore(run_store),
            )
            content, _ids = build_lesson_manifest(lessons)
            return content
        except Exception:  # noqa: BLE001 - an unavailable lesson store injects nothing
            return ""
    return suffix


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m harness.evaluation.ablation",
        description="Compare a baseline harness, a surface snapshot and "
                    "surface+lessons on the same evaluation tasks.",
    )
    parser.add_argument("--dataset", default="benchmark_v1")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--task", default="", help="one task id (debugging)")
    parser.add_argument("--category", default="", help="one category filter")
    parser.add_argument("--limit", type=int, default=0, help="max tasks (debugging)")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--agent", default="eclipse-agent")
    parser.add_argument("--live", action="store_true",
                        help="use a real model (sends provider requests); "
                             "requires --provider and --model")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--surface-snapshot", default="",
                        help="path to a HarnessSnapshot JSON object; omit for a "
                             "no-op surface (pipeline smoke only)")
    parser.add_argument("--lessons-db", default="",
                        help="optional eclipse-memory.db for the surface+lessons arm")
    parser.add_argument("--run-db", default="",
                        help="agent-memory.db path (defaults to the runtime's)")
    parser.add_argument("--out", default="", help="report directory")
    parser.add_argument("--no-persist", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    from ..persistence import AgentMemoryStore  # noqa: PLC0415

    store = AgentMemoryStore(args.run_db or None)
    memory_store = None
    try:
        dataset = load_builtin_dataset(args.dataset)
        tasks = select_tasks(
            dataset,
            split=args.split,
            task_id=args.task or None,
            category=args.category or None,
        )
        if args.limit > 0:
            tasks = tasks[: args.limit]
        if not tasks:
            print(f"no tasks in {args.dataset} split {args.split}", file=sys.stderr)
            return 2
        from .runner import _build_registry  # noqa: PLC0415

        base = baseline_snapshot(
            args.agent, registered=set(_build_registry().names()),
        )
        if args.surface_snapshot:
            surface = load_snapshot(args.surface_snapshot)
        else:
            surface = base
            print(
                "no --surface-snapshot supplied; the surface arm is the base "
                "snapshot (pipeline smoke only, not evidence)",
                file=sys.stderr,
            )
        arms = [
            AblationArm(name="baseline", snapshot=base),
            AblationArm(name="surface", snapshot=surface),
        ]
        if args.lessons_db:
            from ..eclipse_memory import EclipseMemoryStore  # noqa: PLC0415

            memory_store = EclipseMemoryStore(args.lessons_db)
            arms.append(AblationArm(
                name="surface+lessons",
                snapshot=surface,
                prompt_suffix=lesson_suffix_factory(memory_store, store),
            ))
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
        report = asyncio.run(run_ablation(
            store, tasks, arms,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            split=args.split,
            trials=args.trials,
            seed=args.seed,
            concurrency=args.concurrency,
            persist=not args.no_persist,
            live=args.live,
            model_settings=model_settings,
        ))
        paths = report.write(args.out or None)
        print(report.to_markdown())
        for path in paths:
            print(f"\nwrote {path}")
        return 0
    finally:
        if memory_store is not None:
            memory_store.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
