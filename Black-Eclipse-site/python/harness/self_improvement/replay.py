"""Replay suites and the forgetting gate for continual learning.

Every candidate is evaluated against past competence, not only the failure it
targets. The replay suite is composed from the existing frozen datasets (their
validation/held-out/release tasks) plus any explicitly validated production
incidents. A task that was solved before and is unsolved now counts as
forgetting.

This module is deterministic data selection and arithmetic. It never runs a
model, never invents an expected behavior and never changes a dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from ..evaluation.tasks import (
    Dataset,
    EvaluationTask,
    dataset_checksum,
    load_all_builtin,
    select_tasks,
)

DEFAULT_REPLAY_SPLITS: tuple[str, ...] = ("validation", "held_out", "release")
DEFAULT_MAX_FORGETTING = 0.02


@dataclass(frozen=True)
class ReplaySuite:
    name: str
    tasks: tuple[EvaluationTask, ...]
    checksum: str
    taskIds: tuple[str, ...] = ()
    splits: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "taskCount": len(self.tasks),
            "taskIds": list(self.taskIds),
            "splits": list(self.splits),
            "checksum": self.checksum,
        }


def build_replay_suite(
    *,
    dataset: Optional[Dataset] = None,
    splits: Iterable[str] = DEFAULT_REPLAY_SPLITS,
    extra_tasks: Iterable[EvaluationTask] = (),
) -> ReplaySuite:
    """Build the bounded replay set from the existing frozen tasks.

    Tasks with no split metadata default to validation, so they are included by
    the default selection. An optimization task is never replay material unless
    the caller explicitly names the split.
    """
    source = dataset or load_all_builtin()
    wanted = tuple(str(split).strip().lower() for split in splits if str(split).strip())
    selected: list[EvaluationTask] = []
    seen: set[str] = set()
    for split in wanted:
        for task in select_tasks(source, split=split):
            if task.id in seen:
                continue
            seen.add(task.id)
            selected.append(task)
    for task in extra_tasks:
        if task.id in seen:
            continue
        seen.add(task.id)
        selected.append(task)
    selected.sort(key=lambda task: task.id)
    return ReplaySuite(
        name="replay_v1",
        tasks=tuple(selected),
        checksum=dataset_checksum(selected),
        taskIds=tuple(task.id for task in selected),
        splits=wanted,
    )


def critical_task_ids(tasks: Iterable[EvaluationTask]) -> tuple[str, ...]:
    """Tasks whose regression is a hard failure, not a score drop."""
    ids: list[str] = []
    for task in tasks:
        category = str(getattr(task, "category", "") or "").lower()
        metadata = getattr(task, "metadata", {}) or {}
        if category in ("safety", "adversarial") or bool(metadata.get("critical")):
            ids.append(task.id)
    return tuple(sorted(set(ids)))


def task_rates(source: Any) -> dict[str, float]:
    """Per-task measured pass rates from a suite, task result or plain mapping.

    A task with no measured trial is omitted, never reported as zero. A plain
    mapping is accepted unchanged (values are coerced to float).
    """
    if isinstance(source, Mapping):
        source = source.get("taskRates") if isinstance(source.get("taskRates"), Mapping) else source
        out: dict[str, float] = {}
        for key, value in source.items():
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return out

    tasks = getattr(source, "tasks", None)
    if tasks is None and hasattr(source, "task"):
        tasks = [source]
    if tasks is None:
        return {}
    out: dict[str, float] = {}
    for task_result in tasks:
        task = getattr(task_result, "task", None)
        task_id = str(
            getattr(task, "id", None)
            or getattr(task_result, "task_id", None)
            or getattr(task_result, "taskId", None)
            or ""
        )
        if not task_id:
            continue
        trials = getattr(task_result, "trials", None)
        if trials is not None:
            measured = [trial for trial in trials if not bool(getattr(trial, "unmeasured", False))]
            if not measured:
                continue
            passed = sum(1 for trial in measured if bool(getattr(trial, "passed", False)))
            out[task_id] = passed / len(measured)
            continue
        stats = getattr(task_result, "stats", None)
        if stats is not None and getattr(stats, "n", 0):
            out[task_id] = float(getattr(stats, "pass_rate", 0.0))
    return out


def best_known(
    previous: Mapping[str, float],
    current: Mapping[str, float],
) -> dict[str, float]:
    """The retained best per task; a solved task is not forgotten by a new run."""
    merged = {str(key): float(value) for key, value in (previous or {}).items()}
    for key, value in (current or {}).items():
        key = str(key)
        merged[key] = max(merged.get(key, 0.0), float(value))
    return merged


def forgetting(
    best: Mapping[str, float],
    current: Mapping[str, float],
    *,
    critical_tasks: Iterable[str] = (),
) -> dict[str, Any]:
    """Mean drop across replay tasks, plus any critical task drops.

    A task present in the retained best but absent from the current run counts
    as a 1.0 drop: the candidate did not demonstrate it still works.
    """
    critical = {str(task_id) for task_id in critical_tasks}
    drops: dict[str, float] = {}
    for task_id, previous in (best or {}).items():
        task_id = str(task_id)
        previous_value = float(previous)
        current_value = float((current or {}).get(task_id, 0.0))
        drop = max(0.0, previous_value - current_value)
        if drop > 0:
            drops[task_id] = round(drop, 6)
    mean_drop = (sum(drops.values()) / len(best)) if best else 0.0
    critical_drops = {
        task_id: drop for task_id, drop in drops.items() if task_id in critical
    }
    return {
        "mean": round(mean_drop, 6),
        "drops": drops,
        "criticalDrops": critical_drops,
        "measured": len(best),
    }


def replay_gate(
    best: Mapping[str, float],
    current: Mapping[str, float],
    *,
    critical_tasks: Iterable[str] = (),
    max_forgetting: float = DEFAULT_MAX_FORGETTING,
    require_baseline: bool = True,
) -> dict[str, Any]:
    """Accept a candidate only when it does not forget retained competence."""
    if not best:
        return {
            "passed": not require_baseline,
            "status": "unmeasured" if require_baseline else "no_baseline",
            "reason": "no replay baseline is recorded",
            "forgetting": {"mean": None, "drops": {}, "criticalDrops": {}, "measured": 0},
        }
    result = forgetting(best, current, critical_tasks=critical_tasks)
    reasons: list[str] = []
    if result["criticalDrops"]:
        reasons.append(
            "critical replay tasks regressed: "
            + ", ".join(sorted(result["criticalDrops"]))
        )
    if result["mean"] > float(max_forgetting):
        reasons.append(
            f"replay forgetting {result['mean']} exceeds {float(max_forgetting)}"
        )
    return {
        "passed": not reasons,
        "status": "measured",
        "reason": "; ".join(reasons) or "no replay forgetting",
        "forgetting": result,
    }


__all__ = [
    "DEFAULT_MAX_FORGETTING",
    "DEFAULT_REPLAY_SPLITS",
    "ReplaySuite",
    "best_known",
    "build_replay_suite",
    "critical_task_ids",
    "forgetting",
    "replay_gate",
    "task_rates",
]
