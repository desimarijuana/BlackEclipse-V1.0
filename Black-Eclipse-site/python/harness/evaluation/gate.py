"""The offline evaluation gate, usable from CI and the CLI.

Runs the whole deterministic built-in benchmark against a PRIVATE temporary
``agent-memory.db`` (never the developer's runtime DB), then reports per-category
results. A gate failure names the failing dimensions — never a blended score.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from .routing import run_routing_evaluation
from .runner import EvaluationRunner, ScriptedAgentInvoker
from .scoring import check_thresholds
from .store import EvaluationStore
from .tasks import load_all_builtin


def run_offline_gate(
    *,
    dataset_name: str = "",
    suite: str = "",
    trials: int = 1,
    task_id: str = "",
    persist: bool = False,
) -> Any:
    """Run the offline gate on a temp store; returns the SuiteResult."""
    from ..persistence import AgentMemoryStore
    from .tasks import load_builtin_dataset, select_tasks

    directory = tempfile.mkdtemp(prefix="be-eval-gate-")
    db_path = os.path.join(directory, "agent-memory.db")
    store = AgentMemoryStore(db_path)
    try:
        dataset = load_builtin_dataset(dataset_name) if dataset_name else load_all_builtin()
        tasks = select_tasks(dataset, suite=suite or None, task_id=task_id or None)
        runner = EvaluationRunner(
            store, invoker=ScriptedAgentInvoker(store), eval_store=EvaluationStore(store),
        )
        suite_result = asyncio.run(runner.run_suite(
            tasks, dataset_name=dataset.name, dataset_version=dataset.version,
            dataset_checksum=dataset.checksum, suite=suite, trials=trials, tier=0,
            persist=persist,
        ))
        # Round 4 (W3.2/W3.3): the deterministic routing benchmark is a second,
        # explicitly-labelled measurement source. Its two dimensions enter the
        # SAME threshold check as the agent suite, so a routing regression fails
        # the release gate.
        routing = run_routing_evaluation()
        suite_result.routing = routing
        suite_result.aggregates["misroute_rate"] = routing["misroute_rate"]
        suite_result.aggregates["escalation_correct"] = routing["escalation_correct"]
        # Round 4 (W7): the self-evolution metric block — measured from the
        # suite; the store-backed dimensions stay UNMEASURED offline rather than
        # being fabricated (a real run supplies incidents/tasks explicitly).
        from .repair_metrics import collect_self_evolution_metrics  # noqa: PLC0415

        suite_result.self_evolution = collect_self_evolution_metrics(suite=suite_result)
        suite_result.thresholds = check_thresholds(
            suite_result.aggregates,
            sample_size=sum(len(t.trials) for t in suite_result.tasks),
        )
        return suite_result
    finally:
        store.close()


def format_gate_report(suite: Any) -> list[str]:
    """A few terminal-clean lines: per-category counts + gate outcome."""
    lines = [
        f"evaluation gate: {'PASS' if suite.passed else 'FAIL'} "
        f"(tasks={len(suite.tasks)} run={suite.run_id})",
    ]
    for category, row in suite.categories.items():
        rate = "UNKNOWN" if row["passRate"] is None else f"{row['passRate'] * 100:.0f}%"
        lines.append(
            f"  {category}: {row['passed']}/{row['measured']} measured, {rate}"
            + (f", {row['unmeasured']} unmeasured" if row["unmeasured"] else "")
        )
    for dimension, value in suite.aggregates.items():
        if dimension in ("task_success", "safety_score", "hallucination_rate",
                         "financial_accuracy", "citation_accuracy", "tool_accuracy",
                         "misroute_rate", "escalation_correct"):
            lines.append(f"  {dimension}: {'UNKNOWN' if value is None else round(value, 4)}")
    routing = getattr(suite, "routing", None) or {}
    if routing:
        lines.append(
            f"  routing: cases={routing.get('cases')} "
            f"misroute_rate={routing.get('misroute_rate')} "
            f"escalation_correct={routing.get('escalation_correct')}"
        )
    self_evolution = getattr(suite, "self_evolution", None) or {}
    if self_evolution:
        rendered = " ".join(
            f"{name}={round(value, 4) if isinstance(value, (int, float)) else 'UNMEASURED'}"
            for name, value in self_evolution.items()
        )
        lines.append(f"  self-evolution: {rendered}")
    if suite.thresholds.get("failures"):
        lines.append("  failures: " + "; ".join(suite.thresholds["failures"]))
    return lines


__all__ = ["format_gate_report", "run_offline_gate"]
