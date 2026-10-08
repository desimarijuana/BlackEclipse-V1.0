"""Evaluation baselines.

A baseline is the frozen metric snapshot of a known-good run, stamped with the
agent version, git commit, model/provider, task-dataset/grader versions and
configuration that produced it. Historical baselines are never overwritten: a new
baseline is a new row, so a comparison always names the exact run it compares to.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import GRADER_API_VERSION
from .store import EvaluationStore


def suite_metrics(suite: Any) -> dict[str, Any]:
    """The comparable metric snapshot of a suite result."""
    return {
        "aggregates": dict(suite.aggregates),
        "categories": dict(suite.categories),
        "passRate": suite.aggregates.get("task_success"),
        "datasetChecksum": suite.dataset_checksum,
        "tier": suite.tier,
    }


def save_baseline(
    eval_store: EvaluationStore,
    name: str,
    suite: Any,
    *,
    agent_version: Optional[str] = None,
    git_commit: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> str:
    return eval_store.save_baseline(
        name=name,
        runId=suite.run_id,
        datasetChecksum=suite.dataset_checksum,
        agentVersion=agent_version,
        gitCommit=git_commit,
        model=model,
        provider=provider,
        graderVersion=GRADER_API_VERSION,
        config=config or {},
        metrics=suite_metrics(suite),
    )


def get_baseline(eval_store: EvaluationStore, name: str) -> Optional[dict[str, Any]]:
    return eval_store.get_baseline(name)


def promote_if_improved(
    eval_store: EvaluationStore,
    name: str,
    suite: Any,
    *,
    agent_version: Optional[str] = None,
    git_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Record a baseline only when the current suite is at least as good as the
    previous one on the overall pass rate. A proposed change must never silently
    become the new baseline — see :mod:`harness.evaluation.improvement`.
    """
    previous = get_baseline(eval_store, name)
    current_rate = suite.aggregates.get("task_success")
    if previous is not None:
        prev_rate = (previous.get("metrics") or {}).get("passRate")
        if prev_rate is not None and current_rate is not None and current_rate < prev_rate:
            return {"promoted": False, "reason": f"pass rate {current_rate} < baseline {prev_rate}"}
    baseline_id = save_baseline(
        eval_store, name, suite, agent_version=agent_version, git_commit=git_commit,
    )
    return {"promoted": True, "baselineId": baseline_id}


__all__ = ["get_baseline", "promote_if_improved", "save_baseline", "suite_metrics"]
