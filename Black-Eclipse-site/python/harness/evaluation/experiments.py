"""Controlled experiments: A/B, model matrix, routing, skill and memory.

Every experiment keeps the task, environment, graders and trials constant and
varies ONE axis (version, model, routing policy, skill on/off, memory on/off),
then compares the resulting suites. Results are separate metrics plus deltas —
never a single blended number.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .config import EvaluationConfig
from .runner import EvaluationRunner
from .store import EvaluationStore


def _runner(store: Any, invoker: Any, config: Optional[EvaluationConfig]) -> EvaluationRunner:
    return EvaluationRunner(store, invoker=invoker, config=config or EvaluationConfig.from_env())


async def _run(store: Any, invoker: Any, tasks: list[Any], *, trials: Optional[int],
               config: Optional[EvaluationConfig], persist: bool, label: str) -> Any:
    runner = _runner(store, invoker, config)
    return await runner.run_suite(
        tasks, dataset_name="experiment", trials=trials, tier=0,
        persist=persist, run_id=None,
    )


def compare_suites(a: Any, b: Any) -> dict[str, Any]:
    """Per-dimension deltas of two suites (b - a), plus pass-rate delta."""
    deltas: dict[str, Optional[float]] = {}
    for dimension, value in a.aggregates.items():
        other = b.aggregates.get(dimension)
        deltas[dimension] = None if (value is None or other is None) else round(other - value, 4)
    return {
        "a": a.aggregates,
        "b": b.aggregates,
        "deltas": deltas,
        "passRateDelta": (
            None if a.aggregates.get("task_success") is None or b.aggregates.get("task_success") is None
            else round(b.aggregates["task_success"] - a.aggregates["task_success"], 4)
        ),
    }


async def ab_evaluate(
    store: Any,
    tasks: list[Any],
    invoker_a: Any,
    invoker_b: Any,
    *,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Controlled A/B: same tasks, same graders, one axis changed."""
    suite_a = await _run(store, invoker_a, tasks, trials=trials, config=config,
                         persist=persist, label="A")
    suite_b = await _run(store, invoker_b, tasks, trials=trials, config=config,
                         persist=persist, label="B")
    return {
        "a": {"invoker": getattr(invoker_a, "name", "A"), "metrics": suite_a.aggregates,
              "categories": suite_a.categories, "runId": suite_a.run_id},
        "b": {"invoker": getattr(invoker_b, "name", "B"), "metrics": suite_b.aggregates,
              "categories": suite_b.categories, "runId": suite_b.run_id},
        "comparison": compare_suites(suite_a, suite_b),
    }


async def model_matrix(
    store: Any,
    tasks: list[Any],
    models: dict[str, Any],
    *,
    service: Any = None,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
    persist: bool = True,
    eval_store: Optional[EvaluationStore] = None,
) -> dict[str, Any]:
    """model × task × trial. `models` maps a label to ModelSettings (or an invoker).

    Uses the existing model registry through the production service; a label whose
    value is already an invoker is used directly (for deterministic tests).
    """
    from .runner import ServiceAgentInvoker  # noqa: PLC0415

    results: dict[str, Any] = {}
    for label, spec in models.items():
        invoker = spec if hasattr(spec, "invoke") else ServiceAgentInvoker(service, spec)
        suite = await _run(store, invoker, tasks, trials=trials, config=config,
                           persist=persist, label=label)
        results[label] = {
            "metrics": suite.aggregates,
            "categories": suite.categories,
            "flakyTasks": suite.flaky_tasks,
            "runId": suite.run_id,
        }
        if persist and eval_store is not None:
            eval_store.save_model_result(
                runId=suite.run_id, model=getattr(spec, "model", label),
                provider=getattr(spec, "provider", ""), metrics=suite.aggregates,
            )
    return {"models": results}


def routing_accuracy(cases: list[dict[str, Any]], route_fn: Callable[[str], Any]) -> dict[str, Any]:
    """Grade a model router against labelled cases.

    `cases` entries: ``{"query": ..., "expected": <class>}``. `route_fn` returns
    the chosen class (or a settings dict with a ``class``/``model`` key).
    """
    correct = 0
    failures = []
    for case in cases:
        chosen = route_fn(case["query"])
        if isinstance(chosen, dict):
            chosen = chosen.get("class") or chosen.get("model") or chosen.get("provider")
        if chosen == case["expected"]:
            correct += 1
        else:
            failures.append({"query": case["query"], "expected": case["expected"], "chosen": chosen})
    total = len(cases)
    return {
        "routing_accuracy": (correct / total) if total else None,
        "cases": total,
        "correct": correct,
        "failures": failures,
    }


async def skill_delta(
    store: Any,
    tasks: list[Any],
    without_invoker: Any,
    with_invoker: Any,
    *,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
) -> dict[str, Any]:
    return await ab_evaluate(store, tasks, without_invoker, with_invoker,
                             trials=trials, config=config)


async def memory_delta(
    store: Any,
    tasks: list[Any],
    memory_disabled_invoker: Any,
    memory_enabled_invoker: Any,
    *,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
) -> dict[str, Any]:
    return await ab_evaluate(store, tasks, memory_disabled_invoker, memory_enabled_invoker,
                             trials=trials, config=config)


__all__ = [
    "ab_evaluate",
    "compare_suites",
    "memory_delta",
    "model_matrix",
    "routing_accuracy",
    "skill_delta",
]
