"""Controlled experiments: A/B, model matrix, routing, skill, memory, team.

Every experiment keeps the task, environment, graders and trials constant and
varies ONE axis (version, model, routing policy, skill on/off, memory on/off,
single agent vs team), then compares the resulting suites. Results are separate
metrics plus deltas — never a single blended number.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .config import EvaluationConfig
from .runner import EvaluationRunner
from .store import EvaluationStore
from .tasks import dataset_checksum


def _runner(store: Any, invoker: Any, config: Optional[EvaluationConfig]) -> EvaluationRunner:
    return EvaluationRunner(store, invoker=invoker, config=config or EvaluationConfig.from_env())


async def _run(store: Any, invoker: Any, tasks: list[Any], *, trials: Optional[int],
               config: Optional[EvaluationConfig], persist: bool, label: str) -> Any:
    runner = _runner(store, invoker, config)
    return await runner.run_suite(
        tasks, dataset_name="experiment", dataset_version="1",
        dataset_checksum=dataset_checksum(tasks), trials=trials, tier=0,
        persist=persist, run_id=None, metadata={"kind": "experiment"},
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


async def multi_agent_compare(
    store: Any,
    tasks: list[Any],
    *,
    single_invoker: Any = None,
    team_invoker: Any = None,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
    persist: bool = False,
) -> dict[str, Any]:
    """W12: one agent vs a 2-3 specialist team on the SAME frozen tasks.

    Both variants run through the same real runtime; the only axis that changes
    is the orchestration (the team variant is the REAL `TeamService` → A2A →
    `TaskScheduler` → `execute_run` stack over a per-trial isolated store — see
    `team_benchmark.TeamAgentInvoker`). Returns the measured per-axis comparison
    plus the deterministic adoption verdict (ADR-H213: adopt parallelism only
    where the benchmark shows a measured gain).

    Token/cost usage is published only when the variants' REAL trajectories
    reported it: the scripted tier reports none (unmeasured, never estimated),
    while a live suite's usage is summed honestly. For the live tier use
    `multi_agent_compare_live`.
    """
    from .runner import ScriptedAgentInvoker  # noqa: PLC0415
    from .team_benchmark import (  # noqa: PLC0415
        TeamAgentInvoker,
        adoption_verdict,
        measured_usage,
        variant_axes,
    )

    single = single_invoker or ScriptedAgentInvoker(store)
    team = team_invoker or TeamAgentInvoker(store)
    eval_store = EvaluationStore(store) if persist else None

    started = time.monotonic()
    suite_single = await _run(store, single, tasks, trials=trials, config=config,
                              persist=persist, label="single")
    single_wall_ms = int((time.monotonic() - started) * 1000)
    started = time.monotonic()
    suite_team = await _run(store, team, tasks, trials=trials, config=config,
                            persist=persist, label="team")
    team_wall_ms = int((time.monotonic() - started) * 1000)

    axes_single = {**variant_axes(suite_single, wall_ms=single_wall_ms), **measured_usage(suite_single)}
    axes_team = {**variant_axes(suite_team, wall_ms=team_wall_ms), **measured_usage(suite_team)}
    # Token/cost usage is published ONLY when a variant's REAL trajectories
    # reported it. The scripted tier reports 0 (no model ran) — that is
    # unmeasured, never estimated; a live suite's trajectories carry the
    # provider-reported usage and the same axes turn measured.
    unmeasured: list[str] = []
    if axes_single.get("cost") is None or axes_team.get("cost") is None:
        unmeasured.append("cost")
    if axes_single.get("totalTokens") is None or axes_team.get("totalTokens") is None:
        unmeasured.append("token_usage")
    unmeasured_reason = (
        "a variant reported no token/cost usage; an unreported measurement is never estimated"
        if unmeasured
        else "token and cost usage were captured from the live trajectories"
    )
    if eval_store is not None:
        for suite, axes, label in (
            (suite_single, axes_single, "single-agent"),
            (suite_team, axes_team, "team-agents"),
        ):
            eval_store.save_model_result(
                runId=suite.run_id, model=label, provider="scripted",
                metrics={**axes, "aggregates": suite.aggregates},
            )
    return {
        "dataset": {"checksum": dataset_checksum(tasks), "tasks": [t.id for t in tasks]},
        "single": {
            "invoker": getattr(single, "name", "single"),
            "metrics": suite_single.aggregates, "categories": suite_single.categories,
            "runId": suite_single.run_id, **axes_single,
        },
        "team": {
            "invoker": getattr(team, "name", "team"),
            "metrics": suite_team.aggregates, "categories": suite_team.categories,
            "runId": suite_team.run_id, **axes_team,
        },
        "comparison": compare_suites(suite_single, suite_team),
        "adoption": adoption_verdict(axes_single, axes_team),
        "unmeasured": unmeasured,
        "unmeasuredReason": unmeasured_reason,
    }


async def multi_agent_compare_live(
    store: Any,
    tasks: list[Any],
    *,
    service: Any,
    model_settings: Any = None,
    trials: Optional[int] = None,
    config: Optional[EvaluationConfig] = None,
    persist: bool = False,
) -> dict[str, Any]:
    """W12 live tier: the SAME comparison with REAL models.

    The single-agent variant is the production `ServiceAgentInvoker` (the
    operator's service + model settings); the team variant is the SAME real
    team stack with no script pool (`LiveTeamAgentInvoker`). With no model
    settings both variants are honestly `unmeasured` — the comparison publishes
    unmeasured rather than fabricating a run (ADR-H213).
    """
    from .runner import ServiceAgentInvoker  # noqa: PLC0415
    from .team_benchmark import LiveTeamAgentInvoker  # noqa: PLC0415

    return await multi_agent_compare(
        store,
        tasks,
        single_invoker=ServiceAgentInvoker(service, model_settings),
        team_invoker=LiveTeamAgentInvoker(store, model_settings),
        trials=trials,
        config=config,
        persist=persist,
    )


__all__ = [
    "ab_evaluate",
    "compare_suites",
    "memory_delta",
    "model_matrix",
    "multi_agent_compare",
    "multi_agent_compare_live",
    "routing_accuracy",
    "skill_delta",
]
