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

from .runner import EvaluationRunner, ScriptedAgentInvoker
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
        return asyncio.run(runner.run_suite(
            tasks, dataset_name=dataset.name, dataset_version=dataset.version,
            dataset_checksum=dataset.checksum, suite=suite, trials=trials, tier=0,
            persist=persist,
        ))
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
                         "financial_accuracy", "citation_accuracy", "tool_accuracy"):
            lines.append(f"  {dimension}: {'UNKNOWN' if value is None else round(value, 4)}")
    if suite.thresholds.get("failures"):
        lines.append("  failures: " + "; ".join(suite.thresholds["failures"]))
    return lines


__all__ = ["format_gate_report", "run_offline_gate"]
