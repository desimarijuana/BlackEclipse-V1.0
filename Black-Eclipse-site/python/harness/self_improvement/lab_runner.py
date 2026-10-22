"""One RSL session: try to improve the harness, measure it, stage the winner.

A session is the piece the operator, the conductor and a scheduler all call:

1. build the BASE surface (the production agent, restricted to the tools the
   evaluation registry exposes - a tool the registry does not register cannot run
   in a trial);
2. collect the lessons the loop already ADOPTED and derive the variants;
3. measure every variant against the base on the same tasks;
4. stage the winner as an INERT surface candidate - evidence, never a landing.

The session is bounded by the caller's budget and never touches the harness
itself. It returns the lab's full record so the caller can report it.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import HarnessSnapshot


def base_surface(agent_id: str = "eclipse-agent") -> HarnessSnapshot:
    """The production surface, with only the tools the evaluation registry has."""
    from ..agents import get_agent  # noqa: PLC0415
    from ..evaluation.runner import _build_registry  # noqa: PLC0415

    agent = get_agent(agent_id)
    registered = set(_build_registry().names())
    return HarnessSnapshot(
        systemPrompt=agent.systemPrompt,
        toolNames=tuple(
            name for name in (agent.tools or ()) if name in registered
        ),
        maxSteps=min(int(agent.maxSteps or 8), 32),
        maxToolCalls=min(int(agent.maxToolCalls or 200), 200),
    )


async def run_lab_session(
    store: Any,
    *,
    memory_store: Any = None,
    agent_id: str = "eclipse-agent",
    dataset: str = "benchmark_v1",
    split: str = "validation",
    trials: int = 1,
    limit: int = 5,
    live: bool = False,
    model_settings: Any = None,
    stage: bool = True,
    scope: str = "global",
) -> dict[str, Any]:
    """Run one session and (optionally) stage the measured winner."""
    from ..evaluation.store import EvaluationStore  # noqa: PLC0415
    from ..evaluation.tasks import load_builtin_dataset, select_tasks  # noqa: PLC0415
    from .surface_lab import collect_lessons, run_lab, stage_winner  # noqa: PLC0415

    loaded = load_builtin_dataset(dataset)
    tasks = select_tasks(loaded, split=split)
    base = base_surface(agent_id)
    lessons: list[dict[str, Any]] = []
    if memory_store is not None:
        lessons = collect_lessons(
            memory_store, tasks, eval_store=EvaluationStore(store),
        )
    lab = await run_lab(
        store, tasks, base, lessons,
        limit=limit, trials=trials, split=split,
        live=live, model_settings=model_settings,
    )
    if stage:
        lab["staged"] = stage_winner(
            store, lab,
            base=base,
            task_ids=[task.id for task in tasks],
            dataset=dataset,
            dataset_name=loaded.name,
            dataset_version=loaded.version,
            split=split,
            scope=scope,
            trials=trials,
        )
    lab["session"] = {
        "dataset": dataset,
        "split": split,
        "trials": trials,
        "live": live,
        "lessonCount": len(lessons),
    }
    return lab


__all__ = ["base_surface", "run_lab_session"]
